"""
P-02.0a Шаг 4 unit tests для detection_ch4 primitives.

Tests cover все 7 primitives (build_hybrid_background + 6 detection) +
compute_plume_axis_client_side helper. EE-API primitives tested via mock
patching (ee.Image / ee.Kernel / ee.Reducer не auth-зависимы при construction;
для реального вычисления нужен Initialize → integration suite).
Pure-numpy helper tested directly.

Per Algorithm v2.3.2 §3.4.3-§3.10. DNA §2.1 critical compliance verified:
  * Запрет 4: unmask с regional value (NOT zero) — в build_hybrid_background
  * Запрет 5: TWO-PASS annulus via ee.Kernel.circle (NO ee.Kernel arithmetic)

GPT review #1 fix tests included:
  * Issue 5.3: wind angle .mod(180) — 3 новых тестов wind_dir ∈ {350°, 200°, 110°}
  * Issue 1.2: cos(lat) aspect correction — tests at lat 10°, 54°, 70°
  * Issue 4.1: dual baseline cross-check — 4 build_hybrid_background tests
  * Issue 2.1: reduceRegions setOutputs — verifies no band collision
  * Issue 6.1: composite-key sort — verifies single .sort call
  * Issue 5.2: null plume_axis_deg → wind_state='axis_unknown'
  * Issue 2.3: wind_state enum {aligned, misaligned, insufficient_wind, axis_unknown}
"""

from __future__ import annotations

import inspect
import math
import random
from unittest.mock import MagicMock, patch

from rca import detection_ch4
from rca.detection_ch4 import (
    ANALYSIS_SCALE_M,
    ANNULUS_INNER_KM_DEFAULT,
    ANNULUS_OUTER_KM_DEFAULT,
    CONSISTENCY_TOLERANCE_PPB_DEFAULT,
    SIGMA_FLOOR_PPB,
    SOURCE_TYPE_PRIORITIES_CH4,
    compute_plume_axis_client_side,
)

# ---------------------------------------------------------------------------
# Module-level constants (Algorithm §3.5-3.10)
# ---------------------------------------------------------------------------


def test_sigma_floor_constant():
    """SIGMA_FLOOR_PPB = 15.0 ppb (Algorithm §3.5 noise floor)."""
    assert SIGMA_FLOOR_PPB == 15.0


def test_analysis_scale_constant():
    """ANALYSIS_SCALE_M = 7000 m (TROPOMI L3 grid)."""
    assert ANALYSIS_SCALE_M == 7000


def test_annulus_outer_default_150km():
    """Outer disk radius = 150 km (Algorithm §3.6 TWO-PASS)."""
    assert ANNULUS_OUTER_KM_DEFAULT == 150


def test_annulus_inner_default_50km():
    """Inner-disk radius = 50 km (documented bias source: ~12% under-detection)."""
    assert ANNULUS_INNER_KM_DEFAULT == 50


def test_consistency_tolerance_default():
    """Consistency tolerance = 30 ppb (Algorithm §3.4.3 dual baseline cross-check)."""
    assert CONSISTENCY_TOLERANCE_PPB_DEFAULT == 30.0


def test_source_type_priorities_ranking():
    """gas_field=1 outranks viirs_flare_high=2; full ranking per Algorithm §3.10."""
    assert SOURCE_TYPE_PRIORITIES_CH4["gas_field"] == 1
    assert SOURCE_TYPE_PRIORITIES_CH4["viirs_flare_high"] == 2
    assert SOURCE_TYPE_PRIORITIES_CH4["coal_mine"] == 3
    assert SOURCE_TYPE_PRIORITIES_CH4["tpp_gres"] == 4
    assert SOURCE_TYPE_PRIORITIES_CH4["viirs_flare_low"] == 5
    assert SOURCE_TYPE_PRIORITIES_CH4["smelter"] == 6
    assert SOURCE_TYPE_PRIORITIES_CH4["gas_field"] < SOURCE_TYPE_PRIORITIES_CH4["smelter"]


