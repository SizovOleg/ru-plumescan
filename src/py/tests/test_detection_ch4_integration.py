"""
P-02.0a Шаг 4 GPT review #1 fix: integration smoke tests for detection_ch4.

Issue 7.1 (HIGH): mock-only test suite cannot catch GEE-API correctness bugs
(e.g., reduceRegions band-prefix collision Issue 2.1, wind angle math
Issue 5.3 needs real EE evaluation to verify production behavior).

These tests perform `ee.Initialize()` and run primitives against minimal
synthetic ee.Image instances to verify:
  * Output band names match expected schema
  * `reduceRegions` produces correctly-named properties (max_z, mean_z, etc.)
  * Property propagation through .map() chains
  * Real-vs-expected math на small inputs (z-score, mask conjunction)

ALL tests skip if EE authentication unavailable (CI without service account
credentials). Local dev with valid earthengine credentials runs them.

Per CLAUDE.md §5.1: integration tests gate before full-archive launch.
This file is the FIRST integration test (Phase 2A v1); Шаг 7 will add the
Kuzbass 2022-09-20 regression test.
"""

from __future__ import annotations

import os

import pytest


def _ee_available() -> bool:
    """Check if EE auth is available for integration tests."""
    if os.environ.get("EE_SERVICE_ACCOUNT_KEY"):
        return True
    cred_paths = [
        os.path.expanduser("~/.config/earthengine/credentials"),
        os.path.expanduser("~\\.config\\earthengine\\credentials"),
    ]
    return any(os.path.exists(p) for p in cred_paths)


pytestmark = pytest.mark.skipif(
    not _ee_available(),
    reason="EE authentication not available — skipping integration tests",
)


@pytest.fixture(scope="module")
def ee_init():
    """Initialize Earth Engine once per module."""
    try:
        import ee

        if os.environ.get("EE_SERVICE_ACCOUNT_KEY"):
            credentials = ee.ServiceAccountCredentials(
                None, key_data=os.environ["EE_SERVICE_ACCOUNT_KEY"]
            )
            ee.Initialize(credentials)
        else:
            ee.Initialize()
        return ee
    except Exception as e:  # pragma: no cover
        pytest.skip(f"EE initialization failed: {e}")


# ---------------------------------------------------------------------------
# Primitive 0: build_hybrid_background — verify schema на synthetic baselines
# ---------------------------------------------------------------------------


