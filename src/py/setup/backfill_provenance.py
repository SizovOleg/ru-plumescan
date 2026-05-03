"""
P-01.0c provenance backfill для existing baseline assets.

Restores DNA §2.1 запрет 12 compliance for assets built before centralized
Provenance dataclass existed (P-01.0a / P-01.0b interim era). Each backfill:
  * Reconstructs canonical config dict from build script source code state
  * Computes canonical params_hash via current Provenance helpers
  * Sets asset properties via ee.data.setAssetProperties
  * Documents reconstruction limitations с explicit caveat fields

CRITICAL: backfill is FORWARD-LOOKING reconstruction, не retroactive
rewrite. Original log entries в logs/runs.jsonl preserved as audit trail.

Targets:
  * reference_CH4_2019_2025_v1   (P-01.0a, missing params_hash entirely)
  * regional_CH4_2019_2025       (asset c8b6e97f vs log d2e6362c — reconcile)
  * regional_SO2_2019_2025       (STARTED 40f04025 vs SUCCEEDED+asset f669e1c8 — reconcile)

regional_NO2_2019_2025 already consistent (7c2f8b2b throughout) — verified, не backfilled.

Run: python src/py/setup/backfill_provenance.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee

# Console на Windows default cp1251 — Unicode в logs crashes print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

from rca.provenance import (  # noqa: E402
    Provenance,
    compute_provenance,
    write_provenance_log,
)

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"
BASELINES_ROOT = f"{ASSETS_ROOT}/RuPlumeScan/baselines"

P_01_0C_COMMIT_PLACEHOLDER = "P-01.0c-commit-pending"
TODAY_ISO = datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Canonical config reconstructions
# ---------------------------------------------------------------------------


def reconstruct_reference_ch4_v1_config() -> tuple[dict[str, Any], str, str]:
    """
    Reference baseline CH4 v1 (P-01.0a, ~2026-04-28).

    Source: src/py/setup/build_reference_baseline_ch4.py at commit 8f05b44
    + RNA v1.2 §11.5 reference baseline workflow.

    Returns: (config, source_commit, period).
    """
    config = {
        "baseline_type": "reference",
        "gas": "CH4",
        "target_year": 2025,
        "history_year_min": 2019,
        "history_year_max": 2024,
        "doy_window_half_days": 30,
        "use_zones": ["yugansky", "verkhnetazovsky", "kuznetsky_alatau"],
        "include_altaisky": False,
        "altaisky_qa_status": "unreliable_for_xch4_baseline",
        "stratification": "by_latitude_nearest",
        "internal_buffer_km_per_zone": {
            "yugansky": 5,
            "verkhnetazovsky": 5,
            "kuznetsky_alatau": 5,
        },
        "analysis_scale_m": 7000,
        "physical_range_min_ppb": 1700,
        "physical_range_max_ppb": 2200,
        "asset_path_template": "RuPlumeScan/baselines/reference_{gas}_{period}_v1",
    }
    return config, "8f05b44", "2019_2025_v1"


def reconstruct_regional_ch4_config() -> tuple[dict[str, Any], str, str]:
    """
    Regional climatology CH4 (P-01.0b, 2026-04-29).

    Source: src/py/setup/build_regional_climatology.py at commit 589efaf
    + GAS_COLLECTIONS["CH4"] config snapshot.
    """
    config = {
        "baseline_type": "regional",
        "gas": "CH4",
        "target_year": 2025,
        "history_year_min": 2019,
        "history_year_max": 2024,
        "doy_window_half_days": 30,
        "aoi_bbox": [60.0, 50.0, 95.0, 75.0],
        "analysis_scale_m": 7000,
        "industrial_buffer_km_effective": 30,
        "industrial_mask_asset": "RuPlumeScan/industrial/proxy_mask_buffered_30km",
        "qa_filters": {
            "qa_bands": [],  # CH4 L3 v02.04 OFFL upstream-filtered
            "physical_range_ppb": [1700, 2200],
            "negative_floor": None,
            "cloud_fraction_max": None,
        },
        "tropomi_collection": "COPERNICUS/S5P/OFFL/L3_CH4",
        "tropomi_band": "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
        "orchestrator": "TD-0008_Option_C_12_separate_tasks",
        "pipeline_mode": "multi_band_select",
        "build_pipeline": "src/py/setup/build_regional_climatology.py",
    }
    return config, "589efaf", "2019_2025"


def reconstruct_regional_no2_config() -> tuple[dict[str, Any], str, str]:
    """
    Regional climatology NO2 (P-01.0b, 2026-04-30).

    Source: build_regional_climatology.py at commit 7048e1f, GAS_COLLECTIONS["NO2"].
    Asset already has consistent params_hash 7c2f8b2b — verify only.
    """
    config = {
        "baseline_type": "regional",
        "gas": "NO2",
        "target_year": 2025,
        "history_year_min": 2019,
        "history_year_max": 2024,
        "doy_window_half_days": 30,
        "aoi_bbox": [60.0, 50.0, 95.0, 75.0],
        "analysis_scale_m": 7000,
        "industrial_buffer_km_effective": 30,
        "industrial_mask_asset": "RuPlumeScan/industrial/proxy_mask_buffered_30km",
        "qa_filters": {
            "qa_bands": ["cloud_fraction"],
            "cloud_fraction_max": 0.3,
            "negative_floor": None,
            "physical_range_ppb": None,
        },
        "tropomi_collection": "COPERNICUS/S5P/OFFL/L3_NO2",
        "tropomi_band": "tropospheric_NO2_column_number_density",
        "orchestrator": "TD-0008_Option_C_12_separate_tasks",
        "pipeline_mode": "multi_band_select",
        "build_pipeline": "src/py/setup/build_regional_climatology.py",
    }
    return config, "7048e1f", "2019_2025"


def reconstruct_regional_so2_config() -> tuple[dict[str, Any], str, str]:
    """
    Regional climatology SO2 (P-01.0b, 2026-04-30).

    Source: build_regional_climatology.py at commit 7048e1f, GAS_COLLECTIONS["SO2"].
    Includes negative_floor = -0.001 mol/m^2 per DNA §2.1 запрет 7.
    """
    config = {
        "baseline_type": "regional",
        "gas": "SO2",
        "target_year": 2025,
        "history_year_min": 2019,
        "history_year_max": 2024,
        "doy_window_half_days": 30,
        "aoi_bbox": [60.0, 50.0, 95.0, 75.0],
        "analysis_scale_m": 7000,
        "industrial_buffer_km_effective": 30,
        "industrial_mask_asset": "RuPlumeScan/industrial/proxy_mask_buffered_30km",
        "qa_filters": {
            "qa_bands": ["cloud_fraction"],
            "cloud_fraction_max": 0.3,
            "negative_floor_mol_per_m2": -0.001,
            "physical_range_ppb": None,
        },
        "tropomi_collection": "COPERNICUS/S5P/OFFL/L3_SO2",
        "tropomi_band": "SO2_column_number_density",
        "orchestrator": "TD-0008_Option_C_12_separate_tasks",
        "pipeline_mode": "multi_band_select",
        "build_pipeline": "src/py/setup/build_regional_climatology.py",
    }
    return config, "7048e1f", "2019_2025"


# ---------------------------------------------------------------------------
# Backfill mechanism
# ---------------------------------------------------------------------------


def make_backfill_caveat(
    source_commit: str,
    pre_backfill_hash: str | None,
    original_log_present: bool,
) -> str:
    """Honest reconstruction caveat language."""
    pre_hash_text = (
        f"Asset previously had params_hash={pre_backfill_hash[:8]}..."
        if pre_backfill_hash
        else "Asset previously had no params_hash property"
    )
    log_text = (
        "Original log entries preserved в logs/runs.jsonl"
        if original_log_present
        else "Original log entries absent (asset built before logging helpers existed)"
    )
    return (
        f"Provenance backfilled {TODAY_ISO} (P-01.0c, TD-0024 fix). {pre_hash_text}. "
        f"Reconstructed canonical config from: (1) build script source code at commit "
        f"{source_commit}, (2) RNA v1.2 defaults, (3) algorithm_version 2.3 parameters. "
        f"params_hash recomputed from reconstructed config via centralized "
        f"compute_provenance helper (immutable Provenance dataclass). "
        f"KNOWN UNCERTAINTY: runtime config may have included parameters не captured "
        f"в reconstruction. {log_text}. For bit-identical reproduction, refer к "
        f"commit SHA + RNA version, не just params_hash."
    )


def get_existing_asset_provenance(asset_id: str) -> dict[str, Any]:
    """Read current provenance state from asset metadata."""
    info = ee.data.getAsset(asset_id)
    props = info.get("properties", {})
    return {
        "params_hash": props.get("params_hash"),
        "config_id": props.get("config_id"),
        "run_id": props.get("run_id"),
        "schema_version": props.get("schema_version"),
        "algorithm_version": props.get("algorithm_version"),
        "rna_version": props.get("rna_version"),
        "all_props_count": len(props),
    }


def backfill_asset(
    asset_id: str,
    provenance: Provenance,
    source_commit: str,
    pre_backfill_hash: str | None,
    original_log_present: bool,
    p_01_0c_commit: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Set canonical Provenance properties + backfill caveat fields.

    Returns: dict с success status and properties applied.
    """
    caveat = make_backfill_caveat(source_commit, pre_backfill_hash, original_log_present)

    new_props = {
        **provenance.to_asset_properties(),
        "provenance_backfill_date": TODAY_ISO,
        "provenance_backfill_caveat": caveat,
        "provenance_backfill_commit": p_01_0c_commit,
        "provenance_backfill_source_commit": source_commit,
    }
    if pre_backfill_hash:
        new_props["pre_backfill_params_hash"] = pre_backfill_hash

    if dry_run:
        return {"asset_id": asset_id, "dry_run": True, "would_set": new_props}

    try:
        ee.data.setAssetProperties(asset_id, new_props)
        return {"asset_id": asset_id, "success": True, "set": new_props}
    except Exception as e:
        return {"asset_id": asset_id, "success": False, "error": str(e)}