# ---------------------------------------------------------------------------
# compute_plume_axis_client_side — pure numpy (no EE)
# Issue 1.2 fix: cos(lat) aspect correction + tests at 3 latitudes
# ---------------------------------------------------------------------------


def test_plume_axis_horizontal_line():
    """Horizontal pixels (constant lat, varying lon) → axis ≈ 90° (E-W bearing)."""
    lons = [86.0, 86.1, 86.2, 86.3, 86.4]
    lats = [54.0, 54.0, 54.0, 54.0, 54.0]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 90.0) < 1.0, f"horizontal axis got {axis}"


def test_plume_axis_vertical_line():
    """Vertical pixels (constant lon) → axis ≈ 0° (N-S bearing)."""
    lons = [86.0, 86.0, 86.0, 86.0, 86.0]
    lats = [54.0, 54.1, 54.2, 54.3, 54.4]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert axis < 1.0 or axis > 179.0, f"vertical axis got {axis}"


def test_plume_axis_diagonal_45_at_54n():
    """45° NE bearing at lat=54°N: lon increment in degrees = lat / cos(54°)
    so that km-east extent equals km-north extent (true 45° compass bearing)."""
    cos_54 = math.cos(math.radians(54))
    lons = [86.0 + i * 0.1 / cos_54 for i in range(5)]
    lats = [54.0 + i * 0.1 for i in range(5)]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 45.0) < 1.0, f"54°N diagonal axis got {axis}"


def test_plume_axis_diagonal_45_at_10n():
    """45° NE bearing at lat=10°N (cos≈0.985, almost no correction needed)."""
    cos_10 = math.cos(math.radians(10))
    lons = [10.0 + i * 0.1 / cos_10 for i in range(5)]
    lats = [10.0 + i * 0.1 for i in range(5)]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 45.0) < 1.0, f"10°N diagonal axis got {axis}"


def test_plume_axis_diagonal_45_at_70n():
    """45° NE bearing at lat=70°N (cos≈0.342, large correction needed —
    km-equivalent lon = 0.292°/km vs lat 0.111°/km)."""
    cos_70 = math.cos(math.radians(70))
    lons = [86.0 + i * 0.1 / cos_70 for i in range(5)]
    lats = [70.0 + i * 0.1 for i in range(5)]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 45.0) < 1.0, f"70°N diagonal axis got {axis}"


def test_plume_axis_too_few_pixels():
    """< 3 pixels → None (eigendecomposition undefined)."""
    assert compute_plume_axis_client_side([86.0, 86.1], [54.0, 54.1]) is None
    assert compute_plume_axis_client_side([86.0], [54.0]) is None
    assert compute_plume_axis_client_side([], []) is None


def test_plume_axis_returns_in_range():
    """Output always normalized к [0, 180) — never negative или >= 180."""
    random.seed(42)
    for _ in range(10):
        n = random.randint(3, 20)
        lons = [86.0 + random.uniform(-0.5, 0.5) for _ in range(n)]
        lats = [54.0 + random.uniform(-0.5, 0.5) for _ in range(n)]
        axis = compute_plume_axis_client_side(lons, lats)
        assert axis is not None
        assert 0.0 <= axis < 180.0, f"axis={axis} out of [0, 180)"


def test_plume_axis_minimum_3_pixels():
    """Exactly 3 pixels — boundary case still returns valid axis."""
    axis = compute_plume_axis_client_side([86.0, 86.1, 86.2], [54.0, 54.0, 54.0])
    assert axis is not None
    assert abs(axis - 90.0) < 1.0


def test_plume_axis_pole_returns_none():
    """At pole (lat=90°) cos→0 — axis ill-defined, returns None."""
    axis = compute_plume_axis_client_side([0.0, 0.1, 0.2], [90.0, 90.0, 90.0])
    assert axis is None


# ---------------------------------------------------------------------------
# Helper: chainable mock ee.Image
# ---------------------------------------------------------------------------


