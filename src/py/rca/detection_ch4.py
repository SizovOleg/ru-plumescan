"""
CH₄ detection algorithm primitives (Phase 2A, P-02.0a Шаг 4).

Implements Algorithm v2.3.2 §3.4.3-§3.10 в Python via Earth Engine Python API.
JS module `src/js/modules/detection_ch4.js` mirrors this for GEE Code Editor use.

Seven primitives (post Шаг 4 GPT review #1 fixes):
  0. build_hybrid_background      — Algorithm §3.4.3 dual baseline cross-check
  1. compute_z_score              — Algorithm §3.5 z = (obs - primary) / sigma_eff
  2. apply_three_condition_mask   — Algorithm §3.6 z + Δ + relative-to-annulus
  3. extract_clusters             — Algorithm §3.7 connectedComponents
  4. compute_cluster_attributes   — Algorithm §3.8 per-cluster metrics
  5. validate_wind                — Algorithm §3.9 (v2.3.1) ERA5 850hPa
  6. attribute_source             — Algorithm §3.10 50 km + type ranking

DNA §2.1 critical compliances:
  * Запрет 4: no `unmask(0)` для XCH4 — regional fallback в build_hybrid_background
  * Запрет 5: no ee.Kernel arithmetic — annulus = outer-disk-only (two-pass approach)
  * Запрет 6: per-region adaptive z_min applied at orchestrator level (Шаг 5)

GPT review #1 fixes applied:
  * Issue 4.1 (HIGH): build_hybrid_background separates primary-selection logic
    from z-score; consistency_flag + matched_inside_reference_zone propagated as
    metadata bands для downstream classification cascade (Шаг 6)
  * Issue 5.3 (CRITICAL): wind angle .mod(180) before shortest-distance min
  * Issue 2.1 (HIGH): .select('z') before reduceRegions to avoid band-prefix
    collision in property names
  * Issue 1.2 (HIGH): cos(lat) aspect correction в plume axis PCA
  * Issue 6.1 (HIGH): composite-key sort (single .sort) in attribute_source
  * Issue 5.2 (MEDIUM): null plume_axis_deg → wind_consistent=null (not false)
  * Issue 1.3 (MEDIUM): wind direction explicit +360 step before mod
  * Issue 2.3 (MEDIUM): wind_state enum field {aligned, misaligned,
    insufficient_wind, axis_unknown}
"""

from __future__ import annotations

import math

import ee
import numpy as np

# ---------------------------------------------------------------------------
# Constants (per Algorithm v2.3.2)
# ---------------------------------------------------------------------------

ANALYSIS_SCALE_M = 7000  # TROPOMI L3 grid
SIGMA_FLOOR_PPB = 15.0  # CH4 noise floor (Algorithm §3.5)

# Annulus parameters (Algorithm §3.6)
ANNULUS_OUTER_KM_DEFAULT = 150  # outer disk radius
ANNULUS_INNER_KM_DEFAULT = 50  # inner disk excluded ideally; bias ~12%

# Hybrid background tolerance (Algorithm §3.4.3)
CONSISTENCY_TOLERANCE_PPB_DEFAULT = 30.0  # |ref - reg| < 30 ppb → consistent

# Source type priorities for CH₄ detection (Algorithm §3.10)
SOURCE_TYPE_PRIORITIES_CH4 = {
    "gas_field": 1,
    "viirs_flare_high": 2,
    "coal_mine": 3,
    "tpp_gres": 4,
    "viirs_flare_low": 5,
    "smelter": 6,
}


# ---------------------------------------------------------------------------
# Primitive 0: hybrid background (Algorithm §3.4.3 — dual baseline cross-check)
# ---------------------------------------------------------------------------


