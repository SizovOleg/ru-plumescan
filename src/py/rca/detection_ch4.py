"""
CH₄ detection algorithm primitives (Phase 2A, P-02.0a Шаг 4).

Implements Algorithm v2.3.2 §3.5-3.10 в Python via Earth Engine Python API.
JS module `src/js/modules/detection_ch4.js` mirrors this for GEE Code Editor use.

Six primitives:
  1. compute_z_score              — Algorithm §3.5 dual baseline z-score
  2. apply_three_condition_mask   — Algorithm §3.6 z + Δ + relative-to-annulus
  3. extract_clusters             — Algorithm §3.7 connectedComponents
  4. compute_cluster_attributes   — Algorithm §3.8 per-cluster metrics
  5. validate_wind                — Algorithm §3.9 (v2.3.1) ERA5 850hPa
  6. attribute_source             — Algorithm §3.10 50 km + type ranking

DNA §2.1 critical compliances:
  * Запрет 4: no `unmask(0)` для XCH4 — use regional fallback values
  * Запрет 5: no ee.Kernel arithmetic — annulus = outer-disk-only (two-pass approach)
  * Запрет 6: per-region adaptive z_min applied at orchestrator level (Шаг 5)
"""

from __future__ import annotations

import ee

# ---------------------------------------------------------------------------
# Constants (per Algorithm v2.3.2)
# ---------------------------------------------------------------------------

ANALYSIS_SCALE_M = 7000  # TROPOMI L3 grid
SIGMA_FLOOR_PPB = 15.0  # CH4 noise floor (Algorithm §3.5)

# Annulus parameters (Algorithm §3.6)
ANNULUS_OUTER_KM_DEFAULT = 150  # outer disk radius
ANNULUS_INNER_KM_DEFAULT = 50  # inner disk excluded ideally; bias ~12%

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
# Primitive 1: z-score с dual baseline fallback
# ---------------------------------------------------------------------------


