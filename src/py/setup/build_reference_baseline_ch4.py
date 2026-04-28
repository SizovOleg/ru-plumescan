"""
Build RuPlumeScan/baselines/reference_CH4_<period> Image из reference zones.

Python-equivalent JS-модуля `src/js/modules/reference_baseline.js` (RNA v1.2 §11.2).
Те же ee API operations — для batch execution в P-01.0a без ручного запуска
в GEE Code Editor.

Реализует Algorithm v2.3 §11 (Reference Baseline Builder):
  1. Load reference zones (filtered by quality_status="active").
  2. Apply per-zone internal buffer (negative buffer + simplify).
  3. Build per-zone climatology values (median + MAD-sigma + count) для всех
     12 target_month.
  4. Latitude-stratify в один Image с per-month bands.
  5. Export как Asset.

Запуск::

    cd src/py
    # initial v1 (3 active zones, без Алтайского):
    python -m setup.build_reference_baseline_ch4 --target-year 2025 --version v1

    # v2 после Алтайский QA pass:
    python -m setup.build_reference_baseline_ch4 --target-year 2025 --version v2 --include-altaisky

См. DevPrompt P-01.0a §1-§2.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
PROTECTED_AREAS_ASSET = f"projects/{PROJECT_ID}/assets/RuPlumeScan/reference/protected_areas"

# Per-gas TROPOMI L3 collection IDs and bias-corrected band names
GAS_COLLECTIONS: dict[str, dict[str, str]] = {
    "CH4": {
        "id": "COPERNICUS/S5P/OFFL/L3_CH4",
        "band": "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
    },
    "NO2": {
        "id": "COPERNICUS/S5P/OFFL/L3_NO2",
        "band": "tropospheric_NO2_column_number_density",
    },
    "SO2": {
        "id": "COPERNICUS/S5P/OFFL/L3_SO2",
        "band": "SO2_column_number_density",
    },
}

# AOI bbox для production baseline (lon_min, lat_min, lon_max, lat_max)
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)

# Default analysis scale (per RNA §7.1 default preset)
ANALYSIS_SCALE_M = 7000

# Active zones для v1 build (Алтайский excluded по DNA §2.1 запрет 16)
ACTIVE_ZONES_V1 = ["yugansky", "verkhnetazovsky", "kuznetsky_alatau"]

# Production output asset paths
OUTPUT_ASSET_TEMPLATE = (
    f"projects/{PROJECT_ID}/assets/RuPlumeScan/baselines/reference_CH4_2019_2025_{{version}}"
)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_reference_baseline_ch4")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def load_reference_zones(use_zones: list[str], include_altaisky: bool) -> ee.FeatureCollection:
    """
    Загрузить reference zones, отфильтровать по quality_status="active".

    Per DNA §2.1 запрет 16 — `optional_pending_quality` zones (Алтайский по
    умолчанию) НЕ включаются. `include_altaisky=True` + Алтайский с
    quality_status="active" (после QA pass) — единственный путь для inclusion.
    """
    fc = ee.FeatureCollection(PROTECTED_AREAS_ASSET)
    active = fc.filter(ee.Filter.eq("quality_status", "active"))
    active = active.filter(ee.Filter.inList("zone_id", use_zones))

    if include_altaisky:
        altaisky = fc.filter(
            ee.Filter.And(
                ee.Filter.eq("zone_id", "altaisky"),
                ee.Filter.eq("quality_status", "active"),
            )
        )
        active = active.merge(altaisky)

    return active


def apply_internal_buffers(zones: ee.FeatureCollection) -> ee.FeatureCollection:
    """
    Применить per-zone internal buffer (negative buffer для исключения edge effects).

    Pre-simplify maxError=100m перед negative buffer — обходит invalid geometry
    issues на complex polygons (Algorithm §13 GEE gotcha).
    """

    def _shrink(zone: ee.Feature) -> ee.Feature:
        buffer_km = ee.Number(zone.get("internal_buffer_km"))
        simplified = zone.geometry().simplify(maxError=100)
        buffered = simplified.buffer(buffer_km.multiply(-1000))
        return zone.setGeometry(buffered)

    return zones.map(_shrink)


def build_zone_baseline_single_month(
    buffered_zones: ee.FeatureCollection,
    gas: str,
    target_year: int,
    target_month: int,
) -> ee.FeatureCollection:
    """
    Per-zone climatology для одного target_month.

    History window: years [2019, target_year-1], months [target_month-1, target_month+1]
    (3-month DOY window per RNA §7.1 default doy_window_half_days=30).

    Median + MAD-based sigma (1.4826 × MAD ≈ robust σ-equivalent).

    Возвращает FeatureCollection того же размера что buffered_zones, с added
    properties: baseline_ppb, sigma_ppb, count_avg, target_year, target_month, gas.
    """
    ds = GAS_COLLECTIONS[gas]

    def _per_zone(zone: ee.Feature) -> ee.Feature:
        zone_geom = zone.geometry()

        filtered = (
            ee.ImageCollection(ds["id"])
            .select(ds["band"])
            .filter(ee.Filter.calendarRange(2019, target_year - 1, "year"))
            .filter(ee.Filter.calendarRange(target_month - 1, target_month + 1, "month"))
            .map(lambda img: img.clip(zone_geom))
        )

        median_image = filtered.reduce(ee.Reducer.median())
        mad_image = (
            filtered.map(lambda img: img.subtract(median_image).abs())
            .reduce(ee.Reducer.median())
            .multiply(1.4826)
        )
        count_image = filtered.count()

        baseline_value = (
            median_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone_geom,
                scale=ANALYSIS_SCALE_M,
                maxPixels=int(1e8),
            )
            .values()
            .get(0)
        )

        sigma_value = (
            mad_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone_geom,
                scale=ANALYSIS_SCALE_M,
                maxPixels=int(1e8),
            )
            .values()
            .get(0)
        )

        # Total observations contributing to this zone-aggregate value.
        # Sum of count_image * pixel_area / pixel_area = sum of obs over zone pixels.
        # Use reduceRegion with sum then divide by pixel count.
        count_sum = (
            count_image.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=zone_geom,
                scale=ANALYSIS_SCALE_M,
                maxPixels=int(1e8),
            )
            .values()
            .get(0)
        )

        return zone.set(
            {
                "baseline_ppb": baseline_value,
                "sigma_ppb": sigma_value,
                "count_avg": count_sum,
                "target_year": target_year,
                "target_month": target_month,
                "gas": gas,
            }
        )

    return buffered_zones.map(_per_zone)


def build_stratified_baseline_image(
    aoi: ee.Geometry,
    zone_baselines: ee.FeatureCollection,
    band_suffix: str,
    scale_m: int = ANALYSIS_SCALE_M,
) -> ee.Image:
    """
    Latitude-stratified baseline image: каждый pixel получает baseline ближайшего
    по latitude reference zone.

    Server-side iteration через `ee.List.iterate()` (без `evaluate()` callback).

    band_suffix: e.g., "M01" — bands будут `ref_M01`, `sigma_M01`, `lat_dist_M01`.
    """
    lat_image = ee.Image.pixelLonLat().select("latitude")

    n_zones = zone_baselines.size()
    zones_list = zone_baselines.toList(n_zones.min(10))

    init_image = ee.Image.cat(
        [
            ee.Image.constant(99999).rename(f"lat_dist_{band_suffix}"),
            ee.Image.constant(0).rename(f"ref_{band_suffix}"),
            ee.Image.constant(0).rename(f"sigma_{band_suffix}"),
        ]
    )

    def _step(idx, accum):
        zone = ee.Feature(zones_list.get(ee.Number(idx)))
        zone_lat = ee.Number(zone.get("centroid_lat"))
        zone_baseline = ee.Number(zone.get("baseline_ppb"))
        zone_sigma = ee.Number(zone.get("sigma_ppb"))

        lat_dist = lat_image.subtract(zone_lat).abs()
        accum_img = ee.Image(accum)
        closer_mask = lat_dist.lt(accum_img.select(f"lat_dist_{band_suffix}"))

        new_min_dist = lat_dist.where(
            closer_mask.Not(), accum_img.select(f"lat_dist_{band_suffix}")
        )
        new_baseline = ee.Image.constant(zone_baseline).where(
            closer_mask.Not(), accum_img.select(f"ref_{band_suffix}")
        )
        new_sigma = ee.Image.constant(zone_sigma).where(
            closer_mask.Not(), accum_img.select(f"sigma_{band_suffix}")
        )

        return ee.Image.cat(
            [
                new_min_dist.rename(f"lat_dist_{band_suffix}"),
                new_baseline.rename(f"ref_{band_suffix}"),
                new_sigma.rename(f"sigma_{band_suffix}"),
            ]
        )

    result = ee.List.sequence(0, n_zones.subtract(1)).iterate(_step, init_image)
    return ee.Image(result).reproject(crs="EPSG:4326", scale=scale_m).clip(aoi)


def collect_diagnostics(
    target_year: int,
    use_zones: list[str],
    include_altaisky: bool,
    logger: logging.Logger,
) -> list[dict]:
    """
    Phase A: per-zone-per-month diagnostics (без stratification).

    Каждый month — independent ee compute call → не накапливается graph
    (memory limit issue избегается).
    """
    logger.info("Loading zones (use_zones=%s, include_altaisky=%s)", use_zones, include_altaisky)
    zones = load_reference_zones(use_zones, include_altaisky)
    n_zones = zones.size().getInfo()
    logger.info("Active zones: %d", n_zones)

    if n_zones == 0:
        raise RuntimeError("No active zones found. Verify protected_areas FeatureCollection.")

    buffered = apply_internal_buffers(zones)
    diagnostics = []

    # Per OpenSpec MC-2026-04-28-B: 4 of 12 monthly compute calls earlier
    # failed с "User memory limit exceeded" в pattern M02/M05/M08/M11.
    # Mitigation — pacing 60s между monthly compute calls (cumulative GEE
    # user-quota throttling). Total Phase A duration ~10-15 min vs ~5 min
    # without pacing.
    PACING_SEC = 60

    for month in range(1, 13):
        logger.info(
            "Diagnostics month %02d (pacing %ds first)...", month, PACING_SEC if month > 1 else 0
        )
        if month > 1:
            time.sleep(PACING_SEC)
        try:
            zone_baselines = build_zone_baseline_single_month(buffered, "CH4", target_year, month)
            info = zone_baselines.getInfo()
        except ee.EEException as exc:
            logger.error("Month %02d compute failed: %s", month, exc)
            continue

        for feat in info.get("features", []):
            props = feat["properties"]
            diagnostics.append(
                {
                    "zone_id": props.get("zone_id"),
                    "month": month,
                    "baseline_ppb": props.get("baseline_ppb"),
                    "sigma_ppb": props.get("sigma_ppb"),
                    "count_avg": props.get("count_avg"),
                }
            )
            baseline = props.get("baseline_ppb")
            sigma = props.get("sigma_ppb")
            count = props.get("count_avg")
            logger.info(
                "  %s M%02d: baseline=%s, sigma=%s, count=%s",
                props.get("zone_id"),
                month,
                f"{baseline:.2f} ppb" if baseline is not None else "NaN (polar night / no obs)",
                f"{sigma:.2f}" if sigma is not None else "NaN",
                f"{count:.0f}" if count is not None else "0",
            )

    return diagnostics


def build_full_year_image(
    target_year: int,
    use_zones: list[str],
    include_altaisky: bool,
    logger: logging.Logger,
) -> ee.Image:
    """
    Phase B: построить multi-band Image для Export.

    12 separate stratification computations (per-month). Каждый month
    independent — ee.Image.cat() в конце соединяет, без getInfo() в loop
    server graph остаётся manageable.
    """
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    zones = load_reference_zones(use_zones, include_altaisky)
    buffered = apply_internal_buffers(zones)

    monthly_images = []
    for month in range(1, 13):
        suffix = f"M{month:02d}"
        logger.info("Build stratified image M%02d", month)
        zone_baselines = build_zone_baseline_single_month(buffered, "CH4", target_year, month)
        stratified = build_stratified_baseline_image(aoi, zone_baselines, suffix)
        monthly_images.append(stratified)

    return ee.Image.cat(monthly_images)


def export_baseline_asset(
    image: ee.Image,
    asset_id: str,
    metadata: dict,
    logger: logging.Logger,
) -> ee.batch.Task:
    """
    Запустить Export.image.toAsset task.

    Per DNA §2.1 запрет 12 — Run без полного config snapshot не выдаётся.
    metadata должен содержать algorithm_version, build_date, zones_used,
    sanity_validation status.
    """
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))

    # Attach metadata as Image properties
    image_with_meta = image.set(metadata)

    task = ee.batch.Export.image.toAsset(
        image=image_with_meta,
        description=f"reference_CH4_baseline_{metadata.get('version', 'v1')}",
        assetId=asset_id,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    logger.info("Export task started: id=%s", task.id)
    return task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-year",
        type=int,
        default=2025,
        help="Target year (history = [2019, target_year-1]). Default 2025.",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="v1",
        help="Asset version suffix (v1 = 3 zones, v2 = 4 zones with Altaisky if pass).",
    )
    parser.add_argument(
        "--include-altaisky",
        action="store_true",
        help="Include Altaisky if quality_status='active'. Только для v2 после QA pass.",
    )
    parser.add_argument(
        "--diagnostics-out",
        type=str,
        default=None,
        help="Path для save per-zone-per-month diagnostics JSON. По умолчанию — "
        "<project_root>/docs/p-01.0a_diagnostics_<version>.json (cwd-independent).",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Не запускать Export.toAsset (только compute diagnostics).",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)
    logger.info(
        "Building reference CH4 baseline target_year=%d version=%s include_altaisky=%s",
        args.target_year,
        args.version,
        args.include_altaisky,
    )

    started_at = time.time()
    diagnostics = collect_diagnostics(
        args.target_year, ACTIVE_ZONES_V1, args.include_altaisky, logger
    )
    elapsed = time.time() - started_at
    logger.info(
        "Phase A diagnostics duration: %.1f s (%d zone-month entries)",
        elapsed,
        len(diagnostics),
    )

    # Save diagnostics (cwd-independent default — anchor to repo root)
    from pathlib import Path

    if args.diagnostics_out:
        diag_path = Path(args.diagnostics_out)
    else:
        repo_root = Path(__file__).resolve().parents[3]
        diag_path = repo_root / "docs" / f"p-01.0a_diagnostics_{args.version}.json"
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    diag_path.write_text(
        json.dumps(
            {
                "build_date": str(date.today()),
                "target_year": args.target_year,
                "version": args.version,
                "include_altaisky": args.include_altaisky,
                "build_duration_s": elapsed,
                "diagnostics": diagnostics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Diagnostics saved to %s", diag_path)

    if args.no_export:
        logger.info("--no-export specified, skipping Export.toAsset")
        return 0

    asset_id = OUTPUT_ASSET_TEMPLATE.format(version=args.version)

    metadata = {
        "algorithm_version": "2.3",
        "rna_version": "1.2",
        "build_date": str(date.today()),
        "target_year": args.target_year,
        "version": args.version,
        "zones_used": ACTIVE_ZONES_V1 + (["altaisky"] if args.include_altaisky else []),
        "include_altaisky": args.include_altaisky,
        "source_collection": "COPERNICUS/S5P/OFFL/L3_CH4",
        "bias_correction": "bias_corrected",
        "history_year_min": 2019,
        "history_year_max": args.target_year - 1,
        "doy_window_half_days": 30,
        "internal_buffers_km": json.dumps({"yugansky": 10, "others": 5}),
        "stratification": "nearest_by_latitude_centroid",
        "build_pipeline": "src/py/setup/build_reference_baseline_ch4.py",
    }

    logger.info("Phase B: build stratified Image для export")
    full_image = build_full_year_image(
        args.target_year, ACTIVE_ZONES_V1, args.include_altaisky, logger
    )
    logger.info("Exporting to %s", asset_id)
    task = export_baseline_asset(full_image, asset_id, metadata, logger)
    logger.info("Task state: %s", task.status().get("state"))
    logger.info("Monitor через ee.batch.Task.list() или Code Editor 'Tasks' tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