def build_hybrid_background(
    reference_baseline: ee.Image,
    regional_baseline: ee.Image,
    consistency_tolerance_ppb: float = CONSISTENCY_TOLERANCE_PPB_DEFAULT,
    reference_zones_fc: ee.FeatureCollection | None = None,
) -> ee.Image:
    """
    Algorithm §3.4.3: dual baseline cross-check + reference-zone matching.

    Combines reference baseline (zapovedniks — clean zones, positive-space) with
    regional baseline (industrial buffer + urban mask, post P-01.0d) to produce
    per-pixel primary baseline + dual-baseline metadata.

    Primary selection (Algorithm §3.5 mode='reference_only'):
      * primary_value = ref_value where reference defined; regional fallback where
        reference masked (DNA §2.1.4 compliance — never unmask(0))
      * primary_sigma корреспондирует primary_value
      * Reference is preferred even when divergent от regional (более defensible —
        clean-zone baseline is the methodology anchor); consistency_flag captures
        the divergence as metadata для downstream classification

    Metadata bands (consumed Шаг 6 classification cascade):
      * consistency_flag: 1 where |ref - reg| < tolerance, 0 otherwise (masked
        where either baseline masked)
      * matched_inside_reference_zone: 1 where pixel inside any zone polygon, 0
        otherwise (static — same across all months)

    Returns multi-band image (37 bands total):
      * primary_value_M01..M12          (12 bands)
      * primary_sigma_M01..M12          (12 bands)
      * consistency_flag_M01..M12       (12 bands)
      * matched_inside_reference_zone   (1 band — month-invariant)

    Args:
        reference_baseline: image с bands ref_M01..M12, sigma_M01..M12
        regional_baseline: image с bands median_M01..M12, sigma_M01..M12
        consistency_tolerance_ppb: |ref - reg| < tolerance → consistency_flag=1
        reference_zones_fc: zapovednik polygons; if None — matched_inside_reference_zone
            = 0 everywhere (orchestrator passes real FC at runtime)
    """
    bands: list[ee.Image] = []
    for month in range(1, 13):
        suffix = f"M{month:02d}"
        ref_value = reference_baseline.select(f"ref_{suffix}")
        ref_sigma = reference_baseline.select(f"sigma_{suffix}")
        reg_value = regional_baseline.select(f"median_{suffix}")
        reg_sigma = regional_baseline.select(f"sigma_{suffix}")

        # Primary fallback: reference where defined, regional otherwise (DNA §2.1.4)
        primary_value = ref_value.unmask(reg_value).rename(f"primary_value_{suffix}")
        primary_sigma = ref_sigma.unmask(reg_sigma).rename(f"primary_sigma_{suffix}")

        # Consistency flag: |ref - reg| < tolerance — metadata only, не drives selection
        consistency_flag = (
            ref_value.subtract(reg_value)
            .abs()
            .lt(consistency_tolerance_ppb)
            .rename(f"consistency_flag_{suffix}")
        )

        bands.extend([primary_value, primary_sigma, consistency_flag])

    # Reference zone membership — single static band (zones don't change по месяцам)
    if reference_zones_fc is not None:
        zone_mask = (
            ee.Image.constant(0)
            .paint(reference_zones_fc, 1)
            .rename("matched_inside_reference_zone")
        )
    else:
        zone_mask = ee.Image.constant(0).rename("matched_inside_reference_zone")
    bands.append(zone_mask)

    return ee.Image.cat(bands)


# ---------------------------------------------------------------------------
# Primitive 1: z-score (Algorithm §3.5)
# ---------------------------------------------------------------------------


def compute_z_score(
    orbit_image: ee.Image,
    hybrid_background: ee.Image,
    month: int,
    target_band: str = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
    sigma_floor_ppb: float = SIGMA_FLOOR_PPB,
) -> ee.Image:
    """
    Algorithm §3.5: z = (obs - primary) / max(primary_sigma, sigma_floor).

    Consumes pre-computed hybrid_background (output of build_hybrid_background).
    Primary selection logic + consistency_flag computation already happened upstream;
    z-score primitive itself contains no fallback logic — clean separation.

    Returns multi-band image (6 bands):
      * z                              — z-score
      * delta_primary                  — obs - primary
      * primary_value                  — selected primary baseline value
      * primary_sigma                  — corresponding sigma (без floor)
      * consistency_flag               — dual baseline metadata (this month)
      * matched_inside_reference_zone  — zone metadata (static)
    """
    suffix = f"M{month:02d}"
    primary_value = hybrid_background.select(f"primary_value_{suffix}").rename("primary_value")
    primary_sigma = hybrid_background.select(f"primary_sigma_{suffix}").rename("primary_sigma")

    # Sigma floor — prevents z explosion when sigma very small
    sigma_eff = primary_sigma.max(ee.Image.constant(sigma_floor_ppb))

    obs = orbit_image.select(target_band)
    delta_primary = obs.subtract(primary_value).rename("delta_primary")
    z = delta_primary.divide(sigma_eff).rename("z")

    consistency = hybrid_background.select(f"consistency_flag_{suffix}").rename("consistency_flag")
    zone = hybrid_background.select("matched_inside_reference_zone")

    return ee.Image.cat([z, delta_primary, primary_value, primary_sigma, consistency, zone])