def compute_z_score(
    orbit_image: ee.Image,
    reference_baseline: ee.Image,
    regional_baseline: ee.Image,
    month: int,
    target_band: str = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
    sigma_floor_ppb: float = SIGMA_FLOOR_PPB,
) -> ee.Image:
    """
    Algorithm §3.5: z = (obs - primary) / max(primary_sigma, sigma_floor).

    Primary baseline = reference where defined, regional где reference masked
    (DNA §2.1 запрет 4 — НЕ unmask(0); use regional values as fallback).

    Returns multi-band image: ['z', 'delta_primary', 'primary_value'].
    """
    suffix = f"M{month:02d}"

    ref_value = reference_baseline.select(f"ref_{suffix}")
    ref_sigma = reference_baseline.select(f"sigma_{suffix}")
    reg_value = regional_baseline.select(f"median_{suffix}")
    reg_sigma = regional_baseline.select(f"sigma_{suffix}")

    # Primary fallback: reference where defined, regional otherwise
    primary_value = ref_value.unmask(reg_value).rename("primary_value")
    primary_sigma = ref_sigma.unmask(reg_sigma)

    # Sigma floor — prevents z explosion when sigma very small
    sigma_eff = primary_sigma.max(ee.Image.constant(sigma_floor_ppb))

    obs = orbit_image.select(target_band)
    delta_primary = obs.subtract(primary_value).rename("delta_primary")
    z = delta_primary.divide(sigma_eff).rename("z")

    return ee.Image.cat([z, delta_primary, primary_value])


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
# Primitive 4: per-cluster attributes (server-side reduceToVectors + reduceRegions)
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
    """
    # Vectorize
    vectors = cluster_image.reduceToVectors(
        geometry=aoi,
        scale=scale_m,
        geometryType="polygon",
        eightConnected=True,
        bestEffort=False,
        maxPixels=int(1e9),
        labelProperty="cluster_id",
    )

    delta = orbit_image.select(target_band).subtract(baseline_value)

    # Per-cluster z-score statistics
    with_z = z_image.reduceRegions(
        collection=vectors,
        reducer=ee.Reducer.max()
        .combine(ee.Reducer.mean(), "", True)
        .combine(ee.Reducer.count(), "", True),
        scale=scale_m,
    )

    # Rename z-derived properties
    def _rename_z(feat: ee.Feature) -> ee.Feature:
        return feat.set(
            {
                "max_z": feat.get("max"),
                "mean_z": feat.get("mean"),
                "n_pixels": feat.get("count"),
            }
        )

    with_z = with_z.map(_rename_z)

    # Per-cluster delta statistics
    with_delta = delta.reduceRegions(
        collection=with_z,
        reducer=ee.Reducer.max().combine(ee.Reducer.mean(), "", True),
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
                "max_delta": feat.get("max"),
                "mean_delta": feat.get("mean"),
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
    Alignment via shortest angular distance:
        angle_diff = min(|wind_dir - axis|, 180 - |wind_dir - axis|)
    `wind_consistent = null` if wind_speed < min_wind_speed_ms.

    Caller must pre-set `plume_axis_deg` on each cluster feature (computed
    client-side via numpy.linalg.eig at orchestrator stage).
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
            scale=9000,  # ERA5 native ~9 km
        )
        u = ee.Number(sample.get(band_u))
        v = ee.Number(sample.get(band_v))
        wind_speed = u.hypot(v)
        # atmospheric convention: direction wind is FROM, 0=N, 90=E.
        # atan2(u_east, v_north) gives direction wind is GOING TO; +180 для FROM.
        wind_dir = u.atan2(v).multiply(180.0).divide(3.141592653589793).add(180).mod(360)

        plume_axis = ee.Number(feat.get("plume_axis_deg"))
        # Shortest angular distance (axis is mod 180 — symmetric)
        raw_diff = wind_dir.subtract(plume_axis).abs()
        angle_diff = raw_diff.min(ee.Number(180).subtract(raw_diff))

        sufficient_wind = wind_speed.gte(min_wind_speed_ms)
        wind_consistent = ee.Algorithms.If(
            sufficient_wind,
            angle_diff.lte(alignment_threshold_deg),
            None,  # null when insufficient wind
        )
        alignment_score = ee.Number(1).subtract(angle_diff.divide(90).min(1))

        return feat.set(
            {
                f"wind_u_{wind_level_hpa}hPa": u,
                f"wind_v_{wind_level_hpa}hPa": v,
                "wind_u": u,
                "wind_v": v,
                "wind_speed": wind_speed,
                "wind_dir_deg": wind_dir,
                "wind_alignment_score": alignment_score,
                "wind_consistent": wind_consistent,
                "wind_level_hPa": wind_level_hpa,
                "wind_source": f"ERA5_HOURLY_{wind_level_hpa}hPa",
            }
        )

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
            return source.set({"distance_km": distance, "priority": priority})

        ranked = nearby.map(_rank).sort("distance_km").sort("priority")

        size = ranked.size()
        # If no source within radius, return cluster unchanged (null fields)
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
# Helper: client-side plume axis via eigendecomposition (Шаг 4 component)
# ---------------------------------------------------------------------------


def compute_plume_axis_client_side(
    pixel_lons: list[float], pixel_lats: list[float]
) -> float | None:
    """
    Compute plume axis angle (0-180°) via 2D PCA on cluster pixel coordinates.

    Client-side post-reduceRegion (researcher decision Шаг 4):
    server-side `ee.Array.eigen` exists но fragile. Sample pixel coords through
    reduceRegion, do numpy.linalg.eig locally.

    Returns None если < 3 pixels (eigendecomposition undefined).
    """
    import numpy as np

    if len(pixel_lons) < 3 or len(pixel_lats) < 3:
        return None

    coords = np.array([pixel_lons, pixel_lats]).T  # shape (n, 2)
    coords_centered = coords - coords.mean(axis=0)
    cov = np.cov(coords_centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # Dominant axis = eigenvector с largest eigenvalue
    dominant = eigvecs[:, np.argmax(eigvals)]
    # Axis angle 0-180° (atmospheric: 0 = North-South axis, 90 = East-West)
    angle = float(np.degrees(np.arctan2(dominant[0], dominant[1])))
    # Normalize к [0, 180)
    if angle < 0:
        angle += 180
    if angle >= 180:
        angle -= 180
    return angle


# ---------------------------------------------------------------------------
# Module exports summary
# ---------------------------------------------------------------------------

__all__ = [
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
    "SOURCE_TYPE_PRIORITIES_CH4",
    "ANALYSIS_SCALE_M",
]
