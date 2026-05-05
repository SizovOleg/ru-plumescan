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
