"""
Phase 1c (P-01.2) dual baseline cross-check analysis.

Combines reference_CH4_v1 + regional_CH4 baseline assets для:
  Шаг 2: Spatial divergence analysis Δ = regional − reference (M07 + M10)
         → export Δ ee.Image assets к analysis/, async batch tasks
  Шаг 3: 0.5° grid aggregation + global/per-zone stats + Moran's I +
         Hartigan's dip test (PySAL/esda/diptest)
  Шаг 4: Suspect regions identification (Δ > +30 ppb clusters)
  Шаг 5: Cross-zone consistency analysis (75°E transect, fine 0.1° resolution)
  Шаг 6: Article t1 partial comparison (Zone 4 confirmed)

Outputs:
  * Async GEE tasks для Δ asset export (M07, M10)
  * docs/p-01.2_stats.json — formal statistics
  * docs/p-01.2_suspect_regions.geojson — significant clusters
  * docs/p-01.2_transect_75E.json — fine latitude transect
  * docs/p-01.2_grid_samples.json — 0.5° grid raw samples (для Figure 1)
  * docs/p-01.2_pngs/*.png — divergence + transect visualizations

Per DNA §2.1 запрет 12: full Provenance computed once at process start, applied
к export tasks via Provenance.to_asset_properties().

Run: python src/py/setup/dual_baseline_analysis.py [--no-export] [--m07-only]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import matplotlib.pyplot as plt
import numpy as np

# Console на Windows default cp1251 — Unicode (Δ, °, ²) crashes print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

from rca.provenance import compute_provenance, write_provenance_log  # noqa: E402

GEE_PROJECT = "nodal-thunder-481307-u1"
ASSETS_ROOT = "projects/nodal-thunder-481307-u1/assets"
ANALYSIS_FOLDER = f"{ASSETS_ROOT}/RuPlumeScan/analysis"

REF_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/baselines/reference_CH4_2019_2025_v1"
REG_ASSET = f"{ASSETS_ROOT}/RuPlumeScan/baselines/regional_CH4_2019_2025"

AOI_BBOX = (60.0, 50.0, 95.0, 75.0)
ANALYSIS_SCALE_M = 7000

# Latitude band assignments (centroid midpoints)
ZONE_CENTROIDS = {"yugansky": 60.5, "verkhne_tazovsky": 63.5, "kuznetsky_alatau": 54.5}
BAND_BOUNDARIES = (57.5, 62.0)  # midpoints between centroids
ZONE_BAND_DEFS = [
    ("kuznetsky_alatau", (50.0, 57.5)),
    ("yugansky", (57.5, 62.0)),
    ("verkhne_tazovsky", (62.0, 75.0)),
]

# Suspect threshold (per DevPrompt — Δ > +30 ppb systematic)
SUSPECT_DELTA_PPB = 30.0
MIN_CLUSTER_PIXELS = 5  # ~5 × 49 km² ≈ 245 km² minimum signal area

# Tool-paper article t1 zonal stats (Zone 4 only confirmed)
ARTICLE_T1 = {"Zone 4 (Middle taiga 60-63N)": {"value_ppb": 1854, "lat_range": (60, 63)}}


def make_provenance(months: list[str]) -> Any:
    """Compute once at process start (DNA §2.1.12)."""
    config = {
        "phase": "P-01.2",
        "analysis_type": "dual_baseline_cross_check",
        "reference_asset": REF_ASSET,
        "regional_asset": REG_ASSET,
        "aoi_bbox": list(AOI_BBOX),
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "months_analyzed": months,
        "suspect_delta_threshold_ppb": SUSPECT_DELTA_PPB,
        "min_cluster_pixels": MIN_CLUSTER_PIXELS,
        "zone_band_definitions": [
            {"zone": z, "lat_min": lo, "lat_max": hi} for z, (lo, hi) in ZONE_BAND_DEFS
        ],
        "stats_grid_deg": 0.5,
        "pipeline": "src/py/setup/dual_baseline_analysis.py",
    }
    return compute_provenance(
        config=config,
        config_id="default",
        period="2019_2025",
        algorithm_version="2.3",
        rna_version="1.2",
    )


def ensure_analysis_folder() -> None:
    """Create RuPlumeScan/analysis/ folder if absent (idempotent)."""
    try:
        ee.data.createAsset({"type": "FOLDER"}, ANALYSIS_FOLDER)
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "cannot overwrite" in msg:
            pass
        else:
            raise


def compute_delta_image(month: str) -> ee.Image:
    """Return Δ = regional - reference image для given month."""
    ref = ee.Image(REF_ASSET).select(f"ref_{month}")
    reg = ee.Image(REG_ASSET).select(f"median_{month}")
    return reg.subtract(ref).rename(f"delta_{month}")


def export_delta_asset(delta: ee.Image, month: str, prov: Any) -> tuple[str, str]:
    """Launch async batch export of Δ image к analysis/ folder."""
    asset_id = f"{ANALYSIS_FOLDER}/dual_baseline_delta_CH4_{month}"
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    delta_with_meta = delta.set(prov.to_asset_properties()).set(
        {
            "phase": "P-01.2",
            "analysis_type": "dual_baseline_delta",
            "month": month,
            "reference_source_asset": REF_ASSET,
            "regional_source_asset": REG_ASSET,
        }
    )
    task = ee.batch.Export.image.toAsset(
        image=delta_with_meta,
        description=f"P-01.2_delta_{month}",
        assetId=asset_id,
        region=aoi,
        scale=ANALYSIS_SCALE_M,
        crs="EPSG:4326",
        maxPixels=int(1e10),
    )
    task.start()
    return task.id, asset_id


def build_grid_samples(delta_M07: ee.Image, delta_M10: ee.Image) -> list[dict]:
    """
    Sample Δ on systematic 0.5° grid covering AOI. Returns list of dicts
    с (lat, lon, delta_M07, delta_M10, zone_band).
    """
    lon_min, lat_min, lon_max, lat_max = AOI_BBOX
    points = []
    lats = np.arange(lat_min + 0.25, lat_max, 0.5)  # cell-centered
    lons = np.arange(lon_min + 0.25, lon_max, 0.5)
    for lat in lats:
        for lon in lons:
            points.append((float(lat), float(lon)))

    fc = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"lat": lat, "lon": lon, "i": i})
            for i, (lat, lon) in enumerate(points)
        ]
    )

    delta_combined = delta_M07.addBands(delta_M10)
    sampled = delta_combined.reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=ANALYSIS_SCALE_M
    ).getInfo()

    rows = []
    for feat in sampled["features"]:
        p = feat["properties"]
        lat = p["lat"]
        # zone band classification
        zone = next((z for z, (lo, hi) in ZONE_BAND_DEFS if lo <= lat < hi), "unknown")
        rows.append(
            {
                "lat": lat,
                "lon": p["lon"],
                "delta_M07": p.get("delta_M07"),
                "delta_M10": p.get("delta_M10"),
                "zone_band": zone,
            }
        )
    return rows


def compute_statistics(grid_rows: list[dict]) -> dict:
    """
    Formal statistics (Flag 2 — PySAL/esda + diptest).

    Returns per-month stats: global mean/var |Δ|, per-zone means, Moran's I,
    Hartigan's dip test result.
    """
    import esda
    import libpysal
    from diptest import diptest

    stats = {
        "months": {},
        "citations": {"pysal": "Rey & Anselin 2010", "diptest": "Hartigan & Hartigan 1985"},
    }

    for month in ("M07", "M10"):
        key = f"delta_{month}"
        valid = [r for r in grid_rows if r.get(key) is not None and not np.isnan(r[key])]
        deltas = np.array([r[key] for r in valid])
        abs_deltas = np.abs(deltas)

        # Per-zone means
        per_zone = {}
        for zone, (lo, hi) in ZONE_BAND_DEFS:
            band_rows = [r for r in valid if lo <= r["lat"] < hi]
            band_deltas = np.array([r[key] for r in band_rows])
            if band_deltas.size > 0:
                per_zone[zone] = {
                    "n": int(band_deltas.size),
                    "mean_delta_ppb": float(np.mean(band_deltas)),
                    "mean_abs_delta_ppb": float(np.mean(np.abs(band_deltas))),
                    "median_abs_delta_ppb": float(np.median(np.abs(band_deltas))),
                    "std_delta_ppb": float(np.std(band_deltas)),
                }
            else:
                per_zone[zone] = {"n": 0}

        # Global stats
        month_stats: dict[str, Any] = {
            "n_valid": int(deltas.size),
            "n_total_grid": len(grid_rows),
            "mean_delta_ppb": float(np.mean(deltas)) if deltas.size > 0 else None,
            "mean_abs_delta_ppb": float(np.mean(abs_deltas)) if deltas.size > 0 else None,
            "median_abs_delta_ppb": float(np.median(abs_deltas)) if deltas.size > 0 else None,
            "var_abs_delta_ppb": float(np.var(abs_deltas)) if deltas.size > 0 else None,
            "max_abs_delta_ppb": float(np.max(abs_deltas)) if deltas.size > 0 else None,
            "per_zone": per_zone,
        }

        # Moran's I — spatial autocorrelation (queen-style на regular grid)
        if deltas.size >= 30:  # need minimum sample
            try:
                coords = np.array([[r["lon"], r["lat"]] for r in valid])
                # KNN weights k=8 (queen-equivalent on regular grid)
                w = libpysal.weights.KNN(coords, k=8)
                w.transform = "r"  # row-standardize
                moran = esda.Moran(deltas, w, permutations=999)
                month_stats["morans_I"] = {
                    "I": float(moran.I),
                    "expected_I": float(moran.EI),
                    "z_score": float(moran.z_sim),
                    "p_value_simulated": float(moran.p_sim),
                    "n_observations": int(deltas.size),
                    "weights_method": "KNN k=8 row-standardized",
                }
            except Exception as e:
                month_stats["morans_I"] = {"error": str(e)}
        else:
            month_stats["morans_I"] = {"error": "insufficient sample size"}

        # Hartigan's dip test for bimodality
        if deltas.size >= 10:
            try:
                dip_stat, dip_pval = diptest(deltas)
                month_stats["hartigan_dip"] = {
                    "dip_statistic": float(dip_stat),
                    "p_value": float(dip_pval),
                    "interpretation": (
                        "bimodal_likely" if dip_pval < 0.05 else "unimodal_consistent"
                    ),
                }
            except Exception as e:
                month_stats["hartigan_dip"] = {"error": str(e)}

        stats["months"][month] = month_stats

    return stats


def find_suspect_regions(delta: ee.Image, month: str) -> dict:
    """
    Find connected clusters where Δ > +SUSPECT_DELTA_PPB systematically.
    Vectorize к Features с centroid + area.
    """
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))

    suspect_mask = delta.gt(SUSPECT_DELTA_PPB).selfMask()
    cluster_count = suspect_mask.connectedPixelCount(maxSize=256)
    significant = cluster_count.gte(MIN_CLUSTER_PIXELS)
    significant_mask = suspect_mask.updateMask(significant).rename("suspect")

    vectors = significant_mask.reduceToVectors(
        geometry=aoi,
        scale=ANALYSIS_SCALE_M,
        geometryType="polygon",
        bestEffort=False,
        maxPixels=int(1e9),
        labelProperty="cluster_id",
    )

    # Add centroid + area + mean Δ per cluster
    def enrich(feat: ee.Feature) -> ee.Feature:
        centroid = feat.geometry().centroid(maxError=1)
        area_km2 = feat.geometry().area(maxError=1).divide(1e6)
        mean_delta = delta.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feat.geometry(),
            scale=ANALYSIS_SCALE_M,
        ).get(f"delta_{month}")
        max_delta = delta.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=feat.geometry(),
            scale=ANALYSIS_SCALE_M,
        ).get(f"delta_{month}")
        return feat.set(
            {
                "centroid_lon": centroid.coordinates().get(0),
                "centroid_lat": centroid.coordinates().get(1),
                "area_km2": area_km2,
                "mean_delta_ppb": mean_delta,
                "max_delta_ppb": max_delta,
                "month": month,
            }
        )

    enriched = vectors.map(enrich)
    info = enriched.getInfo()
    return info


def latitude_transect(delta_M07: ee.Image, delta_M10: ee.Image, lon: float = 75.0) -> list[dict]:
    """
    Fine-resolution (0.1°) transect at fixed longitude.
    Used для zone-boundary step quantification (TD-0021 handoff).
    """
    lats = np.arange(50.0, 75.01, 0.1)
    points = [(float(lat), lon) for lat in lats]
    fc = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"lat": lat, "lon": lon, "i": i})
            for i, (lat, _) in enumerate(points)
        ]
    )

    ref = ee.Image(REF_ASSET).select(["ref_M07", "ref_M10"])
    reg = ee.Image(REG_ASSET).select(["median_M07", "median_M10"])
    delta_combined = delta_M07.addBands(delta_M10)

    combined = ref.addBands(reg).addBands(delta_combined)
    sampled = combined.reduceRegions(
        collection=fc, reducer=ee.Reducer.first(), scale=ANALYSIS_SCALE_M
    ).getInfo()

    rows = []
    for feat in sampled["features"]:
        p = feat["properties"]
        rows.append(
            {
                "lat": p["lat"],
                "lon": p["lon"],
                "ref_M07": p.get("ref_M07"),
                "reg_M07": p.get("median_M07"),
                "delta_M07": p.get("delta_M07"),
                "ref_M10": p.get("ref_M10"),
                "reg_M10": p.get("median_M10"),
                "delta_M10": p.get("delta_M10"),
            }
        )
    return rows


def quantify_zone_boundary_steps(transect: list[dict]) -> dict:
    """
    Detect step changes в reference baseline at zone boundaries (57.5°N, 62.0°N).
    Returns step sizes для TD-0021 mitigation parameter design.
    """
    out = {}
    for boundary in BAND_BOUNDARIES:
        # Sample ±2° window around boundary
        below = [
            r for r in transect if boundary - 2 <= r["lat"] < boundary and r["ref_M07"] is not None
        ]
        above = [
            r for r in transect if boundary <= r["lat"] < boundary + 2 and r["ref_M07"] is not None
        ]
        out[f"boundary_{boundary}N"] = {
            "boundary_lat": boundary,
            "n_below": len(below),
            "n_above": len(above),
        }
        for month in ("M07", "M10"):
            key = f"ref_{month}"
            below_vals = [r[key] for r in below if r[key] is not None]
            above_vals = [r[key] for r in above if r[key] is not None]
            if below_vals and above_vals:
                step = float(np.mean(above_vals)) - float(np.mean(below_vals))
                out[f"boundary_{boundary}N"][f"step_{month}_ppb"] = step
                out[f"boundary_{boundary}N"][f"mean_below_{month}"] = float(np.mean(below_vals))
                out[f"boundary_{boundary}N"][f"mean_above_{month}"] = float(np.mean(above_vals))
    return out


def article_t1_partial_comparison(grid_rows: list[dict]) -> dict:
    """
    Partial Zone 4 comparison (article = 1854 ppb @ Middle taiga 60-63°N).
    Zones 1+8 deferred (TD-0022 partial closure).
    """
    out = {}
    for label, info in ARTICLE_T1.items():
        lo, hi = info["lat_range"]
        article_val = info["value_ppb"]
        in_band = [r for r in grid_rows if lo <= r["lat"] < hi]
        # We need ref values, not Δ. Sample reference at these grid points.
        # Use existing transect data structure isn't ideal — sample directly.
        out[label] = {
            "article_ppb": article_val,
            "lat_range": [lo, hi],
            "n_grid_cells": len(in_band),
            "note": "Reference value comparison requires separate sampling — see Phase 2A handoff",
        }
    out["TD-0022 status"] = (
        "partial — Zone 4 only; Zones 1 (Tundra 67-72°N) + 8 (Steppe 52-55°N) pending article numbers"
    )
    return out


def render_delta_maps(grid_rows: list[dict], out_dir: Path) -> dict:
    """Generate Δ scatter maps M07 + M10 + |Δ| map (proxy для full PNGs)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    valid_M07 = [r for r in grid_rows if r["delta_M07"] is not None]
    valid_M10 = [r for r in grid_rows if r["delta_M10"] is not None]

    for month, valid in [("M07", valid_M07), ("M10", valid_M10)]:
        if not valid:
            continue
        lats = np.array([r["lat"] for r in valid])
        lons = np.array([r["lon"] for r in valid])
        deltas = np.array([r[f"delta_{month}"] for r in valid])

        fig, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)
        sc = ax.scatter(lons, lats, c=deltas, cmap="RdBu_r", vmin=-50, vmax=50, s=15, alpha=0.85)
        ax.set_xlabel("Longitude (°E)")
        ax.set_ylabel("Latitude (°N)")
        ax.set_title(f"Δ = regional − reference ({month}), CH₄ ppb, 0.5° grid")
        for boundary in BAND_BOUNDARIES:
            ax.axhline(boundary, color="grey", linestyle=":", alpha=0.6)
        cbar = fig.colorbar(sc, ax=ax, label="Δ (ppb)")
        cbar.ax.axhline(SUSPECT_DELTA_PPB, color="black", linestyle="--", linewidth=0.8)
        path = out_dir / f"delta_map_{month}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths[f"delta_map_{month}"] = str(path.relative_to(REPO_ROOT))

    return paths


