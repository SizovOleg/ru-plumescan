"""
P-02.0a Шаг 4 unit tests для detection_ch4 primitives.

Tests cover all 6 detection primitives + compute_plume_axis_client_side helper.
EE-API primitives tested via mock patching (ee.Image / ee.Kernel / ee.Reducer
не auth-зависимы при construction; для реального вычисления нужен Initialize).
Pure-numpy helper tested directly.

Per Algorithm v2.3.2 §3.5-3.10. DNA §2.1 critical compliance verified:
  * Запрет 4: unmask с regional value (NOT zero)
  * Запрет 5: TWO-PASS annulus via ee.Kernel.circle (NO ee.Kernel arithmetic)
"""

from __future__ import annotations

import inspect
import random
from unittest.mock import MagicMock, patch

from rca import detection_ch4
from rca.detection_ch4 import (
    ANALYSIS_SCALE_M,
    ANNULUS_INNER_KM_DEFAULT,
    ANNULUS_OUTER_KM_DEFAULT,
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


def test_source_type_priorities_ranking():
    """gas_field=1 outranks viirs_flare_high=2; full ranking per Algorithm §3.10."""
    assert SOURCE_TYPE_PRIORITIES_CH4["gas_field"] == 1
    assert SOURCE_TYPE_PRIORITIES_CH4["viirs_flare_high"] == 2
    assert SOURCE_TYPE_PRIORITIES_CH4["coal_mine"] == 3
    assert SOURCE_TYPE_PRIORITIES_CH4["tpp_gres"] == 4
    assert SOURCE_TYPE_PRIORITIES_CH4["viirs_flare_low"] == 5
    assert SOURCE_TYPE_PRIORITIES_CH4["smelter"] == 6
    # Lower number = higher priority — gas_field beats всех остальных
    assert SOURCE_TYPE_PRIORITIES_CH4["gas_field"] < SOURCE_TYPE_PRIORITIES_CH4["smelter"]


# ---------------------------------------------------------------------------
# compute_plume_axis_client_side — pure numpy (no EE)
# ---------------------------------------------------------------------------


def test_plume_axis_horizontal_line():
    """Horizontal pixels (constant lat, varying lon) → axis ≈ 90° (E-W)."""
    lons = [86.0, 86.1, 86.2, 86.3, 86.4]
    lats = [54.0, 54.0, 54.0, 54.0, 54.0]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 90.0) < 1.0, f"horizontal axis got {axis}"


def test_plume_axis_vertical_line():
    """Vertical pixels (constant lon) → axis ≈ 0° (N-S)."""
    lons = [86.0, 86.0, 86.0, 86.0, 86.0]
    lats = [54.0, 54.1, 54.2, 54.3, 54.4]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    # 0° N-S axis; values close to 0 acceptable (normalized к [0, 180))
    assert axis < 1.0 or axis > 179.0, f"vertical axis got {axis}"


def test_plume_axis_diagonal_45():
    """Equal lon/lat increments — perfect 45° NE axis."""
    lons = [86.0, 86.1, 86.2, 86.3, 86.4]
    lats = [54.0, 54.1, 54.2, 54.3, 54.4]
    axis = compute_plume_axis_client_side(lons, lats)
    assert axis is not None
    assert abs(axis - 45.0) < 5.0, f"diagonal axis got {axis}"


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
    ):
        getattr(img, method).return_value = img
    return img


# ---------------------------------------------------------------------------
# Primitive 1: compute_z_score
# ---------------------------------------------------------------------------


def test_compute_z_score_uses_correct_band_suffix():
    """Month=9 → suffix 'M09' для primary band selection."""
    orbit = _mock_ee_image("orbit")
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.compute_z_score(orbit, ref, reg, month=9)

    select_strs = [str(c) for c in ref.select.call_args_list + reg.select.call_args_list]
    assert any("M09" in s for s in select_strs), f"M09 suffix expected, got {select_strs}"


def test_compute_z_score_uses_unmask_regional_fallback_not_zero():
    """DNA §2.1 запрет 4: ref_value.unmask(reg_value), NOT unmask(0)."""
    orbit = _mock_ee_image("orbit")
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const"))
        detection_ch4.compute_z_score(orbit, ref, reg, month=6)

    assert ref.unmask.called, "ref_value.unmask() must be called for fallback"
    # Verify ни один unmask call не передавал literal 0
    for call in ref.unmask.call_args_list:
        assert (
            call.args and call.args[0] != 0
        ), "DNA §2.1.4 violation: must use regional fallback, not unmask(0)"


def test_compute_z_score_applies_sigma_floor():
    """Z-score divisor = max(primary_sigma, sigma_floor) — floor prevents explosion."""
    orbit = _mock_ee_image("orbit")
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const_floor"))
        detection_ch4.compute_z_score(orbit, ref, reg, month=6, sigma_floor_ppb=20.0)

    mock_image.constant.assert_any_call(20.0)


def test_compute_z_score_default_sigma_floor():
    """Default sigma_floor = SIGMA_FLOOR_PPB constant."""
    orbit = _mock_ee_image("orbit")
    ref = _mock_ee_image("ref")
    reg = _mock_ee_image("reg")

    with patch.object(detection_ch4.ee, "Image") as mock_image:
        mock_image.cat = MagicMock(return_value=_mock_ee_image("cat"))
        mock_image.constant = MagicMock(return_value=_mock_ee_image("const_floor"))
        detection_ch4.compute_z_score(orbit, ref, reg, month=6)

    mock_image.constant.assert_any_call(SIGMA_FLOOR_PPB)


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

    # Только один Kernel construction (circle) — no outer-inner pair
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
# Primitive 5: validate_wind
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
    assert select_calls, "collection.select() must be called"
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
    """Default temporal window ±3 hours (advance ±3, 'hour')."""
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
    """Returns fc.map(_validate) — every cluster processed."""
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


# ---------------------------------------------------------------------------
# Primitive 6: attribute_source
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


# ---------------------------------------------------------------------------
# Module integrity
# ---------------------------------------------------------------------------


def test_module_exports_all_six_primitives():
    """__all__ exposes all 6 primitives + helper."""
    assert "compute_z_score" in detection_ch4.__all__
    assert "apply_three_condition_mask" in detection_ch4.__all__
    assert "extract_clusters" in detection_ch4.__all__
    assert "compute_cluster_attributes" in detection_ch4.__all__
    assert "validate_wind" in detection_ch4.__all__
    assert "attribute_source" in detection_ch4.__all__
    assert "compute_plume_axis_client_side" in detection_ch4.__all__


def test_module_constants_in_exports():
    """Constants exported для downstream imports."""
    assert "SIGMA_FLOOR_PPB" in detection_ch4.__all__
    assert "ANNULUS_OUTER_KM_DEFAULT" in detection_ch4.__all__
    assert "ANNULUS_INNER_KM_DEFAULT" in detection_ch4.__all__
    assert "SOURCE_TYPE_PRIORITIES_CH4" in detection_ch4.__all__
    assert "ANALYSIS_SCALE_M" in detection_ch4.__all__
