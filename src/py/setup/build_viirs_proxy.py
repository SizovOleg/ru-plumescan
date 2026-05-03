"""
Build VIIRS night lights bright-pixel proxy for industrial sources.

Подход:
  1. Median composite NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG за 2022-01..2024-12.
  2. Threshold radiance >= TH (default 50 nW/cm²/sr) + filter human settlements
     через MODIS/061/MCD12Q1 (LC_Type1 != 13 = Urban and Built-up).
  3. Convert raster bright pixels to centroids (vectorize).
  4. Sanity check: Бованенково (70.40, 68.57) и Уренгой (66.05, 76.85) должны
     попадать в bright pixels.
  5. Generate calibration thumbnail URL для user approval.
  6. После approval: save vectorized centroids as
     `data/industrial_sources/viirs_bright_proxy.geojson`
     (потом подхватывается build_industrial_proxy.py).

Запуск (calibration mode — только thumbnail, не сохраняет GeoJSON)::

    cd src/py
    python -m setup.build_viirs_proxy --threshold 50 --calibrate

Запуск (production — после approval сохранит GeoJSON)::

    cd src/py
    python -m setup.build_viirs_proxy --threshold 50 --commit

См. DevPrompt P-00.1 v2 §1.3.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "industrial_sources"
OUTPUT_GEOJSON = DATA_DIR / "viirs_bright_proxy.geojson"

# AOI canonical (60, 50, 95, 75) per CLAIM 3 fix 2026-04-29 — aligned с
# downstream consumers (mask, baselines). См. OpenSpec MC-F.
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)

# Sanity check anchors (revised per researcher decision: Variant B, threshold=50).
# Все 4 facilities имеют active flaring expected >50 nW/cm²/sr median 2022-2024.
# Replaced earlier anchors (Бованенково/Самотлор) которые имеют APG utilization
# и низкий residual flaring — не подходят как positive controls для high-specificity
# bright detection. Самотлор отдельно добавлен в khmao_yamal_oil_gas.geojson
# manually — он industrial source без active flaring (oil field, APG utilized).
ANCHOR_POINTS = (
    ("sabetta_lng", 72.05, 71.27, "Ямал СПГ — Сабетта (very active flaring expected)"),
    ("severo_urengoy_gpz", 76.95, 66.45, "Северо-Уренгойский ГПЗ"),
    ("vankor", 83.56, 67.81, "Ванкорское — active flaring despite APG"),
    ("urengoy", 76.85, 66.05, "Уренгой — positive control (existing anchor)"),
)

# MODIS Land Cover IGBP class 13 = Urban and built-up
MODIS_LC = "MODIS/061/MCD12Q1"
URBAN_LC_VALUE = 13


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_viirs_proxy")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def build_viirs_composite(start: str = "2022-01-01", end: str = "2024-12-31") -> ee.Image:
    """Median composite VIIRS DNB monthly за период."""
    coll = (
        ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG")
        .filterDate(start, end)
        .select("avg_rad")
    )
    return coll.median().rename("avg_rad")


def build_urban_mask(year: int = 2022) -> ee.Image:
    """
    Маска urban pixels по MODIS Land Cover, расширенная focal_max 5 km для
    исключения city light glow вокруг settlements.
    """
    lc = (
        ee.ImageCollection(MODIS_LC)
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .first()
        .select("LC_Type1")
    )
    urban = lc.eq(URBAN_LC_VALUE)
    # Расширяем urban маску на 5 km buffer чтобы выкинуть city glow
    urban_buffer = urban.focal_max(radius=5000, units="meters")
    return urban_buffer


def build_bright_mask(threshold_nw: float, year_for_lc: int = 2022) -> ee.Image:
    """
    Bright industrial pixels: VIIRS radiance >= threshold AND not urban.
    Returns Image с band 'bright' (1 = bright industrial, 0/masked = иначе).
    """
    viirs = build_viirs_composite()
    urban = build_urban_mask(year_for_lc)
    bright = viirs.gte(threshold_nw).And(urban.Not()).rename("bright").selfMask()
    return bright.addBands(viirs)


def vectorize_bright_pixels(
    bright_with_rad: ee.Image, aoi: ee.Geometry, scale: int = 500
) -> ee.FeatureCollection:
    """
    Convert bright pixels к centroids (один Point per connected component).
    Уменьшаем scale до 500 m чтобы захватить small flares.
    """
    bright = bright_with_rad.select("bright").selfMask()
    rad = bright_with_rad.select("avg_rad")

    # Connected components labels
    objects = bright.connectedComponents(connectedness=ee.Kernel.plus(1), maxSize=128)

    # Reduce to vectors. Default reducer (countEvery) — нет doбавочных
    # data bands, только labels, и countEvery не требует payload band.
    vectors = objects.select("labels").reduceToVectors(
        geometry=aoi,
        scale=scale,
        geometryType="centroid",
        labelProperty="cluster_label",
        maxPixels=int(1e10),
        bestEffort=False,
    )

    # Sample radiance at each centroid
    def attach_radiance(feat: ee.Feature) -> ee.Feature:
        sampled = rad.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feat.geometry().buffer(500),
            scale=scale,
        )
        return feat.set("viirs_radiance_mean", sampled.get("avg_rad"))

    return vectors.map(attach_radiance)


def get_thumbnail_url(bright_with_rad: ee.Image, aoi: ee.Geometry) -> str:
    """Generate visualization thumbnail URL для visual calibration."""
    viirs = bright_with_rad.select("avg_rad")
    bright = bright_with_rad.select("bright").selfMask()

    background = viirs.visualize(min=0, max=30, palette=["black", "yellow"])
    overlay = bright.visualize(palette=["red"])
    composite = ee.ImageCollection([background, overlay]).mosaic()

    return composite.getThumbURL(
        {
            "region": aoi,
            "dimensions": 1024,
            "format": "png",
        }
    )


def sanity_check_anchors(
    bright_with_rad: ee.Image,
    threshold: float,
    logger: logging.Logger,
    year_for_lc: int = 2022,
) -> dict[str, list[dict]]:
    """
    Triage anchors в три диагностические категории (соответствует
    Algorithm v2.3 §3.4.3 epistemic discipline — отделяем diagnostic info
    от system error):

      * `pass` — anchor radiance >= threshold AND coord не в urban buffer.
      * `masked_by_filter` — anchor coord попадает в urban+5km buffer
        (MODIS LC filter работает корректно; anchor coord может быть
        revised в будущем). НЕ блокирует commit.
      * `below_threshold` — coord clean, но radiance < threshold.
        Это либо real low activity (e.g. APG utilization),
        либо threshold too high (real calibration concern).

    Возвращает dict с тремя списками (per-anchor dicts: name, rad, urban,
    desc).
    """
    urban_mask = build_urban_mask(year_for_lc)
    raw_viirs = bright_with_rad.select("avg_rad")

    results: dict[str, list[dict]] = {
        "pass": [],
        "masked_by_filter": [],
        "below_threshold": [],
    }

    for name, lon, lat, desc in ANCHOR_POINTS:
        pt = ee.Geometry.Point([lon, lat])
        # Sample raw VIIRS (без urban mask) на anchor coord, 2 km radius
        rad_value = (
            raw_viirs.reduceRegion(
                reducer=ee.Reducer.max(),
                geometry=pt.buffer(2000),
                scale=500,
            )
            .get("avg_rad")
            .getInfo()
        )
        rad_value = float(rad_value) if rad_value is not None else 0.0

        # Sample urban mask на anchor coord
        urban_value = (
            urban_mask.reduceRegion(
                reducer=ee.Reducer.max(),
                geometry=pt.buffer(2000),
                scale=500,
            )
            .get("LC_Type1")
            .getInfo()
        )
        is_urban = urban_value is not None and urban_value >= 1

        anchor_record = {
            "name": name,
            "lon": lon,
            "lat": lat,
            "desc": desc,
            "rad": rad_value,
            "urban_masked": is_urban,
        }

        if is_urban:
            category = "masked_by_filter"
            marker = "MASKED"
            note = "(urban+5km buffer hit; revise coord in future)"
        elif rad_value >= threshold:
            category = "pass"
            marker = "PASS"
            note = ""
        else:
            category = "below_threshold"
            marker = "BELOW"
            note = "(coord clean but radiance < threshold)"

        results[category].append(anchor_record)
        logger.info(
            "  [%-6s] %-22s rad=%7.2f urban=%s TH=%4.1f %s -- %s",
            marker,
            name,
            rad_value,
            "Y" if is_urban else "N",
            threshold,
            note,
            desc,
        )

    return results


def evaluate_calibration_status(results: dict[str, list[dict]]) -> str:
    """
    Per researcher refactor decision:

      * pass >= 3 AND below_threshold == 0 → CALIBRATION_VALID
      * pass >= 2 AND below_threshold <= 1 → CALIBRATION_VALID_WITH_NOTES
      * below_threshold >= 2 → CALIBRATION_THRESHOLD_TOO_HIGH
      * else → CALIBRATION_INCONCLUSIVE
    """
    n_pass = len(results["pass"])
    n_below = len(results["below_threshold"])

    if n_pass >= 3 and n_below == 0:
        return "CALIBRATION_VALID"
    if n_pass >= 2 and n_below <= 1:
        return "CALIBRATION_VALID_WITH_NOTES"
    if n_below >= 2:
        return "CALIBRATION_THRESHOLD_TOO_HIGH"
    return "CALIBRATION_INCONCLUSIVE"


def export_geojson(
    fc_info: dict,
    threshold: float,
    output_path: Path,
    logger: logging.Logger,
    calibration_status: str = "CALIBRATION_VALID",
    masked_anchors: list[dict] | None = None,
) -> int:
    """Save sampled FeatureCollection как GeoJSON file для consumption build_industrial_proxy."""
    today = str(date.today())
    features_out = []
    masked_anchors = masked_anchors or []
    for i, feat in enumerate(fc_info.get("features", [])):
        coords = feat.get("geometry", {}).get("coordinates")
        if not coords:
            continue
        rad = feat.get("properties", {}).get("viirs_radiance_mean")
        rad = float(rad) if rad is not None else None

        features_out.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coords},
                "properties": {
                    "source_id": f"viirs_{i:04d}",
                    "source_type": "oil_gas",
                    "source_subtype": "viirs_flare_proxy",
                    "country": "RU",
                    "viirs_radiance_mean": rad,
                    "verification_status": "viirs_proxy_unverified",
                    "coordinates_source": (
                        f"VIIRS-DNB-monthly-2022-2024-median-th{int(threshold)}"
                    ),
                    "coordinates_verified_date": today,
                    "data_license": "viirs_proxy_unverified",
                    "data_attribution": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                    "data_source_url": (
                        "https://developers.google.com/earth-engine/datasets/catalog/"
                        "NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG"
                    ),
                    "notes": "Auto-generated bright pixels (NOT urban). Unverified proxy.",
                },
            }
        )

    out = {
        "type": "FeatureCollection",
        "name": "viirs_bright_proxy",
        "description": (
            "VIIRS night lights bright pixels (median 2022-2024, threshold "
            f"{threshold} nW/cm²/sr, urban-masked via MODIS LC). "
            "Unverified proxy for gas flares / industrial activity outside "
            "manual coverage."
        ),
        "_metadata": {
            "ingestion_date": today,
            "threshold_nw_cm2_sr": threshold,
            "viirs_period": "2022-01-01 to 2024-12-31",
            "urban_filter": "MODIS/061/MCD12Q1 LC_Type1==13 + 5 km buffer",
            "license": "viirs_proxy_unverified (NOAA public domain underlying data)",
            "calibration_status": calibration_status,
            "calibration_diagnostic_notes": [
                f"{a['name']} @ ({a['lon']:.4f}, {a['lat']:.4f}) masked by urban "
                f"filter (rad={a['rad']:.2f}); anchor coord may need revision"
                for a in masked_anchors
            ],
        },
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features_out,
    }

    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d features to %s", len(features_out), output_path)
    return len(features_out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="VIIRS radiance threshold (nW/cm²/sr). Default 50.",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Calibration mode: только print thumbnail URL и sanity check anchors. "
        "Не сохраняет GeoJSON.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Production mode: после thumbnail + anchor check сохраняет GeoJSON.",
    )
    args = parser.parse_args()

    if not (args.calibrate or args.commit):
        print("Specify --calibrate (preview only) or --commit (save GeoJSON)")
        return 1

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized.")

    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    bright_with_rad = build_bright_mask(args.threshold)

    # Always: thumbnail + sanity check
    logger.info("Generating thumbnail (background = VIIRS radiance, red overlay = bright pixels)")
    url = get_thumbnail_url(bright_with_rad, aoi)
    logger.info("Thumbnail URL (open in browser, share with reviewer):\n  %s", url)

    # Save PNG locally для repo documentation per researcher's request
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    th_int = int(args.threshold)
    png_path = DATA_DIR / f"viirs_calibration_th{th_int}_{timestamp}.png"
    try:
        urllib.request.urlretrieve(url, png_path)  # noqa: S310 — GEE API URL
        logger.info("Saved local thumbnail: %s", png_path)
    except Exception as exc:
        logger.warning("Could not save local thumbnail (%s). URL still printed above.", exc)

    logger.info("Sanity check anchors at threshold=%s nW/cm²/sr:", args.threshold)
    anchor_results = sanity_check_anchors(bright_with_rad, args.threshold, logger)

    n_pass = len(anchor_results["pass"])
    n_below = len(anchor_results["below_threshold"])
    n_masked = len(anchor_results["masked_by_filter"])
    n_total = n_pass + n_below + n_masked
    status = evaluate_calibration_status(anchor_results)

    logger.info(
        "Anchor triage: pass=%d, below_threshold=%d, masked_by_filter=%d, total=%d",
        n_pass,
        n_below,
        n_masked,
        n_total,
    )
    logger.info("Calibration status: %s", status)

    if anchor_results["masked_by_filter"]:
        for a in anchor_results["masked_by_filter"]:
            logger.warning(
                "  NOTE %s @ (%.4f, %.4f) masked by urban filter — coord may need "
                "revision (ГПЗ может быть в pure non-urban location). Не блокирует commit.",
                a["name"],
                a["lon"],
                a["lat"],
            )

    if args.calibrate:
        logger.info("Calibration mode — done. Status: %s. Если VALID — re-run --commit.", status)
        return 0

    # commit mode: разрешено только VALID или VALID_WITH_NOTES
    if status not in ("CALIBRATION_VALID", "CALIBRATION_VALID_WITH_NOTES"):
        logger.error(
            "Calibration status %s — refusing to commit at threshold %.1f. "
            "Investigate (may need lower threshold или revised anchors).",
            status,
            args.threshold,
        )
        return 2

    logger.info("Vectorizing bright pixels...")
    fc = vectorize_bright_pixels(bright_with_rad, aoi)
    fc_size = fc.size().getInfo()
    logger.info("Bright clusters detected: %d", fc_size)

    if fc_size == 0:
        logger.error("No bright clusters detected. Threshold may be too high.")
        return 3

    if fc_size > 5000:
        logger.error(
            "Too many clusters (%d). Threshold likely too low — would dominate dataset. "
            "Increase threshold and re-calibrate.",
            fc_size,
        )
        return 4

    logger.info("Fetching FeatureCollection info (this may take a minute)...")
    fc_info = fc.getInfo()
    n_saved = export_geojson(
        fc_info,
        args.threshold,
        OUTPUT_GEOJSON,
        logger,
        calibration_status=status,
        masked_anchors=anchor_results["masked_by_filter"],
    )
    logger.info("Done. %d VIIRS proxy features saved.", n_saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
