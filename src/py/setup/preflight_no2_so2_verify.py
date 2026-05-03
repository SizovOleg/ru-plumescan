"""
Pre-flight verifications перед NO2/SO2 regional climatology submit.

1. Band availability check для TROPOMI L3 NO2/SO2 OFFL — confirm
   что cloud_fraction/qa_value присутствуют (CLAIM 5 multi-band-select
   pattern depends on this).

2. 6-point Ref vs Regional CH4 cross-check (M07 + M10) — full numerical
   numbers для validation report (`docs/p-01.0b_validation_report.md`).

Single ee.Initialize, single getInfo() roundtrip per request → fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import ee

GEE_PROJECT = "nodal-thunder-481307-u1"

REF_ASSET = (
    "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/reference_CH4_2019_2025_v1"
)
REG_ASSET = "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/regional_CH4_2019_2025"

# 6 contractual sanity points (Lat, Lon).
POINTS = [
    ("Yugansky centroid", 60.5, 74.5),  # reference clean zone — should be valid both
    ("Verkhne-Tazovsky", 63.5, 84.0),  # reference clean zone
    ("Kuznetsky Alatau", 54.5, 88.0),  # reference clean zone (low counts)
    ("Mid-Yamal clean", 67.0, 72.0),  # outside reference, regional only
    ("Norilsk Nadezhdinsky", 69.32, 87.93),  # industrial — masked в обоих
    ("Bovanenkovo proxy", 70.5, 70.5),  # industrial proxy — masked
]

MONTHS = (7, 10)


def fetch_bands() -> dict[str, list[str]]:
    """Sample first image of NO2 + SO2 L3 OFFL collections."""
    no2 = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_NO2").first().bandNames().getInfo()
    so2 = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_SO2").first().bandNames().getInfo()
    return {"NO2_L3_OFFL": list(no2), "SO2_L3_OFFL": list(so2)}


def sample_points() -> list[dict]:
    """Sample 6 points × 2 assets × 2 months. One getInfo() per asset×month."""
    ref = ee.Image(REF_ASSET)
    reg = ee.Image(REG_ASSET)

    pts = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"name": name, "lat": lat, "lon": lon})
            for (name, lat, lon) in POINTS
        ]
    )

    bands_ref = [f"ref_M{m:02d}" for m in MONTHS]
    bands_reg = [f"median_M{m:02d}" for m in MONTHS]

    ref_sampled = (
        ref.select(bands_ref)
        .reduceRegions(collection=pts, reducer=ee.Reducer.first(), scale=1113.2)  # ~0.01°
        .getInfo()
    )

    reg_sampled = (
        reg.select(bands_reg)
        .reduceRegions(collection=pts, reducer=ee.Reducer.first(), scale=1113.2)
        .getInfo()
    )

    rows = []
    for i, (name, lat, lon) in enumerate(POINTS):
        ref_props = ref_sampled["features"][i]["properties"]
        reg_props = reg_sampled["features"][i]["properties"]
        row = {
            "point": name,
            "lat": lat,
            "lon": lon,
            "ref_M07": ref_props.get("ref_M07"),
            "reg_M07": reg_props.get("median_M07"),
            "ref_M10": ref_props.get("ref_M10"),
            "reg_M10": reg_props.get("median_M10"),
        }
        for m in (7, 10):
            r = row[f"ref_M{m:02d}"]
            g = row[f"reg_M{m:02d}"]
            row[f"delta_M{m:02d}"] = None if r is None or g is None else round(g - r, 3)
        rows.append(row)
    return rows


def main() -> None:
    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")

    print("\n=== STEP 1: TROPOMI L3 OFFL band availability ===")
    bands = fetch_bands()
    print(json.dumps(bands, indent=2, ensure_ascii=False))

    qa_bands_required = {"cloud_fraction", "qa_value"}
    for gas, b in bands.items():
        present = qa_bands_required.intersection(b)
        missing = qa_bands_required - set(b)
        print(f"  {gas}: present={sorted(present)} missing={sorted(missing)}")

    print("\n=== STEP 2: 6-point Ref vs Regional CH4 cross-check ===")
    rows = sample_points()
    print(
        f"{'point':<24} {'lat':>6} {'lon':>6} {'ref_M07':>10} {'reg_M07':>10} "
        f"{'dM07':>8} {'ref_M10':>10} {'reg_M10':>10} {'dM10':>8}"
    )

    def _fmt(v: object) -> str:
        return f"{v:>10.3f}" if isinstance(v, (int, float)) else "       nan"

    def _fmt_d(v: object) -> str:
        return f"{v:>+8.3f}" if isinstance(v, (int, float)) else "     nan"

    for r in rows:
        print(
            f"{r['point']:<24} {r['lat']:>6.2f} {r['lon']:>6.2f} "
            f"{_fmt(r['ref_M07'])} {_fmt(r['reg_M07'])} {_fmt_d(r['delta_M07'])} "
            f"{_fmt(r['ref_M10'])} {_fmt(r['reg_M10'])} {_fmt_d(r['delta_M10'])}"
        )

    repo_root = Path(__file__).resolve().parents[3]
    out_json = repo_root / "docs" / "p-01.0b_validation_data.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps({"bands": bands, "cross_check": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved raw data: {out_json.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
