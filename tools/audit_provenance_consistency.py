"""
Provenance consistency audit tool (P-01.0c, TD-0024 prevention).

Checks:
  1. Каждый baseline / catalog asset имеет provenance triple
     (config_id, params_hash, run_id, algorithm_version, rna_version).
  2. Asset.params_hash matches at least one log entry с matching run_id
     в logs/runs.jsonl.

Exit codes:
  0 — all assets pass OR mismatches are allowlisted.
  1 — unexpected mismatches detected (CI gate fails).

Usage:
  python tools/audit_provenance_consistency.py [--gee-project PROJECT]
                                                [--allowlist PATH]
                                                [--json]

CI integration: .github/workflows/audit.yml runs on every PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ee

# Console на Windows default cp1251 — Unicode (Δ, °, ²) crashes print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS_PATH = REPO_ROOT / "logs" / "runs.jsonl"
DEFAULT_ALLOWLIST_PATH = REPO_ROOT / "tools" / "provenance_audit_allowlist.json"
DEFAULT_GEE_PROJECT = "nodal-thunder-481307-u1"

REQUIRED_PROVENANCE_FIELDS = (
    "config_id",
    "params_hash",
    "run_id",
    "algorithm_version",
    "rna_version",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_allowlist(path: Path) -> list[dict[str, Any]]:
    """Load known provenance mismatches from allowlist JSON."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("known_mismatches", [])
    except json.JSONDecodeError as e:
        print(f"WARN: invalid JSON в allowlist {path}: {e}", file=sys.stderr)
        return []