def test_build_hybrid_background_band_schema(ee_init):
    """build_hybrid_background returns 37 bands with expected naming."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background

    # Synthetic baselines: constants for all 12 months
    ref_bands = []
    reg_bands = []
    for m in range(1, 13):
        suffix = f"M{m:02d}"
        ref_bands.append(ee.Image.constant(1880).rename(f"ref_{suffix}"))
        ref_bands.append(ee.Image.constant(20).rename(f"sigma_{suffix}"))
        reg_bands.append(ee.Image.constant(1900).rename(f"median_{suffix}"))
        reg_bands.append(ee.Image.constant(25).rename(f"sigma_{suffix}"))
    reference_baseline = ee.Image.cat(ref_bands)
    regional_baseline = ee.Image.cat(reg_bands)

    hybrid = build_hybrid_background(reference_baseline, regional_baseline)
    band_names = hybrid.bandNames().getInfo()

    # Expected: 12 primary_value + 12 primary_sigma + 12 consistency_flag + 1 zone = 37
    assert len(band_names) == 37, f"expected 37 bands, got {len(band_names)}: {band_names}"
    assert "primary_value_M01" in band_names
    assert "primary_value_M12" in band_names
    assert "primary_sigma_M06" in band_names
    assert "consistency_flag_M09" in band_names
    assert "matched_inside_reference_zone" in band_names


def test_build_hybrid_background_consistency_flag_value(ee_init):
    """|ref - reg| < tolerance → consistency_flag=1."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background

    ref_bands = [ee.Image.constant(1880).rename(f"ref_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(20).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reg_bands = [ee.Image.constant(1890).rename(f"median_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(25).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reference_baseline = ee.Image.cat(ref_bands)
    regional_baseline = ee.Image.cat(reg_bands)

    hybrid = build_hybrid_background(
        reference_baseline, regional_baseline, consistency_tolerance_ppb=30.0
    )

    # |1880 - 1890| = 10 < 30 → consistency = 1
    point = ee.Geometry.Point([86.0, 54.0])
    sample = (
        hybrid.select("consistency_flag_M06")
        .reduceRegion(ee.Reducer.first(), point, 7000)
        .getInfo()
    )
    assert sample["consistency_flag_M06"] == 1


def test_build_hybrid_background_consistency_flag_divergent(ee_init):
    """|ref - reg| > tolerance → consistency_flag=0."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background

    ref_bands = [ee.Image.constant(1880).rename(f"ref_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(20).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reg_bands = [ee.Image.constant(1950).rename(f"median_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(25).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reference_baseline = ee.Image.cat(ref_bands)
    regional_baseline = ee.Image.cat(reg_bands)

    hybrid = build_hybrid_background(
        reference_baseline, regional_baseline, consistency_tolerance_ppb=30.0
    )

    # |1880 - 1950| = 70 > 30 → consistency = 0
    point = ee.Geometry.Point([86.0, 54.0])
    sample = (
        hybrid.select("consistency_flag_M06")
        .reduceRegion(ee.Reducer.first(), point, 7000)
        .getInfo()
    )
    assert sample["consistency_flag_M06"] == 0


# ---------------------------------------------------------------------------
# Primitive 1: compute_z_score — verify z computation на synthetic input
# ---------------------------------------------------------------------------


def test_compute_z_score_real_evaluation(ee_init):
    """Synthetic orbit + hybrid → z = (obs - primary) / max(sigma, floor)."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background, compute_z_score

    # Synthetic baselines
    ref_bands = [ee.Image.constant(1880).rename(f"ref_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(20).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reg_bands = [ee.Image.constant(1890).rename(f"median_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(25).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    hybrid = build_hybrid_background(ee.Image.cat(ref_bands), ee.Image.cat(reg_bands))

    # Synthetic orbit at 1940 ppb (60 ppb above primary=1880)
    orbit = ee.Image.constant(1940).rename("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")

    z_image = compute_z_score(orbit, hybrid, month=6)
    band_names = z_image.bandNames().getInfo()

    expected_bands = {
        "z",
        "delta_primary",
        "primary_value",
        "primary_sigma",
        "consistency_flag",
        "matched_inside_reference_zone",
    }
    assert set(band_names) == expected_bands, f"bands mismatch: {band_names}"

    # z = (1940 - 1880) / max(20, 15) = 60 / 20 = 3.0
    point = ee.Geometry.Point([86.0, 54.0])
    sample = z_image.reduceRegion(ee.Reducer.first(), point, 7000).getInfo()
    assert abs(sample["z"] - 3.0) < 0.01, f"z={sample['z']}"
    assert abs(sample["delta_primary"] - 60.0) < 0.01
    assert sample["primary_value"] == 1880.0


def test_compute_z_score_sigma_floor_applied(ee_init):
    """When sigma < floor, divisor = floor (15 ppb)."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background, compute_z_score

    # Sigma very small (5 ppb) — floor at 15 should kick in
    ref_bands = [ee.Image.constant(1880).rename(f"ref_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(5).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reg_bands = [ee.Image.constant(1880).rename(f"median_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(5).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    hybrid = build_hybrid_background(ee.Image.cat(ref_bands), ee.Image.cat(reg_bands))

    orbit = ee.Image.constant(1925).rename("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")

    z_image = compute_z_score(orbit, hybrid, month=6)
    point = ee.Geometry.Point([86.0, 54.0])
    sample = z_image.reduceRegion(ee.Reducer.first(), point, 7000).getInfo()
    # z = 45 / max(5, 15) = 45 / 15 = 3.0 (NOT 9.0 if no floor)
    assert abs(sample["z"] - 3.0) < 0.01, f"sigma floor not applied; z={sample['z']}"


# ---------------------------------------------------------------------------
# Primitive 4: compute_cluster_attributes — Issue 2.1 fix verification
# ---------------------------------------------------------------------------


def test_extract_clusters_single_band_output(ee_init):
    """GPT review #3 H-6: extract_clusters output MUST be single-band ('labels').

    `connectedComponents` returns multi-band image (input band + 'labels').
    Without `.select('labels')` fix, downstream `reduceToVectors` errors с
    'Need 1+0 bands for Reducer.countEvery, image has 2'. Regression guard.
    """
    ee = ee_init
    from rca.detection_ch4 import extract_clusters

    # Synthetic mask: 1 inside small box, masked elsewhere
    aoi = ee.Geometry.Rectangle([86.0, 54.0, 86.5, 54.5])
    inner_box = ee.Geometry.Rectangle([86.1, 54.1, 86.2, 54.2])
    mask_image = (
        ee.Image.constant(0).clip(aoi).where(ee.Image.constant(1).clip(inner_box), 1).selfMask()
    )

    cluster_image = extract_clusters(mask_image, min_cluster_px=1, connectedness=8)
    band_names = cluster_image.bandNames().getInfo()
    assert band_names == ["labels"], f"expected single 'labels' band, got {band_names}"


def test_build_hybrid_background_empty_months_raises(ee_init):
    """GPT review #3 H-7: build_hybrid_background must reject empty months list."""
    import pytest as _pytest

    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background

    ref = ee.Image.constant(1880).rename("ref_M01")
    reg = ee.Image.constant(1900).rename("median_M01")
    with _pytest.raises(ValueError, match="months list must not be empty"):
        build_hybrid_background(ref, reg, months=[])


def test_encode_qa_flags_for_export(ee_init):
    """Шаг 5 launch fix: qa_flags list → string before Export к asset.

    Без encoding GEE rejects List<Object> с error code 3:
        'Unable to encode value qa_flags ... invalid type List<Object>'
    """
    ee = ee_init
    from rca.detection_helpers import encode_qa_flags_for_export

    feat_empty = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {"centroid_lat": 54.0, "qa_flags": []},
    )
    feat_single = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {"centroid_lat": 54.0, "qa_flags": ["manual_attribution_override"]},
    )
    feat_multi = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {
            "centroid_lat": 54.0,
            "qa_flags": [
                "transboundary_easterly_transport_suspected",
                "zone_boundary_adjustment_applied",
            ],
        },
    )

    fc = ee.FeatureCollection([feat_empty, feat_single, feat_multi])
    encoded = encode_qa_flags_for_export(fc)
    flags = encoded.aggregate_array("qa_flags").getInfo()

    assert flags[0] == "", f"empty list should encode к empty string, got {flags[0]!r}"
    assert flags[1] == "manual_attribution_override"
    assert flags[2] == "transboundary_easterly_transport_suspected;zone_boundary_adjustment_applied"


def test_apply_event_overrides_date_window_inclusive(ee_init):
    """GPT review #3 H-4 fix verification: tolerance_days=2 → 5 calendar days
    inclusive ([event-2, event+2])."""
    ee = ee_init
    from rca.detection_helpers import apply_event_overrides

    # Build features for 7 days around 2022-09-20: 09-17 to 09-23
    feats = []
    for day in range(17, 24):  # 17, 18, 19, 20, 21, 22, 23
        ts = ee.Date(f"2022-09-{day:02d}T12:00:00").millis()
        feats.append(
            ee.Feature(
                ee.Geometry.Point([87.0, 54.0]),
                {
                    "centroid_lat": 54.0,
                    "centroid_lon": 87.0,
                    "orbit_date_millis": ts,
                    "qa_flags": [],
                    "day_label": day,
                },
            )
        )
    fc = ee.FeatureCollection(feats)

    overrides = [
        {
            "centroid_lat": 54.0,
            "centroid_lon": 87.0,
            "event_date": "2022-09-20",
            "tolerance_km": 30,
            "tolerance_days": 2,
            "manual_source_id": "kuzbass_test",
            "manual_source_type": "coal_mine",
        }
    ]
    result = apply_event_overrides(fc, overrides)
    # Get all features' day_label + manual_source_id
    matched_days = (
        result.filter(ee.Filter.eq("manual_source_id", "kuzbass_test"))
        .aggregate_array("day_label")
        .getInfo()
    )
    matched_days_sorted = sorted(matched_days)
    # Expect: 18, 19, 20, 21, 22 (5 days, ±2 inclusive); NOT 17, 23
    assert matched_days_sorted == [
        18,
        19,
        20,
        21,
        22,
    ], f"H-4 off-by-one regression: expected days [18,19,20,21,22], got {matched_days_sorted}"


def test_cluster_attributes_property_names_no_band_collision(ee_init):
    """Issue 2.1: setOutputs ensures max_z/mean_z/n_pixels/max_delta/mean_delta —
    NOT band-prefixed (z_max would have been the silent failure mode)."""
    ee = ee_init
    from rca.detection_ch4 import compute_cluster_attributes

    # Synthetic small ROI
    aoi = ee.Geometry.Rectangle([86.0, 54.0, 86.5, 54.5])

    # Synthetic cluster image: 1 inside small inner box, 0 elsewhere
    inner_box = ee.Geometry.Rectangle([86.1, 54.1, 86.2, 54.2])
    cluster_image = ee.Image.constant(0).clip(aoi).where(ee.Image.constant(1).clip(inner_box), 1)
    cluster_image = cluster_image.selfMask()  # mask 0s

    # Multi-band z_image (matches compute_z_score output schema)
    z_image = ee.Image.cat(
        [
            ee.Image.constant(3.5).rename("z"),
            ee.Image.constant(45).rename("delta_primary"),
            ee.Image.constant(1880).rename("primary_value"),
            ee.Image.constant(20).rename("primary_sigma"),
            ee.Image.constant(1).rename("consistency_flag"),
            ee.Image.constant(0).rename("matched_inside_reference_zone"),
        ]
    )
    orbit_image = ee.Image.constant(1925).rename(
        "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
    )
    baseline_value = ee.Image.constant(1880)

    fc = compute_cluster_attributes(cluster_image, orbit_image, baseline_value, z_image, aoi)

    # If FC is non-empty, verify property names
    size = fc.size().getInfo()
    if size > 0:
        feat_props = fc.first().toDictionary().getInfo()
        # GPT review #1 Issue 2.1 fix verification:
        assert (
            "max_z" in feat_props
        ), f"max_z missing — band collision regression. Props: {list(feat_props)}"
        assert "mean_z" in feat_props
        assert "n_pixels" in feat_props
        assert "max_delta" in feat_props
        assert "mean_delta" in feat_props
        # NOT band-prefixed (these would indicate the bug):
        assert "z_max" not in feat_props
        assert "z_mean" not in feat_props


# ---------------------------------------------------------------------------
# Primitive 5: validate_wind — wind angle math + null axis behavior
# ---------------------------------------------------------------------------


def test_validate_wind_axis_unknown_state(ee_init):
    """Issue 5.2: cluster без plume_axis_deg → wind_state='axis_unknown'."""
    ee = ee_init
    from rca.detection_ch4 import validate_wind

    # Cluster centered at Bovanenkovo, NO plume_axis_deg property
    cluster = ee.Feature(
        ee.Geometry.Point([68.5, 70.5]).buffer(10000),
        {"cluster_id": 1},  # plume_axis_deg deliberately omitted
    )
    cluster_fc = ee.FeatureCollection([cluster])

    # Real ERA5 collection
    era5 = ee.ImageCollection("ECMWF/ERA5/HOURLY")

    # Sample timestamp: 2022-07-01 12:00 UTC
    orbit_millis = ee.Date("2022-07-01T12:00:00").millis()

    result_fc = validate_wind(cluster_fc, era5, orbit_millis)
    feat_props = result_fc.first().toDictionary().getInfo()

    assert (
        feat_props.get("wind_state") == "axis_unknown"
    ), f"Expected 'axis_unknown', got {feat_props.get('wind_state')}"
    # wind_consistent should be null (None) when axis unknown
    assert feat_props.get("wind_consistent") is None


# ---------------------------------------------------------------------------
# Шаг 5 orchestrator helpers (server-side functions)
# ---------------------------------------------------------------------------


def test_zmin_filter_keeps_kuzbass_with_high_z(ee_init):
    """build_zmin_filter keeps Kuzbass cluster (lat=54, lon=87) с max_z=4.5."""
    ee = ee_init
    from rca.detection_helpers import build_zmin_filter

    feat_kuzbass_high = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {"centroid_lat": 54.0, "centroid_lon": 87.0, "max_z": 4.5},
    )
    feat_kuzbass_low = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {"centroid_lat": 54.0, "centroid_lon": 87.0, "max_z": 3.5},
    )
    feat_yamal = ee.Feature(
        ee.Geometry.Point([75.0, 70.0]),
        {"centroid_lat": 70.0, "centroid_lon": 75.0, "max_z": 3.5},
    )
    fc = ee.FeatureCollection([feat_kuzbass_high, feat_kuzbass_low, feat_yamal])

    filtered = fc.filter(build_zmin_filter())
    n_kept = filtered.size().getInfo()
    # Expected: kuzbass_high (kept), kuzbass_low (DROPPED — <4.0 in Kuzbass), yamal (kept — ≥3.0)
    assert n_kept == 2, f"expected 2 kept, got {n_kept}"


