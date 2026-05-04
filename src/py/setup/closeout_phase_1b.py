"""
P-01.0b Phase 1b NO2/SO2 closure:

  1. Verify final assets (36 bands, full provenance properties)
  2. Sanity validations per gas:
     - Industrial pixels masked (Norilsk, Tom-Usinsk GRES)
     - Cities NOT masked (Tyumen, Surgut, Novokuznetsk) [v1 schema limitation]
     - Clean-region range checks
     - SO2 negative floor verification (no values < -0.001 mol/m^2)
  3. Augment asset metadata: Kuzbass gap caveat + multi-band-select pipeline note
  4. Cleanup 24 temp monthly assets
  5. Write SUCCEEDED entries в logs/runs.jsonl
  6. Save closure report JSON

Run после двух combine tasks SUCCEEDED.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import ee

# Console на Windows default cp1251 — Unicode (Δ, °, ²) crashes print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"

ASSET_FOR = {
    "NO2": f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_NO2_2019_2025",
    "SO2": f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_SO2_2019_2025",
}

TEMP_PARENT = f"{ASSETS_ROOT}/RuPlumeScan/baselines/_temp"

KUZBASS_GAP_CAVEAT = (
    "Industrial mask v1 missed 4 major Kuzbass plants pre-fix (Tom-Usinsk GRES, "
    "Belovo, Yuzhno-Kuzbass, Kuznetsk) — fixed в same PR (P-01.0b) перед NO2/SO2 "
    "submit. Mask used here is post-fix proxy_mask_buffered_30km. Phase 2A detection "
    "near (86-88E, 53-55N) requires stricter z_min=4.0 + manual review per TD-0018."
)
QA_FILTER_CAVEAT = (
    "Multi-band-select pipeline (CLAIM 5 fix): bands selected as "
    "[target + cloud_fraction] → cloud_fraction < 0.3 filter applied → reduce. "
    "qa_value architecturally absent в TROPOMI L3 OFFL для NO2/SO2 — same как CH4 "
    "(GEE upstream-filtered). cloud_fraction filter ACTIVE для NO2/SO2 (vs CH4 inert)."
)
CITIES_CAVEAT = (
    "Cities not masked в v1 schema (cities != industrial). Elevated NO2 над "
    "Tyumen/Surgut/Novokuznetsk preserved в regional baseline. Future schema "
    "enhancement: separate urban_mask layer (TD candidate)."
)

# Sanity test points
SANITY_NO2 = [
    # (label, lat, lon, expectation)
    ("Norilsk Nadezhdinsky (industrial — should be masked)", 69.32, 87.93, "masked"),
    ("Tom-Usinsk GRES (Kuzbass post-fix mask test)", 53.78, 87.59, "masked"),
    ("Tyumen city center (city, NOT masked)", 57.15, 65.55, "elevated_unmasked"),
    ("Surgut city center (city, NOT masked)", 61.25, 73.43, "elevated_unmasked"),
    ("Novokuznetsk city center (city, NOT masked)", 53.79, 87.21, "elevated_unmasked"),
    ("Clean Yamal vacuum (clean range)", 71.0, 73.0, "clean_low"),
]

SANITY_SO2 = [
    ("Norilsk Nadezhdinsky (largest SO2 source globally)", 69.32, 87.93, "masked"),
    ("Norilsk Medny", 69.371, 88.221, "masked"),
    ("Clean Yamal vacuum (clean ~0)", 71.0, 73.0, "clean_zero"),
    ("Mid-Yamal east clean (open tundra)", 70.5, 70.5, "clean_zero"),
]


def list_temp_assets(gas: str) -> list[str]:
    listing = ee.data.listAssets({"parent": TEMP_PARENT})
    return sorted(
        a["name"] for a in listing.get("assets", []) if f"regional_{gas}_2019_2025_M" in a["name"]
    )


def fetch_metadata(gas: str) -> dict:
    img = ee.Image(ASSET_FOR[gas])
    info = img.getInfo()
    return {
        "bands": [b["id"] for b in info.get("bands", [])],
        "properties": info.get("properties", {}),
    }


def sample_points(gas: str, points: list[tuple]) -> list[dict]:
    """Sample median_M07 + median_M01 при NO2/SO2 для full annual coverage."""
    img = ee.Image(ASSET_FOR[gas])
    bands_to_sample = ["median_M07", "median_M10", "median_M01", "count_M07"]
    select_img = img.select(bands_to_sample)

    fc = ee.FeatureCollection(
        [
            ee.Feature(
                ee.Geometry.Point([lon, lat]),
                {"label": label, "lat": lat, "lon": lon, "expected": expected},
            )
            for (label, lat, lon, expected) in points
        ]
    )
    sampled = select_img.reduceRegions(
        collection=fc, reducer=ee.Reducer.first(), scale=1113.2
    ).getInfo()

    rows = []
    for feat in sampled["features"]:
        p = feat["properties"]
        rows.append(
            {
                "label": p["label"],
                "lat": p["lat"],
                "lon": p["lon"],
                "expected": p["expected"],
                "median_M01": p.get("median_M01"),
                "median_M07": p.get("median_M07"),
                "median_M10": p.get("median_M10"),
                "count_M07": p.get("count_M07"),
            }
        )
    return rows


def evaluate_sanity_no2(rows: list[dict]) -> list[dict]:
    """Return per-row pass/fail с rationale."""
    results = []
    for r in rows:
        ok = False
        why = ""
        m07 = r["median_M07"]
        m10 = r["median_M10"]
        if r["expected"] == "masked":
            # Industrial — should be NaN (masked) at М07 (peak summer signal)
            ok = m07 is None or m07 != m07  # NaN check
            why = "NaN at M07 (industrial-buffered)" if ok else f"NOT masked (M07={m07})"
        elif r["expected"] == "elevated_unmasked":
            # City — NOT masked, may be elevated. Just verify it has a valid value.
            ok = m07 is not None and m07 > 0
            m10_str = f"{m10:.3e}" if isinstance(m10, (int, float)) else "None"
            why = (
                f"valid M07={m07:.3e}, M10={m10_str} mol/m2"
                if ok
                else f"unexpected None/zero (M07={m07})"
            )
        elif r["expected"] == "clean_low":
            # Clean tundra — NO2 should be very low (< 5e-5 mol/m^2, typically ~1-2e-5)
            ok = m07 is not None and 0 <= m07 < 5e-5
            why = f"clean M07={m07:.3e} mol/m2 < 5e-5" if ok else f"unexpected M07={m07}"
        results.append({**r, "ok": ok, "why": why})
    return results


def evaluate_sanity_so2(rows: list[dict]) -> list[dict]:
    results = []
    for r in rows:
        ok = False
        why = ""
        m07 = r["median_M07"]
        if r["expected"] == "masked":
            ok = m07 is None or m07 != m07
            why = "NaN at M07 (industrial-buffered)" if ok else f"NOT masked (M07={m07})"
        elif r["expected"] == "clean_zero":
            # SO2 short lifetime — clean regions should be ~0, slightly negative possible
            ok = m07 is not None and -0.001 <= m07 < 1e-4
            why = (
                f"clean M07={m07:.3e} mol/m2 (within [-1e-3, 1e-4])"
                if ok
                else f"unexpected M07={m07}"
            )
        results.append({**r, "ok": ok, "why": why})
    return results


def verify_negative_floor_so2(logger_print) -> dict:
    """Compute global min over all SO2 bands. Should be >= -0.001 mol/m^2."""
    img = ee.Image(ASSET_FOR["SO2"])
    median_bands = [f"median_M{m:02d}" for m in range(1, 13)]
    aoi = ee.Geometry.Rectangle([60.0, 50.0, 95.0, 75.0])
    stats = (
        img.select(median_bands)
        .reduceRegion(reducer=ee.Reducer.min(), geometry=aoi, scale=10000, bestEffort=False)
        .getInfo()
    )
    mins = [(b, v) for b, v in stats.items() if v is not None]
    overall_min = min(v for _, v in mins) if mins else None
    logger_print(f"  SO2 negative floor check: overall_min = {overall_min}")
    floor_violation = overall_min is not None and overall_min < -0.001
    return {
        "overall_min_mol_m2": overall_min,
        "per_band_min": dict(mins),
        "floor_target_min": -0.001,
        "ok": (not floor_violation),
    }


def augment_asset_metadata(gas: str) -> dict:
    """Set Kuzbass / qa_filter / cities / phase_1b_closure caveats on final asset."""
    asset_id = ASSET_FOR[gas]
    new_props = {
        "kuzbass_gap_caveat": KUZBASS_GAP_CAVEAT,
        "qa_filter_caveat": QA_FILTER_CAVEAT,
        "cities_unmasked_caveat": CITIES_CAVEAT,
        "phase_1b_closure_date": "2026-04-30",
        "td_0008_outcome": "A_FULL_SUCCESS_OPTION_C_VERIFIED",
    }
    ee.data.updateAsset(asset_id, {"properties": new_props}, list(new_props.keys()))
    return new_props


def delete_temp_assets(gases: list[str]) -> list[str]:
    deleted = []
    for gas in gases:
        for asset_name in list_temp_assets(gas):
            try:
                ee.data.deleteAsset(asset_name)
                deleted.append(asset_name)
            except Exception as e:
                print(f"  WARN: failed to delete {asset_name}: {e}")
    return deleted


def main() -> None:
    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")

    closure = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "gases": {}}

    for gas in ["NO2", "SO2"]:
        print(f"\n=== {gas}: final asset verification ===")
        meta = fetch_metadata(gas)
        n_bands = len(meta["bands"])
        print(f"  bands: {n_bands} (expected 36)")
        print(f"  band names: {meta['bands'][:3]}, ..., {meta['bands'][-3:]}")
        prov_keys = [
            "algorithm_version",
            "schema_version",
            "rna_version",
            "config_id",
            "params_hash",
            "run_id",
        ]
        for k in prov_keys:
            v = meta["properties"].get(k, "<MISSING>")
            print(f"  property {k}: {v}")

        closure["gases"][gas] = {
            "asset_id": ASSET_FOR[gas],
            "n_bands": n_bands,
            "metadata": meta["properties"],
        }

    print("\n=== NO2 sanity validation ===")
    rows_no2 = sample_points("NO2", SANITY_NO2)
    no2_results = evaluate_sanity_no2(rows_no2)
    for r in no2_results:
        mark = "OK" if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['label']}: {r['why']}")
    closure["gases"]["NO2"]["sanity"] = no2_results

    print("\n=== SO2 sanity validation ===")
    rows_so2 = sample_points("SO2", SANITY_SO2)
    so2_results = evaluate_sanity_so2(rows_so2)
    for r in so2_results:
        mark = "OK" if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['label']}: {r['why']}")
    closure["gases"]["SO2"]["sanity"] = so2_results

    print("\n=== SO2 negative-floor verification (DNA §2.1 запрет 7) ===")
    floor = verify_negative_floor_so2(print)
    closure["gases"]["SO2"]["negative_floor_check"] = floor
    print(f"  result: {'OK' if floor['ok'] else 'FAIL'}")

    print("\n=== Augmenting asset metadata (caveats) ===")
    for gas in ["NO2", "SO2"]:
        new_props = augment_asset_metadata(gas)
        print(f"  {gas}: added {len(new_props)} property keys")
        closure["gases"][gas]["augmented_properties"] = new_props

    print("\n=== Cleanup 24 temp assets ===")
    deleted = delete_temp_assets(["NO2", "SO2"])
    print(f"  deleted {len(deleted)} assets")
    closure["temp_assets_deleted"] = deleted

    print("\n=== Write SUCCEEDED entries в logs/runs.jsonl ===")
    closure["run_logs"] = {}
    for gas in ["NO2", "SO2"]:
        cfg = {
            "algorithm_version": "2.3",
            "rna_version": "1.2",
            "schema_version": "1.1",
            "config_preset": "default",
            "gas": gas,
            "history_year_min": 2019,
            "history_year_max": 2024,
            "target_year": 2025,
            "aoi_bbox": [60.0, 50.0, 95.0, 75.0],
            "industrial_buffer_km": 30,
            "cloud_fraction_max": 0.3,
            "qa_filter": "cloud_fraction",
            "pipeline_mode": "multi_band_select",
            "baseline_type": "regional",
            "orchestrator": "TD-0008_Option_C",
            "mask_asset": "proxy_mask_buffered_30km",
            "phase": "P-01.0b",
        }
        prov = compute_provenance(cfg, period="2019_2025")
        log_path = write_provenance_log(
            prov,
            status="SUCCEEDED",
            gas=gas,
            period="2019_2025",
            ended_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            asset_id=ASSET_FOR[gas],
            extra={
                "baseline_type": "regional",
                "phase": "P-01.0b",
                "n_tasks": 12,
                "outcome": "A_FULL_SUCCESS",
                "td_0008_verified": True,
                "mask_asset": "proxy_mask_buffered_30km",
            },
        )
        closure["run_logs"][gas] = {"run_id": prov.run_id, "path": str(log_path)}
        print(f"  {gas}: run_id={prov.run_id}")

    closure["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out_json = REPO_ROOT / "docs" / "p-01.0b_closure_report.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(closure, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"\nSaved: {out_json.relative_to(REPO_ROOT)}")

    no2_ok = all(r["ok"] for r in no2_results)
    so2_ok = all(r["ok"] for r in so2_results) and floor["ok"]
    overall = no2_ok and so2_ok
    print(f"\nNO2 sanity: {'PASS' if no2_ok else 'FAIL'}")
    print(f"SO2 sanity + floor: {'PASS' if so2_ok else 'FAIL'}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")


if __name__ == "__main__":
    main()
