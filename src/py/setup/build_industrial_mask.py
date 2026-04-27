"""
Build RuPlumeScan/industrial/proxy_mask Image из industrial/source_points.

Output: ee.Image, single band 'industrial_mask' uint8:
  1 = within `buffer_km` (default 15 km) of any industrial source
  0 = clean

Используется в:
  * Climatology construction (Algorithm v2.3 §3.4.1) — exclude industrial buffer
    при regional climatology (secondary baseline в dual baseline approach).
  * Source attribution (Algorithm §3.10) — nearest source distance lookup.

Per Algorithm §3.4.1 default `industrial_buffer_exclude_km` = 30 km применяется
при climatology construction. Здесь raster mask делается с **меньшим** buffer
(15 km) — обеспечивает finer raster resolution; final 30 km exclusion в
detection pipeline применяется через `focal_max(15 km)` поверх этого mask
при необходимости (effective 30 km dilation).

Запуск::

    cd src/py
    python -m setup.build_industrial_mask
    python -m setup.build_industrial_mask --buffer-km 30  # custom
"""

from __future__ import annotations

import argparse
import logging
import sys

import ee

PROJECT_ID = "nodal-thunder-481307-u1"
SOURCES_ASSET = f"projects/{PROJECT_ID}/assets/RuPlumeScan/industrial/source_points"
MASK_ASSET = f"projects/{PROJECT_ID}/assets/RuPlumeScan/industrial/proxy_mask"

# AOI bbox (Western Siberia, lon_min, lat_min, lon_max, lat_max).
# Расширен на юг до 50°N для consistency с reference mask AOI.
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)

DEFAULT_BUFFER_KM = 15
DEFAULT_SCALE_M = 7000


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_industrial_mask")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def build_mask_image(buffer_km: int) -> ee.Image:
    """
    Загрузить industrial source_points, buffer + dissolve + rasterize.

    Returns: ee.Image, single band 'industrial_mask' (uint8), 1=industrial, 0=clean.
    """
    sources = ee.FeatureCollection(SOURCES_ASSET)

    # Per-feature buffer; затем union (dissolve) в один MultiPolygon.
    buffered_fc = sources.map(lambda f: f.buffer(ee.Number(buffer_km).multiply(1000)))  # km -> m
    dissolved = buffered_fc.union(maxError=ee.ErrorMargin(50))

    # Rasterize: 1 inside dissolved geometry, 0 outside.
    mask = (
        ee.Image.constant(1)
        .clip(dissolved)
        .unmask(0)  # outside dissolved -> 0
        .rename("industrial_mask")
        .uint8()
    )
    return mask


def export_mask(mask: ee.Image, asset_id: str, buffer_km: int, scale_m: int) -> ee.batch.Task:
    """Запустить Export.image.toAsset task."""
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    task = ee.batch.Export.image.toAsset(
        image=mask,
        description="industrial_proxy_mask",
        assetId=asset_id,
        region=aoi,
        scale=scale_m,
        maxPixels=int(1e10),
        crs="EPSG:4326",
    )
    task.start()
    return task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--buffer-km",
        type=int,
        default=DEFAULT_BUFFER_KM,
        help=f"Buffer вокруг каждой industrial point (km). Default {DEFAULT_BUFFER_KM}.",
    )
    parser.add_argument(
        "--scale-m",
        type=int,
        default=DEFAULT_SCALE_M,
        help=f"Output raster scale (meters/pixel). Default {DEFAULT_SCALE_M}.",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info("Earth Engine initialized for project '%s'", PROJECT_ID)
    logger.info("Loading sources from: %s", SOURCES_ASSET)

    sources = ee.FeatureCollection(SOURCES_ASSET)
    n_sources = sources.size().getInfo()
    logger.info("Source count: %d", n_sources)
    if n_sources == 0:
        logger.error("Empty source_points Asset. Run build_industrial_proxy.py first.")
        return 1

    logger.info("Building industrial mask с buffer_km=%d", args.buffer_km)
    mask = build_mask_image(args.buffer_km)

    logger.info("Exporting to %s (scale %d m, AOI %s)", MASK_ASSET, args.scale_m, AOI_BBOX)
    task = export_mask(mask, MASK_ASSET, args.buffer_km, args.scale_m)
    logger.info("Export task started: id=%s, state=%s", task.id, task.status().get("state"))
    logger.info("Monitor через ee.batch.Task.list() или Code Editor 'Tasks' tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