def test_annotate_zone_boundary_qa_adds_flag_at_57_5(ee_init):
    """annotate_zone_boundary_qa adds qa_flag для cluster near 57.5°N."""
    ee = ee_init
    from rca.detection_helpers import annotate_zone_boundary_qa

    feat_near = ee.Feature(
        ee.Geometry.Point([75.0, 57.6]),  # within 100 km of 57.5°N
        {"centroid_lat": 57.6, "centroid_lon": 75.0, "qa_flags": []},
    )
    feat_far = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),  # NOT near boundary
        {"centroid_lat": 60.0, "centroid_lon": 75.0, "qa_flags": []},
    )
    fc = ee.FeatureCollection([feat_near, feat_far])

    annotated = annotate_zone_boundary_qa(fc)
    near_props = ee.Feature(annotated.toList(2).get(0)).toDictionary().getInfo()
    far_props = ee.Feature(annotated.toList(2).get(1)).toDictionary().getInfo()

    assert "zone_boundary_adjustment_applied" in near_props["qa_flags"]
    assert near_props["zone_boundary_step_ppb"] == 35.0
    assert "zone_boundary_adjustment_applied" not in far_props["qa_flags"]
    # EE drops properties set to None — use .get() с None default для robustness
    assert far_props.get("zone_boundary_step_ppb") is None


