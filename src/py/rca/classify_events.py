"""
Plume event classification cascade (Phase 2A, P-02.0a Шаг 6).

Implements Algorithm v2.3.2 §3.12 5-priority classification cascade:
  1. Reference zone auto-override (matched_inside_reference_zone) → diffuse_CH4
  2. Wetland heuristic (≥3 of 4 conditions met) → diffuse_CH4
  3. Wind ambiguity (wind_consistent==False) → wind_ambiguous
  4. Industrial (nearest_source_id present + wind ok) → CH4_only
  5. Default → wind_ambiguous

Pure-Python classifier (`classify_event(props)`) — testable, deterministic.
Server-side wrapper (`apply_classification(fc)`) — runs cascade на ee.FeatureCollection
via .map() для catalog export.

Compactness threshold (THRESHOLD_TBD per researcher decision Шаг 6) — Phase 2A
first 1-2 years emit events с class=null OR cascade-without-compactness;
post-100-events analysis determines empirical threshold для retroactive
reclassification (documented Algorithm v2.3.3 patch).
"""

from __future__ import annotations

from typing import Any

import ee

# ---------------------------------------------------------------------------
# Constants (Algorithm §3.12)
# ---------------------------------------------------------------------------

# Wetland heuristic conditions thresholds
WETLAND_AREA_KM2_MIN = 1000.0  # large diffuse signature
WETLAND_SUMMER_MONTHS = frozenset({6, 7, 8, 9})  # Jun-Sep
WETLAND_NO_SOURCE_DISTANCE_KM = 100.0  # > this = "no nearby source"

# Compactness ratio threshold — TBD per researcher (Phase 2A v1 placeholder)
# Phase 2A v1 simplification: compactness condition treated as inconclusive
# (=False) when threshold не yet calibrated. Reduces effective conditions from
# 4 к 3, making wetland classification более conservative (under-detection).
COMPACTNESS_THRESHOLD_PLACEHOLDER: float | None = None  # set after empirical analysis

# Class labels (Common Plume Schema vocabulary)
CLASS_DIFFUSE_CH4 = "diffuse_CH4"
CLASS_WIND_AMBIGUOUS = "wind_ambiguous"
CLASS_CH4_ONLY = "CH4_only"

VALID_CLASSES = frozenset({CLASS_DIFFUSE_CH4, CLASS_WIND_AMBIGUOUS, CLASS_CH4_ONLY})


# ---------------------------------------------------------------------------
# Pure-Python classifier (deterministic, testable)
# ---------------------------------------------------------------------------


def classify_event(props: dict[str, Any]) -> str:
    """
    Apply Algorithm §3.12 5-priority cascade к event properties dict.

    Args:
        props: dict с following keys (all optional — graceful defaults):
            * matched_inside_reference_zone: bool — reference zone membership
            * area_km2: float — cluster area
            * compactness_ratio: float | None — geometric compactness (TBD threshold)
            * month: int (1-12) — orbit month
            * nearest_source_id: str | None — attributed source ID
            * nearest_source_distance_km: float | None — distance к source
            * wind_consistent: bool | None — wind alignment status

    Returns: classification label (one of VALID_CLASSES).

    Cascade priority (highest precedence first):
        Priority 1: matched_inside_reference_zone == True → diffuse_CH4
                    (Reference zones are zapovedniks where any anomaly is
                    natural diffuse — anthropogenic sources excluded by zone
                    definition.)

        Priority 2: ≥3 of 4 wetland heuristic conditions → diffuse_CH4
                    (a) area_km2 > 1000  — large spatial extent
                    (b) compactness_ratio < THRESHOLD — irregular geometry
                        (Phase 2A v1: condition treated as False until threshold
                        empirically calibrated)
                    (c) month ∈ {6, 7, 8, 9} — summer methane peak
                    (d) no nearby source (id=null or distance > 100 km)

        Priority 3: wind_consistent == False → wind_ambiguous
                    (Wind disagreement с plume axis indicates uncertain
                    attribution; flag для manual review.)

        Priority 4: nearest_source_id present + wind ok (wind_consistent != False)
                    → CH4_only
                    (Source attributed AND wind doesn't contradict — confident
                    industrial CH4 plume.)

        Priority 5: default → wind_ambiguous
                    (No source AND not classified wetland AND wind data either
                    missing или null wind_consistent — can't confidently classify.)
    """
    # Priority 1: Reference zone auto-override
    if props.get("matched_inside_reference_zone"):
        return CLASS_DIFFUSE_CH4

    # Priority 2: Wetland heuristic (3 of 4)
    area = props.get("area_km2") or 0.0
    compactness = props.get("compactness_ratio")
    month = props.get("month")
    nearest_source_id = props.get("nearest_source_id")
    nearest_source_distance = props.get("nearest_source_distance_km")

    no_nearby_source = nearest_source_id is None or (
        nearest_source_distance is not None
        and nearest_source_distance > WETLAND_NO_SOURCE_DISTANCE_KM
    )

    # Compactness condition: only true if threshold defined AND value < threshold.
    # When threshold is None (Phase 2A v1), condition treated as False.
    compactness_irregular = (
        COMPACTNESS_THRESHOLD_PLACEHOLDER is not None
        and compactness is not None
        and compactness < COMPACTNESS_THRESHOLD_PLACEHOLDER
    )

    wetland_conditions = [
        area > WETLAND_AREA_KM2_MIN,
        compactness_irregular,
        month is not None and month in WETLAND_SUMMER_MONTHS,
        no_nearby_source,
    ]
    if sum(wetland_conditions) >= 3:
        return CLASS_DIFFUSE_CH4

    # Priority 3: Wind ambiguity
    wind_consistent = props.get("wind_consistent")
    if wind_consistent is False:
        return CLASS_WIND_AMBIGUOUS

    # Priority 4: Industrial — source present + wind not contradicting
    if nearest_source_id is not None:
        return CLASS_CH4_ONLY

    # Priority 5: Default
    return CLASS_WIND_AMBIGUOUS


