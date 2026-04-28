"""
Алтайский заповедник QA test (Algorithm v2.3 §11.4).

Per DNA v2.2 §2.1 запрет 16 — Алтайский имеет initial quality_status=
"optional_pending_quality" и НЕ может использоваться в production reference
baseline до прохождения этого QA test.

Test logic (Algorithm §11.4):
  Сравнить mean XCH4 inside Алтайский vs Кузнецкий Алатау после seasonal
  correction. Both at similar latitudes (51°N vs 54°N), similar seasonal
  forcing — divergence > 30 ppb signals retrieval issue в high-mountain
  Алтайском biome.

  PASS criteria (ALL must hold):
    abs_diff_summer < 30 ppb
    abs_diff_winter < 30 ppb
    cycle_diff < 20 ppb

  PASS → Алтайский.quality_status = "active" (proceed to v2 baseline build)
  FAIL → Алтайский.quality_status = "unreliable_for_xch4_baseline" (stay в v1)

Result сохраняется как Feature в:
  RuPlumeScan/validation/altaisky_qa/test_<YYYYMMDD>

Запуск::

    cd src/py
    python -m setup.altaisky_qa_test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
PROTECTED_AREAS_ASSET = f"projects/{PROJECT_ID}/assets/RuPlumeScan/reference/protected_areas"
QA_RESULT_ASSET_TEMPLATE = (
    f"projects/{PROJECT_ID}/assets/RuPlumeScan/validation/altaisky_qa/test_{{date}}"
)

CH4_COLLECTION = "COPERNICUS/S5P/OFFL/L3_CH4"
CH4_BAND = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"

# History window для test
YEAR_MIN = 2019
YEAR_MAX = 2025

# Pass criteria (Algorithm §11.4)
ABS_DIFF_TOLERANCE_PPB = 30.0
CYCLE_DIFF_TOLERANCE_PPB = 20.0

# Per OpenSpec MC-2026-04-28-B — pacing для GEE memory throttling
PACING_SEC = 30


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("altaisky_qa_test")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def load_zone_buffered(zone_id: str) -> ee.Geometry:
    """Загрузить zone polygon, применить per-zone internal buffer."""
    fc = ee.FeatureCollection(PROTECTED_AREAS_ASSET)
    zone_fc = fc.filter(ee.Filter.eq("zone_id", zone_id))
    n = zone_fc.size().getInfo()
    if n != 1:
        raise RuntimeError(f"Expected single zone for {zone_id}, got {n}")
    zone = zone_fc.first()
    buffer_km = ee.Number(zone.get("internal_buffer_km"))
    simplified = zone.geometry().simplify(maxError=100)
    return simplified.buffer(buffer_km.multiply(-1000))


def compute_seasonal_mean(zone_geom: ee.Geometry, months: list[int]) -> float:
    """
    Mean XCH4 (zone-aggregate) для указанных months и years YEAR_MIN-YEAR_MAX.

    Returns ppb scalar или float('nan') если no observations.
    """
    coll = (
        ee.ImageCollection(CH4_COLLECTION)
        .select(CH4_BAND)
        .filter(ee.Filter.calendarRange(YEAR_MIN, YEAR_MAX, "year"))
        .filter(ee.Filter.calendarRange(months[0], months[-1], "month"))
        .map(lambda img: img.clip(zone_geom))
    )
    median_image = coll.reduce(ee.Reducer.median())
    value = (
        median_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone_geom,
            scale=7000,
            maxPixels=int(1e8),
        )
        .values()
        .get(0)
        .getInfo()
    )
    return float(value) if value is not None else float("nan")


def run_qa_test(logger: logging.Logger) -> dict:
    """
    Главный QA test pipeline. Возвращает dict с full metrics + verdict.
    """
    import time

    logger.info("Loading zones (Алтайский, Кузнецкий Алатау) с internal buffers")
    altaisky_geom = load_zone_buffered("altaisky")
    kuz_geom = load_zone_buffered("kuznetsky_alatau")

    logger.info("Computing seasonal means для %d-%d", YEAR_MIN, YEAR_MAX)

    logger.info("  Алтайский summer (Jun-Aug)...")
    alt_summer = compute_seasonal_mean(altaisky_geom, [6, 8])
    time.sleep(PACING_SEC)

    logger.info("  Алтайский winter (Dec-Feb)...")
    # Dec-Feb wraps year boundary — calendarRange(12, 2) даст empty.
    # Используем filter via month list.
    alt_winter = (
        compute_seasonal_mean(altaisky_geom, [12, 12]) if False else _compute_winter(altaisky_geom)
    )
    time.sleep(PACING_SEC)

    logger.info("  Кузнецкий Алатау summer (Jun-Aug)...")
    kuz_summer = compute_seasonal_mean(kuz_geom, [6, 8])
    time.sleep(PACING_SEC)

    logger.info("  Кузнецкий Алатау winter (Dec-Feb)...")
    kuz_winter = _compute_winter(kuz_geom)

    # Compute test metrics
    abs_diff_summer = (
        abs(alt_summer - kuz_summer)
        if not (alt_summer != alt_summer or kuz_summer != kuz_summer)
        else float("nan")
    )
    abs_diff_winter = (
        abs(alt_winter - kuz_winter)
        if not (alt_winter != alt_winter or kuz_winter != kuz_winter)
        else float("nan")
    )
    seasonal_diff_alt = alt_summer - alt_winter
    seasonal_diff_kuz = kuz_summer - kuz_winter
    cycle_diff = (
        abs(seasonal_diff_alt - seasonal_diff_kuz)
        if not (seasonal_diff_alt != seasonal_diff_alt or seasonal_diff_kuz != seasonal_diff_kuz)
        else float("nan")
    )

    logger.info("Results:")
    logger.info("  alt_summer  = %.2f ppb", alt_summer)
    logger.info("  kuz_summer  = %.2f ppb", kuz_summer)
    logger.info("  abs_diff_summer = %.2f ppb (tol %.1f)", abs_diff_summer, ABS_DIFF_TOLERANCE_PPB)
    logger.info("  alt_winter  = %.2f ppb", alt_winter)
    logger.info("  kuz_winter  = %.2f ppb", kuz_winter)
    logger.info("  abs_diff_winter = %.2f ppb (tol %.1f)", abs_diff_winter, ABS_DIFF_TOLERANCE_PPB)
    logger.info("  seasonal_diff_alt = %.2f ppb", seasonal_diff_alt)
    logger.info("  seasonal_diff_kuz = %.2f ppb", seasonal_diff_kuz)
    logger.info("  cycle_diff = %.2f ppb (tol %.1f)", cycle_diff, CYCLE_DIFF_TOLERANCE_PPB)

    # Verdict
    pass_summer = abs_diff_summer < ABS_DIFF_TOLERANCE_PPB
    pass_winter = abs_diff_winter < ABS_DIFF_TOLERANCE_PPB
    pass_cycle = cycle_diff < CYCLE_DIFF_TOLERANCE_PPB
    overall_pass = pass_summer and pass_winter and pass_cycle

    verdict = "active" if overall_pass else "unreliable_for_xch4_baseline"
    logger.info("=" * 60)
    logger.info("QA verdict: %s", verdict.upper())
    logger.info(
        "  pass_summer=%s pass_winter=%s pass_cycle=%s", pass_summer, pass_winter, pass_cycle
    )
    logger.info("=" * 60)

    return {
        "test_date": str(date.today()),
        "zone_under_test": "altaisky",
        "reference_zone": "kuznetsky_alatau",
        "history_year_min": YEAR_MIN,
        "history_year_max": YEAR_MAX,
        "alt_summer_ppb": alt_summer,
        "alt_winter_ppb": alt_winter,
        "kuz_summer_ppb": kuz_summer,
        "kuz_winter_ppb": kuz_winter,
        "abs_diff_summer_ppb": abs_diff_summer,
        "abs_diff_winter_ppb": abs_diff_winter,
        "seasonal_diff_altaisky_ppb": seasonal_diff_alt,
        "seasonal_diff_kuznetsky_alatau_ppb": seasonal_diff_kuz,
        "cycle_diff_ppb": cycle_diff,
        "tolerance_abs_diff_ppb": ABS_DIFF_TOLERANCE_PPB,
        "tolerance_cycle_diff_ppb": CYCLE_DIFF_TOLERANCE_PPB,
        "pass_summer": pass_summer,
        "pass_winter": pass_winter,
        "pass_cycle": pass_cycle,
        "overall_pass": overall_pass,
        "verdict_quality_status": verdict,
        "algorithm_version": "2.3",
        "rna_version": "1.2",
        "test_pipeline": "src/py/setup/altaisky_qa_test.py",
    }


def _compute_winter(zone_geom: ee.Geometry) -> float:
    """
    Winter mean — months Dec, Jan, Feb. Dec-Feb wraps year boundary, поэтому
    `calendarRange(12, 2, 'month')` даёт empty result. Используем
    `ee.Filter.Or(calendarRange(12, 12), calendarRange(1, 2))` чтобы
    применить filter правильно к `system:time_start` через temporal range.
    """
    winter_filter = ee.Filter.Or(
        ee.Filter.calendarRange(12, 12, "month"),
        ee.Filter.calendarRange(1, 2, "month"),
    )
    coll = (
        ee.ImageCollection(CH4_COLLECTION)
        .select(CH4_BAND)
        .filter(ee.Filter.calendarRange(YEAR_MIN, YEAR_MAX, "year"))
        .filter(winter_filter)
        .map(lambda img: img.clip(zone_geom))
    )
    median_image = coll.reduce(ee.Reducer.median())
    value = (
        median_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone_geom,
            scale=7000,
            maxPixels=int(1e8),
        )
        .values()
        .get(0)
        .getInfo()
    )
    return float(value) if value is not None else float("nan")


def upload_qa_result(result: dict, logger: logging.Logger) -> ee.batch.Task:
    """Upload result Feature в RuPlumeScan/validation/altaisky_qa/test_<date>."""
    asset_id = QA_RESULT_ASSET_TEMPLATE.format(date=result["test_date"].replace("-", ""))

    # Result Feature — geometryless point at Altaisky centroid (для GEE table format)
    feat = ee.Feature(ee.Geometry.Point([88.5, 51.5]), result)
    fc = ee.FeatureCollection([feat])

    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description=f"altaisky_qa_test_{result['test_date']}",
        assetId=asset_id,
    )
    task.start()
    logger.info("QA result Asset upload task: id=%s, asset=%s", task.id, asset_id)
    return task


def update_protected_areas_status(verdict_status: str, logger: logging.Logger) -> None:
    """
    Update Алтайский quality_status в protected_areas FeatureCollection.

    GEE не поддерживает per-feature property update без full re-export, поэтому
    мы скачиваем FC, обновляем нужное Feature, re-uploads (overwrites Asset).
    """
    logger.info("Updating Алтайский quality_status in protected_areas FC: %s", verdict_status)

    fc = ee.FeatureCollection(PROTECTED_AREAS_ASSET)
    info = fc.getInfo()

    updated_features = []
    for feat in info["features"]:
        props = dict(feat["properties"])
        if props.get("zone_id") == "altaisky":
            old_status = props.get("quality_status")
            props["quality_status"] = verdict_status
            props["altaisky_qa_test_date"] = str(date.today())
            logger.info("  Алтайский: %s -> %s", old_status, verdict_status)
        geom = ee.Geometry(feat["geometry"])
        updated_features.append(ee.Feature(geom, props))

    new_fc = ee.FeatureCollection(updated_features)

    # Delete old asset first (overwrite не allowed для table)
    try:
        ee.data.deleteAsset(PROTECTED_AREAS_ASSET)
        logger.info("Old protected_areas Asset deleted (will re-upload)")
    except ee.EEException as exc:
        logger.warning("deleteAsset returned: %s", exc)

    task = ee.batch.Export.table.toAsset(
        collection=new_fc,
        description="reupload_protected_areas_after_qa",
        assetId=PROTECTED_AREAS_ASSET,
    )
    task.start()
    logger.info("Re-upload task: id=%s", task.id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-update-fc",
        action="store_true",
        help="Не trigger re-upload protected_areas FC (только save QA result).",
    )
    parser.add_argument(
        "--save-json",
        type=str,
        default=None,
        help="Local path для save QA result JSON. По умолчанию — "
        "<project_root>/docs/p-01.0a_altaisky_qa_result.json (cwd-independent).",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)

    result = run_qa_test(logger)

    # Save local JSON (cwd-independent default — anchor to repo root)
    from pathlib import Path

    if args.save_json:
        json_path = Path(args.save_json)
    else:
        repo_root = Path(__file__).resolve().parents[3]
        json_path = repo_root / "docs" / "p-01.0a_altaisky_qa_result.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("QA result saved locally: %s", json_path)

    # Upload result Asset
    upload_qa_result(result, logger)

    # Update protected_areas FC если QA pass или fail (always update — записываем
    # status либо active либо unreliable_for_xch4_baseline)
    if not args.no_update_fc:
        update_protected_areas_status(result["verdict_quality_status"], logger)
    else:
        logger.info("--no-update-fc: skipping protected_areas re-upload")

    return 0 if result["overall_pass"] else 0  # both PASS and FAIL — exit 0 (FAIL не error)


if __name__ == "__main__":
    sys.exit(main())