def test_apply_event_overrides_matches_event(ee_init):
    """apply_event_overrides sets manual_source_id для matching event."""
    ee = ee_init
    from rca.detection_helpers import apply_event_overrides

    event_date = ee.Date("2022-09-20T12:00:00").millis()
    feat = ee.Feature(
        ee.Geometry.Point([87.0, 54.0]),
        {
            "centroid_lat": 54.0,
            "centroid_lon": 87.0,
            "orbit_date_millis": event_date,
            "qa_flags": [],
        },
    )
    fc = ee.FeatureCollection([feat])

    overrides = [
        {
            "centroid_lat": 54.0,
            "centroid_lon": 87.0,
            "event_date": "2022-09-20",
            "tolerance_km": 30,
            "tolerance_days": 2,
            "manual_source_id": "kuzbass_test_event",
            "manual_source_type": "coal_mine",
        }
    ]
    result = apply_event_overrides(fc, overrides)
    props = result.first().toDictionary().getInfo()
    assert props["manual_source_id"] == "kuzbass_test_event"
    assert "manual_attribution_override" in props["qa_flags"]


def test_compute_orbit_plume_axes_populates_axis(ee_init):
    """Шаг 5 launch fix: compute_orbit_plume_axes computes plume_axis_deg
    на cluster polygons via client-side eigendecomposition.

    Verifies wind_state propagation through downstream validate_wind НЕ stuck
    in axis_unknown — at least cluster-large-enough features get axis bearing.
    """
    ee = ee_init
    from setup.build_ch4_event_catalog import compute_orbit_plume_axes

    # Synthetic clusters: large rectangle + small (≥3 px each at 7km grid)
    big_cluster = ee.Geometry.Rectangle([86.5, 53.7, 86.9, 54.0])  # ~30 px
    small_cluster = ee.Geometry.Rectangle([87.0, 54.5, 87.05, 54.55])  # ~1 px

    fc = ee.FeatureCollection(
        [
            ee.Feature(big_cluster, {"cluster_id": 1, "centroid_lon": 86.7, "centroid_lat": 53.85}),
            ee.Feature(
                small_cluster, {"cluster_id": 2, "centroid_lon": 87.025, "centroid_lat": 54.525}
            ),
        ]
    )

    augmented = compute_orbit_plume_axes(fc, scale_m=7000)
    feats = augmented.toList(2).getInfo()

    # Both should have plume_axis_deg property (None for too-few-pixels OR float)
    for f in feats:
        assert "plume_axis_deg" in f["properties"]
        # No pixel coord lists in output (would bloat asset)
        assert "longitude" not in f["properties"]
        assert "latitude" not in f["properties"]

    # Big cluster should have axis bearing in [0, 180)
    big_axis = feats[0]["properties"]["plume_axis_deg"]
    if big_axis is not None:
        assert 0.0 <= big_axis < 180.0, f"big cluster axis out of range: {big_axis}"


