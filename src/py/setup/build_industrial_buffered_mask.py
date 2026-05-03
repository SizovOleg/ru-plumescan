"""
One-time helper: pre-compute industrial buffered mask Asset (TD-0011).

Builds `RuPlumeScan/industrial/proxy_mask_buffered_30km` Image:
  - input: existing `RuPlumeScan/industrial/proxy_mask` (P-00.1 — 15 km buffered)
  - apply: focal_max(15 km) → effective 30 km exclusion + `.Not()` invert
  - output: 1=clean, 0=industrial-buffered-30km

**Why:** в P-01.0b CH₄ pipeline на-the-fly focal_max(15km) recomputed в каждом
из 12 monthly batch tasks — это duplicate compute over full AOI (~600,000 km²).
Pre-compute раз → load Asset во всех subsequent monthly tasks → save ~1.5 hr
per gas (researcher feedback 2026-04-28).

Запуск (one-time per repo / once per Algorithm version)::

    cd src/py
    python -m setup.build_industrial_buffered_mask

После SUCCEEDED — запускать NO₂/SO₂ с `--use-prebuilt-mask` flag в
build_regional_climatology.py.

См. KNOWN_TODOS.md TD-0011.
"""

from __future__ import annotations

import argparse
import logging
import sys

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
ASSETS_ROOT = f"projects/{PROJECT_ID}/assets"
SOURCE_MASK = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask"
OUTPUT_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask_buffered_30km"

# AOI bbox identical to industrial mask + protected areas + reference baseline
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
SCALE_M = 7000


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_industrial_buffered_mask")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--additional-buffer-km",
        type=int,
        default=15,
        help="Дополнительный focal_max km (default 15 → effective 30 km exclusion).",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized")

    logger.info("Loading source mask: %s", SOURCE_MASK)
    src = ee.Image(SOURCE_MASK).unmask(0)

    logger.info(
        "Apply focal_max(%d km) + Not() -> clean=1 / industrial-buffered=0",
        args.additional_buffer_km,
    )
    buffered_clean = (
        src.focal_max(radius=args.additional_buffer_km * 1000, units="meters")
        .Not()
        .rename("industrial_clean_mask")
        .uint8()
    )

    metadata = {
        "algorithm_version": "2.3",
        "rna_version": "1.2",
        "source_asset": SOURCE_MASK,
        "additional_focal_max_km": args.additional_buffer_km,
        "effective_industrial_buffer_km": 15 + args.additional_buffer_km,
        "build_pipeline": "src/py/setup/build_industrial_buffered_mask.py",
        "td_0011": "pre_computed_for_regional_climatology_optimization",
    }
    buffered_clean = buffered_clean.set(metadata)

    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    task = ee.batch.Export.image.toAsset(
        image=buffered_clean,
        description="industrial_buffered_mask_30km",
        assetId=OUTPUT_ASSET,
        region=aoi,
        scale=SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    logger.info("Export task started: id=%s", task.id)
    logger.info("Asset: %s", OUTPUT_ASSET)
    logger.info("Monitor через ee.batch.Task.list(). Expected duration ~5-10 min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
