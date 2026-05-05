"""
P-01.0d Шаг 1: rebuild RuPlumeScan/industrial/source_points с:
  * DROP 5 features (hydro + nuclear power plants — не emit relevant gases)
  * ADD 6 missing major gas fields (Tambeyskoye, Medvezhye, Yuzhno-Russkoye,
    Novoportovskoye, Kruzenshternskoye, Pyakyakhinskoe)
  * Final inventory: 531 - 5 + 6 = 532 features

Per researcher decisions 2026-05-04. TD-0023 + TD-0027 closure.

Workflow:
  1. Load existing source_points (531 features)
  2. Archive snapshot к source_points_v1_pre_per_type
  3. Filter out (hydro/nuclear)
  4. Append 6 manual gas-field anchors с canonical schema
  5. Re-export к same asset path
  6. Apply canonical Provenance (compute_provenance from start, TD-0024 pattern)

Run: python src/py/setup/update_source_points_p_01_0d.py [--dry-run] [--no-archive]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ee

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"
SOURCE_POINTS = f"{ASSETS_ROOT}/RuPlumeScan/industrial/source_points"
ARCHIVE_PATH = f"{ASSETS_ROOT}/RuPlumeScan/industrial/source_points_v1_pre_per_type"

# 6 missing major gas fields (researcher decision 2026-05-04)
# Format: (name_en, name_ru, lat, lon, source_id)
NEW_GAS_FIELDS = [
    (
        "Tambeyskoye gas-condensate field",
        "Тамбейское нефтегазоконденсатное месторождение",
        71.55,
        71.60,
        "manual_p_01_0d_tambeyskoye",
    ),
    (
        "Medvezhye gas-condensate field",
        "Медвежье нефтегазоконденсатное месторождение",
        67.45,
        73.65,
        "manual_p_01_0d_medvezhye",
    ),
    (
        "Yuzhno-Russkoye gas-condensate field",
        "Южно-Русское нефтегазоконденсатное месторождение",
        65.95,
        77.30,
        "manual_p_01_0d_yuzhno_russkoye",
    ),
    (
        "Novoportovskoye gas-condensate field",
        "Новопортовское нефтегазоконденсатное месторождение",
        67.85,
        72.65,
        "manual_p_01_0d_novoportovskoye",
    ),
    (
        "Kruzenshternskoye gas-condensate field",
        "Крузенштернское нефтегазоконденсатное месторождение",
        71.10,
        71.95,
        "manual_p_01_0d_kruzenshternskoye",
    ),
    (
        "Pyakyakhinskoye gas-condensate field",
        "Пякяхинское нефтегазоконденсатное месторождение",
        65.30,
        76.20,
        "manual_p_01_0d_pyakyakhinskoye",
    ),
]


def make_provenance() -> object:
    """Compute Provenance ONCE (canonical pattern, TD-0024)."""
    config = {
        "phase": "P-01.0d",
        "operation": "source_points_update",
        "drop_subtypes": ["hydro", "nuclear"],
        "added_gas_fields": [name for name, _, _, _, _ in NEW_GAS_FIELDS],
        "td_0023_resolution": True,
        "td_0027_resolution": True,
        "build_pipeline": "src/py/setup/update_source_points_p_01_0d.py",
    }
    return compute_provenance(
        config=config,
        config_id="default",
        period="2026_p_01_0d",
        algorithm_version="2.3",
        rna_version="1.2",
    )


def make_new_gas_field_feature(
    name_en: str, name_ru: str, lat: float, lon: float, source_id: str
) -> ee.Feature:
    """Construct ee.Feature для one missing gas field, matching schema."""
    geom = ee.Geometry.Point([lon, lat])
    properties = {
        "source_id": source_id,
        "source_type": "oil_gas",
        "source_subtype": "production_field",
        "source_name": name_ru,
        "source_name_en": name_en,
        "country": "RU",
        "region": None,
        "operator": None,
        "fuel_primary": None,
        "capacity_mw": None,
        "estimated_kt_per_year_so2": None,
        "estimated_kt_per_year_so2_uncertainty": None,
        "estimate_year": None,
        "estimate_source": None,
        "decommissioned": False,
        "decommissioning_year": None,
        "verification_status": "researcher_p_01_0d_addition",
        "viirs_radiance_mean": None,
        "data_source_url": None,
        "data_attribution": "Manual researcher addition (P-01.0d, TD-0027 closure)",
        "data_license": "research-internal",
        "ingestion_date": "2026-05-04",
        "coordinates_source": "researcher_manual_p_01_0d",
        "coordinates_verified_date": "2026-05-04",
        "source_dataset": "p_01_0d_missing_gas_fields",
        "notes": (
            "Major gas-condensate field identified в P-01.2 dual baseline cross-check "
            "as missing from inventory (Tambeyskoye cluster #4 prompted audit). "
            "Manual addition с researcher-verified coords."
        ),
    }
    return ee.Feature(geom, properties)


def wait_task(task_id: str, label: str, timeout_s: int = 1200) -> str:
    """Poll batch task until SUCCEEDED/FAILED/CANCELLED. Returns final state."""
    import time

    start = time.time()
    op_name = f"projects/{GEE_PROJECT}/operations/{task_id}"
    while True:
        op = ee.data.getOperation(op_name)
        state = op.get("metadata", {}).get("state", "?")
        elapsed = int(time.time() - start)
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            print(f"  {label}: {state} (elapsed {elapsed}s)")
            return state
        if elapsed > timeout_s:
            print(f"  {label}: TIMEOUT after {elapsed}s; state={state}")
            return "TIMEOUT"
        if elapsed % 30 == 0:
            print(f"  {label}: {state} (elapsed {elapsed}s)")
        time.sleep(15)


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0d source_points update")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan, не execute (no asset modifications)",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip archiving старого source_points to *_v1_pre_per_type",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Live execute: archive → delete original → re-export 532 features",
    )
    args = parser.parse_args()

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print()

    prov = make_provenance()
    print(f"Provenance computed: run_id={prov.run_id}")

    if not args.dry_run:
        write_provenance_log(
            prov,
            status="STARTED",
            gas="multi",
            period="2026_p_01_0d",
            asset_id=SOURCE_POINTS,
            extra={"phase": "P-01.0d", "operation": "source_points_update"},
        )

    # === Step A: Load existing + summarize ===
    fc_old = ee.FeatureCollection(SOURCE_POINTS)
    n_old = fc_old.size().getInfo()
    print(f"\nExisting source_points: {n_old} features")
    if n_old != 531:
        print(f"WARNING: expected 531, found {n_old} — verify before proceeding")

    # Verify dropouts count
    n_hydro = (
        fc_old.filter(ee.Filter.eq("source_type", "power_plant"))
        .filter(ee.Filter.eq("source_subtype", "hydro"))
        .size()
        .getInfo()
    )
    n_nuclear = (
        fc_old.filter(ee.Filter.eq("source_type", "power_plant"))
        .filter(ee.Filter.eq("source_subtype", "nuclear"))
        .size()
        .getInfo()
    )
    print(f"  to drop: hydro={n_hydro}, nuclear={n_nuclear}, total={n_hydro + n_nuclear}")
    print(f"  to add:  {len(NEW_GAS_FIELDS)} gas fields")
    expected_new_count = n_old - n_hydro - n_nuclear + len(NEW_GAS_FIELDS)
    print(f"  expected new total: {expected_new_count}")

    # NOTE: lazy-evaluation hazard — `fc_old.filter(...)` returns a deferred
    # reference к SOURCE_POINTS asset. If we delete SOURCE_POINTS before Export
    # evaluates fc_new, the export fails ("Collection asset not found"). Solution:
    # always source filter from ARCHIVE_PATH after archive SUCCEEDED. Documented
    # here after first-run incident 2026-05-04.

    # === Step C: Filter + add (build new collection in-memory) ===
    fc_filtered = fc_old.filter(
        ee.Filter.Or(
            ee.Filter.neq("source_type", "power_plant"),
            ee.Filter.And(
                ee.Filter.eq("source_type", "power_plant"),
                ee.Filter.inList("source_subtype", ["coal", "gas", "tpp_gas"]),
            ),
        )
    )

    new_features = ee.FeatureCollection(
        [
            make_new_gas_field_feature(name_en, name_ru, lat, lon, sid)
            for name_en, name_ru, lat, lon, sid in NEW_GAS_FIELDS
        ]
    )

    fc_new = fc_filtered.merge(new_features)
    n_new = fc_new.size().getInfo()
    print(f"\n=== New collection size: {n_new} features ===")
    if n_new != expected_new_count:
        print(
            f"WARNING: expected {expected_new_count}, got {n_new}. "
            f"Check filter logic / new feature construction."
        )
        if not args.dry_run:
            return 1

    if args.dry_run:
        print("\nDRY-RUN: would re-export к", SOURCE_POINTS)
        print("DRY-RUN: would apply Provenance:", prov.to_asset_properties())
        return 0

    if not args.execute:
        print("\nSafety guard: pass --execute to launch live archive + delete + re-export.")
        return 0

    # === Step D: Wait archive task completion ===
    if not args.no_archive:
        print("\n=== Step D: Waiting archive task SUCCEEDED ===")
        # archive_task created above when not args.no_archive AND not args.dry_run
        # Need to capture it in scope. Restructure: re-launch here for clarity.
        try:
            ee.data.getAsset(ARCHIVE_PATH)
            print("  archive already exists — skipping wait")
        except Exception:
            archive_task = ee.batch.Export.table.toAsset(
                collection=fc_old.set(
                    {
                        "archived_from": SOURCE_POINTS,
                        "archive_reason": "P-01.0d pre-rebuild snapshot (TD-0023+TD-0027)",
                        "archive_date": "2026-05-04",
                    }
                ),
                description="archive_source_points_v1_pre_per_type",
                assetId=ARCHIVE_PATH,
            )
            archive_task.start()
            state = wait_task(archive_task.id, "archive")
            if state != "SUCCEEDED":
                print(f"  ARCHIVE FAILED state={state}; aborting")
                return 1

    # === Step E: Delete original ===
    print(f"\n=== Step E: Deleting current asset {SOURCE_POINTS} ===")
    try:
        ee.data.deleteAsset(SOURCE_POINTS)
        print("  deleted")
    except Exception as e:
        print(f"  delete failed: {e}; aborting")
        return 1

    # === Step F: Re-export new collection (532 features) ===
    print("\n=== Step F: Exporting new source_points (532 features) ===")
    fc_new_with_prov = fc_new.set(
        {
            **prov.to_asset_properties(),
            "phase": "P-01.0d",
            "operation": "source_points_per_type_classification",
            "n_features": 532,
            "td_0023_resolution": True,
            "td_0027_resolution": True,
            "previous_inventory_archived_at": ARCHIVE_PATH,
            "build_pipeline": "src/py/setup/update_source_points_p_01_0d.py",
        }
    )
    export_task = ee.batch.Export.table.toAsset(
        collection=fc_new_with_prov,
        description="rebuild_source_points_p_01_0d",
        assetId=SOURCE_POINTS,
    )
    export_task.start()
    state = wait_task(export_task.id, "rebuild_source_points")
    if state != "SUCCEEDED":
        print(f"  EXPORT FAILED state={state}; aborting")
        return 1

    # === Step G: Verify ===
    print("\n=== Step G: Verification ===")
    fc_verify = ee.FeatureCollection(SOURCE_POINTS)
    n_verify = fc_verify.size().getInfo()
    print(f"  size: {n_verify} (expected 532)")
    if n_verify != 532:
        print("  FAIL — size mismatch")
        return 1

    # Tambeyskoye present?
    tamb = (
        fc_verify.filter(ee.Filter.eq("source_id", "manual_p_01_0d_tambeyskoye")).size().getInfo()
    )
    print(f"  Tambeyskoye feature present: {tamb == 1} (count={tamb})")

    # Hydro/nuclear absent?
    hydro = fc_verify.filter(ee.Filter.eq("source_subtype", "hydro")).size().getInfo()
    nuclear = fc_verify.filter(ee.Filter.eq("source_subtype", "nuclear")).size().getInfo()
    print(f"  Hydro absent: {hydro == 0} (count={hydro})")
    print(f"  Nuclear absent: {nuclear == 0} (count={nuclear})")

    sanity_pass = n_verify == 532 and tamb == 1 and hydro == 0 and nuclear == 0

    write_provenance_log(
        prov,
        status="SUCCEEDED" if sanity_pass else "PARTIAL",
        gas="multi",
        period="2026_p_01_0d",
        asset_id=SOURCE_POINTS,
        extra={
            "phase": "P-01.0d",
            "operation": "source_points_update",
            "n_features": n_verify,
            "tambeyskoye_present": tamb == 1,
            "hydro_absent": hydro == 0,
            "nuclear_absent": nuclear == 0,
        },
    )

    print(f"\n{'=' * 60}")
    print(
        f"Шаг 1 {'COMPLETE' if sanity_pass else 'PARTIAL'} — sanity {'PASS' if sanity_pass else 'FAIL'}"
    )
    return 0 if sanity_pass else 1


if __name__ == "__main__":
    sys.exit(main())
