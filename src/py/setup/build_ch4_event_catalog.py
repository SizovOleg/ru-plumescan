"""
Build RuPlumeScan/catalog/CH4/events_<year> FeatureCollection — annual CH₄
plume event catalog (P-02.0a Шаг 5).

Per RFC v2 frozen architecture + DevPrompt P-02.0a §5.

Per-year processing (sequential 2019..2025 при full launch):
  1. Load TROPOMI L3 CH4 collection filtered by year + AOI
  2. Build hybrid_background ONCE (Algorithm §3.4.3 dual baseline cross-check)
  3. Per-month iteration over orbits → cluster FeatureCollections via primitives:
       compute_z_score → apply_three_condition_mask → extract_clusters →
       compute_cluster_attributes → validate_wind → attribute_source
  4. Per-region adaptive z_min via build_zmin_filter (TD-0018, DNA §2.1.6)
  5. TD-0017 transboundary easterly check (lat∈[53,56], lon≥92)
  6. TD-0021 zone-boundary qa annotation (centroids ±100 km of 57.5°N or 62°N)
  7. Manual override application (config/event_overrides.json)
  8. Annual catalog export → RuPlumeScan/catalog/CH4/events_<year>

Canonical Provenance pattern (TD-0024/0025): `compute_provenance(config) →
Provenance` ONCE at process start; pass by reference к все subsequent
operations (STARTED log, asset metadata, SUCCEEDED log).

NOT auto-launching full 7-year compute. Use:
  --year <YYYY>           process single year (default: print plan, no submit)
  --launch-year <YYYY>    actually submit batch task (requires GEE auth)
  --dry-run               print pipeline graph node count + plan, no submit
  --combine-years         merge per-year catalogs → master index after full run

Запуск (single-year test 2024 — baselines aligned, recommended first run)::

    cd src/py
    python -m setup.build_ch4_event_catalog --launch-year 2024 --dry-run
    python -m setup.build_ch4_event_catalog --launch-year 2024
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import ee

# sys.path adjustment for module-vs-script invocation
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src" / "py") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "py"))

from rca import detection_ch4  # noqa: E402  — sys.path injected above
from rca.classify_events import apply_classification  # noqa: E402
from rca.detection_helpers import (  # noqa: E402
    REFERENCE_AVAILABLE_MONTHS,
    annotate_transboundary_qa,
    annotate_zone_boundary_qa,
    apply_event_overrides,
    build_event_config,
    build_zmin_filter,
    encode_qa_flags_for_export,
    load_event_overrides,
    prepare_source_points_categories,
)
from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

# ---------------------------------------------------------------------------
# Constants — verified against GEE assets 2026-05-05 (Шаг 5 pre-launch check)
# ---------------------------------------------------------------------------

PROJECT_ID = "nodal-thunder-481307-u1"
ASSETS_ROOT = f"projects/{PROJECT_ID}/assets"

# Single canonical baseline assets (NOT per-year — multi-year climatology used
# для detection в any individual year)
REFERENCE_BASELINE_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/baselines/reference_CH4_2019_2025_v1"
REGIONAL_BASELINE_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_CH4_2019_2025"
# Reference zones (zapovedniks) — verified path 2026-05-05
REFERENCE_ZONES_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/reference/protected_areas"
SOURCE_POINTS_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/source_points"

CATALOG_ASSET_TEMPLATE = f"{ASSETS_ROOT}/RuPlumeScan/catalog/CH4/events_{{year}}"
EVENT_OVERRIDES_PATH = _REPO_ROOT / "config" / "event_overrides.json"

# AOI bbox (Western Siberia + Алтай south extension)
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
ANALYSIS_SCALE_M = 7000

TROPOMI_CH4_COLLECTION = "COPERNICUS/S5P/OFFL/L3_CH4"
TROPOMI_CH4_BAND = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
ERA5_HOURLY_COLLECTION = "ECMWF/ERA5/HOURLY"


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_ch4_event_catalog")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


# ---------------------------------------------------------------------------
# Per-orbit detection pipeline
# ---------------------------------------------------------------------------


def detect_orbit_clusters(
    orbit_image: ee.Image,
    hybrid_background: ee.Image,
    month: int,
    aoi: ee.Geometry,
    era5_collection: ee.ImageCollection,
    source_points_fc: ee.FeatureCollection,
    *,
    delta_min_ppb: float = 30.0,
    relative_min_ppb: float = 15.0,
    annulus_outer_km: float = 150,
    min_cluster_px: int = 5,
    wind_level_hpa: int = 850,
    alignment_threshold_deg: float = 30.0,
    min_wind_speed_ms: float = 2.0,
    temporal_window_hours: int = 3,
    search_radius_km: float = 50.0,
) -> ee.FeatureCollection:
    """
    Run full per-orbit detection pipeline; return cluster FeatureCollection.

    Pipeline (Algorithm §3.5-§3.10):
      1. compute_z_score(orbit, hybrid, month) → 6-band image
      2. apply_three_condition_mask(z, delta_primary, z_min=3.0)
         z_min=3.0 default — Kuzbass region tightened post-cluster via
         build_zmin_filter (DNA §2.1.6 compliant).
      3. extract_clusters → cluster_image
      4. compute_cluster_attributes → FC с max_z, mean_z, area_km2, centroids
      5. validate_wind → adds wind_state, wind_consistent, wind_speed/dir
      6. attribute_source → adds nearest_source_id/distance/type

    Per-region z_min applied as POST-cluster filter (single detection pass с
    z_min=3.0; Kuzbass clusters then required to have max_z >= 4.0).
    """
    z_image = detection_ch4.compute_z_score(orbit_image, hybrid_background, month=month)
    z_band = z_image.select("z")
    delta_band = z_image.select("delta_primary")
    primary_value_band = z_image.select("primary_value")

    mask = detection_ch4.apply_three_condition_mask(
        z_band,
        delta_band,
        z_min=3.0,  # global default; per-region tightening via build_zmin_filter post-cluster
        delta_min_ppb=delta_min_ppb,
        relative_min_ppb=relative_min_ppb,
        annulus_outer_km=annulus_outer_km,
    )

    cluster_image = detection_ch4.extract_clusters(
        mask, min_cluster_px=min_cluster_px, max_size=256, connectedness=8
    )

    attrs_fc = detection_ch4.compute_cluster_attributes(
        cluster_image,
        orbit_image,
        primary_value_band,
        z_image,
        aoi,
        target_band=TROPOMI_CH4_BAND,
        scale_m=ANALYSIS_SCALE_M,
    )

    # Annotate orbit timestamp + month + year on every cluster
    orbit_millis = orbit_image.date().millis()
    orbit_year = orbit_image.date().get("year")
    annotated = attrs_fc.map(
        lambda feat: feat.set(
            {
                "orbit_date_millis": orbit_millis,
                "month": month,
                "year": orbit_year,
                "qa_flags": ee.List([]),  # initialize empty для downstream helpers
            }
        )
    )

    # Per-region z_min filter (TD-0018, DNA §2.1.6)
    filtered = annotated.filter(build_zmin_filter())

    # Wind validation (Algorithm §3.9 TD-0031). plume_axis_deg НЕ set yet —
    # client-side eigendecomposition в Шаг 5+ post-export. validate_wind
    # handles missing axis via wind_state='axis_unknown' (Issue 5.2 fix).
    with_wind = detection_ch4.validate_wind(
        filtered,
        era5_collection,
        orbit_millis,
        wind_level_hpa=wind_level_hpa,
        alignment_threshold_deg=alignment_threshold_deg,
        min_wind_speed_ms=min_wind_speed_ms,
        temporal_window_hours=temporal_window_hours,
    )

    # Source attribution (Algorithm §3.10)
    with_source = detection_ch4.attribute_source(
        with_wind, source_points_fc, search_radius_km=search_radius_km
    )

    return with_source


# ---------------------------------------------------------------------------
# Per-month / per-year aggregation
# ---------------------------------------------------------------------------


def process_month(
    year: int,
    month: int,
    hybrid_background: ee.Image,
    aoi: ee.Geometry,
    era5_collection: ee.ImageCollection,
    source_points_fc: ee.FeatureCollection,
    logger: logging.Logger,
) -> ee.FeatureCollection:
    """
    Process все orbits в given month → merged cluster FC.

    Server-side .map().flatten() pattern; orbit count typically 30-90 per month
    for Western Siberia AOI.
    """
    month_start = f"{year}-{month:02d}-01"
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year = year + 1
    month_end = f"{next_year}-{next_month:02d}-01"

    # GPT review #3 C-1 fix: do NOT pre-select target band — primitives select
    # what they need internally (compute_z_score uses target_band parameter).
    # Pre-selection here would strip QA bands which downstream code may need.
    collection = (
        ee.ImageCollection(TROPOMI_CH4_COLLECTION)
        .filterDate(month_start, month_end)
        .filterBounds(aoi)
    )

    def _per_orbit(orbit_image: ee.Image) -> ee.FeatureCollection:
        return detect_orbit_clusters(
            ee.Image(orbit_image),
            hybrid_background,
            month=month,
            aoi=aoi,
            era5_collection=era5_collection,
            source_points_fc=source_points_fc,
        )

    # Map collection → list of FCs → flatten via FC constructor
    orbit_list = collection.toList(collection.size())
    fcs = orbit_list.map(_per_orbit)
    merged = ee.FeatureCollection(fcs).flatten()

    logger.info("  M%02d %s..%s — processed", month, month_start, month_end)
    return merged


def process_year(
    year: int,
    provenance,  # type: ignore[no-untyped-def]
    overrides: list,
    logger: logging.Logger,
    *,
    aoi_bbox: tuple = AOI_BBOX,
    months_subset: list[int] | None = None,
) -> ee.FeatureCollection:
    """
    Build annual CH4 event catalog for given year.

    Returns ee.FeatureCollection (lazy — Export.table.toAsset materializes).

    Args:
        year: target year (2019..2025)
        provenance: Provenance object computed at process start (passed
            by reference; no recomputation downstream)
        overrides: list of manual override dicts (от load_event_overrides)
        logger: configured logger
        aoi_bbox: AOI lat/lon bbox tuple
        months_subset: optional list of months [1..12] для partial processing
            (default — all 12)
    """
    aoi = ee.Geometry.Rectangle(list(aoi_bbox))
    # TD-0034 — only 7 of 12 months have reference baseline data (M02/M05/M08/M11/M12 absent)
    available_months = REFERENCE_AVAILABLE_MONTHS
    months = months_subset or available_months
    # Filter requested months к those с reference data
    months = [m for m in months if m in available_months]
    if not months:
        logger.error(
            "No requested months overlap reference availability %s — exiting",
            available_months,
        )
        return ee.FeatureCollection([])

    logger.info("=" * 60)
    logger.info("Processing year %d (%d months: %s)", year, len(months), months)

    # Hybrid background — built ONCE per year (consistency_flag pre-computed для
    # available months). Algorithm §3.4.3 dual baseline cross-check.
    reference_baseline = ee.Image(REFERENCE_BASELINE_ASSET)
    regional_baseline = ee.Image(REGIONAL_BASELINE_ASSET)  # canonical multi-year asset

    # Reference zones FC — verified path RuPlumeScan/reference/protected_areas
    try:
        reference_zones_fc = ee.FeatureCollection(REFERENCE_ZONES_ASSET)
        n_zones = reference_zones_fc.size().getInfo()
        logger.info("Reference zones FC loaded: %d zones", n_zones)
    except Exception as exc:  # pragma: no cover — runtime path
        logger.warning("Reference zones FC unavailable (%s) — zone band = 0", exc)
        reference_zones_fc = None

    hybrid_background = detection_ch4.build_hybrid_background(
        reference_baseline,
        regional_baseline,
        consistency_tolerance_ppb=30.0,
        reference_zones_fc=reference_zones_fc,
        months=available_months,  # TD-0034: 7 months only in v1 reference
    )

    # ERA5 collection (filter happens per-orbit inside validate_wind)
    era5_collection = ee.ImageCollection(ERA5_HOURLY_COLLECTION)

    # Source points FC — preprocess to add source_type_category (Algorithm §3.10)
    raw_source_points = ee.FeatureCollection(SOURCE_POINTS_ASSET)
    source_points_fc = prepare_source_points_categories(raw_source_points)

    # Process each month
    month_fcs = []
    for m in months:
        month_fc = process_month(
            year=year,
            month=m,
            hybrid_background=hybrid_background,
            aoi=aoi,
            era5_collection=era5_collection,
            source_points_fc=source_points_fc,
            logger=logger,
        )
        month_fcs.append(month_fc)

    annual_fc = ee.FeatureCollection(month_fcs).flatten()

    # TD-0017 transboundary qa annotation
    annual_fc = annotate_transboundary_qa(annual_fc, era5_collection)

    # TD-0021 zone-boundary qa annotation
    annual_fc = annotate_zone_boundary_qa(annual_fc)

    # Manual overrides (Algorithm §6)
    if overrides:
        logger.info("Applying %d manual overrides", len(overrides))
        annual_fc = apply_event_overrides(annual_fc, overrides)

    # Шаг 6: Algorithm §3.12 5-priority classification cascade
    annual_fc = apply_classification(annual_fc)

    # Attach provenance к each event (DNA §2.1 запрет 12 — every Feature has
    # params_hash, config_id, run_id, algorithm_version, build_date)
    prov_props = provenance.to_asset_properties()
    annual_fc = annual_fc.map(lambda f: f.set(prov_props))

    # Шаг 5 launch fix: convert qa_flags list к string для GEE Export
    # compatibility (Export.table.toAsset rejects List<Object>; см.
    # encode_qa_flags_for_export docstring). Last step before return —
    # all helpers that operate на qa_flags must run BEFORE this point.
    annual_fc = encode_qa_flags_for_export(annual_fc)

    return annual_fc


# ---------------------------------------------------------------------------
# Export task submission
# ---------------------------------------------------------------------------


def submit_export(
    fc: ee.FeatureCollection,
    asset_id: str,
    provenance,  # type: ignore[no-untyped-def]
    logger: logging.Logger,
    *,
    description: str | None = None,
) -> ee.batch.Task:
    """
    Submit Export.table.toAsset для annual catalog FC.

    Asset metadata gets full Provenance (DNA §2.1 запрет 12). Single batch
    task per year (vs per-month) — typical event count 100-1000 per year,
    fits в single FC export.
    """
    description = description or f"ch4_event_catalog_{asset_id.split('/')[-1]}"
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description=description,
        assetId=asset_id,
        # Note: Export.table.toAsset doesn't accept properties param;
        # asset metadata set post-completion via setAssetProperties OR
        # baked-in via .map(set provenance) at FC level. Latter approach
        # used here — every Feature carries provenance.
    )
    task.start()
    logger.info("Submitted: %s (task_id=%s)", asset_id, task.id)
    return task


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build annual CH4 plume event catalog (P-02.0a Шаг 5)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Single year к plan (no launch); shows pipeline summary",
    )
    parser.add_argument(
        "--launch-year",
        type=int,
        default=None,
        help="Single year к actually submit к GEE batch (requires auth + assets)",
    )
    parser.add_argument(
        "--full-launch",
        action="store_true",
        help="Submit все 7 years (2019..2025); BLOCKED unless --i-know-what-im-doing",
    )
    parser.add_argument(
        "--i-know-what-im-doing",
        action="store_true",
        help="Acknowledge full 7-year launch is expensive (3-5h × 7 years = wall-clock days)",
    )
    parser.add_argument(
        "--months", type=str, default=None, help="Comma-separated months 1-12 (default all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build FC graph + print summary, but не submit Export task",
    )
    parser.add_argument(
        "--config-preset", type=str, default="default", help="Configuration preset name"
    )
    parser.add_argument(
        "--ee-project", type=str, default=PROJECT_ID, help="GEE project ID for ee.Initialize"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logger()

    # Validate args
    if args.full_launch and not args.i_know_what_im_doing:
        logger.error("--full-launch requires --i-know-what-im-doing (7 years × 3-5h compute)")
        return 2

    if args.year is None and args.launch_year is None and not args.full_launch:
        logger.info("Usage: --year YYYY (plan) | --launch-year YYYY (submit) | --full-launch")
        logger.info("See --help для full options")
        return 0

    # Initialize EE
    try:
        ee.Initialize(project=args.ee_project)
        logger.info("EE initialized: project=%s", args.ee_project)
    except Exception as exc:
        logger.error("ee.Initialize() failed: %s", exc)
        return 1

    # Resolve years к process
    if args.full_launch:
        years = list(range(2019, 2026))
    elif args.launch_year is not None:
        years = [args.launch_year]
    else:
        years = [args.year]

    months_subset = [int(m.strip()) for m in args.months.split(",")] if args.months else None

    # Manual overrides
    overrides = load_event_overrides(EVENT_OVERRIDES_PATH)
    logger.info("Manual overrides loaded: %d entries", len(overrides))

    # Process each year sequentially (per-year batch task)
    for year in years:
        logger.info("\n" + "=" * 60)
        logger.info("Year %d", year)
        logger.info("=" * 60)

        # Canonical Provenance — computed ONCE per year run (config differs by year)
        config = build_event_config(year, config_preset=args.config_preset)
        prov = compute_provenance(
            config=config,
            config_id=args.config_preset,
            period=f"2019_{year}",
            algorithm_version="2.3.2",
            rna_version="1.2",
        )
        logger.info(
            "Provenance: run_id=%s params_hash=%s",
            prov.run_id,
            prov.params_hash[:8],
        )

        asset_id = CATALOG_ASSET_TEMPLATE.format(year=year)
        logger.info("Target asset: %s", asset_id)

        # Build lazy FC (no compute yet — Export materializes)
        annual_fc = process_year(
            year=year,
            provenance=prov,
            overrides=overrides,
            logger=logger,
            months_subset=months_subset,
        )

        if args.dry_run:
            logger.info("Dry-run: Lazy FC graph constructed (not submitted)")
            logger.info("FC summary: lazy graph; getInfo() skipped to avoid full compute")
            continue

        # Submit Export
        if args.launch_year is None and not args.full_launch:
            logger.info("--year mode: plan only (no submit). Use --launch-year к actually run.")
            continue

        # GPT review #3 C-2 fix: empty FC guard — don't waste batch quota on
        # zero-event year (would create empty asset). Happens when months_subset
        # filtered out все available reference months.
        try:
            n_events = annual_fc.size().getInfo()
        except Exception as exc:
            logger.warning("Could not pre-check FC size (%s) — proceeding к submit", exc)
            n_events = -1  # unknown; proceed but log
        if n_events == 0:
            logger.error(
                "Year %d produced 0 events (likely months filtered out OR detection "
                "found nothing). Skipping export to avoid empty asset.",
                year,
            )
            write_provenance_log(
                prov,
                status="SKIPPED_EMPTY",
                gas="CH4",
                period=f"2019_{year}",
                asset_id=asset_id,
                extra={
                    "reason": "zero_events_after_pipeline",
                    "n_overrides": len(overrides),
                },
            )
            continue

        # STARTED log
        write_provenance_log(
            prov,
            status="STARTED",
            gas="CH4",
            period=f"2019_{year}",
            asset_id=asset_id,
            extra={
                "phase": config["phase"],
                "operation": "ch4_event_catalog_build",
                "target_year": year,
                "n_overrides": len(overrides),
            },
        )

        try:
            task = submit_export(annual_fc, asset_id, prov, logger)
            logger.info("Year %d task submitted: %s", year, task.id)
            # SUCCEEDED log при submit success — actual completion polled
            # separately (orchestrator не waits — single-year task can be
            # 30+ min; user runs --combine-only после)
            write_provenance_log(
                prov,
                status="SUBMITTED",
                gas="CH4",
                period=f"2019_{year}",
                asset_id=asset_id,
                extra={
                    "task_id": task.id,
                    "n_overrides": len(overrides),
                },
            )
        except Exception as exc:
            logger.error("Submit failed for year %d: %s", year, exc)
            write_provenance_log(
                prov,
                status="FAILED",
                gas="CH4",
                period=f"2019_{year}",
                asset_id=asset_id,
                extra={"error": str(exc)},
            )
            return 1

    logger.info("\nDone. Use Tasks Manager (https://code.earthengine.google.com/tasks) к monitor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
