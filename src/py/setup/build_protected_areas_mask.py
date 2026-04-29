"""
Build RuPlumeScan/reference/protected_areas FeatureCollection и
RuPlumeScan/reference/protected_areas_mask Image из manual GeoJSON
файлов в `data/protected_areas/`.

Реализует Часть 2 (Protected Areas reference mask) из P-00.1 v2 (CHANGE-0017).
Сопровождающие документы:
  * DNA.md v2.2 §1.2 (Reference Clean Zone), §1.5 (positive baseline distinction),
    §2.1 запрет 16 (Алтайский без QA test).
  * Algorithm.md v2.3 §11 (Reference Baseline Builder), §11.4 (Алтайский QA test).
  * RNA.md v1.2 §11.3 (Python implementation шаблон, ZONE_METADATA dict).

Ожидаемый запуск (после P-00.1 ingestion approval)::

    cd src/py
    python -m setup.build_protected_areas_mask validate     # local sanity check
    python -m setup.build_protected_areas_mask upload       # FeatureCollection upload
    python -m setup.build_protected_areas_mask mask         # protected_areas_mask Image

`validate` запускается без Earth Engine — только локально проверяет полигоны и
выдаёт area_km2_measured per zone (через pyproj geodesic area). Используется как
gate перед `upload`: если |measured-documented|/documented > 0.10 — print warning
и предложить пользователю принять решение.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Earth Engine импортируется лениво (внутри upload/mask), чтобы validate работал
# без EE auth.

PROJECT_ID = "nodal-thunder-481307-u1"
ASSET_FC_ID = f"projects/{PROJECT_ID}/assets/RuPlumeScan/reference/protected_areas"
ASSET_MASK_ID = f"projects/{PROJECT_ID}/assets/RuPlumeScan/reference/protected_areas_mask"

# Папка с GeoJSON файлами (project_root/data/protected_areas)
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "protected_areas"

# AOI bbox для raster mask (Western Siberia + Кузбасс + Алтай) — совпадает
# с industrial mask AOI plus extension на юг до 50°N для Алтайского.
# lon_min, lat_min, lon_max, lat_max
MASK_AOI_BBOX = (60.0, 50.0, 95.0, 75.0)

# Acceptable tolerance для local area validation (R2 от researcher).
# < 5%: OK, log only
# 5-10%: warning
# > 10%: escalate (script exits with non-zero)
AREA_TOLERANCE_OK = 0.05
AREA_TOLERANCE_WARNING = 0.10

# Метаданные зон. Hardcoded set per RNA v1.2 §11.3, источник — DNA v2.2 §1.2.
# Изменения этого dict требуют мутации DNA per DNA §2.3.
ZONE_METADATA: dict[str, dict[str, Any]] = {
    "yugansky": {
        "zone_id": "yugansky",
        "zone_name_ru": "Юганский заповедник",
        "zone_name_en": "Yugansky Strict Nature Reserve",
        "internal_buffer_km": 10,
        "centroid_lat": 60.5,
        "centroid_lon": 74.5,
        "area_km2_total": 6500,
        "natural_zone": "middle_taiga_with_wetlands",
        "latitude_band_min": 58.0,
        "latitude_band_max": 65.0,
        "quality_status": "active",
        "established_year": 1982,
        "iucn_category": "Ia",
        "official_url": "http://ugansky.ru",
    },
    "verkhnetazovsky": {
        "zone_id": "verkhnetazovsky",
        "zone_name_ru": "Верхне-Тазовский заповедник",
        "zone_name_en": "Verkhne-Tazovsky Strict Nature Reserve",
        "internal_buffer_km": 5,
        "centroid_lat": 63.5,
        "centroid_lon": 84.0,
        "area_km2_total": 6313,
        "natural_zone": "northern_taiga_permafrost",
        "latitude_band_min": 62.0,
        "latitude_band_max": 68.0,
        "quality_status": "active",
        "established_year": 1986,
        "iucn_category": "Ia",
        "official_url": "https://oopt.info/index.php?oopt=125",
    },
    "kuznetsky_alatau": {
        "zone_id": "kuznetsky_alatau",
        "zone_name_ru": "Кузнецкий Алатау заповедник",
        "zone_name_en": "Kuznetsky Alatau Strict Nature Reserve",
        "internal_buffer_km": 5,
        "centroid_lat": 54.5,
        "centroid_lon": 88.0,
        "area_km2_total": 4019,
        "natural_zone": "mountain_taiga",
        "latitude_band_min": 53.0,
        "latitude_band_max": 57.0,
        "quality_status": "active",
        "established_year": 1989,
        "iucn_category": "Ia",
        "official_url": "http://www.kuz-alatau.ru",
    },
    "altaisky": {
        "zone_id": "altaisky",
        "zone_name_ru": "Алтайский заповедник",
        "zone_name_en": "Altaisky Strict Nature Reserve",
        "internal_buffer_km": 5,
        "centroid_lat": 51.5,
        "centroid_lon": 88.5,
        "area_km2_total": 8810,
        "natural_zone": "high_mountain_with_alpine",
        "latitude_band_min": 51.0,
        "latitude_band_max": 54.0,
        # Status set per Algorithm v2.3 §11.4 QA test result 2026-04-28.
        # Initial value был "optional_pending_quality"; QA test FAIL
        # (abs_diff_winter=34.86 ppb >30, cycle_diff=34.25 ppb >20)
        # — high-altitude biome above winter PBL inversion.
        # См. docs/p-01.0a_altaisky_qa_result.json + Algorithm.md §11.4.1
        # worked example. Per DNA §2.1 запрет 16 — Алтайский excluded
        # from production reference baseline.
        "quality_status": "unreliable_for_xch4_baseline",
        "established_year": 1932,
        "iucn_category": "Ia",
        "official_url": "https://www.altzapovednik.ru",
    },
}


def setup_logger() -> logging.Logger:
    """Создать unified logger (stdout). Reconfigure stdout в UTF-8 на Windows
    чтобы logged Unicode (русский, спец-символы) корректно печатались в cp1251 console.
    """
    # Best-effort: переключить stdout на UTF-8 (Python 3.7+ supports reconfigure).
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logger = logging.getLogger("build_protected_areas_mask")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def load_zone_geojson(zone_id: str) -> dict[str, Any]:
    """
    Прочитать GeoJSON FeatureCollection и вернуть единственную Feature
    с заполненной geometry. Бросает FileNotFoundError если файл отсутствует.
    """
    path = DATA_DIR / f"{zone_id}.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing zone polygon: {path}. "
            "См. P-00.1 §2.1 — нужен ручной GeoJSON для каждого заповедника."
        )

    with open(path, encoding="utf-8") as f:
        gj = json.load(f)

    # Normalize: если FeatureCollection — взять features[0]; если уже Feature — as is.
    if gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        if len(feats) != 1:
            raise ValueError(f"{zone_id}.geojson: expected exactly 1 feature, got {len(feats)}")
        feat = feats[0]
    elif gj.get("type") == "Feature":
        feat = gj
    else:
        raise ValueError(f"{zone_id}.geojson: top-level type must be Feature or FeatureCollection")

    geom = feat.get("geometry") or {}
    if geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{zone_id}.geojson: geometry must be Polygon or MultiPolygon")

    return feat


# ----- Local geodesic area validation (без Earth Engine) -----------------------


def _ring_area_geodesic_km2(ring: list[list[float]]) -> float:
    """
    Вычислить площадь линейного кольца (геодезическая, на сфере) в км².
    Используется L'Huilier-style spherical excess для каждого треугольника
    с центром (lon_mean, lat_mean).

    Простая, достаточная для валидации заповедников (~1% accuracy на размерах
    < 10000 км²). Для production EE area() — точнее.
    """
    if len(ring) < 4:
        return 0.0

    # Радиус Земли в км
    r = 6371.0088

    # Spherical excess через формулу Чемберлена-Дюкена (для closed planar ring
    # в радианах на сфере).
    # Метод: суммируем (lon[i+1] - lon[i]) * (2 + sin(lat[i]) + sin(lat[i+1]))
    # затем умножаем на R²/2.
    total = 0.0
    n = len(ring)
    for i in range(n - 1):
        lon1 = math.radians(ring[i][0])
        lat1 = math.radians(ring[i][1])
        lon2 = math.radians(ring[i + 1][0])
        lat2 = math.radians(ring[i + 1][1])
        total += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))

    return abs(total) * r * r / 2.0


def measure_geometry_km2(geom: dict[str, Any]) -> float:
    """Площадь Polygon/MultiPolygon (с дырками) в км² (геодезическая)."""
    total = 0.0
    if geom["type"] == "Polygon":
        rings = geom["coordinates"]
        if not rings:
            return 0.0
        total += _ring_area_geodesic_km2(rings[0])
        for hole in rings[1:]:
            total -= _ring_area_geodesic_km2(hole)
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            if not poly:
                continue
            total += _ring_area_geodesic_km2(poly[0])
            for hole in poly[1:]:
                total -= _ring_area_geodesic_km2(hole)
    return total


def validate_zones(logger: logging.Logger) -> int:
    """
    Локальный sanity check всех 4 zones без EE.
    Печатает таблицу documented vs measured area.
    Возвращает exit code: 0 если все < 10% diff, 1 иначе.
    """
    logger.info("=" * 70)
    logger.info("Local zone polygon validation (no Earth Engine required)")
    logger.info("=" * 70)
    logger.info(f"{'zone_id':20s}  {'doc km^2':>9s}  {'meas km^2':>9s}  {'diff %':>7s}  status")
    logger.info("-" * 70)

    worst_diff = 0.0
    failures = 0

    for zone_id, meta in ZONE_METADATA.items():
        try:
            feat = load_zone_geojson(zone_id)
        except (FileNotFoundError, ValueError) as exc:
            logger.error(f"{zone_id:20s}  ERROR: {exc}")
            failures += 1
            continue

        documented = float(meta["area_km2_total"])
        measured = measure_geometry_km2(feat["geometry"])
        diff_pct = abs(measured - documented) / documented * 100.0
        worst_diff = max(worst_diff, diff_pct)

        if diff_pct < AREA_TOLERANCE_OK * 100:
            status = "OK"
        elif diff_pct < AREA_TOLERANCE_WARNING * 100:
            status = "WARN"
        else:
            status = "ESCALATE"
            failures += 1

        logger.info(
            f"{zone_id:20s}  {documented:9.0f}  {measured:9.0f}  " f"{diff_pct:+6.1f}%  {status}"
        )

    logger.info("-" * 70)
    logger.info(f"Worst diff: {worst_diff:.1f}%")

    if failures > 0:
        logger.error(
            "Validation FAILED: %d zones with diff > %.0f%%. "
            "Не загружай в GEE без human review. См. P-00.1 §2.1.",
            failures,
            AREA_TOLERANCE_WARNING * 100,
        )
        return 1

    logger.info("Validation PASSED: все zones в пределах tolerance.")
    return 0


# ----- Earth Engine upload pipeline --------------------------------------------


def _geom_to_ee(geom: dict[str, Any]):
    """
    Конвертировать GeoJSON Polygon/MultiPolygon dict в ee.Geometry.
    EE ожидает GeoJSON-подобный input.
    """
    import ee

    if geom["type"] == "Polygon":
        return ee.Geometry.Polygon(geom["coordinates"], None, False)
    if geom["type"] == "MultiPolygon":
        return ee.Geometry.MultiPolygon(geom["coordinates"], None, False)
    raise ValueError(f"Unsupported geometry type: {geom['type']}")


def build_features(logger: logging.Logger) -> list[Any]:
    """
    Загрузить 4 GeoJSON, объединить с ZONE_METADATA, вычислить
    area_km2_useable (после internal buffer), вернуть list[ee.Feature].
    """
    import ee

    today = str(date.today())
    features: list[Any] = []

    for zone_id, meta in ZONE_METADATA.items():
        feat_in = load_zone_geojson(zone_id)
        ee_geom = _geom_to_ee(feat_in["geometry"])

        # area_km2_measured из самого polygon (через EE) — точнее чем local геодезик
        try:
            measured_m2 = ee_geom.area(maxError=1.0).getInfo()
            area_km2_measured = float(measured_m2) / 1e6
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: ee.Geometry.area() failed (%s); falling back to local geodesic.",
                zone_id,
                exc,
            )
            area_km2_measured = measure_geometry_km2(feat_in["geometry"])

        # Useable area: после internal buffer (negative) и simplify-safe.
        # Pre-simplify polygon чтобы избежать invalid geometry на complex coastlines
        # (см. RNA §10.10).
        simplified = ee_geom.simplify(maxError=100)
        buffered = simplified.buffer(-meta["internal_buffer_km"] * 1000)
        try:
            useable_m2 = buffered.area(maxError=1.0).getInfo()
            area_km2_useable = float(useable_m2) / 1e6
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: useable area computation failed (%s); using 0.",
                zone_id,
                exc,
            )
            area_km2_useable = 0.0

        # Pull through provenance from GeoJSON Feature properties (data_license,
        # data_source_url, etc.) — если переопределены в GeoJSON, респектируем.
        in_props = feat_in.get("properties", {}) or {}

        out_props = {
            **meta,
            "area_km2_measured": round(area_km2_measured, 2),
            "area_km2_useable": round(area_km2_useable, 2),
            "data_license": in_props.get("data_license", "OSM-ODbL-1.0"),
            "data_source_url": in_props.get("data_source_url", ""),
            "data_attribution": in_props.get("data_attribution", "OpenStreetMap contributors"),
            "coordinates_source": in_props.get("coordinates_source", "OSM"),
            "coordinates_verified_date": in_props.get("coordinates_verified_date", today),
            "ingestion_date": today,
            "notes": in_props.get("notes", ""),
        }

        features.append(ee.Feature(ee_geom, out_props))
        logger.info(
            "%s: doc=%d km², measured=%.0f km², useable=%.0f km², status=%s",
            zone_id,
            meta["area_km2_total"],
            area_km2_measured,
            area_km2_useable,
            meta["quality_status"],
        )

    return features


def upload_protected_areas(logger: logging.Logger):
    """Запустить Export.table.toAsset для protected_areas FeatureCollection."""
    import ee

    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)

    features = build_features(logger)
    fc = ee.FeatureCollection(features)
    fc = fc.set(
        "title",
        "RU-PlumeScan reference protected_areas",
    ).set(
        "description",
        "Federal strict nature reserves used for positive-space reference baseline "
        "construction (DNA v2.2 §1.2). Hardcoded set: Юганский, Верхнетазовский, "
        "Кузнецкий Алатау, Алтайский. Алтайский имеет quality_status="
        "'optional_pending_quality' до Algorithm §11.4 QA test.",
    )

    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description="upload_protected_areas",
        assetId=ASSET_FC_ID,
    )
    task.start()
    logger.info("Upload task started: id=%s, status=%s", task.id, task.status())
    logger.info("Asset ID: %s", ASSET_FC_ID)
    logger.info("Monitor task в Code Editor 'Tasks' tab или через ee.batch.Task.list().")
    return task


def build_mask_raster(logger: logging.Logger):
    """
    Build protected_areas_mask Image (1 inside any zone after internal buffer,
    0 outside). Запускать ПОСЛЕ того как FeatureCollection asset готов.
    """
    import ee

    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)

    fc = ee.FeatureCollection(ASSET_FC_ID)

    # Применить per-zone internal buffer (как в reference_baseline.js)
    def _buffer_zone(feat: Any) -> Any:
        buffer_km = ee.Number(feat.get("internal_buffer_km"))
        simplified = feat.geometry().simplify(maxError=100)
        buffered = simplified.buffer(buffer_km.multiply(-1000))
        return ee.Feature(buffered, feat.toDictionary())

    buffered_fc = fc.map(_buffer_zone)

    aoi = ee.Geometry.Rectangle(list(MASK_AOI_BBOX))

    # Painted raster: 1 inside any buffered zone, 0 outside.
    base = ee.Image.constant(0).clip(aoi)
    mask_img = (
        base.paint(buffered_fc, 1)
        .rename("protected_mask")
        .toUint8()
        .reproject(crs="EPSG:4326", scale=7000)
    )

    task = ee.batch.Export.image.toAsset(
        image=mask_img,
        description="build_protected_areas_mask",
        assetId=ASSET_MASK_ID,
        region=aoi,
        scale=7000,
        maxPixels=int(1e10),
    )
    task.start()
    logger.info("Mask export task started: id=%s, status=%s", task.id, task.status())
    logger.info("Asset ID: %s", ASSET_MASK_ID)
    return task


def main(argv: list[str]) -> int:
    logger = setup_logger()

    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(
            "Usage: python -m setup.build_protected_areas_mask "
            "{validate|upload|mask}\n\n"
            "  validate  — local sanity check (no EE auth required)\n"
            "  upload    — Export.table.toAsset для protected_areas FC\n"
            "  mask      — Export.image.toAsset для protected_areas_mask\n"
        )
        return 0

    action = argv[1].lower()
    if action == "validate":
        return validate_zones(logger)
    if action == "upload":
        upload_protected_areas(logger)
        return 0
    if action == "mask":
        build_mask_raster(logger)
        return 0

    logger.error("Unknown action: %s. Use validate|upload|mask.", action)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