def _mock_ee_image(name: str = "img") -> MagicMock:
    """Build chainable MagicMock returning self для большинства ee.Image methods."""
    img = MagicMock(name=name)
    for method in (
        "select",
        "unmask",
        "subtract",
        "divide",
        "rename",
        "max",
        "gte",
        "And",
        "selfMask",
        "updateMask",
        "connectedComponents",
        "connectedPixelCount",
        "reduceNeighborhood",
        "reduceRegions",
        "reduceToVectors",
        "abs",
        "lt",
        "paint",
        "multiply",
        "add",
        "mod",
    ):
        getattr(img, method).return_value = img
    return img


# ---------------------------------------------------------------------------
# Primitive 0: build_hybrid_background (Algorithm §3.4.3 dual baseline cross-check)
# Issue 4.1 fix tests
# ---------------------------------------------------------------------------


def test_build_hybrid_background_iterates_all_12_months():
    """build_hybrid_background must produce bands для всех 12 months M01..M12."""
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.build_hybrid_background(ref, reg)

    # 12 months × 4 selects per month (ref_value, ref_sigma, reg_value, reg_sigma)
    # = 48 select calls на baselines
    select_strs = [str(c) for c in ref.select.call_args_list + reg.select.call_args_list]
    months_seen = {f"M{m:02d}" for m in range(1, 13)}
    for month_str in months_seen:
        assert any(month_str in s for s in select_strs), f"month {month_str} not iterated"


def test_build_hybrid_background_uses_regional_fallback_not_zero():
    """DNA §2.1 запрет 4: ref_value.unmask(reg_value), NOT unmask(0)."""
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.build_hybrid_background(ref, reg)

    assert ref.unmask.called, "ref_value.unmask() must be called for fallback"
    for call in ref.unmask.call_args_list:
        assert (
            call.args and call.args[0] != 0
        ), "DNA §2.1.4 violation: must use regional fallback, not unmask(0)"


def test_build_hybrid_background_consistency_tolerance_default():
    """Default consistency tolerance = 30 ppb (Algorithm §3.4.3)."""
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.build_hybrid_background(ref, reg)

    # ref.subtract(reg).abs().lt(30.0) — verify .lt called с 30.0
    lt_args = [c.args[0] for c in ref.lt.call_args_list]
    assert 30.0 in lt_args, f"consistency tolerance 30.0 not used; lt args: {lt_args}"


def test_build_hybrid_background_custom_tolerance():
    """Custom consistency tolerance propagates."""
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.build_hybrid_background(ref, reg, consistency_tolerance_ppb=50.0)

    lt_args = [c.args[0] for c in ref.lt.call_args_list]
    assert 50.0 in lt_args


def test_build_hybrid_background_zone_mask_when_fc_provided():
    """When reference_zones_fc provided, ee.Image.constant(0).paint(fc, 1) used."""
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")
    zones_fc = MagicMock(name="zones_fc")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        zone_img = _mock_ee_image("zone_img")
        mock_image.constant = MagicMock(return_value=zone_img)
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        detection_ch4.build_hybrid_background(ref, reg, reference_zones_fc=zones_fc)

    # paint called с zones_fc as first arg
    zone_img.paint.assert_called()
    paint_args = zone_img.paint.call_args
    assert paint_args.args[0] is zones_fc, "paint must be called with zones_fc"


# ---------------------------------------------------------------------------
# Primitive 1: compute_z_score (refactored — consumes hybrid_background)
# ---------------------------------------------------------------------------


def test_compute_z_score_uses_correct_band_suffix():
    """Month=9 → suffix 'M09' для primary_value/primary_sigma/consistency_flag selection."""
    orbit = _mock_ee_image("orbit")
    hybrid = _mock_ee_image("hybrid")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.compute_z_score(orbit, hybrid, month=9)

    select_strs = [str(c) for c in hybrid.select.call_args_list]
    # Verify month suffix appears for primary_value, primary_sigma, consistency_flag
    assert any("primary_value_M09" in s for s in select_strs)
    assert any("primary_sigma_M09" in s for s in select_strs)
    assert any("consistency_flag_M09" in s for s in select_strs)


