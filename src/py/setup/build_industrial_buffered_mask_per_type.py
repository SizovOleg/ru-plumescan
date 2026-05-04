"""
P-01.0d Шаг 3: build RuPlumeScan/industrial/proxy_mask_buffered_per_type Asset.

Per-source-type buffer mapping (TD-0027 closure, researcher decision 2026-05-04):

  category           | buffer_km
  -------------------+-----------
  gas_field          | 50
  viirs_flare_high   | 30  (radiance ≥ 100)
  viirs_flare_low    | 15  (radiance < 100)
  tpp_gres           | 30
  coal_mine          | 30
  smelter            | 30

Replaces uniform `proxy_mask_buffered_30km`. Output: binary Image
`industrial_clean_mask` band (1=clean, 0=industrial-buffered) at 7 km scale.

Approach (server-side):
  1. Load source_points FeatureCollection (532 features, post-Шаг 1)
  2. Tag каждый Feature с buffer_km via classify_source logic (computed
     server-side via ee.Filter / ee.Algorithms.If chain)
  3. For each category, filter subset, buffer geometries, paint к 1.0
  4. Combine paints → industrial_layer (1=industrial-buffered)
  5. Invert → industrial_clean_mask (1=clean, 0=buffered)

Sanity targets:
  Tambeyskoye centroid (71.55°N, 71.60°E) → MASKED (50 km gas_field buffer)
  Bovanenkovo centroid (70.4°N, 68.4°E)   → MASKED (50 km gas_field buffer)
  Tom-Usinsk GRES (53.78°N, 87.59°E)      → MASKED (30 km tpp_gres buffer)
  Yamal vacuum (71.0°N, 73.0°E)           → CLEAN  (>buffer from any source)

Run: python src/py/setup/build_industrial_buffered_mask_per_type.py [--execute]
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

from rca.classify_source_types import (  # noqa: E402
    BUFFER_KM,
    VIIRS_RADIANCE_THRESHOLD_HIGH,
)
from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"
SOURCE_POINTS = f"{ASSETS_ROOT}/RuPlumeScan/industrial/source_points"
OUTPUT_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/industrial/proxy_mask_buffered_per_type"

AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
ANALYSIS_SCALE_M = 7000

SANITY_POINTS = [
    ("Tambeyskoye centroid", 71.55, 71.60, "masked"),
    ("Bovanenkovo centroid", 70.40, 68.40, "masked"),
    ("Tom-Usinsk GRES", 53.78, 87.59, "masked"),
    ("Norilsk Nadezhdinsky", 69.32, 87.93, "masked"),
    # Yamal vacuum (71.0, 73.0) was used previously но now within 50 km of
    # Kruzenshternskoye gas field (~40 km away). Updated coord (73.0, 78.0)
    # — northern Yamal Sea, well outside any gas-field 50 km buffer.
    ("Yamal vacuum (north)", 73.0, 78.0, "clean"),
    ("Mid-Yamal east clean", 70.5, 70.5, "clean"),
    ("Vasyugan swamp center", 58.0, 77.0, "clean"),  # central swamp, no industry
]


def make_provenance() -> object:
    config = {
        "phase": "P-01.0d",
        "operation": "build_industrial_buffered_mask_per_type",
        "source_points_asset": SOURCE_POINTS,
        "buffer_km_per_category": BUFFER_KM,
        "viirs_radiance_threshold_high": VIIRS_RADIANCE_THRESHOLD_HIGH,
        "aoi_bbox": list(AOI_BBOX),
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "td_0027_resolution": True,
        "build_pipeline": "src/py/setup/build_industrial_buffered_mask_per_type.py",
    }
    return compute_provenance(
        config=config,
        config_id="default",
        period="2026_p_01_0d",
        algorithm_version="2.3",
        rna_version="1.2",
    )


def assign_buffer_km(feat: ee.Feature) -> ee.Feature:
    """
    Server-side per-feature buffer_km assignment matching
    rca.classify_source_types.classify_source. Implemented via nested
    `ee.Algorithms.If(...)` to avoid GEE Python API type-coercion gotcha
    where `ee.String.equals()` returns a `ComputedObject` (not `ee.Number`)
    that doesn't expose `.And()`.

    Logic chain (first match wins):
        oil_gas + production_field          → 50
        oil_gas + viirs_flare_proxy + ≥100  → 30
        oil_gas + viirs_flare_proxy + <100  → 15
        power_plant + (coal|gas|tpp_gas)    → 30
        coal_mine                           → 30
        metallurgy                          → 30
        otherwise (incl. hydro/nuclear)     → 0  (filtered out downstream)
    """
    st = feat.getString("source_type")
    sst = feat.getString("source_subtype")
    radiance = ee.Number(
        ee.Algorithms.If(
            feat.get("viirs_radiance_mean"),
            feat.get("viirs_radiance_mean"),
            0,
        )
    )

    # Deeply nested If chain — avoids GEE Number/Boolean coercion issues с .And()/.Or()
    # на list containment. Each branch returns Number immediately.
    is_oil_gas = st.compareTo("oil_gas").eq(0)
    is_production_field = sst.compareTo("production_field").eq(0)
    is_viirs_flare = sst.compareTo("viirs_flare_proxy").eq(0)
    is_high_rad = radiance.gte(VIIRS_RADIANCE_THRESHOLD_HIGH)
    is_power_plant = st.compareTo("power_plant").eq(0)
    is_pp_subtype = (
        sst.compareTo("coal")
        .eq(0)
        .Or(sst.compareTo("gas").eq(0))
        .Or(sst.compareTo("tpp_gas").eq(0))
    )
    is_coal_mine = st.compareTo("coal_mine").eq(0)
    is_metallurgy = st.compareTo("metallurgy").eq(0)

    buffer_km = ee.Number(
        ee.Algorithms.If(
            is_oil_gas.And(is_production_field),
            50,
            ee.Algorithms.If(
                is_oil_gas.And(is_viirs_flare).And(is_high_rad),
                30,
                ee.Algorithms.If(
                    is_oil_gas.And(is_viirs_flare),
                    15,
                    ee.Algorithms.If(
                        is_power_plant.And(is_pp_subtype),
                        30,
                        ee.Algorithms.If(
                            is_coal_mine,
                            30,
                            ee.Algorithms.If(is_metallurgy, 30, 0),
                        ),
                    ),
                ),
            ),
        )
    )

    return feat.set({"buffer_km": buffer_km})


def buffer_feature(feat: ee.Feature) -> ee.Feature:
    """Buffer geometry by feature's buffer_km field (server-side)."""
    bkm = ee.Number(feat.get("buffer_km"))
    buffered_geom = feat.geometry().buffer(bkm.multiply(1000))
    return feat.setGeometry(buffered_geom)


