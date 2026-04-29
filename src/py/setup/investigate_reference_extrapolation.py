"""
Investigation: quantitative impact of latitude-only zone stratification
в reference baseline (`reference_CH4_2019_2025_v1`).

Trigger: P-01.0b cross-check showed 38 ppb spread (-17.91 to +21.56) для
non-industrial points across AOI — beyond consistency_tolerance_ppb=30.

Reference architecture (build_reference_baseline_ch4.py:226-247): each pixel
gets baseline of nearest zone purely by |Δlat|, NO longitude weighting.
Zone centroids (lat°): Yugansky 60.5, Verkhne-Tazovsky 63.5, Kuznetsky-
Alatau 54.5.

Deliverables (per researcher 2026-04-29):
  1. Spatial zone-assignment map + lat_dist heatmap (PNG)
  2. Δ(reg-ref) vs lat_dist scatter с linear fit + Pearson R² (PNG)
  3. Latitude transect at lon=75°E (PNG)
  4. Article t1 zonal stats comparison (where available)

Decision criterion (researcher):
  R² > 0.5 → STOP, methodology revision (CHANGE-0018 candidate)
  R² 0.2..0.5 → proceed с extended caveat
  R² < 0.2 → proceed normally
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

# Console на Windows default cp1251 — Unicode (Δ, °, ²) crashes print().
# Reconfigure stdout/stderr to UTF-8 with replacement fallback.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GEE_PROJECT = "nodal-thunder-481307-u1"

REF_ASSET = (
    "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/reference_CH4_2019_2025_v1"
)
REG_ASSET = "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/regional_CH4_2019_2025"
BUFFERED_MASK_ASSET = (
    "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/industrial/proxy_mask_buffered_30km"
)

AOI_BBOX = (60.0, 50.0, 95.0, 75.0)  # lon_min, lat_min, lon_max, lat_max

ZONES = {
    "yugansky": (60.5, 74.5),
    "verkhne_tazovsky": (63.5, 84.0),
    "kuznetsky_alatau": (54.5, 88.0),
}

MONTH = 7  # July — peak summer signal, full daylight

N_RANDOM_POINTS = 120  # researcher said 50-100, take 120 для headroom после mask filter

# Article t1 (adjacent project) — researcher provided partial data:
ARTICLE_T1_ZONAL = {
    # zone_label -> (lat_min, lat_max, baseline_ppb_M07_or_year_mean)
    "Zone 1 (Tundra)": (67.0, 72.0, None),  # not provided
    "Zone 4 (Middle taiga)": (60.0, 63.0, 1854.0),
    "Zone 8 (Steppe)": (52.0, 55.0, None),  # not provided
}


def km_per_degree_lat(lat_deg: float) -> float:
    """Approx km per 1° latitude (essentially constant ~111 km)."""
    _ = lat_deg
    return 111.32


def assigned_zone(lat: float) -> tuple[str, float]:
    """Find nearest zone centroid by |Δlat|. Returns (zone_id, lat_dist_deg)."""
    best_id, best_dist = None, 1e9
    for zid, (zlat, _zlon) in ZONES.items():
        d = abs(lat - zlat)
        if d < best_dist:
            best_dist = d
            best_id = zid
    return best_id, best_dist  # type: ignore[return-value]


def render_zone_map(out_png: Path) -> None:
    """Coarse PNG of zone assignment + lat_dist heatmap (computed locally)."""
    lon_min, lat_min, lon_max, lat_max = AOI_BBOX
    lats = np.arange(lat_min, lat_max + 0.01, 0.5)
    lons = np.arange(lon_min, lon_max + 0.01, 0.5)
    LON, LAT = np.meshgrid(lons, lats)

    zone_ids = list(ZONES.keys())
    dist_grid = np.full(LAT.shape, 1e9)
    zone_grid = np.full(LAT.shape, -1, dtype=int)
    for i, zid in enumerate(zone_ids):
        zlat, _zlon = ZONES[zid]
        d = np.abs(LAT - zlat)
        better = d < dist_grid
        dist_grid = np.where(better, d, dist_grid)
        zone_grid = np.where(better, i, zone_grid)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)

    cmap = plt.get_cmap("tab10", len(zone_ids))
    im0 = axes[0].pcolormesh(LON, LAT, zone_grid, cmap=cmap, vmin=-0.5, vmax=len(zone_ids) - 0.5)
    axes[0].set_title(f"Zone assignment (latitude stratification, M{MONTH:02d})")
    axes[0].set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    cbar0 = fig.colorbar(im0, ax=axes[0], ticks=range(len(zone_ids)))
    cbar0.ax.set_yticklabels(zone_ids)
    for zid, (zlat, zlon) in ZONES.items():
        axes[0].plot(zlon, zlat, "k*", markersize=14)
        axes[0].annotate(zid, (zlon, zlat), xytext=(6, 6), textcoords="offset points", fontsize=9)

    im1 = axes[1].pcolormesh(LON, LAT, dist_grid * 111.32, cmap="viridis")
    axes[1].set_title("Distance to nearest zone centroid (km, latitude only)")
    axes[1].set_xlabel("Longitude")
    axes[1].set_ylabel("Latitude")
    fig.colorbar(im1, ax=axes[1], label="lat_dist (km)")
    for _zid, (zlat, zlon) in ZONES.items():
        axes[1].plot(zlon, zlat, "r*", markersize=14)

    fig.suptitle("Reference baseline zone assignment + lat-distance heatmap", fontsize=12)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def random_points_outside_industrial(n: int, seed: int = 42) -> list[tuple[float, float]]:
    """Generate n random (lat, lon) inside AOI, sampling buffered_mask to exclude
    industrial pixels. Uses GEE sample for masked-out exclusion.
    """
    aoi = ee.Geometry.Rectangle(list(AOI_BBOX))
    # Band: industrial_clean_mask (1=clean non-industrial, 0=industrial-buffered).
    mask = ee.Image(BUFFERED_MASK_ASSET).unmask(0)
    candidates = ee.FeatureCollection.randomPoints(region=aoi, points=n * 3, seed=seed)
    sampled = mask.sampleRegions(
        collection=candidates,
        scale=1113.2,
        geometries=True,
    )
    keepers = sampled.filter(ee.Filter.eq("industrial_clean_mask", 1)).limit(n).getInfo()
    out: list[tuple[float, float]] = []
    for feat in keepers["features"]:
        lon, lat = feat["geometry"]["coordinates"]
        out.append((lat, lon))
    return out


def sample_ref_reg_at_points(points: list[tuple[float, float]]) -> list[dict]:
    """Single round-trip: sample ref + reg + lat_dist на N points для месяца MONTH."""
    fc = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"lat": lat, "lon": lon, "i": i})
            for i, (lat, lon) in enumerate(points)
        ]
    )

    ref = ee.Image(REF_ASSET).select([f"ref_M{MONTH:02d}", f"lat_dist_M{MONTH:02d}"])
    reg = ee.Image(REG_ASSET).select([f"median_M{MONTH:02d}"])
    combo = ref.addBands(reg)

    sampled = combo.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=1113.2).getInfo()

    rows = []
    for feat in sampled["features"]:
        p = feat["properties"]
        lat = p["lat"]
        lon = p["lon"]
        ref_v = p.get(f"ref_M{MONTH:02d}")
        reg_v = p.get(f"median_M{MONTH:02d}")
        lat_dist_deg = p.get(f"lat_dist_M{MONTH:02d}")
        zone_id, _local_dist = assigned_zone(lat)
        if lat_dist_deg is None:
            lat_dist_deg = _local_dist
        delta = None if ref_v is None or reg_v is None else reg_v - ref_v
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "ref": ref_v,
                "reg": reg_v,
                "delta": delta,
                "lat_dist_deg": lat_dist_deg,
                "lat_dist_km": (lat_dist_deg * 111.32) if lat_dist_deg is not None else None,
                "assigned_zone": zone_id,
            }
        )
    return rows


def render_delta_vs_distance(rows: list[dict], out_png: Path) -> dict:
    """Scatter Δ vs lat_dist + linear fit + Pearson R² for |Δ|."""
    xs = np.array([r["lat_dist_km"] for r in rows if r["delta"] is not None])
    ys = np.array([r["delta"] for r in rows if r["delta"] is not None])
    abs_ys = np.abs(ys)

    if xs.size < 3:
        raise RuntimeError(f"Only {xs.size} valid points — need ≥ 3 для regression.")

    slope, intercept, r_value, p_value, _ = stats.linregress(xs, abs_ys)
    r_squared = r_value**2

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.scatter(xs, ys, alpha=0.6, label=f"Δ = reg − ref (n={xs.size})")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.axhline(30, color="red", linestyle="--", linewidth=0.8, label="±tolerance 30 ppb")
    ax.axhline(-30, color="red", linestyle="--", linewidth=0.8)
    xs_line = np.linspace(xs.min(), xs.max(), 100)
    ax.plot(
        xs_line,
        slope * xs_line + intercept,
        color="black",
        linewidth=1.5,
        label=f"|Δ| linear fit: slope={slope:.3f} ppb/km, R²={r_squared:.3f}",
    )
    ax.plot(
        xs_line,
        -(slope * xs_line + intercept),
        color="black",
        linewidth=1.5,
        linestyle=":",
    )
    ax.set_xlabel("lat_dist to nearest zone centroid (km)")
    ax.set_ylabel("Δ = reg − ref (ppb)  [M07]")
    ax.set_title(
        f"Reference extrapolation impact — Δ vs distance, M07, n={xs.size} clean random points"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)

    return {
        "n": int(xs.size),
        "slope_ppb_per_km": float(slope),
        "intercept_ppb": float(intercept),
        "r": float(r_value),
        "r_squared": float(r_squared),
        "p_value": float(p_value),
        "abs_delta_max": float(np.max(abs_ys)),
        "abs_delta_mean": float(np.mean(abs_ys)),
        "abs_delta_median": float(np.median(abs_ys)),
        "lat_dist_km_max": float(xs.max()),
        "lat_dist_km_mean": float(xs.mean()),
    }


def latitude_transect(out_png: Path) -> list[dict]:
    """Fixed lon=75°E, lat 50..75 step 0.5°. Sample ref/reg M07."""
    lon_fixed = 75.0
    lats = np.arange(50.0, 75.01, 0.5)
    points = [(float(lat), lon_fixed) for lat in lats]
    rows = sample_ref_reg_at_points(points)

    lat_arr = np.array([r["lat"] for r in rows])
    ref_arr = np.array([r["ref"] if r["ref"] is not None else np.nan for r in rows])
    reg_arr = np.array([r["reg"] if r["reg"] is not None else np.nan for r in rows])
    delta_arr = reg_arr - ref_arr

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True, sharex=True)
    axes[0].plot(lat_arr, ref_arr, "o-", label="ref (latitude-stratified)", color="C0")
    axes[0].plot(lat_arr, reg_arr, "s-", label="reg (industrial-buffered climatology)", color="C1")
    for zid, (zlat, _zlon) in ZONES.items():
        axes[0].axvline(zlat, color="grey", linestyle="--", alpha=0.6)
        axes[0].annotate(zid, (zlat, axes[0].get_ylim()[1]), fontsize=8, ha="center")
    axes[0].set_ylabel("XCH₄ (ppb), M07")
    axes[0].set_title(f"Latitude transect at lon = {lon_fixed}°E (M07)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(lat_arr, delta_arr, "o-", color="C2")
    axes[1].axhline(0, color="grey", linewidth=0.8)
    axes[1].axhline(30, color="red", linestyle="--", linewidth=0.8)
    axes[1].axhline(-30, color="red", linestyle="--", linewidth=0.8)
    for _zid, (zlat, _zlon) in ZONES.items():
        axes[1].axvline(zlat, color="grey", linestyle="--", alpha=0.6)
    axes[1].set_xlabel("Latitude (°N)")
    axes[1].set_ylabel("Δ = reg − ref (ppb)")
    axes[1].grid(True, alpha=0.3)

    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return rows


def article_comparison(transect_rows: list[dict]) -> dict:
    """Compare reference values to adjacent project article t1 zonal stats."""
    cmp = {}
    for label, (lat_lo, lat_hi, article_val) in ARTICLE_T1_ZONAL.items():
        in_band = [
            r for r in transect_rows if lat_lo <= r["lat"] <= lat_hi and r["ref"] is not None
        ]
        if not in_band:
            cmp[label] = {"article": article_val, "ref_mean": None, "n": 0}
            continue
        ref_mean = float(np.mean([r["ref"] for r in in_band]))
        cmp[label] = {
            "article": article_val,
            "ref_mean": ref_mean,
            "n": len(in_band),
            "delta_vs_article": (ref_mean - article_val) if article_val is not None else None,
        }
    return cmp


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / "docs" / "p-01.0b_extrapolation_investigation"
    out_dir.mkdir(parents=True, exist_ok=True)

    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")

    print("\n=== Step 1: Zone-assignment map + lat-distance heatmap (local compute) ===")
    map_png = out_dir / "01_zone_map.png"
    render_zone_map(map_png)
    print(f"  saved: {map_png.relative_to(repo_root)}")

    print("\n=== Step 2: Random clean points sample (mask-filtered) ===")
    points = random_points_outside_industrial(N_RANDOM_POINTS)
    print(f"  obtained {len(points)} clean (non-industrial-buffered) points")

    print("\n=== Step 3: Sample ref+reg+lat_dist на random points (M07) ===")
    rows = sample_ref_reg_at_points(points)
    rows_with_delta = [r for r in rows if r["delta"] is not None]
    print(f"  valid delta values: {len(rows_with_delta)} / {len(rows)} (NaN excluded)")

    print("\n=== Step 4: Δ vs distance scatter + linear regression ===")
    scatter_png = out_dir / "02_delta_vs_distance.png"
    stats_d = render_delta_vs_distance(rows_with_delta, scatter_png)
    print(f"  saved: {scatter_png.relative_to(repo_root)}")
    print(f"  R² (|Δ| vs lat_dist_km) = {stats_d['r_squared']:.4f}")
    print(f"  slope = {stats_d['slope_ppb_per_km']:.4f} ppb/km")
    print(f"  p-value = {stats_d['p_value']:.4g}")
    print(
        f"  |Δ|: max={stats_d['abs_delta_max']:.2f}, mean={stats_d['abs_delta_mean']:.2f}, "
        f"median={stats_d['abs_delta_median']:.2f} ppb"
    )

    print("\n=== Step 5: Latitude transect at 75°E ===")
    transect_png = out_dir / "03_latitude_transect.png"
    transect_rows = latitude_transect(transect_png)
    print(f"  saved: {transect_png.relative_to(repo_root)}")

    print("\n=== Step 6: Article t1 zonal stats comparison ===")
    cmp = article_comparison(transect_rows)
    for label, d in cmp.items():
        if d["article"] is None:
            print(f"  {label}: article=N/A, ref_mean={d['ref_mean']}, n={d['n']}")
        else:
            print(
                f"  {label}: article={d['article']:.0f}, ref_mean={d['ref_mean']:.2f}, "
                f"n={d['n']}, Δ={d['delta_vs_article']:.2f} ppb"
            )

    print("\n=== Decision criterion ===")
    r2 = stats_d["r_squared"]
    if r2 > 0.5:
        verdict = "STOP — methodology revision (CHANGE-0018 candidate)"
    elif r2 >= 0.2:
        verdict = "PROCEED with extended caveat"
    else:
        verdict = (
            "PROCEED normally — Δ values reflect biome differences, not extrapolation artifact"
        )
    print(f"  R² = {r2:.4f} → {verdict}")

    out_json = out_dir / "stats.json"
    out_json.write_text(
        json.dumps(
            {
                "month": MONTH,
                "n_random_points_requested": N_RANDOM_POINTS,
                "regression": stats_d,
                "transect_lon": 75.0,
                "article_comparison": cmp,
                "verdict": verdict,
                "rows_random": rows,
                "rows_transect": transect_rows,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved stats: {out_json.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