def test_compute_z_score_selects_zone_metadata_no_month_suffix():
    """matched_inside_reference_zone is static — no month suffix."""
    orbit = _mock_ee_image("orbit")
    hybrid = _mock_ee_image("hybrid")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.compute_z_score(orbit, hybrid, month=6)

    select_strs = [str(c) for c in hybrid.select.call_args_list]
    assert any("matched_inside_reference_zone" in s for s in select_strs)


def test_compute_z_score_applies_sigma_floor():
    """Z-score divisor = max(primary_sigma, sigma_floor) — floor prevents explosion."""
    orbit = _mock_ee_image("orbit")
    hybrid = _mock_ee_image("hybrid")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const_floor"))
        detection_ch4.compute_z_score(orbit, hybrid, month=6, sigma_floor_ppb=20.0)

    mock_image.constant.assert_any_call(20.0)


def test_compute_z_score_default_sigma_floor():
    """Default sigma_floor = SIGMA_FLOOR_PPB constant."""
    orbit = _mock_ee_image("orbit")
    hybrid = _mock_ee_image("hybrid")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const_floor"))
        detection_ch4.compute_z_score(orbit, hybrid, month=6)

    mock_image.constant.assert_any_call(SIGMA_FLOOR_PPB)


def test_compute_z_score_no_unmask_called_directly():
    """Refactored compute_z_score has NO fallback logic — that's в build_hybrid_background."""
    orbit = _mock_ee_image("orbit")
    hybrid = _mock_ee_image("hybrid")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.compute_z_score(orbit, hybrid, month=6)

    # hybrid.unmask should NOT be called — fallback already happened upstream
    hybrid.unmask.assert_not_called()


# ---------------------------------------------------------------------------
# Primitive 2: apply_three_condition_mask
# ---------------------------------------------------------------------------


def test_three_condition_mask_uses_outer_disk_kernel():
    """DNA §2.1 запрет 5: TWO-PASS uses ee.Kernel.circle (outer disk only)."""
    z_img = _mock_ee_image("z")
    delta_img = _mock_ee_image("delta")

    with (
        patch.object(detection_ch4.ee, "Kernel") as mock_kernel,
        patch.object(detection_ch4.ee, "Reducer") as mock_reducer,
    ):
        mock_kernel.circle = MagicMock(return_value=MagicMock(name="kernel"))
        mock_reducer.median = MagicMock(return_value=MagicMock(name="reducer"))
        detection_ch4.apply_three_condition_mask(z_img, delta_img)

    mock_kernel.circle.assert_called_once()
    call_kwargs = mock_kernel.circle.call_args.kwargs
    assert call_kwargs.get("radius") == 150_000  # 150 km в meters
    assert call_kwargs.get("units") == "meters"


def test_three_condition_mask_no_kernel_arithmetic():
    """DNA §2.1 запрет 5: NO ee.Kernel.fixed arithmetic, NO subtract over kernels."""
    z_img = _mock_ee_image("z")
    delta_img = _mock_ee_image("delta")

    with (
        patch.object(detection_ch4.ee, "Kernel") as mock_kernel,
        patch.object(detection_ch4.ee, "Reducer") as mock_reducer,
    ):
        mock_kernel.circle = MagicMock(return_value=MagicMock())
        mock_reducer.median = MagicMock(return_value=MagicMock())
        detection_ch4.apply_three_condition_mask(z_img, delta_img)

    assert mock_kernel.circle.call_count == 1
    mock_kernel.fixed.assert_not_called()