# ---------------------------------------------------------------------------
# Primitive 2: 3-condition mask (z + Δ + relative-to-annulus)
# ---------------------------------------------------------------------------


def apply_three_condition_mask(
    z_image: ee.Image,
    delta_primary: ee.Image,
    z_min: float = 3.0,
    delta_min_ppb: float = 30.0,
    relative_min_ppb: float = 15.0,
    annulus_outer_km: float = ANNULUS_OUTER_KM_DEFAULT,
) -> ee.Image:
    """
    Algorithm §3.6: 3-condition pixel mask conjunction.

      mask = (z ≥ z_min) AND (Δ ≥ delta_min) AND (Δ - annulus_median ≥ relative_min)

    Annulus computation (DNA §2.1 запрет 5 — no ee.Kernel arithmetic):
        TWO-PASS approach — `annulus_median ≈ outer_disk_median(150 km)`.
        Bias: inner disk (50 km) included в outer median computation contributes
        ~12.5% area weight. Maximum bias ~12% under-estimation when inner disk
        contains anomaly. Conservative direction (under-detection — fewer FPs).
        Documented Algorithm §3.6 inline note.

    Returns: binary mask (1 where all 3 conditions met, masked otherwise).
    """
    # Condition 1: z-score
    z_test = z_image.gte(z_min)

    # Condition 2: absolute delta floor
    delta_test = delta_primary.gte(delta_min_ppb)

    # Condition 3: relative-to-annulus (two-pass via outer disk only)
    outer_kernel = ee.Kernel.circle(radius=annulus_outer_km * 1000, units="meters")
    annulus_median = delta_primary.reduceNeighborhood(
        reducer=ee.Reducer.median(),
        kernel=outer_kernel,
        skipMasked=True,
    )
    rel_test = delta_primary.subtract(annulus_median).gte(relative_min_ppb)

    return z_test.And(delta_test).And(rel_test).rename("anomaly_mask").selfMask()


# ---------------------------------------------------------------------------
# Primitive 3: connectedComponents clustering
# ---------------------------------------------------------------------------


def extract_clusters(
    mask_image: ee.Image,
    min_cluster_px: int = 5,
    max_size: int = 256,
    connectedness: int = 8,
) -> ee.Image:
    """
    Algorithm §3.7: connectedComponents 8-conn (default), min cluster size filter.

    `min_cluster_px=5` ≈ 245 km² minimum signal area at 7 km grid.
    """
    # 8-connected = ee.Kernel.square(1); 4-connected = ee.Kernel.plus(1)
    kernel = ee.Kernel.square(1) if connectedness == 8 else ee.Kernel.plus(1)

    labeled = mask_image.connectedComponents(connectedness=kernel, maxSize=max_size)

    # Filter by size
    pixel_counts = mask_image.connectedPixelCount(
        maxSize=max_size, eightConnected=(connectedness == 8)
    )
    significant = pixel_counts.gte(min_cluster_px)

    return labeled.updateMask(significant)


# ---------------------------------------------------------------------------
# Primitive 4: per-cluster attributes
# ---------------------------------------------------------------------------


