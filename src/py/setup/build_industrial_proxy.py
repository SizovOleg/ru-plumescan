"""
Build RuPlumeScan/industrial/source_points FeatureCollection.

Source aggregation:
  1. Manual GeoJSONs из data/industrial_sources/*.geojson
     (kuzbass_mines, khmao_yamal_oil_gas, norilsk_complex,
     additional_western_siberia, viirs_bright_proxy)
  2. GPPD (Global Power Plant Database, WRI) subset:
     country=Russia, bounds=AOI [60, 55, 90, 75].

Все источники нормализуются в общую schema (см. SCHEMA_FIELDS ниже)
и собираются в один FeatureCollection.

Запуск::

    cd src/py
    python -m setup.build_industrial_proxy

Требования:
  * Manual GeoJSON files существуют в `data/industrial_sources/`.
  * `viirs_bright_proxy.geojson` опционально (создаётся отдельно через
    `build_viirs_proxy.py`).
  * Earth Engine аутентифицирован.

См. RNA.md §3.1 (Asset structure), DevPrompt P-00.1 v2 §1.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
ASSET_ID = f"projects/{PROJECT_ID}/assets/RuPlumeScan/industrial/source_points"

# AOI bbox: lon_min, lat_min, lon_max, lat_max (Western Siberia, canonical
# per CLAIM 3 fix 2026-04-29). Earlier narrower (60-55-90-75) excluded 18
# GPPD plants including 4 critical Kuzbass TPPs (Tom-Usinsk GRES, etc.) и
# Krasnoyarsk-region cluster в 90-95°E. Aligned с baseline / mask scripts
# для consistency. См. OpenSpec MC-F.
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)

# GeoJSON inputs
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "industrial_sources"
MANUAL_FILES = (
    "kuzbass_mines.geojson",
    "khmao_yamal_oil_gas.geojson",
    "norilsk_complex.geojson",
    "additional_western_siberia.geojson",
    "viirs_bright_proxy.geojson",  # опциональный, создаётся отдельным скриптом
)

# Поля Common Industrial Schema. Не Pydantic-модель (per R3.5),
# но фиксированный список валидных колонок для нормализации.
SCHEMA_FIELDS = (
    "source_id",
    "source_type",
    "source_subtype",
    "source_name",
    "source_name_en",
    "country",
    "region",
    "operator",
    "fuel_primary",
    "capacity_mw",
    "estimated_kt_per_year_ch4",
    "estimated_kt_per_year_so2",
    "estimated_kt_per_year_so2_uncertainty",
    "estimate_year",
    "estimate_source",
    "decommissioned",
    "decommissioning_year",
    "verification_status",
    "viirs_radiance_mean",
    "coordinates_source",
    "coordinates_verified_date",
    "data_license",
    "data_attribution",
    "data_source_url",
    "source_dataset",
    "ingestion_date",
    "notes",
)

VALID_SOURCE_TYPES = {"coal_mine", "oil_gas", "power_plant", "metallurgy", "other"}


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_industrial_proxy")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def normalize_properties(
    raw: dict[str, Any], source_dataset: str, ingestion_date: str
) -> dict[str, Any]:
    """
    Привести `raw` properties (из GeoJSON Feature) к Common Industrial Schema.
    Заполняет defaults, валидирует enum source_type, отбрасывает unknown поля.
    """
    out: dict[str, Any] = {f: None for f in SCHEMA_FIELDS}

    for k, v in raw.items():
        if k.startswith("_"):  # внутренние/metadata поля игнорируем
            continue
        if k in SCHEMA_FIELDS:
            out[k] = v

    # Required enum check
    if out.get("source_type") not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"Invalid source_type={out.get('source_type')!r} for "
            f"source_id={out.get('source_id')!r} in {source_dataset}"
        )

    # Defaults
    if out["source_dataset"] is None:
        out["source_dataset"] = source_dataset
    if out["ingestion_date"] is None:
        out["ingestion_date"] = ingestion_date
    if out["decommissioned"] is None:
        out["decommissioned"] = False
    if out["country"] is None:
        out["country"] = "RU"

    return out


def load_manual_geojsons(logger: logging.Logger) -> list[ee.Feature]:
    """Прочитать manual GeoJSON files, нормализовать, вернуть список ee.Feature."""
    today = str(date.today())
    features: list[ee.Feature] = []

    for fname in MANUAL_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            logger.warning("Skipping (not found): %s", path.name)
            continue

        with open(path, encoding="utf-8") as f:
            geojson = json.load(f)

        dataset = path.stem
        n_in = 0
        for feat in geojson.get("features", []):
            geom = feat.get("geometry")
            if not geom or geom.get("type") != "Point":
                logger.warning("Skipping non-Point feature in %s", fname)
                continue
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
            props = normalize_properties(feat.get("properties", {}), dataset, today)
            ee_feat = ee.Feature(ee.Geometry.Point([lon, lat]), props)
            features.append(ee_feat)
            n_in += 1
        logger.info("Loaded %3d features from %s", n_in, fname)

    return features


def load_gppd_subset(logger: logging.Logger) -> list[ee.Feature]:
    """
    Подгрузить GPPD Russia subset в AOI bbox.
    Конвертировать каждое Feature в Common Industrial Schema.
    """
    today = str(date.today())
    aoi_geom = ee.Geometry.Rectangle(list(AOI_BBOX))

    # GPPD WRI uses 3-letter ISO country code field 'country', not 'country_long'.
    # Long name field is 'country_lg'. Fuel field is 'fuel1'. Capacity = 'capacitymw'.
    gppd = (
        ee.FeatureCollection("WRI/GPPD/power_plants")
        .filter(ee.Filter.eq("country", "RUS"))
        .filterBounds(aoi_geom)
    )

    raw_count = gppd.size().getInfo()
    logger.info("GPPD: %d Russian plants in AOI bbox", raw_count)

    if raw_count == 0:
        logger.warning("GPPD subset empty (likely AOI / country code mismatch)")
        return []

    raw_list = gppd.toList(raw_count).getInfo()
    features: list[ee.Feature] = []

    for item in raw_list:
        props = item.get("properties", {})
        coords = item.get("geometry", {}).get("coordinates")
        if not coords:
            continue
        lon, lat = float(coords[0]), float(coords[1])

        gppd_id = props.get("gppd_idnr") or props.get("name") or "unknown"
        capacity = props.get("capacitymw")
        if isinstance(capacity, str):
            try:
                capacity = float(capacity)
            except ValueError:
                capacity = None

        primary_fuel = props.get("fuel1") or None
        normalized = normalize_properties(
            {
                "source_id": f"gppd_{gppd_id}",
                "source_type": "power_plant",
                "source_subtype": (primary_fuel.lower() if primary_fuel else None),
                "source_name": props.get("name"),
                "source_name_en": props.get("name"),
                "country": "RU",
                "region": None,
                "operator": props.get("owner"),
                "fuel_primary": primary_fuel,
                "capacity_mw": capacity,
                "verification_status": "gppd_official",
                "coordinates_source": "GPPD",
                "data_license": "GPPD-CCBY-4.0",
                "data_attribution": "Global Power Plant Database (WRI)",
                "data_source_url": "https://datasets.wri.org/dataset/globalpowerplantdatabase",
                "notes": "From WRI/GPPD/power_plants Earth Engine collection.",
            },
            "gppd_zapsib_subset",
            today,
        )
        features.append(ee.Feature(ee.Geometry.Point([lon, lat]), normalized))

    logger.info("GPPD subset: %d features ingested into Common Industrial Schema", len(features))
    return features


def upload_collection(
    features: list[ee.Feature], asset_id: str, logger: logging.Logger
) -> ee.batch.Task:
    """Создать FeatureCollection и запустить Export.table.toAsset task."""
    fc = ee.FeatureCollection(features)
    fc = fc.set(
        "title",
        "RU-PlumeScan industrial source_points",
    ).set(
        "description",
        "Manual + GPPD + VIIRS-proxy industrial sources for Western Siberia AOI. "
        "Schema: SCHEMA_FIELDS in build_industrial_proxy.py. "
        "Per-feature data_license: researcher_contributed_public_domain | OSM-ODbL-1.0 | "
        "GPPD-CCBY-4.0 | viirs_proxy_unverified.",
    )

    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description="industrial_source_points",
        assetId=asset_id,
    )
    task.start()
    logger.info("Upload task started: id=%s, status=%s", task.id, task.status())
    return task


def main() -> int:
    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)

    manual = load_manual_geojsons(logger)
    gppd = load_gppd_subset(logger)
    all_features = manual + gppd

    if not all_features:
        logger.error("No features collected. Aborting.")
        return 1

    logger.info(
        "Total: %d features (manual=%d, gppd=%d). Uploading to %s",
        len(all_features),
        len(manual),
        len(gppd),
        ASSET_ID,
    )
    upload_collection(all_features, ASSET_ID, logger)
    logger.info(
        "Done. Monitor task в Code Editor 'Tasks' tab или через "
        "ee.batch.Task.list(). Asset ID: %s",
        ASSET_ID,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