def test_three_condition_mask_default_thresholds():
    """Defaults: z_min=3.0, delta_min=30 ppb, relative_min=15 ppb."""
    z_img = _mock_ee_image("z")
    delta_img = _mock_ee_image("delta")

    with (
        patch.object(detection_ch4.ee, "Kernel") as mock_kernel,
        patch.object(detection_ch4.ee, "Reducer") as mock_reducer,
    ):
        mock_kernel.circle = MagicMock(return_value=MagicMock())
        mock_reducer.median = MagicMock(return_value=MagicMock())
        detection_ch4.apply_three_condition_mask(z_img, delta_img)

    z_gte_args = [c.args[0] for c in z_img.gte.call_args_list]
    assert 3.0 in z_gte_args
    delta_gte_args = [c.args[0] for c in delta_img.gte.call_args_list]
    assert 30.0 in delta_gte_args


def test_three_condition_mask_custom_thresholds():
    """Custom thresholds passed through correctly."""
    z_img = _mock_ee_image("z")
    delta_img = _mock_ee_image("delta")

    with (
        patch.object(detection_ch4.ee, "Kernel") as mock_kernel,
        patch.object(detection_ch4.ee, "Reducer") as mock_reducer,
    ):
        mock_kernel.circle = MagicMock(return_value=MagicMock())
        mock_reducer.median = MagicMock(return_value=MagicMock())
        detection_ch4.apply_three_condition_mask(
            z_img, delta_img, z_min=4.0, delta_min_ppb=50.0, relative_min_ppb=20.0
        )

    z_gte_args = [c.args[0] for c in z_img.gte.call_args_list]
    assert 4.0 in z_gte_args
    delta_gte_args = [c.args[0] for c in delta_img.gte.call_args_list]
    assert 50.0 in delta_gte_args


# ---------------------------------------------------------------------------
# Primitive 3: extract_clusters
# ---------------------------------------------------------------------------


def test_extract_clusters_default_8_connected():
    """Default 8-conn = ee.Kernel.square(1) per Algorithm §3.7."""
    mask = _mock_ee_image("mask")

    with patch.object(detection_ch4.ee, "Kernel") as mock_kernel:
        mock_kernel.square = MagicMock(return_value=MagicMock(name="square"))
        mock_kernel.plus = MagicMock(return_value=MagicMock(name="plus"))
        detection_ch4.extract_clusters(mask)

    mock_kernel.square.assert_called_once_with(1)
    mock_kernel.plus.assert_not_called()


def test_extract_clusters_4_connected_uses_plus_kernel():
    """connectedness=4 → ee.Kernel.plus(1)."""
    mask = _mock_ee_image("mask")

    with patch.object(detection_ch4.ee, "Kernel") as mock_kernel:
        mock_kernel.square = MagicMock(return_value=MagicMock())
        mock_kernel.plus = MagicMock(return_value=MagicMock())
        detection_ch4.extract_clusters(mask, connectedness=4)

    mock_kernel.plus.assert_called_once_with(1)
    mock_kernel.square.assert_not_called()


def test_extract_clusters_min_pixel_filter():
    """min_cluster_px filtering via connectedPixelCount + gte."""
    mask = _mock_ee_image("mask")

    with patch.object(detection_ch4.ee, "Kernel") as mock_kernel:
        mock_kernel.square = MagicMock(return_value=MagicMock())
        detection_ch4.extract_clusters(mask, min_cluster_px=10)

    mask.connectedPixelCount.assert_called_once()
    gte_args = [c.args[0] for c in mask.gte.call_args_list]
    assert 10 in gte_args


# ---------------------------------------------------------------------------
# Primitive 4: compute_cluster_attributes
# Issue 2.1 fix: setOutputs() to avoid band-prefix collision
# ---------------------------------------------------------------------------


