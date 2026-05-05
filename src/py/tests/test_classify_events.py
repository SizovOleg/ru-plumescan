"""
P-02.0a Шаг 6 unit tests для classify_events cascade.

Per Algorithm §3.12 v2.3.2 5-priority cascade:
  1. Reference zone auto-override (matched_inside_reference_zone) → diffuse_CH4
  2. Wetland heuristic (≥3 of 4 conditions met) → diffuse_CH4
  3. Wind ambiguity (wind_consistent==False) → wind_ambiguous
  4. Industrial (nearest_source_id present + wind ok) → CH4_only
  5. Default → wind_ambiguous

Pure-Python tests verify deterministic cascade. Server-side
`apply_classification` tested via integration suite (test_detection_ch4_integration.py).
"""

from __future__ import annotations

from rca.classify_events import (
    CLASS_CH4_ONLY,
    CLASS_DIFFUSE_CH4,
    CLASS_WIND_AMBIGUOUS,
    VALID_CLASSES,
    WETLAND_AREA_KM2_MIN,
    WETLAND_SUMMER_MONTHS,
    classify_event,
)

# ---------------------------------------------------------------------------
# Class label constants
# ---------------------------------------------------------------------------


def test_valid_classes_set():
    """Three canonical classes per Common Plume Schema."""
    assert {CLASS_DIFFUSE_CH4, CLASS_WIND_AMBIGUOUS, CLASS_CH4_ONLY} == VALID_CLASSES


def test_class_labels():
    """Label spelling matches Algorithm §3.12 vocabulary."""
    assert CLASS_DIFFUSE_CH4 == "diffuse_CH4"
    assert CLASS_WIND_AMBIGUOUS == "wind_ambiguous"
    assert CLASS_CH4_ONLY == "CH4_only"


def test_wetland_constants():
    """Wetland heuristic thresholds per Algorithm §3.12."""
    assert WETLAND_AREA_KM2_MIN == 1000.0
    assert frozenset({6, 7, 8, 9}) == WETLAND_SUMMER_MONTHS


# ---------------------------------------------------------------------------
# Priority 1: Reference zone auto-override (highest precedence)
# ---------------------------------------------------------------------------


def test_priority1_reference_zone_overrides_to_diffuse():
    """matched_inside_reference_zone=True → diffuse_CH4 regardless of other conditions."""
    props = {
        "matched_inside_reference_zone": True,
        # Even с conflicting industrial signal:
        "nearest_source_id": "kuzbass_tpp",
        "nearest_source_distance_km": 5,
        "wind_consistent": True,
        "area_km2": 100,
        "month": 1,  # winter — non-wetland month
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority1_reference_zone_truthy_check():
    """Truthy values trigger override — bool True or other truthy."""
    assert classify_event({"matched_inside_reference_zone": True}) == CLASS_DIFFUSE_CH4
    assert classify_event({"matched_inside_reference_zone": 1}) == CLASS_DIFFUSE_CH4


def test_priority1_falsy_zone_does_not_override():
    """matched_inside_reference_zone=False (or 0/None) does NOT trigger Priority 1."""
    # Wind ambiguous but no reference zone → wind_ambiguous (Priority 3 OR Priority 5)
    props = {
        "matched_inside_reference_zone": False,
        "wind_consistent": False,
        "area_km2": 50,
        "month": 1,
    }
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS

    # None также falsy
    props["matched_inside_reference_zone"] = None
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


# ---------------------------------------------------------------------------
# Priority 2: Wetland heuristic (≥3 of 4 conditions)
# ---------------------------------------------------------------------------


def test_priority2_wetland_3of4_summer_no_source_large():
    """Summer + large area + no source → wetland (compactness disabled = 3 of 4)."""
    # Wetland conditions: area>1000 ✓, compactness_irregular ✗ (disabled),
    #   summer month ✓, no_nearby_source ✓ — 3 of 4 → wetland
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 1500,
        "month": 7,
        "nearest_source_id": None,
        "wind_consistent": True,  # not relevant — wetland wins before Priority 3
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority2_wetland_2of4_falls_through():
    """Only 2 of 4 wetland conditions → не wetland; cascade continues."""
    # Conditions: area>1000 ✓, summer month ✓ (2 conditions),
    # compactness disabled, has nearby source — 2 of 4 → не wetland
    # Wind not False, source present → Priority 4 → CH4_only
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 1500,
        "month": 7,
        "nearest_source_id": "kuzbass_tpp",
        "nearest_source_distance_km": 30,
        "wind_consistent": True,
    }
    assert classify_event(props) == CLASS_CH4_ONLY


def test_priority2_wetland_winter_month_falls_through():
    """Winter month (not 6-9) — 2 of 4 conditions max → не wetland."""
    # area>1000 ✓, no source ✓, winter month ✗, compactness disabled — 2 of 4
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 1500,
        "month": 1,
        "nearest_source_id": None,
        "wind_consistent": True,
    }
    # wind ok + no source + не wetland → Priority 5 default = wind_ambiguous
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


def test_priority2_wetland_no_source_via_distance():
    """Source present but distance > 100 km counts as no-source."""
    # area ✓, summer ✓, source present но 150 km away (no_nearby=True), compactness disabled
    # 3 of 4 → wetland
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 1500,
        "month": 8,
        "nearest_source_id": "far_factory",
        "nearest_source_distance_km": 150,
        "wind_consistent": True,
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority2_small_area_summer_no_source():
    """Small area (area ✗) + summer + no source = 2 of 4 → не wetland."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 500,
        "month": 7,
        "nearest_source_id": None,
        "wind_consistent": True,
    }
    # No source + не wetland + wind ok → default = wind_ambiguous
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


# ---------------------------------------------------------------------------
# Priority 3: Wind ambiguity
# ---------------------------------------------------------------------------


def test_priority3_wind_consistent_false_with_source():
    """wind_consistent=False (explicit) → wind_ambiguous, even с source nearby."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 200,  # not wetland
        "month": 1,
        "nearest_source_id": "kuzbass_tpp",
        "nearest_source_distance_km": 30,
        "wind_consistent": False,  # explicit false
    }
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


