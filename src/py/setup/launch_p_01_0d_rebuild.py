"""
P-01.0d Шаг 5: archive 3 old regional baselines + launch fresh rebuild
с per-type + urban mask combined.

Sequence per gas (CH4, NO2, SO2):
  1. Archive existing `regional_<gas>_2019_2025` → `..._v1_pre_urban_mask`
     via ee.data.copyAsset
  2. Delete original `regional_<gas>_2019_2025`
  3. Delete old state JSON `docs/p-01.0b_state_<gas>_2025.json`
  4. Launch 12 monthly tasks через build_regional_climatology.py
     с `--use-per-type-mask --use-urban-mask --launch-only`

Total: 36 batch tasks fired (12 × 3 gases). Wall-clock ~24-30 hours
для completion.

Run: python src/py/setup/launch_p_01_0d_rebuild.py [--dry-run] [--execute]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import ee

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"

GASES = ["CH4", "NO2", "SO2"]
TARGET_YEAR = 2025


def archive_old_baseline(gas: str) -> bool:
    src = f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_{gas}_2019_{TARGET_YEAR}"
    dst = f"{src}_v1_pre_urban_mask"
    print(f"\n=== Archiving {gas} ===")
    print(f"  src: {src}")
    print(f"  dst: {dst}")

    # Check src exists
    try:
        ee.data.getAsset(src)
    except Exception as e:
        print(f"  src not found: {e}")
        return False

    # Check dst doesn't exist already
    try:
        ee.data.getAsset(dst)
        print("  dst already exists — skip archive (assume previously archived)")
        return True
    except Exception:
        pass

    try:
        ee.data.copyAsset(src, dst)
        print("  copyAsset SUCCEEDED")
        return True
    except Exception as e:
        print(f"  copyAsset FAILED: {e}")
        return False


def delete_old_asset(gas: str) -> bool:
    src = f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_{gas}_2019_{TARGET_YEAR}"
    print(f"  Deleting {src}")
    try:
        ee.data.deleteAsset(src)
        print("  deleted")
        return True
    except Exception as e:
        if "not found" in str(e).lower():
            print(f"  already absent: {e}")
            return True
        print(f"  delete FAILED: {e}")
        return False


def delete_state_file(gas: str) -> None:
    p = REPO_ROOT / "docs" / f"p-01.0b_state_{gas}_{TARGET_YEAR}.json"
    if p.exists():
        p.unlink()
        print(f"  deleted state file: {p.relative_to(REPO_ROOT)}")
    else:
        print(f"  state file absent: {p.relative_to(REPO_ROOT)}")


def launch_rebuild(gas: str) -> bool:
    print(f"\n=== Launching {gas} rebuild (12 monthly tasks) ===")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "src" / "py" / "setup" / "build_regional_climatology.py"),
        "--gas",
        gas,
        "--target-year",
        str(TARGET_YEAR),
        "--use-per-type-mask",
        "--use-urban-mask",
        "--launch-only",
    ]
    print(f"  cmd: {' '.join(cmd[2:])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0d Шаг 5 rebuild launcher")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")

    if not args.execute and not args.dry_run:
        print("\nSafety guard: pass --execute (or --dry-run для preview)")
        return 0

    if args.dry_run:
        print("\n=== DRY-RUN plan ===")
        for gas in GASES:
            print(
                f"  {gas}: archive → delete final asset → delete state JSON → launch 12 monthly tasks"
            )
        print(f"\nTotal: {len(GASES) * 12} batch tasks would launch")
        return 0

    print("\n=== Step 1: Archive old final assets ===")
    for gas in GASES:
        if not archive_old_baseline(gas):
            print(f"  ABORT — archive failed для {gas}")
            return 1

    print("\n=== Step 2: Delete old final assets ===")
    for gas in GASES:
        delete_old_asset(gas)

    print("\n=== Step 3: Delete old state JSON files ===")
    for gas in GASES:
        delete_state_file(gas)

    print("\n=== Step 4: Launch fresh rebuild для 3 gases ===")
    for gas in GASES:
        ok = launch_rebuild(gas)
        if not ok:
            print(f"  ABORT — launch failed для {gas}")
            return 1

    print(f"\n{'=' * 70}")
    print("P-01.0d Шаг 5 LAUNCHED: 36 batch tasks fired (12 × 3 gases)")
    print("Expected wall-clock: ~24-30 hours")
    print("State files saved per gas. Run --poll-only / --combine-only to resume.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