def compute_cluster_attributes(
    cluster_image: ee.Image,
    orbit_image: ee.Image,
    baseline_value: ee.Image,
    z_image: ee.Image,
    aoi: ee.Geometry,
    target_band: str = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
    scale_m: int = ANALYSIS_SCALE_M,
) -> ee.FeatureCollection:
    """
    Algorithm §3.8: vectorize clusters + per-cluster reduceRegions для metrics.

    plume_axis_deg НЕ computed here (requires client-side eigendecomposition —
    handled at orchestrator level via reduceRegions(coords) → numpy.linalg.eig).

    Returns FC с per-cluster: cluster_id (geometry implicit), max_z, mean_z,
    max_delta, mean_delta, n_pixels, area_km2, centroid_lon/lat.

    GPT review #1 Issue 2.1 fix: explicit .select('z') / single-band delta
    before reduceRegions; reducers use .setOutputs() for unambiguous property
    naming. Multi-band z_image (output of compute_z_score) would otherwise
    produce band-prefixed property names (z_max etc.) and cluster z-statistics
    would silently come out null.
    """
    # Vectorize clusters
    vectors = cluster_image.reduceToVectors(
        geometry=aoi,
        scale=scale_m,
        geometryType="polygon",
        eightConnected=True,
        bestEffort=False,
        maxPixels=int(1e9),
        labelProperty="cluster_id",
    )

    # Single-band z and delta — avoid band-prefix collision in reduceRegions output
    z_only = z_image.select("z")
    delta_only = orbit_image.select(target_band).subtract(baseline_value)

    # Per-cluster z-score statistics (renamed via setOutputs)
    z_reducer = (
        ee.Reducer.max()
        .setOutputs(["max_z"])
        .combine(ee.Reducer.mean().setOutputs(["mean_z"]), "", True)
        .combine(ee.Reducer.count().setOutputs(["n_pixels"]), "", True)
    )
    with_z = z_only.reduceRegions(
        collection=vectors,
        reducer=z_reducer,
        scale=scale_m,
    )

    # Per-cluster delta statistics
    delta_reducer = (
        ee.Reducer.max()
        .setOutputs(["max_delta"])
        .combine(ee.Reducer.mean().setOutputs(["mean_delta"]), "", True)
    )
    with_delta = delta_only.reduceRegions(
        collection=with_z,
        reducer=delta_reducer,
        scale=scale_m,
    )

    def _enrich_geometric(feat: ee.Feature) -> ee.Feature:
        centroid = feat.geometry().centroid(maxError=1)
        coords = ee.List(centroid.coordinates())
        area_km2 = feat.geometry().area(maxError=1).divide(1e6)
        return feat.set(
            {
                "centroid_lon": coords.get(0),
                "centroid_lat": coords.get(1),
                "area_km2": area_km2,
            }
        )

    return with_delta.map(_enrich_geometric)


# ---------------------------------------------------------------------------
# Primitive 5: wind validation (ERA5 850hPa, vector averaging)
# ---------------------------------------------------------------------------