def test_priority3_wind_consistent_null_does_not_trigger():
    """wind_consistent=None (not False) does NOT trigger Priority 3 — falls through."""
    # wind_consistent=null + source present → Priority 4 (CH4_only)
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 200,
        "month": 1,
        "nearest_source_id": "kuzbass_tpp",
        "nearest_source_distance_km": 30,
        "wind_consistent": None,  # axis_unknown or insufficient_wind state
    }
    assert classify_event(props) == CLASS_CH4_ONLY


# ---------------------------------------------------------------------------
# Priority 4: Industrial (CH4_only)
# ---------------------------------------------------------------------------


def test_priority4_industrial_with_wind_ok():
    """Source present + wind_consistent=True + не wetland → CH4_only."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 100,
        "month": 1,
        "nearest_source_id": "bovanenkovo_gas",
        "nearest_source_distance_km": 10,
        "wind_consistent": True,
    }
    assert classify_event(props) == CLASS_CH4_ONLY


def test_priority4_industrial_wind_null():
    """Source present + wind_consistent=None → CH4_only (null doesn't block)."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 100,
        "month": 1,
        "nearest_source_id": "bovanenkovo_gas",
        "nearest_source_distance_km": 10,
        "wind_consistent": None,
    }
    assert classify_event(props) == CLASS_CH4_ONLY


# ---------------------------------------------------------------------------
# Priority 5: Default (wind_ambiguous)
# ---------------------------------------------------------------------------


def test_priority5_default_no_source_no_wetland_wind_ok():
    """No source, не wetland, wind ok → default wind_ambiguous."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 100,
        "month": 1,
        "nearest_source_id": None,
        "wind_consistent": True,
    }
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


def test_priority5_default_no_source_no_wetland_wind_null():
    """No source, не wetland, wind null → default wind_ambiguous."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 100,
        "month": 1,
        "nearest_source_id": None,
        "wind_consistent": None,
    }
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


def test_priority5_empty_props():
    """All defaults → wind_ambiguous."""
    assert classify_event({}) == CLASS_WIND_AMBIGUOUS


# ---------------------------------------------------------------------------
# Cascade priority verification (overlapping conditions)
# ---------------------------------------------------------------------------


def test_priority_order_zone_overrides_wetland():
    """Reference zone wins over wetland (Priority 1 > Priority 2)."""
    props = {
        "matched_inside_reference_zone": True,
        # Also wetland conditions met:
        "area_km2": 5000,
        "month": 7,
        "nearest_source_id": None,
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority_order_wetland_overrides_industrial():
    """Wetland wins over Priority 4 industrial."""
    # Wetland 3 of 4: area, summer, no nearby (distant source)
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 5000,
        "month": 7,
        "nearest_source_id": "distant_factory",
        "nearest_source_distance_km": 200,  # > 100 km — counts as no_nearby
        "wind_consistent": True,
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority_order_wetland_overrides_wind_ambiguous():
    """Wetland (Priority 2) wins over wind_consistent=False (Priority 3)."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 5000,
        "month": 7,
        "nearest_source_id": None,
        "wind_consistent": False,  # would trigger Priority 3
    }
    assert classify_event(props) == CLASS_DIFFUSE_CH4


def test_priority_order_wind_ambiguous_overrides_industrial():
    """wind_consistent=False (Priority 3) wins over has source (Priority 4)."""
    props = {
        "matched_inside_reference_zone": False,
        "area_km2": 100,  # not wetland
        "month": 1,
        "nearest_source_id": "kuzbass_tpp",  # would otherwise → CH4_only
        "nearest_source_distance_km": 10,
        "wind_consistent": False,
    }
    assert classify_event(props) == CLASS_WIND_AMBIGUOUS


# ---------------------------------------------------------------------------
# Output validity
# ---------------------------------------------------------------------------


def test_classification_always_returns_valid_class():
    """Any input combination produces одну из VALID_CLASSES."""
    test_cases = [
        {},
        {"matched_inside_reference_zone": True},
        {"area_km2": 0},
        {"month": 13},  # invalid month
        {"wind_consistent": "weird_string"},
        {"nearest_source_id": "", "nearest_source_distance_km": -1},
    ]
    for props in test_cases:
        result = classify_event(props)
        assert result in VALID_CLASSES, f"Got invalid class {result} для {props}"


def test_classify_event_is_pure_function():
    """Same input → same output (no internal state)."""
    props = {"area_km2": 1500, "month": 7, "nearest_source_id": None}
    r1 = classify_event(props)
    r2 = classify_event(props)
    assert r1 == r2


def test_classify_event_does_not_mutate_input():
    """Input props dict stays unchanged."""
    props = {"area_km2": 1500, "month": 7}
    snapshot = dict(props)
    _ = classify_event(props)
    assert props == snapshot


# ---------------------------------------------------------------------------
# Module integrity
# ---------------------------------------------------------------------------


def test_module_exports():
    """__all__ exposes function + constants."""
    from rca import classify_events

    expected = {
        "classify_event",
        "apply_classification",
        "CLASS_DIFFUSE_CH4",
        "CLASS_WIND_AMBIGUOUS",
        "CLASS_CH4_ONLY",
        "VALID_CLASSES",
    }
    for name in expected:
        assert name in classify_events.__all__