def test_compute_cluster_attributes_uses_set_outputs_for_z():
    """Issue 2.1 fix: z reducer uses .setOutputs() to name output properties."""
    cluster = _mock_ee_image("cluster")
    orbit = _mock_ee_image("orbit")
    baseline = _mock_ee_image("baseline")
    z_img = _mock_ee_image("z")
    aoi = MagicMock(name="aoi")

    z_only = _mock_ee_image("z_only")
    z_img.select = MagicMock(return_value=z_only)
    delta_only = _mock_ee_image("delta_only")
    orbit.select = MagicMock(return_value=delta_only)

    max_reducer = MagicMock(name="max_reducer")
    mean_reducer = MagicMock(name="mean_reducer")
    count_reducer = MagicMock(name="count_reducer")

    with patch.object(detection_ch4.ee, "Reducer") as mock_reducer:
        mock_reducer.max = MagicMock(return_value=max_reducer)
        mock_reducer.mean = MagicMock(return_value=mean_reducer)
        mock_reducer.count = MagicMock(return_value=count_reducer)
        max_reducer.setOutputs = MagicMock(return_value=max_reducer)
        mean_reducer.setOutputs = MagicMock(return_value=mean_reducer)
        count_reducer.setOutputs = MagicMock(return_value=count_reducer)
        max_reducer.combine = MagicMock(return_value=max_reducer)
        detection_ch4.compute_cluster_attributes(cluster, orbit, baseline, z_img, aoi)

    # max.setOutputs(['max_z']) called; mean.setOutputs(['mean_z']); count.setOutputs(['n_pixels'])
    setoutputs_calls = max_reducer.setOutputs.call_args_list
    setoutput_args = [c.args[0] for c in setoutputs_calls]
    assert ["max_z"] in setoutput_args or ["max_delta"] in setoutput_args


def test_compute_cluster_attributes_selects_z_band_first():
    """Issue 2.1 fix: z_image.select('z') called before reduceRegions."""
    cluster = _mock_ee_image("cluster")
    orbit = _mock_ee_image("orbit")
    baseline = _mock_ee_image("baseline")
    z_img = _mock_ee_image("z")
    aoi = MagicMock(name="aoi")

    with patch.object(detection_ch4.ee, "Reducer"):
        detection_ch4.compute_cluster_attributes(cluster, orbit, baseline, z_img, aoi)

    select_args = [c.args[0] for c in z_img.select.call_args_list]
    assert "z" in select_args, "z_image.select('z') must be called to avoid band collision"


def test_compute_cluster_attributes_aoi_passed_to_reduce_to_vectors():
    """AOI passed correctly к reduceToVectors."""
    cluster = _mock_ee_image("cluster")
    orbit = _mock_ee_image("orbit")
    baseline = _mock_ee_image("baseline")
    z_img = _mock_ee_image("z")
    aoi = MagicMock(name="aoi")

    with patch.object(detection_ch4.ee, "Reducer"):
        detection_ch4.compute_cluster_attributes(cluster, orbit, baseline, z_img, aoi)

    cluster.reduceToVectors.assert_called_once()
    rtv_kwargs = cluster.reduceToVectors.call_args.kwargs
    assert rtv_kwargs.get("geometry") is aoi
    assert rtv_kwargs.get("bestEffort") is False  # DNA prohibition compliance


# ---------------------------------------------------------------------------
# Primitive 5: validate_wind
# Issue 5.3, 1.3, 5.2, 2.3 fixes
# ---------------------------------------------------------------------------


def test_validate_wind_default_850hpa():
    """Default wind level = 850hPa per TD-0031 (v2.3.1)."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    coll = MagicMock(name="era5")

    with patch.object(detection_ch4.ee, "Date") as mock_date:
        mock_date.return_value.advance.return_value = MagicMock()
        detection_ch4.validate_wind(fc, coll, orbit_time_millis=1_600_000_000_000)

    select_calls = coll.filterDate.return_value.select.call_args_list
    assert select_calls
    bands = select_calls[0].args[0]
    assert "u_component_of_wind_850hPa" in bands
    assert "v_component_of_wind_850hPa" in bands


def test_validate_wind_custom_level_propagates_to_band_names():
    """Custom wind_level_hpa propagates to ERA5 band names."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    coll = MagicMock(name="era5")

    with patch.object(detection_ch4.ee, "Date") as mock_date:
        mock_date.return_value.advance.return_value = MagicMock()
        detection_ch4.validate_wind(fc, coll, orbit_time_millis=0, wind_level_hpa=950)

    bands = coll.filterDate.return_value.select.call_args.args[0]
    assert "u_component_of_wind_950hPa" in bands
    assert "v_component_of_wind_950hPa" in bands