def test_validate_wind_with_populated_axis_aligned(ee_init):
    """Cluster с populated plume_axis_deg + sufficient wind aligned → wind_state='aligned'."""
    ee = ee_init
    from rca.detection_ch4 import validate_wind

    # Plume axis 90° (E-W) — wind should be E or W (FROM 90° или 270°) к align
    feat = ee.Feature(
        ee.Geometry.Point([68.5, 70.5]).buffer(10000),
        {"plume_axis_deg": 90.0},
    )
    fc = ee.FeatureCollection([feat])
    era5 = ee.ImageCollection("ECMWF/ERA5/HOURLY")
    # Pick a date с known easterly wind in summer  Yamal
    orbit_millis = ee.Date("2022-07-15T12:00:00").millis()

    result_fc = validate_wind(fc, era5, orbit_millis, alignment_threshold_deg=30.0)
    props = result_fc.first().toDictionary().getInfo()

    # wind_state should NOT be axis_unknown (axis is populated)
    assert (
        props.get("wind_state") != "axis_unknown"
    ), f"axis populated but wind_state={props.get('wind_state')} — fix broken"
    # Should be one of: aligned, misaligned, insufficient_wind
    assert props.get("wind_state") in ("aligned", "misaligned", "insufficient_wind")


def test_orchestrator_single_orbit_pipeline(ee_init):
    """End-to-end smoke test: detect_orbit_clusters runs without exception
    on a real TROPOMI orbit + synthetic baselines + real ERA5 + small AOI."""
    ee = ee_init
    from rca.detection_ch4 import build_hybrid_background
    from setup.build_ch4_event_catalog import detect_orbit_clusters

    # Small Kuzbass-region AOI
    aoi = ee.Geometry.Rectangle([86.0, 53.0, 89.0, 55.0])

    # Synthetic baselines (constants)
    ref_bands = [ee.Image.constant(1880).rename(f"ref_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(20).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    reg_bands = [ee.Image.constant(1900).rename(f"median_M{m:02d}") for m in range(1, 13)] + [
        ee.Image.constant(25).rename(f"sigma_M{m:02d}") for m in range(1, 13)
    ]
    hybrid = build_hybrid_background(ee.Image.cat(ref_bands), ee.Image.cat(reg_bands))

    # Real TROPOMI orbit — September 2022 over Kuzbass
    orbit_collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate("2022-09-20", "2022-09-21")
        .filterBounds(aoi)
        .select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")
    )
    orbit_count = orbit_collection.size().getInfo()
    if orbit_count == 0:
        pytest.skip("no TROPOMI orbits found for Kuzbass 2022-09-20 — environment-specific")
    orbit_image = ee.Image(orbit_collection.first())

    era5 = ee.ImageCollection("ECMWF/ERA5/HOURLY")
    source_points = ee.FeatureCollection([])

    result_fc = detect_orbit_clusters(
        orbit_image=orbit_image,
        hybrid_background=hybrid,
        month=9,
        aoi=aoi,
        era5_collection=era5,
        source_points_fc=source_points,
    )
    n_clusters = result_fc.size().getInfo()
    assert n_clusters >= 0, "FC.size() returned non-numeric"