def validate_wind(
    cluster_fc: ee.FeatureCollection,
    era5_collection: ee.ImageCollection,
    orbit_time_millis: int | ee.Date,
    wind_level_hpa: int = 850,
    alignment_threshold_deg: float = 30.0,
    min_wind_speed_ms: float = 2.0,
    temporal_window_hours: int = 3,
) -> ee.FeatureCollection:
    """
    Algorithm §3.9 (v2.3.1, TD-0031): ERA5 wind sampling at cluster centroids.

    Vector averaging (NOT directional — prevents 359°→0° wrap).
    Alignment via shortest angular distance к 180°-symmetric axis line:
        raw = |wind_dir - axis|, reduced mod 180 → [0, 180)
        angle_diff = min(raw_mod180, 180 - raw_mod180) → [0, 90]

    Three-state wind classification (GPT review #1 Issue 2.3):
        wind_state ∈ {aligned, misaligned, insufficient_wind, axis_unknown}
        wind_consistent: true if aligned, false if misaligned, null otherwise

    GPT review #1 fixes:
      * Issue 5.3 (CRITICAL): .mod(180) before angle_diff min — fixes broken
        formula for wind_dir ∈ [180, 360) where raw_diff > 180 made angle_diff
        negative and .lte(threshold) trivially true
      * Issue 1.3 (MEDIUM): wind_dir formula explicit +360 mod 360 step before
        +180 (FROM convention)
      * Issue 5.2 (MEDIUM): null plume_axis_deg → wind_consistent=null,
        wind_state='axis_unknown' (not silent false)

    Caller must pre-set `plume_axis_deg` on each cluster feature (computed
    client-side via numpy.linalg.eig at orchestrator stage). When axis is
    unknown (cluster < 3 pixels), set `plume_axis_deg=None`.
    """
    band_u = f"u_component_of_wind_{wind_level_hpa}hPa"
    band_v = f"v_component_of_wind_{wind_level_hpa}hPa"

    orbit_date = ee.Date(orbit_time_millis)
    window = era5_collection.filterDate(
        orbit_date.advance(-temporal_window_hours, "hour"),
        orbit_date.advance(temporal_window_hours, "hour"),
    ).select([band_u, band_v])
    mean_wind = window.mean()  # vector averaging — u, v separately

    def _validate(feat: ee.Feature) -> ee.Feature:
        centroid = feat.geometry().centroid(maxError=1)
        sample = mean_wind.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=centroid,
            scale=27830,  # ERA5 native ~28 km (0.25° at equator)
        )
        u = ee.Number(sample.get(band_u))
        v = ee.Number(sample.get(band_v))
        wind_speed = u.hypot(v)

        # Atmospheric FROM convention: 0=N, 90=E. Two-step explicit (Issue 1.3 fix):
        #   wind_to_deg = atan2(u, v) → [-180, 180]; +360 mod 360 → [0, 360)
        #   wind_dir (FROM) = wind_to_deg + 180 mod 360
        wind_to_deg = u.atan2(v).multiply(180.0 / math.pi).add(360).mod(360)
        wind_dir = wind_to_deg.add(180).mod(360)

        # Plume axis null handling (Issue 5.2): if missing, downstream null state
        plume_axis_value = feat.get("plume_axis_deg")
        plume_axis = ee.Number(ee.Algorithms.If(plume_axis_value, plume_axis_value, 0))

        # Shortest angular distance to 180°-symmetric axis (Issue 5.3 fix):
        # mod 180 before min — corrects raw_diff > 180 case
        raw_diff_mod = wind_dir.subtract(plume_axis).abs().mod(180)
        angle_diff = raw_diff_mod.min(ee.Number(180).subtract(raw_diff_mod))

        sufficient_wind = wind_speed.gte(min_wind_speed_ms)
        axis_known = ee.Algorithms.If(plume_axis_value, True, False)

        # Three-state wind classification (Issue 2.3)
        wind_state = ee.Algorithms.If(
            axis_known,
            ee.Algorithms.If(
                sufficient_wind,
                ee.Algorithms.If(
                    angle_diff.lte(alignment_threshold_deg),
                    "aligned",
                    "misaligned",
                ),
                "insufficient_wind",
            ),
            "axis_unknown",
        )

        # Boolean wind_consistent: true=aligned, false=misaligned, null=other
        ok_to_check = ee.Algorithms.If(axis_known, sufficient_wind, False)
        wind_consistent = ee.Algorithms.If(
            ok_to_check,
            angle_diff.lte(alignment_threshold_deg),
            None,
        )

        # Alignment score [0,1] — defined regardless of wind state
        alignment_score = ee.Number(1).subtract(angle_diff.divide(90).min(1))

        props = {
            f"wind_u_{wind_level_hpa}hPa": u,
            f"wind_v_{wind_level_hpa}hPa": v,
            "wind_u": u,
            "wind_v": v,
            "wind_speed": wind_speed,
            "wind_dir_deg": wind_dir,
            "wind_alignment_score": alignment_score,
            "wind_consistent": wind_consistent,
            "wind_state": wind_state,
            "wind_level_hPa": wind_level_hpa,
            "wind_source": f"ERA5_HOURLY_{wind_level_hpa}hPa",
        }
        return feat.set(props)

    return cluster_fc.map(_validate)


# ---------------------------------------------------------------------------
# Primitive 6: source attribution (50 km radius + type ranking)
# ---------------------------------------------------------------------------


