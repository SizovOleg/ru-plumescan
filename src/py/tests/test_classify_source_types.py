"""Unit tests для classify_source_types (TD-0027 P-01.0d)."""

from __future__ import annotations

import pytest

from rca.classify_source_types import (
    BUFFER_KM,
    VIIRS_RADIANCE_THRESHOLD_HIGH,
    Classification,
    classify_source,
)


def test_gas_field_production_field_50km():
    """oil_gas + production_field → gas_field 50 km."""
    c = classify_source("oil_gas", "production_field")
    assert c.category == "gas_field"
    assert c.buffer_km == 50
    assert c.drop is False


def test_viirs_flare_high_radiance_30km():
    """oil_gas + viirs_flare_proxy + radiance=200 → viirs_flare_high 30 km."""
    c = classify_source("oil_gas", "viirs_flare_proxy", viirs_radiance_mean=200.0)
    assert c.category == "viirs_flare_high"
    assert c.buffer_km == 30


def test_viirs_flare_low_radiance_15km():
    """oil_gas + viirs_flare_proxy + radiance=50 → viirs_flare_low 15 km."""
    c = classify_source("oil_gas", "viirs_flare_proxy", viirs_radiance_mean=50.0)
    assert c.category == "viirs_flare_low"
    assert c.buffer_km == 15


def test_viirs_flare_threshold_boundary():
    """Exactly at threshold 100 → high (>=)."""
    c = classify_source(
        "oil_gas", "viirs_flare_proxy", viirs_radiance_mean=VIIRS_RADIANCE_THRESHOLD_HIGH
    )
    assert c.category == "viirs_flare_high"


def test_viirs_flare_below_threshold():
    """Just below threshold → low."""
    c = classify_source(
        "oil_gas",
        "viirs_flare_proxy",
        viirs_radiance_mean=VIIRS_RADIANCE_THRESHOLD_HIGH - 0.01,
    )
    assert c.category == "viirs_flare_low"


def test_viirs_flare_missing_radiance_treated_as_low():
    """No radiance reading → defensive: default 0.0 → low."""
    c = classify_source("oil_gas", "viirs_flare_proxy", viirs_radiance_mean=None)
    assert c.category == "viirs_flare_low"
    assert c.buffer_km == 15


def test_power_plant_coal_30km():
    c = classify_source("power_plant", "coal")
    assert c.category == "tpp_gres"
    assert c.buffer_km == 30


def test_power_plant_gas_30km():
    c = classify_source("power_plant", "gas")
    assert c.category == "tpp_gres"
    assert c.buffer_km == 30


def test_power_plant_tpp_gas_30km():
    """Alternative subtype label → same tpp_gres category."""
    c = classify_source("power_plant", "tpp_gas")
    assert c.category == "tpp_gres"


def test_power_plant_hydro_dropped():
    c = classify_source("power_plant", "hydro")
    assert c.drop is True
    assert c.category == "dropped"
    assert c.buffer_km == 0


def test_power_plant_nuclear_dropped():
    c = classify_source("power_plant", "nuclear")
    assert c.drop is True
    assert c.category == "dropped"


def test_coal_mine_open_pit_30km():
    c = classify_source("coal_mine", "open_pit")
    assert c.category == "coal_mine"
    assert c.buffer_km == 30


def test_coal_mine_deep_mine_30km():
    c = classify_source("coal_mine", "deep_mine")
    assert c.category == "coal_mine"


def test_metallurgy_smelter_30km():
    c = classify_source("metallurgy", "smelter")
    assert c.category == "smelter"
    assert c.buffer_km == 30


def test_metallurgy_ore_concentrator_30km():
    c = classify_source("metallurgy", "ore_concentrator")
    assert c.category == "smelter"


def test_metallurgy_aggregate_point_30km():
    c = classify_source("metallurgy", "aggregate_point")
    assert c.category == "smelter"


def test_unknown_defaults_to_30km():
    """Unrecognized type/subtype → 30 km defensive default."""
    c = classify_source("unknown_type", "unknown_subtype")
    assert c.category == "unknown"
    assert c.buffer_km == 30
    assert c.drop is False


def test_classification_is_frozen():
    """Immutability — same as Provenance pattern."""
    c = classify_source("oil_gas", "production_field")
    with pytest.raises((AttributeError, Exception)):
        c.category = "tampered"  # type: ignore[misc]


def test_buffer_km_constants():
    """Buffer values match researcher decision."""
    assert BUFFER_KM["gas_field"] == 50
    assert BUFFER_KM["viirs_flare_high"] == 30
    assert BUFFER_KM["viirs_flare_low"] == 15
    assert BUFFER_KM["tpp_gres"] == 30
    assert BUFFER_KM["coal_mine"] == 30
    assert BUFFER_KM["smelter"] == 30


def test_real_world_examples_full_inventory():
    """Spot-check examples spanning the full classification table."""
    cases = [
        # (st, sst, radiance, expected_category, expected_buffer, expected_drop)
        ("oil_gas", "production_field", None, "gas_field", 50, False),  # Bovanenkovo
        ("oil_gas", "viirs_flare_proxy", 6042.24, "viirs_flare_high", 30, False),  # max radiance
        ("oil_gas", "viirs_flare_proxy", 22.56, "viirs_flare_low", 15, False),  # p10 radiance
        ("power_plant", "coal", None, "tpp_gres", 30, False),  # Krasnoyarskaya GRES-2
        ("power_plant", "gas", None, "tpp_gres", 30, False),
        ("power_plant", "hydro", None, "dropped", 0, True),  # дропнуть
        ("power_plant", "nuclear", None, "dropped", 0, True),
        ("coal_mine", "open_pit", None, "coal_mine", 30, False),
        ("metallurgy", "smelter", None, "smelter", 30, False),  # Norilsk
    ]
    for st, sst, rad, ec, eb, ed in cases:
        c = classify_source(st, sst, rad)
        assert c.category == ec, f"{st}/{sst}/{rad}: got category={c.category}, expected {ec}"
        assert c.buffer_km == eb, f"{st}/{sst}/{rad}: got buffer={c.buffer_km}, expected {eb}"
        assert c.drop is ed, f"{st}/{sst}/{rad}: got drop={c.drop}, expected {ed}"


def test_classification_dataclass_type():
    c = classify_source("oil_gas", "production_field")
    assert isinstance(c, Classification)
    assert hasattr(c, "category")
    assert hasattr(c, "buffer_km")
    assert hasattr(c, "drop")
    assert hasattr(c, "rationale")
