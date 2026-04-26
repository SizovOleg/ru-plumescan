"""
Тесты Common Plume Schema (см. Algorithm.md §2.1).

Покрывают:
  * Создание valid event (минимальный + полный набор полей).
  * Невалидные значения enum-ов (gas, confidence, class, source_catalog).
  * Невалидные диапазоны (lat, lon, wind_alignment_score, confidence_score).
  * Round-trip dict ↔ PlumeEvent ↔ dict (bit-identical).
  * Round-trip PlumeEvent → GeoJSON Feature → PlumeEvent.
  * Provenance enforcement для source_catalog="ours" (DNA §2.1).
  * Bulk validation через `validate_batch`.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError as PydanticValidationError

from rca.common_schema import (
    EVENT_CLASSES,
    GAS_TYPES,
    SCHEMA_VERSION,
    SOURCE_CATALOGS,
    from_dict,
    to_geojson_feature,
    validate_batch,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def minimal_reference_event() -> dict:
    """
    Минимальный валидный event из reference catalog (без provenance —
    они required только для source_catalog="ours").
    """
    return {
        "event_id": "schuit2023_CH4_20210715_700100_730500",
        "source_catalog": "schuit2023",
        "source_event_id": "schuit_42",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 25),
        "gas": "CH4",
        "date_utc": date(2021, 7, 15),
        "lon": 73.05,
        "lat": 70.01,
    }


@pytest.fixture
def full_ours_event() -> dict:
    """
    Полный event от нашего детектора (`source_catalog="ours"`) с
    обязательным config snapshot и большинством полей заполнено.
    """
    return {
        "event_id": "ours_CH4_20220920_540500_870300",
        "source_catalog": "ours",
        "source_event_id": "ours_CH4_20220920_540500_870300",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 26),
        "gas": "CH4",
        "date_utc": date(2022, 9, 20),
        "time_utc": time(8, 30, 0),
        "orbit": 25430,
        "lon": 87.03,
        "lat": 54.05,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[87.0, 54.0], [87.1, 54.0], [87.1, 54.1], [87.0, 54.1], [87.0, 54.0]]],
        },
        "area_km2": 75.0,
        "n_pixels": 5,
        "max_z": 3.96,
        "mean_z": 3.2,
        "max_delta": 65.0,
        "mean_delta": 45.0,
        "detection_method": "regional_threshold",
        "wind_u": 4.2,
        "wind_v": 1.8,
        "wind_speed": 4.57,
        "wind_dir_deg": 113.2,
        "plume_axis_deg": 110.0,
        "wind_alignment_score": 0.95,
        "wind_source": "ERA5_HOURLY",
        "nearest_source_id": "kuzbass_mine_42",
        "nearest_source_distance_km": 8.5,
        "nearest_source_type": "coal_mine",
        "magnitude_proxy": 65.0,
        "magnitude_proxy_unit": "ppb",
        "class": "CH4_only",
        "confidence": "high",
        "confidence_score": 0.78,
        "qa_flags": "",
        "algorithm_version": "2.2",
        "config_id": "default",
        "params_hash": "abc123def456789",
        "run_id": "default_20220920_abc12345",
        "run_date": date(2026, 4, 26),
    }


# --------------------------------------------------------------------------- #
# Создание valid events                                                       #
# --------------------------------------------------------------------------- #


def test_create_minimal_reference_event(minimal_reference_event: dict) -> None:
    event = from_dict(minimal_reference_event)
    assert event.gas == "CH4"
    assert event.source_catalog == "schuit2023"
    assert event.lat == 70.01
    assert event.lon == 73.05
    # Provenance fields допустимы None для не-ours
    assert event.config_id is None


def test_create_full_ours_event(full_ours_event: dict) -> None:
    event = from_dict(full_ours_event)
    assert event.source_catalog == "ours"
    assert event.config_id == "default"
    assert event.params_hash == "abc123def456789"
    assert event.class_ == "CH4_only"
    assert event.detection_method == "regional_threshold"
    assert event.geometry is not None
    assert event.geometry["type"] == "Polygon"


def test_class_alias_works_both_ways() -> None:
    """Поле `class` (зарезервированное слово Python) маппится на `class_`."""
    data = {
        "event_id": "x",
        "source_catalog": "schuit2023",
        "source_event_id": "y",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 25),
        "gas": "CH4",
        "date_utc": date(2021, 1, 1),
        "lon": 70.0,
        "lat": 60.0,
        "class": "CH4_only",
    }
    event = from_dict(data)
    assert event.class_ == "CH4_only"
    # Сериализация обратно по alias
    dumped = event.model_dump(by_alias=True)
    assert dumped["class"] == "CH4_only"
    assert "class_" not in dumped


# --------------------------------------------------------------------------- #
# Enum валидаторы                                                             #
# --------------------------------------------------------------------------- #


def test_invalid_gas_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["gas"] = "CO2"  # не в GAS_TYPES
    with pytest.raises(PydanticValidationError) as exc_info:
        from_dict(minimal_reference_event)
    assert "gas must be one of" in str(exc_info.value)


def test_invalid_source_catalog_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["source_catalog"] = "made_up_source"
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_invalid_confidence_raises(full_ours_event: dict) -> None:
    full_ours_event["confidence"] = "extremely_high"  # не в CONFIDENCE_LEVELS
    with pytest.raises(PydanticValidationError):
        from_dict(full_ours_event)


def test_invalid_class_raises(full_ours_event: dict) -> None:
    full_ours_event["class"] = "CH4_NO2_SO2_extra"
    with pytest.raises(PydanticValidationError):
        from_dict(full_ours_event)


def test_invalid_detection_method_raises(full_ours_event: dict) -> None:
    full_ours_event["detection_method"] = "novel_super_method"
    with pytest.raises(PydanticValidationError):
        from_dict(full_ours_event)


def test_invalid_magnitude_unit_raises(full_ours_event: dict) -> None:
    full_ours_event["magnitude_proxy_unit"] = "bogus_unit"
    with pytest.raises(PydanticValidationError):
        from_dict(full_ours_event)


def test_schema_version_mismatch_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["schema_version"] = "0.9"
    with pytest.raises(PydanticValidationError) as exc_info:
        from_dict(minimal_reference_event)
    assert "schema_version" in str(exc_info.value).lower()


# --------------------------------------------------------------------------- #
# Coordinate range                                                            #
# --------------------------------------------------------------------------- #


def test_invalid_lat_high_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["lat"] = 91.0
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_invalid_lat_low_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["lat"] = -91.0
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_invalid_lon_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["lon"] = 200.0
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_wind_alignment_out_of_range_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["wind_alignment_score"] = 1.5
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_confidence_score_out_of_range_raises(minimal_reference_event: dict) -> None:
    minimal_reference_event["confidence_score"] = 1.2
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


# --------------------------------------------------------------------------- #
# Provenance enforcement (DNA §2.1)                                           #
# --------------------------------------------------------------------------- #


def test_ours_without_provenance_raises() -> None:
    """
    DNA §2.1: Run без полного config snapshot не публикуется.
    Source_catalog="ours" без provenance полей должен поднимать ошибку.
    """
    incomplete = {
        "event_id": "ours_CH4_x",
        "source_catalog": "ours",
        "source_event_id": "ours_CH4_x",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 26),
        "gas": "CH4",
        "date_utc": date(2022, 9, 20),
        "lon": 87.0,
        "lat": 54.0,
        # provenance отсутствует
    }
    with pytest.raises(PydanticValidationError) as exc_info:
        from_dict(incomplete)
    err = str(exc_info.value)
    assert "config snapshot" in err or "provenance" in err.lower()


def test_ours_with_partial_provenance_raises() -> None:
    """Только часть provenance полей — всё ещё ошибка."""
    partial = {
        "event_id": "ours_CH4_x",
        "source_catalog": "ours",
        "source_event_id": "ours_CH4_x",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 26),
        "gas": "CH4",
        "date_utc": date(2022, 9, 20),
        "lon": 87.0,
        "lat": 54.0,
        "algorithm_version": "2.2",
        "config_id": "default",
        # params_hash, run_id, run_date, detection_method отсутствуют
    }
    with pytest.raises(PydanticValidationError):
        from_dict(partial)


def test_reference_without_provenance_ok(minimal_reference_event: dict) -> None:
    """Reference catalog не требует provenance."""
    event = from_dict(minimal_reference_event)
    assert event.source_catalog == "schuit2023"


# --------------------------------------------------------------------------- #
# Round-trip                                                                  #
# --------------------------------------------------------------------------- #


def test_dict_roundtrip_minimal(minimal_reference_event: dict) -> None:
    """dict → PlumeEvent → dict bit-identical (для полей, явно заданных)."""
    event = from_dict(minimal_reference_event)
    dumped = event.model_dump(mode="json", by_alias=True, exclude_none=True)
    # Ingestion_date и date_utc в JSON сериализуются как ISO strings.
    assert dumped["gas"] == "CH4"
    assert dumped["lat"] == 70.01
    assert dumped["lon"] == 73.05
    assert dumped["date_utc"] == "2021-07-15"


def test_dict_roundtrip_full(full_ours_event: dict) -> None:
    """Round-trip полного ours event."""
    event = from_dict(full_ours_event)
    dumped = event.model_dump(by_alias=True, exclude_none=True)
    # Re-validate
    event2 = from_dict(dumped)
    assert event2.event_id == event.event_id
    assert event2.class_ == event.class_
    assert event2.params_hash == event.params_hash
    assert event2.geometry == event.geometry


# --------------------------------------------------------------------------- #
# GeoJSON                                                                     #
# --------------------------------------------------------------------------- #


def test_to_geojson_feature_uses_explicit_geometry(full_ours_event: dict) -> None:
    event = from_dict(full_ours_event)
    feat = to_geojson_feature(event)
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Polygon"
    assert feat["properties"]["gas"] == "CH4"
    assert feat["properties"]["class"] == "CH4_only"  # alias preserved
    # geometry не должна быть в properties
    assert "geometry" not in feat["properties"]


def test_to_geojson_feature_falls_back_to_point(minimal_reference_event: dict) -> None:
    """Если geometry None — используется Point из (lon, lat)."""
    event = from_dict(minimal_reference_event)
    feat = to_geojson_feature(event)
    assert feat["geometry"]["type"] == "Point"
    assert feat["geometry"]["coordinates"] == [73.05, 70.01]


# --------------------------------------------------------------------------- #
# Bulk validation                                                             #
# --------------------------------------------------------------------------- #


def test_validate_batch_separates_valid_and_invalid(
    minimal_reference_event: dict,
    full_ours_event: dict,
) -> None:
    invalid_a = dict(minimal_reference_event)
    invalid_a["gas"] = "CO2"
    invalid_b = dict(minimal_reference_event)
    invalid_b["lat"] = 95.0

    batch = [
        minimal_reference_event,
        invalid_a,
        full_ours_event,
        invalid_b,
    ]
    valid, invalid = validate_batch(batch)
    assert len(valid) == 2
    assert len(invalid) == 2
    invalid_indices = [idx for idx, _ in invalid]
    assert invalid_indices == [1, 3]


# --------------------------------------------------------------------------- #
# Sanity / constants                                                          #
# --------------------------------------------------------------------------- #


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_gas_types_complete() -> None:
    assert set(GAS_TYPES) == {"CH4", "NO2", "SO2"}


def test_event_classes_match_dna() -> None:
    """DNA §1.3 классы — присутствуют все."""
    expected_dna_classes = {
        "CH4_only",
        "NO2_only",
        "SO2_only",
        "CH4_NO2",
        "NO2_SO2",
        "CH4_NO2_SO2",
        "diffuse_CH4",
        "wind_ambiguous",
    }
    assert expected_dna_classes.issubset(set(EVENT_CLASSES))


def test_extra_fields_forbidden(minimal_reference_event: dict) -> None:
    """`extra="forbid"` — попытка передать неизвестное поле должна падать."""
    minimal_reference_event["unknown_field"] = "boom"
    with pytest.raises(PydanticValidationError):
        from_dict(minimal_reference_event)


def test_agreement_score_consistency_check() -> None:
    """
    agreement_score должен быть согласован с matched_* booleans, если они
    выставлены явно.
    """
    base = {
        "event_id": "x",
        "source_catalog": "schuit2023",
        "source_event_id": "y",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 25),
        "gas": "CH4",
        "date_utc": date(2021, 1, 1),
        "lon": 70.0,
        "lat": 60.0,
        "matched_schuit2023": True,
        "matched_imeo_mars": True,
        "matched_cams": False,
        "agreement_score": 5,  # неверно: должно быть 2
    }
    with pytest.raises(PydanticValidationError) as exc_info:
        from_dict(base)
    assert "agreement_score" in str(exc_info.value)


def test_agreement_score_correct_passes() -> None:
    base = {
        "event_id": "x",
        "source_catalog": "schuit2023",
        "source_event_id": "y",
        "schema_version": SCHEMA_VERSION,
        "ingestion_date": date(2026, 4, 25),
        "gas": "CH4",
        "date_utc": date(2021, 1, 1),
        "lon": 70.0,
        "lat": 60.0,
        "matched_schuit2023": True,
        "matched_imeo_mars": False,
        "matched_cams": True,
        "agreement_score": 2,
    }
    event = from_dict(base)
    assert event.agreement_score == 2


def test_source_catalogs_includes_required() -> None:
    """Базовые reference catalogs должны быть в списке."""
    required = {"ours", "schuit2023", "imeo_mars", "cams_hotspot"}
    assert required.issubset(set(SOURCE_CATALOGS))