def render_transect(transect: list[dict], out_dir: Path) -> str:
    """Latitude transect at 75°E (publication quality)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lats = np.array([r["lat"] for r in transect])
    ref_M07 = np.array([r["ref_M07"] if r["ref_M07"] is not None else np.nan for r in transect])
    reg_M07 = np.array([r["reg_M07"] if r["reg_M07"] is not None else np.nan for r in transect])
    delta_M07 = reg_M07 - ref_M07

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), constrained_layout=True, sharex=True)
    axes[0].plot(
        lats, ref_M07, "o-", label="Reference (latitude-stratified)", color="C0", markersize=4
    )
    axes[0].plot(
        lats,
        reg_M07,
        "s-",
        label="Regional (industrial-buffered climatology)",
        color="C1",
        markersize=4,
    )
    for boundary in BAND_BOUNDARIES:
        axes[0].axvline(boundary, color="grey", linestyle="--", alpha=0.6)
    axes[0].set_ylabel("XCH₄ (ppb), M07")
    axes[0].set_title("Latitude transect at lon = 75°E (M07) — fine 0.1° resolution")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(lats, delta_M07, "o-", color="C2", markersize=4)
    axes[1].axhline(0, color="grey", linewidth=0.8)
    axes[1].axhline(30, color="red", linestyle="--", alpha=0.6, label="±30 ppb tolerance")
    axes[1].axhline(-30, color="red", linestyle="--", alpha=0.6)
    for boundary in BAND_BOUNDARIES:
        axes[1].axvline(boundary, color="grey", linestyle="--", alpha=0.6)
    axes[1].set_xlabel("Latitude (°N)")
    axes[1].set_ylabel("Δ = reg − ref (ppb)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    path = out_dir / "transect_75E.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.relative_to(REPO_ROOT))


def write_suspect_geojson(suspect_info: dict, out_path: Path) -> int:
    """Write GeoJSON of suspect clusters."""
    geojson = {"type": "FeatureCollection", "features": []}
    for feat in suspect_info.get("features", []):
        # GEE returns Feature objects already; ensure properties
        geojson["features"].append(
            {
                "type": "Feature",
                "geometry": feat["geometry"],
                "properties": feat.get("properties", {}),
            }
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(geojson, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return len(geojson["features"])


def main() -> int:
    parser = argparse.ArgumentParser(description="P-01.2 dual baseline analysis")
    parser.add_argument("--no-export", action="store_true", help="Skip Δ asset Export tasks")
    parser.add_argument("--m07-only", action="store_true", help="Only M07 (skip M10)")
    args = parser.parse_args()

    months = ["M07"] if args.m07_only else ["M07", "M10"]

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print(f"Months: {months}")
    print()

    # === Provenance (compute ONCE, DNA §2.1.12) ===
    prov = make_provenance(months)
    print(f"Provenance computed — run_id={prov.run_id}")

    write_provenance_log(
        prov,
        status="STARTED",
        gas="CH4",
        period="2019_2025",
        asset_id=ANALYSIS_FOLDER,
        extra={"phase": "P-01.2", "analysis_type": "dual_baseline_cross_check"},
    )

    # === Шаг 2: Spatial divergence + async export ===
    print("\n=== Шаг 2: Compute Δ images + async export ===")
    ensure_analysis_folder()

    delta_images: dict[str, ee.Image] = {}
    export_tasks: dict[str, dict] = {}
    for month in months:
        delta = compute_delta_image(month)
        delta_images[month] = delta
        if not args.no_export:
            task_id, asset_id = export_delta_asset(delta, month, prov)
            export_tasks[month] = {"task_id": task_id, "asset_id": asset_id}
            print(f"  {month}: export task launched id={task_id}")
        else:
            print(f"  {month}: Δ image computed (export skipped --no-export)")

    # === Шаг 3: 0.5° grid sampling + statistics ===
    print("\n=== Шаг 3: 0.5° grid sampling + formal statistics ===")
    delta_M07 = delta_images["M07"]
    delta_M10 = delta_images.get("M10", delta_M07)  # fallback

    print("  sampling 0.5° grid...")
    grid_rows = build_grid_samples(delta_M07, delta_M10)
    print(f"  grid: {len(grid_rows)} cells")

    print("  computing statistics (PySAL/esda + diptest)...")
    stats = compute_statistics(grid_rows)
    for month, s in stats["months"].items():
        n = s["n_valid"]
        mad = s.get("mean_abs_delta_ppb", "?")
        moran = s.get("morans_I", {}).get("I", "?")
        moran_p = s.get("morans_I", {}).get("p_value_simulated", "?")
        dip = s.get("hartigan_dip", {}).get("p_value", "?")
        print(
            f"  {month}: n={n}, mean|Δ|={mad if isinstance(mad, str) else f'{mad:.2f}'} ppb, "
            f"Moran I={moran if isinstance(moran, str) else f'{moran:.3f}'} "
            f"(p={moran_p if isinstance(moran_p, str) else f'{moran_p:.3f}'}), "
            f"dip p={dip if isinstance(dip, str) else f'{dip:.3f}'}"
        )

    # === Шаг 4: Suspect regions ===
    print("\n=== Шаг 4: Suspect regions (Δ > +30 ppb clusters) ===")
    suspect_info = {}
    for month in months:
        info = find_suspect_regions(delta_images[month], month)
        n_clusters = len(info.get("features", []))
        suspect_info[month] = info
        print(f"  {month}: {n_clusters} significant clusters (≥{MIN_CLUSTER_PIXELS} px)")

    # === Шаг 5: Cross-zone consistency (transect 75°E) ===
    print("\n=== Шаг 5: Cross-zone consistency (transect 75°E, 0.1° resolution) ===")
    transect = latitude_transect(delta_M07, delta_M10, lon=75.0)
    print(f"  transect: {len(transect)} sampled latitudes")
    boundary_steps = quantify_zone_boundary_steps(transect)
    for k, v in boundary_steps.items():
        step_M07 = v.get("step_M07_ppb")
        step_M10 = v.get("step_M10_ppb")
        print(
            f"  {k}: step_M07={step_M07 if step_M07 is None else f'{step_M07:.2f}'} ppb, "
            f"step_M10={step_M10 if step_M10 is None else f'{step_M10:.2f}'} ppb"
        )

    # === Шаг 6: Article t1 partial comparison ===
    print("\n=== Шаг 6: Article t1 partial comparison (Zone 4 only) ===")
    article_cmp = article_t1_partial_comparison(grid_rows)
    for k, v in article_cmp.items():
        print(f"  {k}: {v}")

    # === Save all stats + Render visualizations ===
    print("\n=== Saving outputs ===")
    out_docs = REPO_ROOT / "docs"
    out_docs.mkdir(parents=True, exist_ok=True)

    # Stats JSON
    stats_full = {
        "phase": "P-01.2",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "run_id": prov.run_id,
        "params_hash": prov.params_hash,
        "config_id": prov.config_id,
        "months_analyzed": months,
        "export_tasks": export_tasks,
        "grid_n_total": len(grid_rows),
        "statistics": stats,
        "boundary_step_quantification": boundary_steps,
        "article_t1_partial_comparison": article_cmp,
    }
    stats_path = out_docs / "p-01.2_stats.json"
    stats_path.write_text(
        json.dumps(stats_full, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"  saved: {stats_path.relative_to(REPO_ROOT)}")

    # Grid samples (для downstream)
    grid_path = out_docs / "p-01.2_grid_samples.json"
    grid_path.write_text(
        json.dumps(grid_rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"  saved: {grid_path.relative_to(REPO_ROOT)}")

    # Transect
    transect_path = out_docs / "p-01.2_transect_75E.json"
    transect_path.write_text(
        json.dumps(transect, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"  saved: {transect_path.relative_to(REPO_ROOT)}")

    # Suspect GeoJSON (concat months)
    n_suspect_total = 0
    for month in months:
        path = out_docs / f"p-01.2_suspect_regions_{month}.geojson"
        n = write_suspect_geojson(suspect_info[month], path)
        n_suspect_total += n
        print(f"  saved: {path.relative_to(REPO_ROOT)} ({n} clusters)")

    # PNGs
    pngs_dir = out_docs / "p-01.2_pngs"
    map_paths = render_delta_maps(grid_rows, pngs_dir)
    transect_png = render_transect(transect, pngs_dir)
    print(f"  saved: {transect_png}")
    for _k, p in map_paths.items():
        print(f"  saved: {p}")

    # === SUCCEEDED log entry ===
    write_provenance_log(
        prov,
        status="SUCCEEDED",
        gas="CH4",
        period="2019_2025",
        asset_id=ANALYSIS_FOLDER,
        ended_at=datetime.now(timezone.utc).isoformat(),
        extra={
            "phase": "P-01.2",
            "n_grid_cells": len(grid_rows),
            "n_suspect_clusters_total": n_suspect_total,
            "export_tasks": export_tasks,
        },
    )

    print("\n=== Phase 1c analysis COMPLETE ===")
    print(f"Run ID: {prov.run_id}")
    print(f"Stats: {stats_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