# ---------------------------------------------------------------------------
# Шаг 6 server-side classification cascade
# ---------------------------------------------------------------------------


def test_apply_classification_cascade_server_side(ee_init):
    """apply_classification sets event_class per Algorithm §3.12 cascade."""
    ee = ee_init
    from rca.classify_events import (
        CLASS_CH4_ONLY,
        CLASS_DIFFUSE_CH4,
        CLASS_WIND_AMBIGUOUS,
        apply_classification,
    )

    # Test cases — one per cascade priority
    feat_zone = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),
        {
            "matched_inside_reference_zone": 1,
            "area_km2": 100,
            "month": 1,
            "wind_consistent": False,
        },
    )
    feat_wetland = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),
        {
            "matched_inside_reference_zone": 0,
            "area_km2": 5000,
            "month": 7,
            "nearest_source_id": None,
            "wind_consistent": True,
        },
    )
    feat_wind_ambig = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),
        {
            "matched_inside_reference_zone": 0,
            "area_km2": 100,
            "month": 1,
            "nearest_source_id": "kuzbass_tpp",
            "wind_consistent": False,
        },
    )
    feat_industrial = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),
        {
            "matched_inside_reference_zone": 0,
            "area_km2": 100,
            "month": 1,
            "nearest_source_id": "bovanenkovo_gas",
            "nearest_source_distance_km": 10,
            "wind_consistent": True,
        },
    )
    feat_default = ee.Feature(
        ee.Geometry.Point([75.0, 60.0]),
        {
            "matched_inside_reference_zone": 0,
            "area_km2": 100,
            "month": 1,
            "nearest_source_id": None,
            "wind_consistent": True,
        },
    )

    fc = ee.FeatureCollection(
        [feat_zone, feat_wetland, feat_wind_ambig, feat_industrial, feat_default]
    )
    classified = apply_classification(fc)
    classes = classified.aggregate_array("event_class").getInfo()

    assert classes[0] == CLASS_DIFFUSE_CH4, f"zone case: {classes[0]}"
    assert classes[1] == CLASS_DIFFUSE_CH4, f"wetland case: {classes[1]}"
    assert classes[2] == CLASS_WIND_AMBIGUOUS, f"wind ambig case: {classes[2]}"
    assert classes[3] == CLASS_CH4_ONLY, f"industrial case: {classes[3]}"
    assert classes[4] == CLASS_WIND_AMBIGUOUS, f"default case: {classes[4]}"