# ---------------------------------------------------------------------------
# Server-side wrapper (ee.FeatureCollection.map)
# ---------------------------------------------------------------------------


def apply_classification(fc: ee.FeatureCollection) -> ee.FeatureCollection:
    """
    Apply classification cascade server-side к each feature в FC.

    Sets `event_class` property per Algorithm §3.12. Mirrors
    `classify_event` Python logic via ee.Algorithms.If chain.

    Wetland compactness condition: Phase 2A v1 currently disabled (treated as
    False) per COMPACTNESS_THRESHOLD_PLACEHOLDER=None. Mirror behavior server-side.
    """

    def _classify(feat: ee.Feature) -> ee.Feature:
        # Priority 1: matched_inside_reference_zone
        zone_match = ee.Number(ee.Algorithms.If(feat.get("matched_inside_reference_zone"), 1, 0))

        # Priority 2: wetland heuristic (3 of 4)
        area = ee.Number(ee.Algorithms.If(feat.get("area_km2"), feat.get("area_km2"), 0))
        large_area = area.gt(WETLAND_AREA_KM2_MIN)

        # Compactness — Phase 2A v1 placeholder: condition always False
        compactness_irregular = ee.Number(0)  # disabled until threshold calibrated

        month = ee.Number(ee.Algorithms.If(feat.get("month"), feat.get("month"), 0))
        is_summer = month.gte(6).And(month.lte(9))

        nearest_id = feat.get("nearest_source_id")
        # Treat None or empty string as "no source"
        no_id = ee.Number(ee.Algorithms.If(nearest_id, 0, 1))
        nearest_dist = ee.Number(
            ee.Algorithms.If(
                feat.get("nearest_source_distance_km"),
                feat.get("nearest_source_distance_km"),
                0,
            )
        )
        far_away = nearest_dist.gt(WETLAND_NO_SOURCE_DISTANCE_KM)
        # no_nearby_source = (no_id) OR (has id AND far_away)
        no_nearby = no_id.eq(1).Or(far_away)

        wetland_score = (
            ee.Number(0)
            .add(ee.Algorithms.If(large_area, 1, 0))
            .add(compactness_irregular)
            .add(ee.Algorithms.If(is_summer, 1, 0))
            .add(ee.Algorithms.If(no_nearby, 1, 0))
        )
        is_wetland = wetland_score.gte(3)

        # Priority 3: wind_consistent == False (explicit false, не null)
        wind_consistent = feat.get("wind_consistent")
        # ee.Algorithms.If treats null as falsy. We want strict "==False".
        # Pattern: check whether wind_consistent can be coerced k integer 0
        # via ee.Number(.. default=-1). True→1, False→0, null→-1.
        wind_value = ee.Number(
            ee.Algorithms.If(
                wind_consistent,
                1,
                ee.Algorithms.If(ee.Algorithms.IsEqual(wind_consistent, False), 0, -1),
            )
        )
        wind_explicit_false = wind_value.eq(0)

        # Priority 4: source present (regardless of wind)
        has_source = no_id.eq(0)

        # Cascade resolution
        event_class = ee.String(
            ee.Algorithms.If(
                zone_match.eq(1),
                CLASS_DIFFUSE_CH4,
                ee.Algorithms.If(
                    is_wetland,
                    CLASS_DIFFUSE_CH4,
                    ee.Algorithms.If(
                        wind_explicit_false,
                        CLASS_WIND_AMBIGUOUS,
                        ee.Algorithms.If(has_source, CLASS_CH4_ONLY, CLASS_WIND_AMBIGUOUS),
                    ),
                ),
            )
        )

        return feat.set("event_class", event_class)

    return fc.map(_classify)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "classify_event",
    "apply_classification",
    "CLASS_DIFFUSE_CH4",
    "CLASS_WIND_AMBIGUOUS",
    "CLASS_CH4_ONLY",
    "VALID_CLASSES",
    "WETLAND_AREA_KM2_MIN",
    "WETLAND_SUMMER_MONTHS",
    "WETLAND_NO_SOURCE_DISTANCE_KM",
    "COMPACTNESS_THRESHOLD_PLACEHOLDER",
]