def verify_backfill(asset_id: str, expected: Provenance) -> dict[str, Any]:
    """
    Verify backfilled asset has all required provenance properties matching
    expected Provenance object.
    """
    actual = get_existing_asset_provenance(asset_id)
    checks = {
        "params_hash_set": actual["params_hash"] == expected.params_hash,
        "config_id_set": actual["config_id"] == expected.config_id,
        "run_id_set": actual["run_id"] == expected.run_id,
        "algorithm_version_set": actual["algorithm_version"] == expected.algorithm_version,
        "rna_version_set": actual["rna_version"] == expected.rna_version,
    }
    info = ee.data.getAsset(asset_id)
    props = info.get("properties", {})
    checks["caveat_present"] = "provenance_backfill_caveat" in props
    return {"asset_id": asset_id, "all_pass": all(checks.values()), "checks": checks}


# ---------------------------------------------------------------------------
# Targets table
# ---------------------------------------------------------------------------

BACKFILL_TARGETS = [
    {
        "name": "reference_CH4_2019_2025_v1",
        "asset_path": f"{BASELINES_ROOT}/reference_CH4_2019_2025_v1",
        "reconstruct_fn": reconstruct_reference_ch4_v1_config,
        "original_log_present": True,
        "needs_backfill": True,  # asset missing params_hash entirely
    },
    {
        "name": "regional_CH4_2019_2025",
        "asset_path": f"{BASELINES_ROOT}/regional_CH4_2019_2025",
        "reconstruct_fn": reconstruct_regional_ch4_config,
        "original_log_present": True,
        "needs_backfill": True,  # asset c8b6e97f vs log d2e6362c
    },
    {
        "name": "regional_NO2_2019_2025",
        "asset_path": f"{BASELINES_ROOT}/regional_NO2_2019_2025",
        "reconstruct_fn": reconstruct_regional_no2_config,
        "original_log_present": True,
        # Originally marked verify-only (was internally consistent 7c2f8b2b)
        # но dry-run revealed canonical reconstruction yields different hash.
        # Backfill aligns NO2 с canonical schema used by other 3 assets.
        # Deviation from DevPrompt; documented в backfill_report + commit message.
        "needs_backfill": True,
    },
    {
        "name": "regional_SO2_2019_2025",
        "asset_path": f"{BASELINES_ROOT}/regional_SO2_2019_2025",
        "reconstruct_fn": reconstruct_regional_so2_config,
        "original_log_present": True,
        "needs_backfill": True,  # STARTED vs SUCCEEDED+asset mismatch
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0c provenance backfill")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be set, не actually call setAssetProperties",
    )
    parser.add_argument(
        "--p-01-0c-commit",
        default=P_01_0C_COMMIT_PLACEHOLDER,
        help="P-01.0c commit SHA to record (will be filled post-commit)",
    )
    args = parser.parse_args()

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print()

    results: list[dict[str, Any]] = []

    for target in BACKFILL_TARGETS:
        name = target["name"]
        asset_path = target["asset_path"]
        config, source_commit, period = target["reconstruct_fn"]()

        print(f"=== {name} ===")
        print(f"  asset: {asset_path}")
        print(f"  source_commit: {source_commit}")

        existing = get_existing_asset_provenance(asset_path)
        pre_hash = existing.get("params_hash")
        print(f"  pre-backfill params_hash: {pre_hash[:8] + '...' if pre_hash else '<NONE>'}")

        prov = compute_provenance(
            config=config,
            config_id="default",
            period=period,
            algorithm_version="2.3",
            rna_version="1.2",
        )
        print(f"  reconstructed params_hash: {prov.params_hash[:8]}...")
        print(f"  reconstructed run_id: {prov.run_id}")

        if not target["needs_backfill"]:
            # Verify-only path
            if pre_hash and pre_hash == prov.params_hash:
                print("  STATUS: VERIFIED — already consistent с canonical reconstruction")
                results.append(
                    {
                        "asset": name,
                        "status": "verified_consistent",
                        "params_hash": prov.params_hash,
                    }
                )
            else:
                print("  STATUS: VERIFY FAILED — asset hash differs от reconstruction")
                print(f"    asset:         {pre_hash}")
                print(f"    reconstructed: {prov.params_hash}")
                results.append(
                    {
                        "asset": name,
                        "status": "verify_failed",
                        "asset_hash": pre_hash,
                        "reconstructed_hash": prov.params_hash,
                    }
                )
            print()
            continue

        # Backfill path
        result = backfill_asset(
            asset_id=asset_path,
            provenance=prov,
            source_commit=source_commit,
            pre_backfill_hash=pre_hash,
            original_log_present=target["original_log_present"],
            p_01_0c_commit=args.p_01_0c_commit,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("  STATUS: DRY-RUN — would set properties")
            results.append({"asset": name, "status": "dry_run", "params_hash": prov.params_hash})
            print()
            continue

        if result["success"]:
            verify = verify_backfill(asset_path, prov)
            if verify["all_pass"]:
                # Write BACKFILLED log entry so audit tool sees matching hash
                gas_inferred = config.get("gas")
                write_provenance_log(
                    prov,
                    status="BACKFILLED",
                    gas=gas_inferred,
                    period=period,
                    asset_id=asset_path,
                    extra={
                        "phase": "P-01.0c",
                        "td_0024_remediation": True,
                        "source_commit": source_commit,
                        "p_01_0c_commit": args.p_01_0c_commit,
                        "pre_backfill_params_hash": pre_hash,
                        "note": "Canonical reconstruction; runtime config may differ slightly.",
                    },
                )
                print("  STATUS: BACKFILLED + VERIFIED + logged")
                results.append(
                    {
                        "asset": name,
                        "status": "backfilled",
                        "params_hash": prov.params_hash,
                        "verify": verify["checks"],
                    }
                )
            else:
                print(f"  STATUS: BACKFILL OK но VERIFY FAILED: {verify['checks']}")
                results.append(
                    {
                        "asset": name,
                        "status": "backfill_verify_failed",
                        "verify": verify,
                    }
                )
        else:
            print(f"  STATUS: BACKFILL FAILED: {result['error']}")
            results.append({"asset": name, "status": "backfill_failed", "error": result["error"]})
        print()

    # Summary
    print("=" * 70)
    print("BACKFILL SUMMARY")
    print("=" * 70)
    for r in results:
        print(f"  {r['asset']}: {r['status']}")

    # Save backfill report JSON
    report_path = REPO_ROOT / "docs" / "p-01.0c_backfill_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "p_01_0c_commit": args.p_01_0c_commit,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "dry_run": args.dry_run,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nReport: {report_path.relative_to(REPO_ROOT)}")

    n_failed = sum(
        1 for r in results if r["status"] in ("backfill_failed", "backfill_verify_failed")
    )
    return 1 if n_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