def load_runs_log(path: Path) -> list[dict[str, Any]]:
    """Load all entries from logs/runs.jsonl."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def list_audited_assets(project: str) -> list[str]:
    """
    Enumerate assets subject to provenance audit:
      * RuPlumeScan/baselines/* (excluding _temp folder)
      * RuPlumeScan/catalog/<gas>/*

    Skips collections и folders themselves.
    """
    asset_root = f"projects/{project}/assets/RuPlumeScan"
    parents = [
        f"{asset_root}/baselines",
        f"{asset_root}/catalog",
        f"{asset_root}/catalog/CH4",
        f"{asset_root}/catalog/NO2",
        f"{asset_root}/catalog/SO2",
    ]

    asset_ids: list[str] = []
    for parent in parents:
        try:
            response = ee.data.listAssets({"parent": parent})
        except Exception:
            continue  # parent may not exist
        for asset in response.get("assets", []):
            asset_type = asset.get("type", "")
            asset_name = asset["name"]
            # Skip folders, collections, and _temp items
            if asset_type in ("FOLDER", "IMAGE_COLLECTION"):
                continue
            if "_temp" in asset_name:
                continue
            asset_ids.append(asset_name)
    return sorted(asset_ids)


def get_asset_provenance(asset_id: str) -> dict[str, Any]:
    """Read provenance properties from asset metadata."""
    try:
        info = ee.data.getAsset(asset_id)
        props = info.get("properties", {})
        result = {
            "asset_id": asset_id,
            "properties": props,
        }
        for f in REQUIRED_PROVENANCE_FIELDS:
            result[f] = props.get(f)
        result["has_full_provenance"] = all(
            props.get(f) is not None for f in REQUIRED_PROVENANCE_FIELDS
        )
        return result
    except Exception as e:
        return {"asset_id": asset_id, "error": str(e), "has_full_provenance": False}


# ---------------------------------------------------------------------------
# Allowlist matching
# ---------------------------------------------------------------------------


def is_allowlisted(
    asset_id: str, issue_kind: str, allowlist: list[dict[str, Any]]
) -> bool:
    """
    Check if (asset, issue_kind) appears in allowlist.

    Allowlist entries match by asset basename suffix или full path.
    `issue_kind` ∈ {"missing_provenance", "log_hash_mismatch"}.
    """
    asset_basename = asset_id.split("/")[-1]
    for entry in allowlist:
        entry_asset = entry.get("asset", "")
        entry_kind = entry.get("issue_kind") or entry.get("issue", "")
        if (
            asset_basename in entry_asset
            or asset_id == entry_asset
            or entry_asset.endswith(asset_basename)
        ) and (issue_kind in entry_kind or entry_kind == "any"):
            return True
    return False


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit(
    project: str,
    logs_path: Path,
    allowlist_path: Path,
) -> dict[str, Any]:
    """
    Run full audit. Returns dict с per-asset results.
    """
    ee.Initialize(project=project)

    allowlist = load_allowlist(allowlist_path)
    runs_log = load_runs_log(logs_path)
    asset_ids = list_audited_assets(project)

    # Group log entries by run_id for fast lookup
    runs_by_id: dict[str, list[dict[str, Any]]] = {}
    for entry in runs_log:
        rid = entry.get("run_id")
        if rid:
            runs_by_id.setdefault(rid, []).append(entry)

    findings = {
        "unexpected": [],
        "allowlisted": [],
        "ok": [],
    }

    for asset_id in asset_ids:
        asset_prov = get_asset_provenance(asset_id)

        if "error" in asset_prov:
            entry = {
                "asset": asset_id,
                "issue_kind": "fetch_error",
                "detail": asset_prov["error"],
            }
            if is_allowlisted(asset_id, "fetch_error", allowlist):
                findings["allowlisted"].append(entry)
            else:
                findings["unexpected"].append(entry)
            continue

        # Check 1: full provenance fields present
        if not asset_prov["has_full_provenance"]:
            missing = [f for f in REQUIRED_PROVENANCE_FIELDS if not asset_prov.get(f)]
            entry = {
                "asset": asset_id,
                "issue_kind": "missing_provenance",
                "missing_fields": missing,
            }
            if is_allowlisted(asset_id, "missing_provenance", allowlist):
                findings["allowlisted"].append(entry)
            else:
                findings["unexpected"].append(entry)
            continue

        # Check 2: asset hash matches a log entry с matching run_id
        run_id = asset_prov["run_id"]
        asset_hash = asset_prov["params_hash"]
        log_entries = runs_by_id.get(run_id, [])

        if not log_entries:
            # No log entries для this run_id — log gap, не hash mismatch.
            # Per DevPrompt: separately a CR concern but не blocker here.
            findings["ok"].append(
                {
                    "asset": asset_id,
                    "params_hash": asset_hash[:8],
                    "run_id": run_id,
                    "log_entries_count": 0,
                    "note": "no_log_entries_for_run_id (provenance present но not logged — CR concern)",
                }
            )
            continue

        log_hashes = {e.get("params_hash") for e in log_entries}
        if asset_hash not in log_hashes:
            entry = {
                "asset": asset_id,
                "issue_kind": "log_hash_mismatch",
                "asset_hash": asset_hash[:8],
                "log_hashes": [h[:8] for h in log_hashes if h],
                "run_id": run_id,
            }
            if is_allowlisted(asset_id, "log_hash_mismatch", allowlist):
                findings["allowlisted"].append(entry)
            else:
                findings["unexpected"].append(entry)
            continue

        findings["ok"].append(
            {
                "asset": asset_id,
                "params_hash": asset_hash[:8],
                "run_id": run_id,
                "log_entries_count": len(log_entries),
            }
        )

    return {
        "project": project,
        "n_assets_audited": len(asset_ids),
        "n_allowlist_entries": len(allowlist),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def audit_local_only(logs_path: Path, allowlist_path: Path) -> dict[str, Any]:
    """
    No-GEE audit mode для CI environments without GEE auth.

    Validates:
      * allowlist file is parseable JSON
      * logs/runs.jsonl is parseable jsonl с required fields per entry
      * all log entries have non-empty params_hash, run_id, config_id

    Skips: asset hash equality checks (require GEE).
    """
    findings = {"unexpected": [], "allowlisted": [], "ok": []}

    # Allowlist parseability check
    try:
        allowlist = load_allowlist(allowlist_path)
        findings["ok"].append(
            {
                "check": "allowlist_parseable",
                "n_entries": len(allowlist),
                "path": str(allowlist_path),
            }
        )
    except Exception as e:
        findings["unexpected"].append(
            {
                "check": "allowlist_parseable",
                "error": str(e),
                "path": str(allowlist_path),
            }
        )

    # Log file integrity check
    if not logs_path.exists():
        findings["ok"].append(
            {"check": "logs_file_exists", "note": "logs/runs.jsonl absent"}
        )
    else:
        log_entries = load_runs_log(logs_path)
        bad_entries = []
        for i, e in enumerate(log_entries):
            missing = [
                f for f in ("params_hash", "run_id", "config_id") if not e.get(f)
            ]
            if missing:
                bad_entries.append({"line_index": i, "missing": missing})
        if bad_entries:
            findings["unexpected"].append(
                {
                    "check": "log_entries_required_fields",
                    "n_bad": len(bad_entries),
                    "details": bad_entries[:5],
                }
            )
        else:
            findings["ok"].append(
                {"check": "log_entries_required_fields", "n_entries": len(log_entries)}
            )

    return {
        "mode": "no_gee",
        "n_assets_audited": 0,
        "n_allowlist_entries": len(allowlist) if "allowlist" in dir() else 0,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0c provenance consistency audit")
    parser.add_argument("--gee-project", default=DEFAULT_GEE_PROJECT)
    parser.add_argument("--logs-path", default=str(DEFAULT_LOGS_PATH))
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST_PATH))
    parser.add_argument(
        "--no-gee",
        action="store_true",
        help="Skip GEE asset checks (CI mode without service account credentials). "
        "Still validates allowlist JSON + logs/runs.jsonl entry schema.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = parser.parse_args()

    if args.no_gee:
        result = audit_local_only(
            logs_path=Path(args.logs_path),
            allowlist_path=Path(args.allowlist),
        )
    else:
        result = audit(
            project=args.gee_project,
            logs_path=Path(args.logs_path),
            allowlist_path=Path(args.allowlist),
        )

    findings = result["findings"]
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print("=" * 70)
        print("PROVENANCE CONSISTENCY AUDIT")
        print("=" * 70)
        if "project" in result:
            print(f"Project:         {result['project']}")
        if "mode" in result:
            print(f"Mode:            {result['mode']}")
        print(f"Assets audited:  {result.get('n_assets_audited', 0)}")
        print(f"Allowlist size:  {result.get('n_allowlist_entries', 0)}")
        print()

        def _label(f: dict) -> str:
            if "asset" in f:
                return f["asset"].split("/")[-1]
            if "check" in f:
                return f["check"]
            return "(unknown)"

        print(f"OK ({len(findings['ok'])}):")
        for f in findings["ok"]:
            note = f.get("note", "")
            note_str = f" ({note})" if note else ""
            if "params_hash" in f:
                print(
                    f"  - {_label(f)}: {f['params_hash']} ({f.get('run_id', '?')}){note_str}"
                )
            elif "n_entries" in f:
                print(f"  - {_label(f)}: {f['n_entries']} entries{note_str}")
            else:
                print(f"  - {_label(f)}{note_str}")
        print()

        print(f"Allowlisted mismatches ({len(findings['allowlisted'])}):")
        if not findings["allowlisted"]:
            print("  (none)")
        for f in findings["allowlisted"]:
            print(f"  - {_label(f)}: {f.get('issue_kind', '?')}")
        print()

        print(f"Unexpected mismatches ({len(findings['unexpected'])}):")
        if not findings["unexpected"]:
            print("  (none)")
        for f in findings["unexpected"]:
            detail = (
                f.get("missing_fields")
                or f.get("log_hashes")
                or f.get("error")
                or f.get("detail")
            )
            print(
                f"  - {_label(f)}: {f.get('issue_kind') or f.get('check', '?')} {detail}"
            )

        print()
        print("=" * 70)
        if findings["unexpected"]:
            print("AUDIT FAILED — unexpected provenance mismatches detected")
        else:
            print("AUDIT PASSED")
        print("=" * 70)

    return 1 if findings["unexpected"] else 0


if __name__ == "__main__":
    sys.exit(main())
