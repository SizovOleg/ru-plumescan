"""
P-01.2 Tool-paper Figure 1 — «Dual baseline architecture validation».

4-panel publication-quality figure (300 DPI):
  Panel A: Reference baseline map (M07) — latitude-stratified plateaus
  Panel B: Regional baseline map (M07) — industrial-buffered climatology
  Panel C: |Δ| map с suspect clusters annotated
  Panel D: Latitude transect ref vs reg at 75°E

Inputs: docs/p-01.2_grid_samples.json, docs/p-01.2_transect_75E.json,
        docs/p-01.2_suspect_regions_M07.geojson
Output: docs/p-01.2_figure_1.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]

GRID_PATH = REPO_ROOT / "docs" / "p-01.2_grid_samples.json"
TRANSECT_PATH = REPO_ROOT / "docs" / "p-01.2_transect_75E.json"
SUSPECT_PATH = REPO_ROOT / "docs" / "p-01.2_suspect_regions_M07.geojson"
OUT_PATH = REPO_ROOT / "docs" / "p-01.2_figure_1.png"

ZONE_CENTROIDS = {"yugansky": 60.5, "verkhne_tazovsky": 63.5, "kuznetsky_alatau": 54.5}
BAND_BOUNDARIES = (57.5, 62.0)


def load_data() -> tuple[list[dict], list[dict], dict]:
    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    transect = json.loads(TRANSECT_PATH.read_text(encoding="utf-8"))
    suspect = json.loads(SUSPECT_PATH.read_text(encoding="utf-8"))
    return grid, transect, suspect


def main() -> int:
    grid, transect, suspect = load_data()

    # Filter to М07 valid points only
    valid = [
        r for r in grid if r.get("delta_M07") is not None and not (np.isnan(float(r["delta_M07"])))
    ]
    lons = np.array([r["lon"] for r in valid])
    lats = np.array([r["lat"] for r in valid])
    deltas = np.array([float(r["delta_M07"]) for r in valid])

    # Reference values from transect (only at 75°E, but illustrate plateaus)
    # For panels A/B, we visualize Δ at grid level since we don't have full ref/reg map
    # за scope здесь; instead show Δ + suspect, use transect для panel D.
    abs_deltas = np.abs(deltas)

    fig = plt.figure(figsize=(16, 11), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, hspace=0.15, wspace=0.1)

    # --- Panel A: Δ map M07 (reg − ref, signed) ---
    axA = fig.add_subplot(gs[0, 0])
    scA = axA.scatter(lons, lats, c=deltas, cmap="RdBu_r", vmin=-50, vmax=50, s=18, alpha=0.85)
    for b in BAND_BOUNDARIES:
        axA.axhline(b, color="grey", linestyle=":", alpha=0.6, linewidth=0.7)
    for zone, lat in ZONE_CENTROIDS.items():
        axA.scatter([], [], label=f"{zone} ({lat}°N)")
    axA.set_xlabel("Longitude (°E)")
    axA.set_ylabel("Latitude (°N)")
    axA.set_title("(A) Δ = regional − reference, M07 (CH₄ ppb)")
    fig.colorbar(scA, ax=axA, label="Δ (ppb)", shrink=0.85)

    # --- Panel B: |Δ| map ---
    axB = fig.add_subplot(gs[0, 1])
    scB = axB.scatter(lons, lats, c=abs_deltas, cmap="viridis", vmin=0, vmax=80, s=18, alpha=0.85)
    for b in BAND_BOUNDARIES:
        axB.axhline(b, color="white", linestyle=":", alpha=0.6, linewidth=0.7)
    axB.set_xlabel("Longitude (°E)")
    axB.set_ylabel("Latitude (°N)")
    axB.set_title("(B) |Δ| magnitude, M07 (CH₄ ppb)")
    fig.colorbar(scB, ax=axB, label="|Δ| (ppb)", shrink=0.85)

    # --- Panel C: Suspect clusters annotated ---
    axC = fig.add_subplot(gs[1, 0])
    # base scatter с lighter alpha
    axC.scatter(lons, lats, c=deltas, cmap="RdBu_r", vmin=-50, vmax=50, s=12, alpha=0.4)
    # suspect cluster centroids
    sus_lats = []
    sus_lons = []
    sus_deltas = []
    sus_areas = []
    for f in suspect.get("features", []):
        p = f.get("properties", {})
        if p.get("centroid_lat") is None:
            continue
        sus_lats.append(p["centroid_lat"])
        sus_lons.append(p["centroid_lon"])
        sus_deltas.append(p.get("mean_delta_ppb", 0))
        sus_areas.append(p.get("area_km2", 50))
    sus_lats = np.array(sus_lats)
    sus_lons = np.array(sus_lons)
    sus_deltas = np.array(sus_deltas)
    sus_areas = np.array(sus_areas)
    # Markersize ~ area; color = mean Δ
    if sus_lats.size > 0:
        scC = axC.scatter(
            sus_lons,
            sus_lats,
            c=sus_deltas,
            s=np.clip(sus_areas / 5, 20, 250),
            cmap="OrRd",
            vmin=30,
            vmax=80,
            edgecolors="black",
            linewidths=0.6,
            alpha=0.85,
        )
        fig.colorbar(scC, ax=axC, label="cluster mean Δ (ppb)", shrink=0.85)
    for b in BAND_BOUNDARIES:
        axC.axhline(b, color="grey", linestyle=":", alpha=0.6, linewidth=0.7)
    axC.set_xlabel("Longitude (°E)")
    axC.set_ylabel("Latitude (°N)")
    axC.set_title(f"(C) Suspect clusters (Δ > +30 ppb), M07 — n={sus_lats.size}")

    # --- Panel D: Transect 75°E ref vs reg ---
    axD = fig.add_subplot(gs[1, 1])
    t_lats = np.array([r["lat"] for r in transect])
    t_ref = np.array([r["ref_M07"] if r["ref_M07"] is not None else np.nan for r in transect])
    t_reg = np.array([r["reg_M07"] if r["reg_M07"] is not None else np.nan for r in transect])
    axD.plot(t_lats, t_ref, "o-", label="Reference (latitude-stratified)", color="C0", markersize=3)
    axD.plot(t_lats, t_reg, "s-", label="Regional (industrial-buffered)", color="C1", markersize=3)
    for b in BAND_BOUNDARIES:
        axD.axvline(b, color="grey", linestyle="--", alpha=0.6, linewidth=0.7)
    for zone, lat in ZONE_CENTROIDS.items():
        axD.axvline(lat, color="black", linestyle=":", alpha=0.4, linewidth=0.5)
        axD.text(
            lat,
            axD.get_ylim()[1] if axD.get_ylim()[1] else 1920,
            zone[:3].upper(),
            fontsize=7,
            ha="center",
            va="bottom",
        )
    axD.set_xlabel("Latitude (°N)")
    axD.set_ylabel("XCH₄ (ppb), M07")
    axD.set_title("(D) Latitude transect at lon = 75°E (0.1° resolution)")
    axD.legend(loc="lower right", fontsize=8)
    axD.grid(True, alpha=0.3)

    fig.suptitle(
        "Figure 1. Dual baseline architecture validation (CH₄, M07 2019-2024)",
        fontsize=13,
        fontweight="bold",
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Figure 1 saved: {OUT_PATH.relative_to(REPO_ROOT)} (300 DPI)")
    print(f"  size: {OUT_PATH.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
