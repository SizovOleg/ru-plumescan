"""
Unit tests для immutable Provenance dataclass (P-01.0c, TD-0024 prevention).

Critical invariants tested:
  * Same config → same hash (bit-identical reproducibility)
  * Dict ordering doesn't affect hash
  * Frozen dataclass prevents mutation
  * to_asset_properties excludes config_serialized (size limit)
  * to_log_entry includes full audit trail
  * run_id format `<config_id>_<period>_<sha8>`
  * canonical_serialize produces no whitespace
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rca.provenance import (
    Provenance,
    canonical_serialize,
    compute_params_hash,
    compute_provenance,
)


def test_same_config_produces_same_hash():
    """Critical invariant: same config → same Provenance."""
    config = {"key1": "value", "key2": 42, "nested": {"a": 1}}

    p1 = compute_provenance(config, "default", "2019_2025")
    p2 = compute_provenance(config, "default", "2019_2025")

    assert p1.params_hash == p2.params_hash
    assert p1.run_id == p2.run_id
    assert p1.config_serialized == p2.config_serialized


def test_different_dict_order_produces_same_hash():
    """sort_keys=True ensures order-independence."""
    config_a = {"a": 1, "b": 2, "c": 3}
    config_b = {"c": 3, "b": 2, "a": 1}

    p_a = compute_provenance(config_a, "default", "2019_2025")
    p_b = compute_provenance(config_b, "default", "2019_2025")

    assert p_a.params_hash == p_b.params_hash


def test_provenance_is_frozen():
    """frozen=True prevents mutation — TD-0024 structural prevention."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")

    with pytest.raises(FrozenInstanceError):
        p.params_hash = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        p.config_id = "other"  # type: ignore[misc]


def test_to_asset_properties_excludes_config_serialized():
    """Asset properties small; config_serialized stays в logs."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")
    props = p.to_asset_properties()

    assert "config_serialized" not in props
    assert "params_hash" in props
    assert "run_id" in props
    assert "config_id" in props
    assert "algorithm_version" in props
    assert "rna_version" in props
    assert "build_date" in props


def test_to_log_entry_includes_all():
    """Log entries get full audit trail including config_serialized."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")
    entry = p.to_log_entry("STARTED", gas="CH4", asset_id="foo/bar", n_tasks=12)

    assert entry["event"] == "STARTED"
    assert entry["status"] == "STARTED"
    assert "config_serialized" in entry
    assert entry["gas"] == "CH4"
    assert entry["asset_id"] == "foo/bar"
    assert entry["n_tasks"] == 12
    assert entry["params_hash"] == p.params_hash
    assert entry["run_id"] == p.run_id


def test_run_id_format():
    """run_id = `<config_id>_<period>_<hash[:8]>`."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")

    assert p.run_id.startswith("default_2019_2025_")
    assert len(p.run_id.split("_")[-1]) == 8
    assert p.run_id.endswith(p.params_hash[:8])


def test_canonical_serialize_no_whitespace():
    """No whitespace variations possible — stable across formatters."""
    s = canonical_serialize({"a": 1, "b": 2})

    assert " " not in s
    assert "\n" not in s
    assert s == '{"a":1,"b":2}'


def test_canonical_serialize_handles_non_native():
    """default=str coerces non-JSON-native objects (datetime etc.) consistently."""
    from datetime import date

    config = {"build_date": date(2026, 4, 30), "n": 42}
    s = canonical_serialize(config)

    assert "2026-04-30" in s
    assert s == '{"build_date":"2026-04-30","n":42}'


def test_compute_params_hash_matches_provenance():
    """Standalone helper agrees с Provenance computation."""
    config = {"gas": "CH4", "year": 2025}
    standalone = compute_params_hash(config)
    p = compute_provenance(config, "default", "2019_2025")

    assert p.params_hash == standalone


def test_period_derived_from_history_year_keys():
    """period auto-derives from history_year_min + history_year_max."""
    config = {"history_year_min": 2019, "history_year_max": 2024}
    p = compute_provenance(config, "default")

    assert "2019_2024" in p.run_id


def test_period_derived_from_target_year():
    """period falls back на target_year when history range absent."""
    config = {"target_year": 2025}
    p = compute_provenance(config, "default")

    assert "2019_2024" in p.run_id


def test_period_unknown_when_no_clues():
    """Unknown period documented explicitly, не silent default."""
    p = compute_provenance({"k": "v"}, "default")

    assert "unknown_period" in p.run_id


def test_config_id_default_falls_back_to_default():
    """config_id defaults к 'default' if not set in config or argument."""
    p = compute_provenance({"key": "value"})
    assert p.config_id == "default"


def test_config_id_from_config_preset():
    """config_id derived from config['config_preset'] if present."""
    p = compute_provenance({"config_preset": "schuit_eq"}, period="2019_2025")
    assert p.config_id == "schuit_eq"


def test_provenance_immutable_object_stable_across_methods():
    """to_asset_properties and to_log_entry don't mutate original Provenance."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")
    original_hash = p.params_hash
    original_run_id = p.run_id

    _ = p.to_asset_properties()
    _ = p.to_log_entry("STARTED", gas="CH4")

    assert p.params_hash == original_hash
    assert p.run_id == original_run_id


def test_provenance_dataclass_fields():
    """Verify expected fields on Provenance dataclass."""
    p = compute_provenance({"k": "v"}, "default", "2019_2025")

    assert isinstance(p, Provenance)
    expected_fields = {
        "config_id",
        "params_hash",
        "run_id",
        "config_serialized",
        "algorithm_version",
        "rna_version",
        "build_date",
    }
    actual_fields = {f.name for f in p.__dataclass_fields__.values()}
    assert actual_fields == expected_fields