def attribute_source(
    cluster_fc: ee.FeatureCollection,
    source_points: ee.FeatureCollection,
    search_radius_km: float = 50.0,
    type_priorities: dict[str, int] | None = None,
) -> ee.FeatureCollection:
    """
    Algorithm §3.10: nearest source within search_radius, ranked by type priority.

    Priority lower = better (gas_field=1 wins over viirs_flare_high=2).
    Ties broken by distance.

    Sets nearest_source_id, nearest_source_distance_km, nearest_source_type.
    If no source within radius → all three null.

    GPT review #1 Issue 6.1 fix: composite-key sort (priority * 1e6 + distance)
    instead of double .sort() — single allocation, avoids stable-sort assumption,
    reduces inner-map memory pressure.
    """
    priorities_dict = type_priorities or SOURCE_TYPE_PRIORITIES_CH4
    priorities = ee.Dictionary(priorities_dict)
    default_priority = 999

    def _attribute(cluster: ee.Feature) -> ee.Feature:
        centroid = cluster.geometry().centroid(maxError=1)
        nearby = source_points.filterBounds(centroid.buffer(search_radius_km * 1000))

        def _rank(source: ee.Feature) -> ee.Feature:
            distance = centroid.distance(source.geometry()).divide(1000)  # km
            stype = source.get("source_type_category")
            priority = ee.Number(priorities.get(stype, default_priority))
            # Composite rank: priority dominant (× 1e6), distance breaks ties
            composite = priority.multiply(1_000_000).add(distance)
            return source.set(
                {
                    "distance_km": distance,
                    "priority": priority,
                    "composite_rank": composite,
                }
            )

        ranked = nearby.map(_rank).sort("composite_rank")  # single sort

        size = ranked.size()
        return ee.Feature(
            ee.Algorithms.If(
                size.gt(0),
                cluster.set(
                    {
                        "nearest_source_id": ee.Feature(ranked.first()).get("source_id"),
                        "nearest_source_distance_km": ee.Feature(ranked.first()).get("distance_km"),
                        "nearest_source_type": ee.Feature(ranked.first()).get(
                            "source_type_category"
                        ),
                    }
                ),
                cluster.set(
                    {
                        "nearest_source_id": None,
                        "nearest_source_distance_km": None,
                        "nearest_source_type": None,
                    }
                ),
            )
        )

    return cluster_fc.map(_attribute)


# ---------------------------------------------------------------------------
# Helper: client-side plume axis via eigendecomposition
# ---------------------------------------------------------------------------


def compute_plume_axis_client_side(
    pixel_lons: list[float], pixel_lats: list[float]
) -> float | None:
    """
    Compute plume axis bearing (compass; 0=N, 90=E; range [0, 180)) via 2D PCA
    on cluster pixel coordinates.

    Client-side post-reduceRegion (researcher decision Шаг 4): server-side
    `ee.Array.eigen` exists но fragile — sample pixel coords through reduceRegion,
    do numpy.linalg.eigh locally.

    GPT review #1 Issue 1.2 fix: cos(lat) aspect correction. At 54°N,
    1° lon ≈ 65 km vs 1° lat ≈ 111 km (cos 54° ≈ 0.588). Without correction PCA
    on raw degrees would over-weight latitudinal extent ~1.7× and bias E-W
    elongated clusters toward N-S axis, corrupting wind alignment validation.
    Correction: scale lons by cos(mean_lat) before covariance, recover bearing
    from km-space eigenvector.

    Returns None если < 3 pixels (eigendecomposition undefined).
    """
    if len(pixel_lons) < 3 or len(pixel_lats) < 3:
        return None

    lons = np.array(pixel_lons, dtype=float)
    lats = np.array(pixel_lats, dtype=float)

    # Aspect correction: scale lons to km-equivalent at cluster mean latitude
    mean_lat = float(np.mean(lats))
    cos_lat = math.cos(math.radians(mean_lat))
    if cos_lat < 1e-6:  # at poles, axis ill-defined
        return None
    lons_scaled = (lons - lons.mean()) * cos_lat
    lats_centered = lats - lats.mean()

    coords = np.column_stack([lons_scaled, lats_centered])  # km-space (relative)
    cov = np.cov(coords.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    dominant = eigvecs[:, np.argmax(eigvals)]

    # In km-space, bearing = atan2(east_km, north_km) (compass: 0=N, 90=E)
    angle = float(np.degrees(np.arctan2(dominant[0], dominant[1])))
    # Normalize to [0, 180) — axis is symmetric
    return angle % 180


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "build_hybrid_background",
    "compute_z_score",
    "apply_three_condition_mask",
    "extract_clusters",
    "compute_cluster_attributes",
    "validate_wind",
    "attribute_source",
    "compute_plume_axis_client_side",
    "SIGMA_FLOOR_PPB",
    "ANNULUS_OUTER_KM_DEFAULT",
    "ANNULUS_INNER_KM_DEFAULT",
    "CONSISTENCY_TOLERANCE_PPB_DEFAULT",
    "SOURCE_TYPE_PRIORITIES_CH4",
    "ANALYSIS_SCALE_M",
]