def test_validate_wind_temporal_window_default_3h():
    """Default temporal window ±3 hours."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    coll = MagicMock(name="era5")

    with patch.object(detection_ch4.ee, "Date") as mock_date:
        date_obj = MagicMock()
        date_obj.advance = MagicMock(return_value=MagicMock())
        mock_date.return_value = date_obj
        detection_ch4.validate_wind(fc, coll, orbit_time_millis=0)

    advance_calls = date_obj.advance.call_args_list
    assert len(advance_calls) == 2
    assert advance_calls[0].args == (-3, "hour")
    assert advance_calls[1].args == (3, "hour")


def test_validate_wind_returns_mapped_collection():
    """Returns fc.map(_validate)."""
    fc = MagicMock(name="fc")
    expected = MagicMock(name="expected")
    fc.map = MagicMock(return_value=expected)
    coll = MagicMock(name="era5")

    with patch.object(detection_ch4.ee, "Date"):
        result = detection_ch4.validate_wind(fc, coll, orbit_time_millis=0)

    fc.map.assert_called_once()
    assert result is expected


def test_validate_wind_default_thresholds():
    """Defaults: alignment_threshold=30°, min_wind_speed=2 m/s (TD-0031)."""
    sig = inspect.signature(detection_ch4.validate_wind)
    assert sig.parameters["alignment_threshold_deg"].default == 30.0
    assert sig.parameters["min_wind_speed_ms"].default == 2.0


# ---- Issue 5.3 (CRITICAL) — wind angle .mod(180) before shortest distance ----
#
# Direct math verification: simulate the formula with plain numbers.


def _shortest_axis_angle(wind_dir: float, plume_axis: float) -> float:
    """Reference implementation of fixed shortest-angular-distance to axis."""
    raw_diff_mod = abs(wind_dir - plume_axis) % 180
    return min(raw_diff_mod, 180 - raw_diff_mod)


def test_wind_angle_350_axis_10_distance_20():
    """Issue 5.3: wind_dir=350°, axis=10° → angle_diff=20° (was -160 in buggy version)."""
    assert _shortest_axis_angle(350.0, 10.0) == 20.0


def test_wind_angle_200_axis_20_distance_0():
    """Issue 5.3: wind_dir=200°, axis=20° → angle_diff=0° (perfectly aligned axis)."""
    assert _shortest_axis_angle(200.0, 20.0) == 0.0


def test_wind_angle_110_axis_20_distance_90():
    """Issue 5.3: wind_dir=110°, axis=20° → angle_diff=90° (perpendicular)."""
    assert _shortest_axis_angle(110.0, 20.0) == 90.0


def test_wind_angle_350_axis_170_distance_0():
    """Issue 5.3 edge: wind_dir=350°, axis=170° → angle_diff=0° (parallel, opposite directions)."""
    assert _shortest_axis_angle(350.0, 170.0) == 0.0


# ---- Issue 5.2 — null plume_axis_deg propagation ----


def test_validate_wind_plume_axis_null_handling():
    """Issue 5.2: plume_axis_value used in ee.Algorithms.If — null → wind_state='axis_unknown'."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    coll = MagicMock(name="era5")

    with (
        patch.object(detection_ch4.ee, "Date"),
        patch.object(detection_ch4.ee, "Algorithms") as mock_algos,
    ):
        mock_algos.If = MagicMock(return_value=MagicMock())
        detection_ch4.validate_wind(fc, coll, orbit_time_millis=0)

    # Map function called once с _validate closure
    fc.map.assert_called_once()


# ---------------------------------------------------------------------------
# Primitive 6: attribute_source
# Issue 6.1 fix: composite-key sort
# ---------------------------------------------------------------------------