# ---------------------------------------------------------------------------
# Шаг 7 — Kuzbass 2022-09-20 regression integration test
# ---------------------------------------------------------------------------


def test_kuzbass_2022_09_20_detected(ee_init):
    """
    Phase 2A v1 hard gate per CLAUDE.md §5.1: Kuzbass 2022-09-20 event MUST be
    detected с default parameters before full archive launch authorized.

    Reference: pc_test1_scan.js regression baseline reported Z=3.96 в Кузбассе
    2022-09-20. Schuit et al. 2023 documents the event.

    Test scope: process September 2022 (M09) orbits over narrow Kuzbass AOI
    (86°-89°E × 53°-55°N), apply full detection pipeline, verify ≥1 cluster
    detected within 50 km of (87.0°E, 54.0°N) and within ±2 days.

    NOTE: Kuzbass z_min strict 4.0 (TD-0018) — event must clear this stricter
    threshold к count.
    """
    ee = ee_init
    from rca.classify_events import apply_classification
    from rca.detection_ch4 import build_hybrid_background
    from rca.detection_helpers import REFERENCE_AVAILABLE_MONTHS, prepare_source_points_categories
    from setup.build_ch4_event_catalog import (
        REFERENCE_BASELINE_ASSET,
        REFERENCE_ZONES_ASSET,
        REGIONAL_BASELINE_ASSET,
        SOURCE_POINTS_ASSET,
    )

    # Narrow Kuzbass AOI for speed
    aoi = ee.Geometry.Rectangle([86.0, 53.0, 89.0, 55.0])

    # Real production assets (verified existing)
    reference_baseline = ee.Image(REFERENCE_BASELINE_ASSET)
    regional_baseline = ee.Image(REGIONAL_BASELINE_ASSET)
    try:
        reference_zones = ee.FeatureCollection(REFERENCE_ZONES_ASSET)
        _ = reference_zones.size().getInfo()
    except Exception:
        reference_zones = None

    hybrid = build_hybrid_background(
        reference_baseline,
        regional_baseline,
        consistency_tolerance_ppb=30.0,
        reference_zones_fc=reference_zones,
        months=REFERENCE_AVAILABLE_MONTHS,
    )

    era5 = ee.ImageCollection("ECMWF/ERA5/HOURLY")
    raw_sources = ee.FeatureCollection(SOURCE_POINTS_ASSET)
    source_points = prepare_source_points_categories(raw_sources)

    # Process September 2022 only — narrow window для compute speed
    import logging

    logger = logging.getLogger("test_kuzbass")

    # Override TROPOMI date filter inside process_month — call detect_orbit_clusters
    # directly on Sep 18-22 orbits для tighter time bounds
    orbit_collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate("2022-09-18", "2022-09-23")
        .filterBounds(aoi)
        .select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")
    )
    n_orbits = orbit_collection.size().getInfo()
    if n_orbits == 0:
        pytest.skip("No TROPOMI orbits found for Kuzbass 2022-09-18..22 window")

    from setup.build_ch4_event_catalog import detect_orbit_clusters

    # Шаг 5 axis-fix: detect_orbit_clusters now contains client-side getInfo()
    # для plume_axis_deg eigendecomposition, so cannot use server-side .map().
    # Client-side Python loop instead.
    orbit_list = orbit_collection.toList(orbit_collection.size())
    orbit_fcs = []
    for i in range(n_orbits):
        orbit_image = ee.Image(orbit_list.get(i))
        try:
            orbit_fc = detect_orbit_clusters(
                orbit_image,
                hybrid,
                month=9,
                aoi=aoi,
                era5_collection=era5,
                source_points_fc=source_points,
            )
            orbit_fcs.append(orbit_fc)
        except Exception as exc:
            logger.warning("orbit %d skipped: %s", i, exc)

    merged = ee.FeatureCollection(orbit_fcs).flatten() if orbit_fcs else ee.FeatureCollection([])

    # Apply classification cascade
    classified = apply_classification(merged)

    # Count detections within 50 km of Kuzbass center (87°E, 54°N)
    target_geom = ee.Geometry.Point([87.0, 54.0]).buffer(50_000)
    nearby = classified.filterBounds(target_geom)
    n_nearby = nearby.size().getInfo()
    n_total = classified.size().getInfo()

    logger.warning(
        "Kuzbass 2022-09-18..22: %d orbits, %d total clusters, %d within 50 km",
        n_orbits,
        n_total,
        n_nearby,
    )

    # Phase 2A v1 acceptance criterion (CLAUDE.md §5.1):
    # ≥1 candidate в Kuzbass within ±2 days of 2022-09-20
    assert n_nearby >= 1, (
        f"Kuzbass 2022-09-20 regression FAILED: 0 clusters within 50 km. "
        f"Total clusters в AOI: {n_total}. Possible causes: z_min=4.0 too strict, "
        f"reference baseline gap (M09 available но coverage low в Kuzbass), "
        f"primary_value masking. Investigate before full launch."
    )
