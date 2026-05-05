"""
P-01.0d Шаг 2: build RuPlumeScan/urban/urban_mask_smod22 Asset.

Source: GHS-SMOD (JRC Global Human Settlement urban grid, 1 km resolution).
Asset: `JRC/GHSL/P2023A/GHS_SMOD/2030`. Threshold ≥22 captures urban centre +
urban cluster classes (Degree of Urbanisation L2 schema):
  10/11/12/13 — rural
  21         — suburban
  22/23      — semi-dense urban cluster
  30         — urban centre

For NO₂/SO₂ baseline construction we mask anywhere SMOD ≥ 22 (semi-dense + urban
centre — anthropogenic combustion от transport/heating/urban activity contributes
significantly above this density threshold).

Output: `RuPlumeScan/urban/urban_mask_smod22` Image (binary, 1=non_urban,
0=urban) с canonical Provenance.

Sanity targets:
  Tyumen city center (57.15°N, 65.55°E)        — urban (mask=0)
  Surgut city center (61.25°N, 73.43°E)        — urban (mask=0)
  Novokuznetsk city (53.79°N, 87.21°E)         — urban (mask=0)
  Yamal vacuum (71.0°N, 73.0°E)                — non-urban (mask=1)

Run: python src/py/setup/build_urban_mask.py [--dry-run] [--execute]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import ee

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"
OUTPUT_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/urban/urban_mask_smod22"
URBAN_FOLDER = f"{ASSETS_ROOT}/RuPlumeScan/urban"

# GHS-SMOD JRC Global Human Settlement Layer
GHS_SMOD_ASSET = "JRC/GHSL/P2023A/GHS_SMOD/2030"
SMOD_THRESHOLD = 22  # ≥22 = semi-dense urban cluster + urban centre

AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
ANALYSIS_SCALE_M = 7000

SANITY_POINTS = [
    ("Tyumen", 57.15, 65.55, "urban"),
    ("Surgut", 61.25, 73.43, "urban"),
    ("Novokuznetsk", 53.79, 87.21, "urban"),
    ("Yamal vacuum", 71.0, 73.0, "non_urban"),
]


def make_provenance() -> object:
    config = {
        "phase": "P-01.0d",
        "operation": "build_urban_mask",
        "ghs_smod_asset": GHS_SMOD_ASSET,
        "smod_threshold": SMOD_THRESHOLD,
        "smod_threshold_meaning": "≥22 = semi-dense urban cluster + urban centre",
        "aoi_bbox": list(AOI_BBOX),
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "td_0023_resolution": True,
        "build_pipeline": "src/py/setup/build_urban_mask.py",
    }
    return compute_provenance(
        config=config,
        config_id="default",
        period="2026_p_01_0d",
        algorithm_version="2.3",
        rna_version="1.2",
    )


def ensure_folder(folder_path: str) -> None:
    try:
        ee.data.createAsset({"type": "FOLDER"}, folder_path)
    except ee.EEException as e:
        msg = str(e).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            pass
        else:
            raise


def build_urban_mask_image(prov: object) -> ee.Image:
    """
    Build binary urban mask: 1=non_urban (clean), 0=urban.

    Reprojection design: GHS-SMOD native 1 km → analysis 7 km via reduceResolution
    с MAX reducer over urban=1 (any 1 km urban pixel inside the 7 km cell → 7 km
    cell urban). This is conservative — avoids diluting urban signal away. Without
    this, default mean-reducer reprojection produced false-non-urban results на
    cities like Surgut (one 1 km urban pixel surrounded by rural в 7 km cell mean).
    """
    smod = ee.Image(GHS_SMOD_ASSET).select(0)
    # urban=1 at native 1 km
    urban_native = smod.gte(SMOD_THRESHOLD)
    # Reproject к 7 km using MAX reducer — any urban pixel propagates
    urban_7km = urban_native.reduceResolution(reducer=ee.Reducer.max(), maxPixels=1024).reproject(
        crs="EPSG:4326", scale=ANALYSIS_SCALE_M
    )
    non_urban = urban_7km.Not().rename("non_urban_mask").uint8()

    metadata = {
        **prov.to_asset_properties(),
        "phase": "P-01.0d",
        "operation": "build_urban_mask",
        "ghs_smod_source": GHS_SMOD_ASSET,
        "smod_threshold": SMOD_THRESHOLD,
        "value_1_meaning": "non_urban (clean)",
        "value_0_meaning": "urban (semi-dense cluster or centre, SMOD≥22)",
        "td_0023_resolution": True,
        "build_pipeline": "src/py/setup/build_urban_mask.py",
    }
    return non_urban.set(metadata)


def wait_task(task_id: str, label: str, timeout_s: int = 1200) -> str:
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


def sanity_check(asset_id: str) -> bool:
    img = ee.Image(asset_id)
    print("\n=== Sanity check ===")
    all_pass = True
    for name, lat, lon, expected in SANITY_POINTS:
        pt = ee.Geometry.Point([lon, lat])
        val = img.reduceRegion(
            reducer=ee.Reducer.first(), geometry=pt, scale=ANALYSIS_SCALE_M
        ).getInfo()
        v = val.get("non_urban_mask")
        # Expected: urban → 0; non_urban → 1
        expected_v = 1 if expected == "non_urban" else 0
        ok = v == expected_v
        all_pass = all_pass and ok
        mark = "PASS" if ok else "FAIL"
        print(
            f"  [{mark}] {name:<22} ({lat:.2f}, {lon:.2f}): mask={v}, expected={expected_v} ({expected})"
        )
    return all_pass


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0d Шаг 2 build_urban_mask")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")

    prov = make_provenance()
    print(f"Provenance: run_id={prov.run_id}")

    if args.dry_run:
        print("\nDRY-RUN: would export к", OUTPUT_ASSET)
        return 0

    if not args.execute:
        print("\nSafety guard: pass --execute к launch live build.")
        return 0

    write_provenance_log(
        prov,
        status="STARTED",
        gas="multi",
        period="2026_p_01_0d",
        asset_id=OUTPUT_ASSET,
        extra={"phase": "P-01.0d", "operation": "build_urban_mask"},
    )

    print(f"\n=== Ensuring folder {URBAN_FOLDER} ===")
    ensure_folder(URBAN_FOLDER)

    # Check if existing — delete first
    try:
        ee.data.getAsset(OUTPUT_ASSET)
        print(f"  existing asset found: {OUTPUT_ASSET} — deleting")
        ee.data.deleteAsset(OUTPUT_ASSET)
    except Exception:
        pass

    print("\n=== Build + Export urban_mask ===")
    img = build_urban_mask_image(prov)
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    task = ee.batch.Export.image.toAsset(
        image=img,
        description="urban_mask_smod22",
        assetId=OUTPUT_ASSET,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    state = wait_task(task.id, "urban_mask_export")
    if state != "SUCCEEDED":
        print(f"  EXPORT FAILED state={state}")
        return 1

    sanity_pass = sanity_check(OUTPUT_ASSET)

    write_provenance_log(
        prov,
        status="SUCCEEDED" if sanity_pass else "PARTIAL",
        gas="multi",
        period="2026_p_01_0d",
        asset_id=OUTPUT_ASSET,
        extra={"phase": "P-01.0d", "operation": "build_urban_mask", "sanity_pass": sanity_pass},
    )

    print(f"\n{'=' * 60}")
    print(
        f"Шаг 2 {'COMPLETE' if sanity_pass else 'PARTIAL'} — sanity {'PASS' if sanity_pass else 'FAIL'}"
    )
    return 0 if sanity_pass else 1


if __name__ == "__main__":
    sys.exit(main())
