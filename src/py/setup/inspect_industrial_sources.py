"""
P-01.0d pre-work — read-only inspection of industrial/source_points schema.

Goal: understand what fields exist on the 531 features, what GPPD/manual/VIIRS
provenance is preserved, and identify the path forward для per-source-type
classification (TD-0027) before finalized DevPrompt.

This script is **read-only**. Не writes anything (no asset mutations, no
files saved). Output goes к stdout only.

Run: python src/py/setup/inspect_industrial_sources.py
"""

from __future__ import annotations

import sys
from collections import Counter

import ee

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GEE_PROJECT = "nodal-thunder-481307-u1"
SOURCE_POINTS_ASSET = "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/industrial/source_points"


def main() -> int:
    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print(f"Asset: {SOURCE_POINTS_ASSET}")
    print()

    fc = ee.FeatureCollection(SOURCE_POINTS_ASSET)

    # === Counts ===
    n_total = fc.size().getInfo()
    print(f"Total features: {n_total}")

    # === Schema (property names from first feature) ===
    first = fc.first()
    prop_names = first.propertyNames().getInfo()
    print(f"\nProperty names on first feature ({len(prop_names)}):")
    for p in prop_names:
        print(f"  - {p}")

    # === Sample first feature ===
    print("\nFirst feature properties (full):")
    sample = first.getInfo()
    props = sample.get("properties", {})
    for k, v in props.items():
        v_str = str(v)
        if len(v_str) > 80:
            v_str = v_str[:77] + "..."
        print(f"  {k}: {v_str}")
    geom = sample.get("geometry", {})
    print(f"  geometry type: {geom.get('type')}")
    print(f"  coordinates: {geom.get('coordinates')}")

    # === Field availability counts ===
    print("\n=== Field availability across collection ===")
    candidate_fields = [
        "type",
        "source_type",
        "source_type_category",
        "category",
        "capacity_mw",
        "fuel",
        "plant_type",
        "commissioning_year",
        "name",
        "country",
        "primary_fuel",
        "owner",
        "gppd_idnr",
        "viirs_intensity",
        "manual_provenance",
        "data_source",
        "facility_type",
        "industry",
        "subtype",
    ]
    for field in candidate_fields:
        try:
            count = fc.filter(ee.Filter.notNull([field])).size().getInfo()
            present_pct = 100.0 * count / n_total if n_total > 0 else 0
            mark = "*" if count > 0 else " "
            print(f"  [{mark}] {field:<28}: {count:>4}/{n_total} ({present_pct:5.1f}%)")
        except ee.EEException as e:
            print(f"  [?] {field:<28}: ERROR ({e})")

    # === Distribution analysis для key fields, if present ===
    print("\n=== Distributions (top values per field) ===")
    distribution_fields = [
        "type",
        "source_type",
        "fuel",
        "primary_fuel",
        "plant_type",
        "facility_type",
        "data_source",
        "subtype",
    ]
    for field in distribution_fields:
        try:
            count = fc.filter(ee.Filter.notNull([field])).size().getInfo()
            if count == 0:
                continue
            values = fc.aggregate_array(field).getInfo()
            counter = Counter(str(v) for v in values if v is not None)
            print(f"\n  Field: {field} (n={count})")
            for value, n in counter.most_common(15):
                v_str = value if len(value) < 60 else value[:57] + "..."
                print(f"    {n:>4} × {v_str}")
        except ee.EEException:
            continue

    # === Spatial distribution rough check ===
    print("\n=== Spatial distribution ===")
    try:
        # Sample geo properties: aggregate lat/lon ranges
        lon_range = fc.aggregate_array("system:index").size().getInfo()
        # Get geometry centroid bounds for the whole collection
        bounds = fc.geometry().bounds().coordinates().getInfo()
        print(f"  features: {lon_range}")
        print(f"  collection bounds (LL/UR corners): {bounds}")
    except Exception as e:
        print(f"  spatial check: ERROR {e}")

    # === Suggested next steps ===
    print()
    print("=" * 70)
    print("Inspection complete. Next steps depend on findings:")
    print("  1. Identify which field(s) carry source-type classification")
    print("  2. Map field values → {gas_field, tpp_gres, oil_refinery, smelter, coal_mine}")
    print("  3. Document gaps (manual classification needed для VIIRS-derived)")
    print("  4. Researcher finalizes P-01.0d DevPrompt с classification logic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
