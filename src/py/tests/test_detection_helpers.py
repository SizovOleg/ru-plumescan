"""
P-02.0a Шаг 5 unit tests для detection_helpers (orchestrator helpers).

Tests cover:
  * get_zmin — per-region adaptive z_min (TD-0018, DNA §2.1.6)
  * is_transboundary_candidate — pure-Python lat/lon check (TD-0017)
  * zone_boundary_step_ppb — per-cluster step lookup (TD-0021)
  * load_event_overrides — JSON parsing (Algorithm §6)
  * apply_event_overrides — robustness when overrides empty/malformed
  * build_event_config — config schema integrity для compute_provenance

Server-side functions (annotate_transboundary_qa, annotate_zone_boundary_qa,
apply_event_overrides на real FC) tested via integration tests с ee.Initialize().
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rca.detection_helpers import (
    DEFAULT_Z_MIN,
    EASTERLY_RANGE_DEG,
    KUZBASS_LAT_RANGE,
    KUZBASS_LON_RANGE,
    KUZBASS_Z_MIN,
    TRANSBOUNDARY_BACK_HOURS,
    TRANSBOUNDARY_LAT_RANGE,
    TRANSBOUNDARY_LON_MIN,
    ZONE_BOUNDARIES_LAT,
    ZONE_BOUNDARY_STEP_PPB,
    ZONE_BOUNDARY_TOLERANCE_KM,
    apply_event_overrides,
    build_event_config,
    get_zmin,
    is_transboundary_candidate,
    load_event_overrides,
    zone_boundary_step_ppb,
)

# ---------------------------------------------------------------------------
# Constants verification
# ---------------------------------------------------------------------------


def test_constants_kuzbass():
    """Kuzbass region constants per TD-0018 Phase 1c handoff."""
    assert KUZBASS_LAT_RANGE == (53.0, 55.0)
    assert KUZBASS_LON_RANGE == (86.0, 88.0)
    assert KUZBASS_Z_MIN == 4.0
    assert DEFAULT_Z_MIN == 3.0
    assert KUZBASS_Z_MIN > DEFAULT_Z_MIN  # strict > default


def test_constants_transboundary():
    """TD-0017 transboundary parameters."""
    assert TRANSBOUNDARY_LAT_RANGE == (53.0, 56.0)
    assert TRANSBOUNDARY_LON_MIN == 92.0
    assert TRANSBOUNDARY_BACK_HOURS == 24
    assert EASTERLY_RANGE_DEG == (45.0, 135.0)


def test_constants_zone_boundary():
    """TD-0021 step-inflation per P-01.2 handoff (75°E quantification)."""
    assert ZONE_BOUNDARIES_LAT == [57.5, 62.0]
    assert ZONE_BOUNDARY_STEP_PPB[57.5] == 35.0  # Kuznetsky → Yugansky M07 step
    assert ZONE_BOUNDARY_STEP_PPB[62.0] == 16.0  # Yugansky → Verkhne-Tazovsky M07 step
    assert ZONE_BOUNDARY_TOLERANCE_KM == 100.0


# ---------------------------------------------------------------------------
# get_zmin (TD-0018, DNA §2.1.6)
# ---------------------------------------------------------------------------


def test_get_zmin_kuzbass_center():
    """Centroid в самом центре Kuzbass (87°E, 54°N) → 4.0."""
    assert get_zmin(54.0, 87.0) == 4.0


def test_get_zmin_kuzbass_corner_inclusive():
    """Boundary corners inclusive (lat=53, lon=86 — corner of bbox)."""
    assert get_zmin(53.0, 86.0) == 4.0
    assert get_zmin(55.0, 88.0) == 4.0


def test_get_zmin_just_outside_kuzbass_lat():
    """Lat 52.99 (just south of bbox) → default 3.0."""
    assert get_zmin(52.99, 87.0) == 3.0


def test_get_zmin_just_outside_kuzbass_lon():
    """Lon 88.01 (just east of bbox) → default 3.0."""
    assert get_zmin(54.0, 88.01) == 3.0


def test_get_zmin_far_default():
    """Far from Kuzbass — Yamal, Norilsk, etc. — default 3.0."""
    assert get_zmin(70.0, 75.0) == 3.0  # Yamal
    assert get_zmin(69.5, 88.0) == 3.0  # Norilsk
    assert get_zmin(60.0, 75.0) == 3.0  # central Khanty
    assert get_zmin(50.0, 60.0) == 3.0  # SW corner AOI


def test_get_zmin_returns_float():
    """Type stability — always float."""
    z = get_zmin(54.0, 87.0)
    assert isinstance(z, float)
    assert z == 4.0


# ---------------------------------------------------------------------------
# is_transboundary_candidate (TD-0017)
# ---------------------------------------------------------------------------


def test_transboundary_in_zone_eastern_edge():
    """Lat 54°N, lon 93°E — eastern edge AOI, transboundary risk."""
    assert is_transboundary_candidate(54.0, 93.0) is True


def test_transboundary_lat_below_range():
    """Lat 52°N too far south — outside risk zone."""
    assert is_transboundary_candidate(52.0, 93.0) is False


def test_transboundary_lat_above_range():
    """Lat 57°N too far north — outside risk zone."""
    assert is_transboundary_candidate(57.0, 93.0) is False


def test_transboundary_lon_too_west():
    """Lon 91.99°E (just west of threshold 92) — not transboundary."""
    assert is_transboundary_candidate(54.0, 91.99) is False


def test_transboundary_lon_at_threshold():
    """Lon 92.0 exactly — boundary inclusive."""
    assert is_transboundary_candidate(54.0, 92.0) is True


# ---------------------------------------------------------------------------
# zone_boundary_step_ppb (TD-0021)
# ---------------------------------------------------------------------------


def test_zone_boundary_step_at_57_5():
    """Centroid 57.5°N exactly → step 35 ppb."""
    assert zone_boundary_step_ppb(57.5) == 35.0


def test_zone_boundary_step_at_62_0():
    """Centroid 62.0°N exactly → step 16 ppb."""
    assert zone_boundary_step_ppb(62.0) == 16.0


def test_zone_boundary_step_within_100km_57_5():
    """100 km tolerance ≈ 0.9° latitude. 56.7°N (within ~90 km of 57.5) — match."""
    assert zone_boundary_step_ppb(56.7) == 35.0
    assert zone_boundary_step_ppb(58.3) == 35.0


def test_zone_boundary_step_outside_tolerance():
    """61°N (~166 km from 57.5°N, ~111 km from 62°N) — outside both tolerances."""
    assert zone_boundary_step_ppb(60.5) is None  # > 100 km from both


def test_zone_boundary_step_far_from_boundaries():
    """Centroids far from any boundary → None."""
    assert zone_boundary_step_ppb(54.0) is None  # Kuzbass
    assert zone_boundary_step_ppb(70.0) is None  # Yamal
    assert zone_boundary_step_ppb(50.0) is None  # SW corner


def test_zone_boundary_step_within_100km_62_0():
    """61.2°N (within ~89 km of 62°N) — match step 16 ppb."""
    assert zone_boundary_step_ppb(61.2) == 16.0
    assert zone_boundary_step_ppb(62.8) == 16.0


# ---------------------------------------------------------------------------
# load_event_overrides
# ---------------------------------------------------------------------------


def test_load_overrides_missing_file():
    """Missing file → empty list (graceful)."""
    assert load_event_overrides("/nonexistent/path.json") == []


def test_load_overrides_valid():
    """Valid JSON list → parsed entries."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(
            [
                {
                    "centroid_lat": 54.0,
                    "centroid_lon": 87.0,
                    "event_date": "2022-09-20",
                    "manual_source_id": "kuzbass_event_test",
                    "manual_source_type": "coal_mine",
                }
            ],
            f,
        )
        tmppath = f.name
    try:
        result = load_event_overrides(tmppath)
        assert len(result) == 1
        assert result[0]["centroid_lat"] == 54.0
        assert result[0]["manual_source_id"] == "kuzbass_event_test"
    finally:
        Path(tmppath).unlink()