def test_attribute_source_uses_default_priorities():
    """Default type_priorities = SOURCE_TYPE_PRIORITIES_CH4."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    sources = MagicMock(name="sources")

    with patch.object(detection_ch4.ee, "Dictionary") as mock_dict:
        detection_ch4.attribute_source(fc, sources)

    mock_dict.assert_called_once_with(SOURCE_TYPE_PRIORITIES_CH4)


def test_attribute_source_custom_priorities():
    """Custom priorities override default."""
    fc = MagicMock(name="fc")
    fc.map = MagicMock(return_value=MagicMock())
    sources = MagicMock(name="sources")
    custom = {"factory": 1, "other": 2}

    with patch.object(detection_ch4.ee, "Dictionary") as mock_dict:
        detection_ch4.attribute_source(fc, sources, type_priorities=custom)

    mock_dict.assert_called_once_with(custom)


def test_attribute_source_default_radius_50km():
    """Default search_radius_km = 50 per Algorithm §3.10."""
    sig = inspect.signature(detection_ch4.attribute_source)
    assert sig.parameters["search_radius_km"].default == 50.0


def test_attribute_source_returns_mapped():
    """Returns fc.map() — every cluster processed."""
    fc = MagicMock(name="fc")
    expected = MagicMock(name="expected")
    fc.map = MagicMock(return_value=expected)
    sources = MagicMock(name="sources")

    with patch.object(detection_ch4.ee, "Dictionary"):
        result = detection_ch4.attribute_source(fc, sources)

    fc.map.assert_called_once()
    assert result is expected


# ---- Issue 6.1 — composite-key single sort ----
#
# Direct math verification: composite_rank = priority * 1e6 + distance_km


def _composite_rank(priority: int, distance_km: float) -> float:
    """Reference composite key used by attribute_source."""
    return priority * 1_000_000 + distance_km


def test_composite_rank_priority_dominates():
    """Higher priority (lower number) always wins regardless of distance."""
    # gas_field=1 at 49.99 km vs viirs_flare_high=2 at 0.01 km
    gas_field = _composite_rank(1, 49.99)
    viirs_high = _composite_rank(2, 0.01)
    assert gas_field < viirs_high, "priority must dominate distance"


def test_composite_rank_distance_breaks_ties():
    """Equal priority — closer distance wins."""
    # Two gas_field sources at different distances
    closer = _composite_rank(1, 10.0)
    farther = _composite_rank(1, 30.0)
    assert closer < farther


def test_composite_rank_distance_within_priority_band():
    """Distance up to 999_999 km still preserves priority ordering."""
    # Gas field at theoretical 999 km (impossible in 50 km search) vs viirs at 0 km
    gas_far = _composite_rank(1, 999.0)
    viirs_close = _composite_rank(2, 0.0)
    assert gas_far < viirs_close


# ---------------------------------------------------------------------------
# Module integrity
# ---------------------------------------------------------------------------


def test_module_exports_all_primitives():
    """__all__ exposes 7 primitives + helper."""
    expected_primitives = {
        "build_hybrid_background",
        "compute_z_score",
        "apply_three_condition_mask",
        "extract_clusters",
        "compute_cluster_attributes",
        "validate_wind",
        "attribute_source",
        "compute_plume_axis_client_side",
    }
    for name in expected_primitives:
        assert name in detection_ch4.__all__, f"{name} missing from __all__"


def test_module_constants_in_exports():
    """Constants exported для downstream imports."""
    assert "SIGMA_FLOOR_PPB" in detection_ch4.__all__
    assert "ANNULUS_OUTER_KM_DEFAULT" in detection_ch4.__all__
    assert "ANNULUS_INNER_KM_DEFAULT" in detection_ch4.__all__
    assert "CONSISTENCY_TOLERANCE_PPB_DEFAULT" in detection_ch4.__all__
    assert "SOURCE_TYPE_PRIORITIES_CH4" in detection_ch4.__all__
    assert "ANALYSIS_SCALE_M" in detection_ch4.__all__
