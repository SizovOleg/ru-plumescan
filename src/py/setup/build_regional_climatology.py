"""
Build RuPlumeScan/baselines/regional_<gas>_<period> Image — secondary baseline
с industrial buffer exclusion (Algorithm v2.3 §3.4.1).

**TD-0008 Option C test embedded:**

Single-iteration approach в P-01.0a Phase B failed для Q-mid months
(M02/M05/M08/M11) с `User memory limit exceeded`. Pattern deterministic,
не throttle. Researcher hypothesis 2026-04-28: каждый месяц — separate
batch task → own server-side memory allocation → bypass Q-mid.

Этот script implements Option C:

  1. Per gas, launch 12 **separate** batch tasks (one per month).
  2. Each task — own Export.image.toAsset на temp asset path.
  3. Poll all 12 to completion.
  4. Combine results в final multi-band asset (median_M01..12,
     sigma_M01..12, count_M01..12) via ee.Image.cat.
  5. Cleanup temp assets.

**Embedded experiment:** P-01.0b CH₄ run is the test of Option C
hypothesis. Outcome A (12/12 success) → confirmed; B (Q-mid pattern
reproduced) → rejected; C (partial) → investigate.

Per DevPrompt P-01.0b §6 critical escalation: после CH₄ complete, ВСЕГДА
escalate Outcome A/B/C к researcher перед NO₂/SO₂.

Запуск (per-gas, sequential)::

    cd src/py
    python -m setup.build_regional_climatology --gas CH4 --target-year 2025
    python -m setup.build_regional_climatology --gas NO2 --target-year 2025
    python -m setup.build_regional_climatology --gas SO2 --target-year 2025

Опции::

    --launch-only      Только launch 12 monthly tasks, не poll (resume позже)
    --poll-only        Только poll existing tasks (resume from saved state)
    --combine-only     Только combine existing temp assets в final + cleanup
    --buffer-km N      Industrial buffer в km (default 15 → effective 30 with
                       pre-buffered proxy_mask)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import ee

# Allow `from rca.provenance import ...` whether script run as module
# (cd src/py; python -m setup.build_regional_climatology) или as path
# (python src/py/setup/build_regional_climatology.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src" / "py") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "py"))

PROJECT_ID = "nodal-thunder-481307-u1"
ASSETS_ROOT = f"projects/{PROJECT_ID}/assets"
INDUSTRIAL_MASK_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask"

# Output asset paths (final + temp per-month)
FINAL_ASSET_TEMPLATE = f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_{{gas}}_2019_{{year}}"
TEMP_ASSET_TEMPLATE = (
    f"{ASSETS_ROOT}/RuPlumeScan/baselines/_temp/regional_{{gas}}_2019_{{year}}_M{{month:02d}}"
)
TEMP_FOLDER = f"{ASSETS_ROOT}/RuPlumeScan/baselines/_temp"

# AOI bbox (Western Siberia + Алтай south extension)
AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
ANALYSIS_SCALE_M = 7000

# Per-gas TROPOMI L3 metadata.
#
# CLAIM 5 fix (CR review 2026-04-29): `qa_bands` lists auxiliary bands
# нужные для apply_qa_filter. Pre-fix: pipeline делал .select(band) рано —
# QA bands lost before filter. Post-fix: select([band] + qa_bands), filter,
# затем drop QA via .select([band]).
#
# CH4 L3 v02.04 doesn't have cloud_fraction or qa_value (upstream-filtered
# by GEE Lorente 2021). NO2 / SO2 L3 имеют cloud_fraction → must include.
GAS_COLLECTIONS: dict[str, dict] = {
    "CH4": {
        "id": "COPERNICUS/S5P/OFFL/L3_CH4",
        "band": "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
        "qa_bands": [],  # L3 v02.04 OFFL upstream-filtered, no QA bands needed
        "qa_value_min": 0.5,
        "physical_range": (1700, 2200),
        "negative_floor": None,
        "cloud_fraction_max": None,
    },
    "NO2": {
        "id": "COPERNICUS/S5P/OFFL/L3_NO2",
        "band": "tropospheric_NO2_column_number_density",
        "qa_bands": ["cloud_fraction"],  # CLAIM 5 fix — keep available для filter
        "qa_value_min": 0.75,
        "physical_range": None,
        "negative_floor": None,
        "cloud_fraction_max": 0.3,
    },
    "SO2": {
        "id": "COPERNICUS/S5P/OFFL/L3_SO2",
        "band": "SO2_column_number_density",
        "qa_bands": ["cloud_fraction"],  # CLAIM 5 fix
        "qa_value_min": 0.5,
        "physical_range": None,
        "negative_floor": -0.001,  # DNA §2.1 запрет 7
        "cloud_fraction_max": 0.3,
    },
}

# Default polling settings
POLL_INTERVAL_SEC = 60
POLL_TIMEOUT_MINUTES = 90  # generous; per-month tasks usually 1-5 min


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("build_regional_climatology")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger


def ensure_temp_folder(logger: logging.Logger) -> None:
    """Создать temp folder если не exists."""
    try:
        ee.data.createAsset({"type": "Folder"}, TEMP_FOLDER)
        logger.info("Created temp folder: %s", TEMP_FOLDER)
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            logger.info("Temp folder exists: %s", TEMP_FOLDER)
        else:
            raise


def apply_qa_filter(img: ee.Image, gas_meta: dict) -> ee.Image:
    """
    Per-gas QA filter (Algorithm §3.3 / §4.3 / §5.3).

    Note: TROPOMI L3 GEE bands variable per release; some QA bands могут
    отсутствовать в L3 (qa_value embedded в pre-filtering by GEE). Code
    defensively checks band presence.
    """
    masked = img

    band_names = img.bandNames()

    # Cloud fraction filter
    if gas_meta["cloud_fraction_max"] is not None:
        cf_thresh = gas_meta["cloud_fraction_max"]
        masked = ee.Image(
            ee.Algorithms.If(
                band_names.contains("cloud_fraction"),
                masked.updateMask(masked.select("cloud_fraction").lt(cf_thresh)),
                masked,
            )
        )

    # Physical range (CH4)
    if gas_meta["physical_range"] is not None:
        rng_min, rng_max = gas_meta["physical_range"]
        target_band = masked.select(gas_meta["band"])
        masked = masked.updateMask(target_band.gte(rng_min).And(target_band.lte(rng_max)))

    # Negative floor (SO2 — only strong negatives filtered, DNA §2.1 запрет 7)
    if gas_meta["negative_floor"] is not None:
        floor = gas_meta["negative_floor"]
        target_band = masked.select(gas_meta["band"])
        masked = masked.updateMask(target_band.gte(floor))

    return masked


PREBUILT_MASK_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask_buffered_30km"
PER_TYPE_MASK_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask_buffered_per_type"
URBAN_MASK_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/urban/urban_mask_smod22"


def build_clean_mask(
    buffer_km: int,
    use_prebuilt: bool = False,
    use_per_type: bool = False,
    use_urban_mask: bool = False,
) -> ee.Image:
    """
    Industrial buffer exclusion mask: 1=clean, 0=industrial-buffered.

    Modes (priority: per-type > prebuilt > on-the-fly):
      * `use_per_type=True` (P-01.0d, TD-0027) — load
        `proxy_mask_buffered_per_type` (heterogeneous buffer 50/30/15 km
        per source category). When combined с `use_urban_mask=True`,
        AND-merges с GHS-SMOD ≥22 urban exclusion (TD-0023). Recommended
        для new regional baselines after P-01.0d.
      * `use_prebuilt=True` (legacy, P-01.0b TD-0011) — load
        `proxy_mask_buffered_30km` (uniform 30 km buffer). Saved ~1.5 hours
        per gas vs on-the-fly. Pre-P-01.0d clean mask.
      * `use_prebuilt=False` (default) — on-the-fly: load `proxy_mask` (P-00.1,
        already 15 km buffered) + apply focal_max(buffer_km) → effective
        (15 + buffer_km) km exclusion.
    """
    if use_per_type:
        per_type = ee.Image(PER_TYPE_MASK_ASSET).unmask(0)
        if use_urban_mask:
            # combined: clean ↔ industrial-clean AND non-urban
            urban = ee.Image(URBAN_MASK_ASSET).unmask(0)
            return per_type.And(urban).rename("industrial_clean_mask").uint8()
        return per_type
    if use_prebuilt:
        return ee.Image(PREBUILT_MASK_ASSET).unmask(0)
    return (
        ee.Image(INDUSTRIAL_MASK_ASSET)
        .unmask(0)
        .focal_max(radius=buffer_km * 1000, units="meters")
        .Not()
    )


def build_monthly_image(
    gas: str,
    target_year: int,
    target_month: int,
    buffer_km: int,
    use_prebuilt_mask: bool = False,
    use_per_type_mask: bool = False,
    use_urban_mask: bool = False,
) -> ee.Image:
    """
    Per-pixel monthly climatology Image: 3 bands [median, sigma, count].

    Median + MAD × 1.4826 (robust σ-equivalent). DOY window ±1 month from
    `target_month` (RNA §7.1 default 30 days).

    DNA §2.1 запрет 4: для CH₄ no `unmask(0)`. Pixels masked остаются masked.
    """
    gas_meta = GAS_COLLECTIONS[gas]

    # CLAIM 5 fix: select multi-band [target + qa_bands] FIRST, потом apply
    # qa_filter (which sees QA bands intact), потом drop QA via final select.
    bands_for_pipeline = [gas_meta["band"]] + gas_meta.get("qa_bands", [])
    coll = (
        ee.ImageCollection(gas_meta["id"])
        .select(bands_for_pipeline)
        .filter(ee.Filter.calendarRange(2019, target_year - 1, "year"))
        .filter(ee.Filter.calendarRange(target_month - 1, target_month + 1, "month"))
        .map(lambda img: apply_qa_filter(img, gas_meta))
        # Drop QA bands после filter applied — keep only target band для reduce
        .select([gas_meta["band"]])
    )

    # Apply industrial buffer (per-type post-P-01.0d, prebuilt P-01.0b, или on-the-fly).
    # Optionally combined с urban_mask (P-01.0d, TD-0023).
    clean_mask = build_clean_mask(
        buffer_km,
        use_prebuilt=use_prebuilt_mask,
        use_per_type=use_per_type_mask,
        use_urban_mask=use_urban_mask,
    )
    masked_coll = coll.map(lambda img: img.updateMask(clean_mask))

    # Per-pixel reductions
    median_img = masked_coll.reduce(ee.Reducer.median()).rename("median")

    # MAD-based sigma
    def _abs_dev(img: ee.Image) -> ee.Image:
        return img.subtract(median_img).abs()

    mad_img = masked_coll.map(_abs_dev).reduce(ee.Reducer.median()).multiply(1.4826).rename("sigma")

    count_img = masked_coll.count().rename("count")

    return median_img.addBands(mad_img).addBands(count_img)


def launch_monthly_task(
    gas: str,
    target_year: int,
    target_month: int,
    buffer_km: int,
    logger: logging.Logger,
    use_prebuilt_mask: bool = False,
    use_per_type_mask: bool = False,
    use_urban_mask: bool = False,
    provenance: object | None = None,
) -> dict:
    """
    Launch single monthly batch task.

    Per TD-0024 / TD-0025: when `provenance` passed, applies canonical Provenance
    properties natively at Export time (instead of post-hoc setAssetProperties в
    closure scripts). Same Provenance instance flows through entire run.

    Returns dict с {month, task_id, asset_path, state, started_at}.
    """
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    monthly_img = build_monthly_image(
        gas,
        target_year,
        target_month,
        buffer_km,
        use_prebuilt_mask=use_prebuilt_mask,
        use_per_type_mask=use_per_type_mask,
        use_urban_mask=use_urban_mask,
    )

    if use_per_type_mask:
        mask_mode = "per_type_buffered"
    elif use_prebuilt_mask:
        mask_mode = "prebuilt_uniform_30km"
    else:
        mask_mode = "on_the_fly_focal_max"

    metadata = {
        "algorithm_version": "2.3",
        "rna_version": "1.2",
        "build_date": str(date.today()),
        "baseline_type": "regional",
        "baseline_method": "industrial_buffer_exclusion",
        "industrial_buffer_km": "per_type" if use_per_type_mask else 30,
        "mask_mode": mask_mode,
        "urban_mask_applied": use_urban_mask,
        "gas": gas,
        "target_year": target_year,
        "target_month": target_month,
        "history_year_min": 2019,
        "history_year_max": target_year - 1,
        "doy_window_half_days": 30,
        "td_0008_option": "C",
        "build_pipeline": "src/py/setup/build_regional_climatology.py",
    }
    # Native Provenance pattern (TD-0025): caller passes Provenance object;
    # we embed canonical fields так asset gets them at Export time, не post-hoc.
    if provenance is not None:
        metadata = {**metadata, **provenance.to_asset_properties()}
    monthly_img = monthly_img.set(metadata)

    asset_path = TEMP_ASSET_TEMPLATE.format(gas=gas, year=target_year, month=target_month)

    task = ee.batch.Export.image.toAsset(
        image=monthly_img,
        description=f"regional_{gas}_M{target_month:02d}",
        assetId=asset_path,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()

    record = {
        "month": target_month,
        "task_id": task.id,
        "asset_path": asset_path,
        "state": task.status().get("state", "READY"),
        "started_at": time.time(),
    }
    logger.info(
        "M%02d launched: task=%s state=%s asset=%s",
        target_month,
        task.id,
        record["state"],
        asset_path,
    )
    return record


def poll_tasks(tasks: list[dict], timeout_minutes: int, logger: logging.Logger) -> list[dict]:
    """
    Poll all tasks until SUCCEEDED/FAILED/CANCELLED or timeout.

    Updates `tasks` in place with `state` and `error` fields.
    """
    deadline = time.time() + timeout_minutes * 60

    while time.time() < deadline:
        terminal = {"SUCCEEDED", "FAILED", "CANCELLED"}
        state_summary: dict[str, int] = {}

        for t in tasks:
            if t["state"] in terminal:
                state_summary[t["state"]] = state_summary.get(t["state"], 0) + 1
                continue
            try:
                op = ee.data.getOperation(f"projects/{PROJECT_ID}/operations/{t['task_id']}")
                meta = op.get("metadata", {})
                t["state"] = meta.get("state", t["state"])
                if t["state"] == "FAILED":
                    t["error"] = op.get("error", {})
            except Exception as exc:  # pragma: no cover
                logger.warning("Poll error for task %s: %s", t["task_id"], exc)
            state_summary[t["state"]] = state_summary.get(t["state"], 0) + 1

        all_terminal = all(t["state"] in terminal for t in tasks)
        logger.info(
            "Poll status: %s (elapsed %.0fs)",
            state_summary,
            time.time() - tasks[0]["started_at"],
        )
        if all_terminal:
            return tasks
        time.sleep(POLL_INTERVAL_SEC)

    logger.warning("Polling timeout reached (%d min)", timeout_minutes)
    return tasks


def combine_monthly_assets(
    gas: str,
    target_year: int,
    tasks: list[dict],
    logger: logging.Logger,
    provenance: object | None = None,
) -> str | None:
    """
    Combine successful per-month temp assets в final multi-band Image.

    Bands: median_M01..M12, sigma_M01..M12, count_M01..M12 (если есть).
    Failed months skipped.

    Returns final asset_id or None if no successful months.
    """
    successful = [t for t in tasks if t["state"] == "SUCCEEDED"]
    if not successful:
        logger.error("No successful monthly tasks — cannot combine")
        return None

    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    monthly_imgs = []
    for t in successful:
        m = t["month"]
        img = ee.Image(t["asset_path"]).select(
            ["median", "sigma", "count"],
            [f"median_M{m:02d}", f"sigma_M{m:02d}", f"count_M{m:02d}"],
        )
        monthly_imgs.append(img)

    combined = ee.Image.cat(monthly_imgs)

    final_metadata = {
        "algorithm_version": "2.3",
        "rna_version": "1.2",
        "build_date": str(date.today()),
        "baseline_type": "regional",
        "gas": gas,
        "target_year": target_year,
        "history_year_min": 2019,
        "history_year_max": target_year - 1,
        "months_completed": [t["month"] for t in successful],
        "months_failed": [t["month"] for t in tasks if t["state"] != "SUCCEEDED"],
        "td_0008_option_c_outcome": (
            "A_full_success"
            if len(successful) == 12
            else (
                "B_q_mid_reproduced"
                if {2, 5, 8, 11}.issubset({t["month"] for t in tasks if t["state"] != "SUCCEEDED"})
                else "C_partial"
            )
        ),
    }
    # TD-0025: native Provenance applied at Export, не post-hoc.
    if provenance is not None:
        final_metadata = {**final_metadata, **provenance.to_asset_properties()}
    combined = combined.set(final_metadata)

    final_path = FINAL_ASSET_TEMPLATE.format(gas=gas, year=target_year)
    task = ee.batch.Export.image.toAsset(
        image=combined,
        description=f"regional_{gas}_combined",
        assetId=final_path,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    logger.info("Combine task launched: id=%s asset=%s", task.id, final_path)
    return final_path


def cleanup_temp_assets(tasks: list[dict], logger: logging.Logger) -> None:
    """Delete successful temp monthly assets after combine SUCCEEDED."""
    for t in tasks:
        if t["state"] != "SUCCEEDED":
            continue
        try:
            ee.data.deleteAsset(t["asset_path"])
            logger.info("Deleted temp asset: %s", t["asset_path"])
        except ee.EEException as exc:
            logger.warning("Failed to delete %s: %s", t["asset_path"], exc)


def save_state(state: dict, gas: str, year: int) -> Path:
    """Save tasks state JSON для resume."""
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "docs" / f"p-01.0b_state_{gas}_{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return path


def load_state(gas: str, year: int) -> dict | None:
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "docs" / f"p-01.0b_state_{gas}_{year}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gas", required=True, choices=["CH4", "NO2", "SO2"], help="Газ для climatology"
    )
    parser.add_argument(
        "--target-year", type=int, default=2025, help="Target year (history [2019, year-1])"
    )
    parser.add_argument(
        "--buffer-km",
        type=int,
        default=15,
        help="Дополнительный industrial buffer (proxy_mask уже 15 km → effective 30 km).",
    )
    parser.add_argument("--launch-only", action="store_true", help="Launch 12 tasks, no poll")
    parser.add_argument("--poll-only", action="store_true", help="Poll existing state file")
    parser.add_argument("--combine-only", action="store_true", help="Combine existing temp assets")
    parser.add_argument(
        "--task-launch-throttle-sec",
        type=int,
        default=5,
        help="Sleep between task launches (avoid quota burst).",
    )
    parser.add_argument(
        "--months",
        type=str,
        default=None,
        help="Comma-separated list of months to launch (e.g. '6,7,8,9,10,11,12'). "
        "Default — все 12. Use для resubmit subset после partial cancel.",
    )
    parser.add_argument(
        "--serial-wait",
        action="store_true",
        help="После launching each task, poll until COMPLETED перед launching next. "
        "Avoids GEE batch queue parallelism. Slower but guaranteed serial execution.",
    )
    parser.add_argument(
        "--use-prebuilt-mask",
        action="store_true",
        help="Use pre-computed RuPlumeScan/industrial/proxy_mask_buffered_30km Asset "
        "вместо on-the-fly focal_max. ~1.5h faster per gas. См. TD-0011.",
    )
    parser.add_argument(
        "--use-per-type-mask",
        action="store_true",
        help="Use pre-computed RuPlumeScan/industrial/proxy_mask_buffered_per_type "
        "(P-01.0d, TD-0027). Heterogeneous buffers: gas_field 50 km, others 30/15.",
    )
    parser.add_argument(
        "--use-urban-mask",
        action="store_true",
        help="Combine с RuPlumeScan/urban/urban_mask_smod22 (P-01.0d, TD-0023). "
        "AND-merge: clean ↔ industrial-clean AND non-urban.",
    )
    args = parser.parse_args()

    logger = setup_logger()
    ee.Initialize(project=PROJECT_ID)
    logger.info(
        "Earth Engine initialized. Gas=%s target_year=%d buffer_km=%d",
        args.gas,
        args.target_year,
        args.buffer_km,
    )

    # === Canonical Provenance pattern (TD-0024 / TD-0025) ===
    # Compute ONCE at process start; pass through all subsequent operations.
    # Lazy import to keep module-load cheap для tests / poll-only runs.
    from rca.provenance import compute_provenance, write_provenance_log

    cfg = {
        "phase": "P-01.0b" if not args.use_per_type_mask else "P-01.0d",
        "operation": "regional_climatology_build",
        "gas": args.gas,
        "target_year": args.target_year,
        "history_year_min": 2019,
        "history_year_max": args.target_year - 1,
        "doy_window_half_days": 30,
        "aoi_bbox": list(AOI_BBOX),
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "buffer_km_focal_max": args.buffer_km,
        "use_prebuilt_mask": args.use_prebuilt_mask,
        "use_per_type_mask": args.use_per_type_mask,
        "use_urban_mask": args.use_urban_mask,
        "tropomi_collection": GAS_COLLECTIONS[args.gas]["id"],
        "tropomi_band": GAS_COLLECTIONS[args.gas]["band"],
        "qa_filters": {
            "qa_bands": GAS_COLLECTIONS[args.gas].get("qa_bands", []),
            "physical_range": GAS_COLLECTIONS[args.gas].get("physical_range"),
            "negative_floor": GAS_COLLECTIONS[args.gas].get("negative_floor"),
            "cloud_fraction_max": GAS_COLLECTIONS[args.gas].get("cloud_fraction_max"),
        },
        "orchestrator": "TD-0008_Option_C",
        "build_pipeline": "src/py/setup/build_regional_climatology.py",
    }
    period = f"{cfg['history_year_min']}_{cfg['history_year_max'] + 1}"
    provenance = compute_provenance(
        config=cfg,
        config_id="default",
        period=period,
        algorithm_version="2.3",
        rna_version="1.2",
    )
    logger.info(
        "Provenance computed once: run_id=%s params_hash=%s",
        provenance.run_id,
        provenance.params_hash[:8],
    )

    if args.poll_only or args.combine_only:
        state = load_state(args.gas, args.target_year)
        if state is None:
            logger.error("No saved state for %s/%d", args.gas, args.target_year)
            return 1
        tasks = state["tasks"]
    else:
        ensure_temp_folder(logger)

        if args.months:
            months_to_run = [int(m.strip()) for m in args.months.split(",")]
        else:
            months_to_run = list(range(1, 13))
        logger.info(
            "=== Launching %d tasks (mode: %s, prebuilt_mask=%s) ===",
            len(months_to_run),
            "serial-wait" if args.serial_wait else "parallel-batch",
            args.use_prebuilt_mask,
        )

        # Resume mode: load existing state, append new months only
        existing_state = load_state(args.gas, args.target_year)
        if existing_state and isinstance(existing_state.get("tasks"), list):
            tasks = existing_state["tasks"]
            existing_months = {t["month"] for t in tasks}
            new_months = [m for m in months_to_run if m not in existing_months]
            if new_months != months_to_run:
                logger.info(
                    "Resume — already in state: %s; appending: %s",
                    sorted(existing_months),
                    new_months,
                )
            months_to_run = new_months
        else:
            tasks = []

        # Write STARTED log entry once, before submitting any tasks
        write_provenance_log(
            provenance,
            status="STARTED",
            gas=args.gas,
            period=period,
            asset_id=FINAL_ASSET_TEMPLATE.format(gas=args.gas, year=args.target_year),
            extra={
                "phase": cfg["phase"],
                "n_months_to_launch": len(months_to_run),
                "operation": "regional_climatology_build",
            },
        )

        for i, m in enumerate(months_to_run):
            record = launch_monthly_task(
                args.gas,
                args.target_year,
                m,
                args.buffer_km,
                logger,
                use_prebuilt_mask=args.use_prebuilt_mask,
                use_per_type_mask=args.use_per_type_mask,
                use_urban_mask=args.use_urban_mask,
                provenance=provenance,
            )
            tasks.append(record)
            save_state(
                {"tasks": tasks, "gas": args.gas, "year": args.target_year},
                args.gas,
                args.target_year,
            )

            if args.serial_wait:
                logger.info("M%02d submitted; waiting for COMPLETED перед следующим...", m)
                op_name = f"projects/{PROJECT_ID}/operations/{record['task_id']}"
                while True:
                    op = ee.data.getOperation(op_name)
                    state_now = op.get("metadata", {}).get("state", "")
                    if state_now in ("SUCCEEDED", "FAILED", "CANCELLED"):
                        record["state"] = state_now
                        if state_now == "FAILED":
                            record["error"] = op.get("error", {})
                        save_state(
                            {"tasks": tasks, "gas": args.gas, "year": args.target_year},
                            args.gas,
                            args.target_year,
                        )
                        logger.info("M%02d %s -- proceeding к next", m, state_now)
                        break
                    time.sleep(120)
            elif i < len(months_to_run) - 1:
                time.sleep(args.task_launch_throttle_sec)

    if args.launch_only:
        logger.info("--launch-only: stopping after launches. Use --poll-only to resume.")
        return 0

    if not args.combine_only:
        logger.info("=== Polling 12 monthly tasks (timeout %d min) ===", POLL_TIMEOUT_MINUTES)
        tasks = poll_tasks(tasks, POLL_TIMEOUT_MINUTES, logger)
        save_state(
            {"tasks": tasks, "gas": args.gas, "year": args.target_year}, args.gas, args.target_year
        )

    # Outcome summary
    succeeded = [t for t in tasks if t["state"] == "SUCCEEDED"]
    failed = [t for t in tasks if t["state"] == "FAILED"]
    other = [t for t in tasks if t["state"] not in ("SUCCEEDED", "FAILED")]

    logger.info("=" * 60)
    logger.info("TD-0008 Option C outcome summary для %s:", args.gas)
    logger.info("  SUCCEEDED: %d/12 — months %s", len(succeeded), [t["month"] for t in succeeded])
    logger.info("  FAILED:    %d/12 — months %s", len(failed), [t["month"] for t in failed])
    if other:
        logger.info(
            "  OTHER:     %d/12 — states %s", len(other), {t["month"]: t["state"] for t in other}
        )
    failed_months = {t["month"] for t in failed}
    q_mid = {2, 5, 8, 11}
    if len(succeeded) == 12:
        outcome = "A — FULL SUCCESS (Option C confirmed solution)"
    elif q_mid.issubset(failed_months):
        outcome = "B — Q-mid pattern reproduced (Option C REJECTED)"
    elif failed:
        outcome = "C — partial (mixed pattern)"
    else:
        outcome = "indeterminate (some non-terminal states)"
    logger.info("  -> Outcome: %s", outcome)
    logger.info("=" * 60)

    if args.combine_only or len(succeeded) > 0:
        logger.info("=== Combining %d successful monthly assets ===", len(succeeded))
        final_path = combine_monthly_assets(
            args.gas, args.target_year, tasks, logger, provenance=provenance
        )
        if final_path:
            logger.info("Final asset export task started: %s", final_path)
            logger.info(
                "После combine SUCCEEDED — run with --combine-only re-tries cleanup if needed"
            )
            # Write SUCCEEDED log entry с canonical Provenance (TD-0024 pattern)
            write_provenance_log(
                provenance,
                status="SUCCEEDED" if len(succeeded) == 12 else "PARTIAL",
                gas=args.gas,
                period=period,
                asset_id=final_path,
                extra={
                    "phase": cfg["phase"],
                    "n_succeeded": len(succeeded),
                    "n_failed": len(failed),
                    "td_0008_outcome": outcome,
                    "operation": "regional_climatology_build",
                    "mask_mode": (
                        "per_type_with_urban"
                        if args.use_per_type_mask and args.use_urban_mask
                        else (
                            "per_type"
                            if args.use_per_type_mask
                            else "uniform_30km_prebuilt" if args.use_prebuilt_mask else "on_the_fly"
                        )
                    ),
                },
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