def test_load_overrides_malformed_json():
    """Malformed JSON → empty list (defensive)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not valid JSON {{{")
        tmppath = f.name
    try:
        assert load_event_overrides(tmppath) == []
    finally:
        Path(tmppath).unlink()


def test_load_overrides_not_a_list():
    """JSON object (not list) → empty list."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"not": "a list"}, f)
        tmppath = f.name
    try:
        assert load_event_overrides(tmppath) == []
    finally:
        Path(tmppath).unlink()


# ---------------------------------------------------------------------------
# apply_event_overrides (server-side robustness)
# ---------------------------------------------------------------------------


def test_apply_overrides_empty_returns_input():
    """Empty overrides list → returns input FC unchanged (no-op)."""
    from unittest.mock import MagicMock

    fc = MagicMock(name="fc")
    result = apply_event_overrides(fc, [])
    assert result is fc  # same reference, no transformation


# ---------------------------------------------------------------------------
# build_event_config (Provenance schema)
# ---------------------------------------------------------------------------


def test_build_event_config_target_year_set():
    """target_year propagates correctly."""
    config = build_event_config(2024)
    assert config["target_year"] == 2024
    assert config["history_year_min"] == 2019
    assert config["history_year_max"] == 2025


def test_build_event_config_default_preset():
    """Default config_preset='default'."""
    config = build_event_config(2022)
    assert config["config_preset"] == "default"


def test_build_event_config_custom_preset():
    """Custom config_preset propagates."""
    config = build_event_config(2022, config_preset="kuzbass-strict")
    assert config["config_preset"] == "kuzbass-strict"