def build_industrial_layer(prov: object) -> ee.Image:
    """
    Build industrial-buffered layer:
      1. Tag features с buffer_km
      2. Filter out 0-km (hydro/nuclear should already be dropped after Шаг 1, defensive)
      3. Buffer geometries
      4. Paint к 1.0 (industrial buffered) → produce mask Image
      5. Invert → clean mask (1=clean, 0=buffered)
    """
    fc = ee.FeatureCollection(SOURCE_POINTS)
    tagged = fc.map(assign_buffer_km).filter(ee.Filter.gt("buffer_km", 0))
    buffered = tagged.map(buffer_feature)
    industrial_layer = ee.Image(0).paint(buffered, 1)
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    industrial_layer = (
        industrial_layer.unmask(0).clip(aoi).reproject(crs="EPSG:4326", scale=ANALYSIS_SCALE_M)
    )
    clean_mask = industrial_layer.Not().rename("industrial_clean_mask").uint8()

    metadata = {
        **prov.to_asset_properties(),
        "phase": "P-01.0d",
        "operation": "build_industrial_buffered_mask_per_type",
        "source_points_asset": SOURCE_POINTS,
        "buffer_km_per_category_json": str(BUFFER_KM),
        "value_1_meaning": "clean (no industrial source within per-type buffer)",
        "value_0_meaning": "industrial-buffered (within source's per-type buffer)",
        "td_0027_resolution": True,
        "build_pipeline": "src/py/setup/build_industrial_buffered_mask_per_type.py",
    }
    return clean_mask.set(metadata)


def wait_task(task_id: str, label: str, timeout_s: int = 1800) -> str:
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
        v = val.get("industrial_clean_mask")
        # Expected: masked → 0 (industrial-buffered); clean → 1
        expected_v = 1 if expected == "clean" else 0
        ok = v == expected_v
        all_pass = all_pass and ok
        mark = "PASS" if ok else "FAIL"
        print(
            f"  [{mark}] {name:<26} ({lat:.2f}, {lon:.2f}): mask={v}, "
            f"expected={expected_v} ({expected})"
        )
    return all_pass


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.0d Шаг 3 industrial_buffered_mask_per_type")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")

    prov = make_provenance()
    print(f"Provenance: run_id={prov.run_id}")

    # Pre-flight: count features by category (sanity)
    fc = ee.FeatureCollection(SOURCE_POINTS)
    n_total = fc.size().getInfo()
    print(f"\nsource_points: {n_total} features (expected 532)")
    tagged = fc.map(assign_buffer_km)
    for thr in [50, 30, 15, 0]:
        n = tagged.filter(ee.Filter.eq("buffer_km", thr)).size().getInfo()
        print(f"  buffer_km={thr}: {n} features")

    if args.dry_run:
        print("\nDRY-RUN: would build per-type mask + export к", OUTPUT_ASSET)
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
        extra={"phase": "P-01.0d", "operation": "build_industrial_buffered_mask_per_type"},
    )

    # Delete existing if any
    try:
        ee.data.getAsset(OUTPUT_ASSET)
        print(f"\nExisting asset found: deleting {OUTPUT_ASSET}")
        ee.data.deleteAsset(OUTPUT_ASSET)
    except Exception:
        pass

    print("\n=== Build + Export per-type mask ===")
    img = build_industrial_layer(prov)
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    task = ee.batch.Export.image.toAsset(
        image=img,
        description="proxy_mask_buffered_per_type",
        assetId=OUTPUT_ASSET,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    state = wait_task(task.id, "per_type_mask_export")
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
        extra={
            "phase": "P-01.0d",
            "operation": "build_industrial_buffered_mask_per_type",
            "sanity_pass": sanity_pass,
        },
    )

    print(f"\n{'=' * 60}")
    print(
        f"Шаг 3 {'COMPLETE' if sanity_pass else 'PARTIAL'} — sanity {'PASS' if sanity_pass else 'FAIL'}"
    )
    return 0 if sanity_pass else 1


if __name__ == "__main__":
    sys.exit(main())