def test_build_event_config_anomaly_thresholds():
    """Anomaly thresholds match Algorithm §3.6 defaults."""
    config = build_event_config(2024)
    anom = config["anomaly"]
    assert anom["z_min_default"] == 3.0
    assert anom["z_min_kuzbass"] == 4.0
    assert anom["delta_min_ppb"] == 30.0
    assert anom["relative_min_ppb"] == 15.0


def test_build_event_config_wind_td_0031():
    """Wind config matches TD-0031 (850hPa, ±30°, 2 m/s)."""
    config = build_event_config(2024)
    wind = config["wind"]
    assert wind["level_hpa"] == 850
    assert wind["alignment_threshold_deg"] == 30.0
    assert wind["min_wind_speed_ms"] == 2.0
    assert wind["temporal_window_hours"] == 3


def test_build_event_config_background_mode_reference_only():
    """TD-0032 Phase 2A v1 simplification: mode='reference_only'."""
    config = build_event_config(2024)
    assert config["background"]["mode"] == "reference_only"
    assert config["background"]["consistency_tolerance_ppb"] == 30.0
    assert config["background"]["sigma_floor_ppb"] == 15.0


def test_build_event_config_transboundary_td_0017():
    """TD-0017 transboundary parameters."""
    config = build_event_config(2024)
    tb = config["transboundary"]
    assert tb["lat_range"] == [53.0, 56.0]
    assert tb["lon_min"] == 92.0
    assert tb["back_trajectory_hours"] == 24
    assert tb["easterly_range_deg"] == [45.0, 135.0]


def test_build_event_config_zone_boundary_td_0021():
    """TD-0021 zone-boundary parameters."""
    config = build_event_config(2024)
    zb = config["zone_boundary"]
    assert zb["boundaries_lat"] == [57.5, 62.0]
    assert zb["step_inflation_ppb"]["57.5"] == 35.0
    assert zb["step_inflation_ppb"]["62.0"] == 16.0
    assert zb["tolerance_km"] == 100.0


def test_build_event_config_serialization_stable():
    """Same year + preset → bit-identical JSON (provenance hash invariant)."""
    config_a = build_event_config(2024, config_preset="default")
    config_b = build_event_config(2024, config_preset="default")
    # JSON sort_keys ensures determinism
    serialized_a = json.dumps(config_a, sort_keys=True)
    serialized_b = json.dumps(config_b, sort_keys=True)
    assert serialized_a == serialized_b


def test_build_event_config_different_years_different_serialization():
    """Different target_year → different config → different hash."""
    config_2022 = build_event_config(2022)
    config_2024 = build_event_config(2024)
    s_2022 = json.dumps(config_2022, sort_keys=True)
    s_2024 = json.dumps(config_2024, sort_keys=True)
    assert s_2022 != s_2024


# ---------------------------------------------------------------------------
# Provenance integration
# ---------------------------------------------------------------------------


def test_provenance_from_event_config():
    """compute_provenance accepts build_event_config output without errors."""
    from rca.provenance import compute_provenance

    config = build_event_config(2024)
    prov = compute_provenance(
        config=config,
        config_id="default",
        period="2019_2024",
        algorithm_version="2.3.2",
        rna_version="1.2",
    )
    assert prov.config_id == "default"
    assert "2024" in prov.run_id
    assert prov.algorithm_version == "2.3.2"
    assert len(prov.params_hash) == 64  # SHA-256 hex


def test_provenance_same_year_same_hash():
    """Same year + same preset → same provenance hash (TD-0024 invariant)."""
    from rca.provenance import compute_provenance

    config_a = build_event_config(2024, config_preset="default")
    config_b = build_event_config(2024, config_preset="default")
    prov_a = compute_provenance(config_a, "default", "2019_2024", "2.3.2", "1.2")
    prov_b = compute_provenance(config_b, "default", "2019_2024", "2.3.2", "1.2")
    assert prov_a.params_hash == prov_b.params_hash
    assert prov_a.run_id == prov_b.run_id


def test_provenance_different_year_different_hash():
    """Different target_year → different provenance hash."""
    from rca.provenance import compute_provenance

    p_2022 = compute_provenance(build_event_config(2022), "default", "2019_2022", "2.3.2", "1.2")
    p_2024 = compute_provenance(build_event_config(2024), "default", "2019_2024", "2.3.2", "1.2")
    assert p_2022.params_hash != p_2024.params_hash


# ---------------------------------------------------------------------------
# Module integrity
# ---------------------------------------------------------------------------


def test_helpers_module_exports():
    """__all__ exposes constants + functions."""
    from rca import detection_helpers

    expected = {
        "DEFAULT_Z_MIN",
        "KUZBASS_Z_MIN",
        "get_zmin",
        "build_zmin_filter",
        "is_transboundary_candidate",
        "annotate_transboundary_qa",
        "zone_boundary_step_ppb",
        "annotate_zone_boundary_qa",
        "load_event_overrides",
        "apply_event_overrides",
        "build_event_config",
    }
    for name in expected:
        assert name in detection_helpers.__all__, f"{name} missing from __all__"
