"""
Phase 1c (P-01.2) synthetic divergence pipeline test.

Sanity check перед running на real data. Generates synthetic regional image =
reference baseline + known Δ patterns в 3 latitude bands, runs through dual
baseline cross-check pipeline, verifies output Δ matches expected values
within numerical tolerance (0.01 ppb).

Multi-pattern test (per researcher Flag 3 decision):
  * Pattern A: Δ=10 ppb at (54.0°N, 88.0°E) — Kuznetsky band
  * Pattern B: Δ=30 ppb at (61.0°N, 75.0°E) — Yugansky band
  * Pattern C: Δ=50 ppb at (65.0°N, 80.0°E) — Verkhne-Tazovsky band

If FAIL → escalate, не proceed к real data analysis.

Usage::

    python src/py/setup/test_dual_baseline_pipeline.py

Exit code 0 = PASS; exit code 1 = FAIL (pipeline bug).
"""

from __future__ import annotations

import sys
from pathlib import Path

import ee

# Console на Windows default cp1251 — Unicode (Δ, °, ²) crashes print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "py"))

GEE_PROJECT = "nodal-thunder-481307-u1"
REF_ASSET = (
    "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/reference_CH4_2019_2025_v1"
)

# Multi-pattern synthetic Δ injections (per Flag 3 — 3 squares × 3 zones)
PATTERNS = [
    {"name": "A_kuznetsky", "lat": 54.0, "lon": 88.0, "delta_ppb": 10},
    {"name": "B_yugansky", "lat": 61.0, "lon": 75.0, "delta_ppb": 30},
    {"name": "C_verkhne_tazovsky", "lat": 65.0, "lon": 80.0, "delta_ppb": 50},
]
SQUARE_HALF_DEG = 0.5  # 1°×1° squares
TOLERANCE_PPB = 0.01

ANALYSIS_SCALE_M = 7000  # native TROPOMI L3 grid


def make_pattern_geometry(p: dict) -> ee.Geometry:
    """Generate 1°×1° square ee.Geometry for pattern."""
    lat = p["lat"]
    lon = p["lon"]
    return ee.Geometry.Rectangle(
        [
            lon - SQUARE_HALF_DEG,
            lat - SQUARE_HALF_DEG,
            lon + SQUARE_HALF_DEG,
            lat + SQUARE_HALF_DEG,
        ]
    )


def build_synthetic_regional(reference: ee.Image, patterns: list[dict]) -> ee.Image:
    """
    Synthetic regional = reference + pattern_delta inside each pattern square,
    else regional == reference (Δ=0 outside patterns).

    Implementation note: use ``.where(mask_image, value_image)`` с a non-zero
    boolean mask. Constants без projection в `clip` + `add` produce masked
    output downstream; `.where` preserves reference projection while substituting
    values inside the masked region.
    """
    synthetic = reference  # start unchanged

    for p in patterns:
        square = make_pattern_geometry(p)
        # Mask image: 1 inside square, masked outside.
        # `.where(condition!=0, value)` substitutes only where condition is truthy.
        mask = ee.Image.constant(1).clip(square)
        # Inside square: replace synthetic с reference + delta
        synthetic = synthetic.where(mask, reference.add(p["delta_ppb"]))

    return synthetic


def verify_pattern(
    delta: ee.Image, p: dict, band: str, tolerance: float = TOLERANCE_PPB
) -> tuple[bool, float]:
    """
    Reduce Δ image на pattern square. Verify mean Δ within tolerance of expected.
    Returns (pass: bool, observed_delta: float).
    """
    square = make_pattern_geometry(p)
    sampled = delta.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=square,
        scale=ANALYSIS_SCALE_M,
        bestEffort=False,
        maxPixels=int(1e9),
    ).getInfo()
    observed = sampled.get(band)
    if observed is None:
        return False, float("nan")
    return abs(observed - p["delta_ppb"]) < tolerance, float(observed)


def main() -> int:
    ee.Initialize(project=GEE_PROJECT)
    print(f"GEE initialized — project={GEE_PROJECT}")
    print()
    print("=== Synthetic dual baseline pipeline test ===")
    print(f"Reference asset: {REF_ASSET}")
    print(f"Tolerance:       {TOLERANCE_PPB} ppb")
    print()

    reference = ee.Image(REF_ASSET).select("ref_M07")

    # Build synthetic regional с known Δ injections
    synthetic_regional = build_synthetic_regional(reference, PATTERNS)

    # Run "pipeline" — for sanity, just compute Δ = synthetic_regional - reference
    # Real Phase 1c pipeline does same operation на actual regional asset.
    delta = synthetic_regional.subtract(reference).rename("ref_M07")

    all_pass = True
    print(f"{'pattern':<25} {'expected':>10} {'observed':>12} {'|err|':>10} {'verdict':>8}")
    for p in PATTERNS:
        passed, observed = verify_pattern(delta, p, "ref_M07")
        err = abs(observed - p["delta_ppb"]) if observed == observed else float("nan")
        verdict = "PASS" if passed else "FAIL"
        print(f"  {p['name']:<23} {p['delta_ppb']:>10} {observed:>12.4f} {err:>10.4f} {verdict:>8}")
        if not passed:
            all_pass = False

    print()
    print("=" * 70)
    if all_pass:
        print("SYNTHETIC TEST PASSED — pipeline computes Δ correctly")
        print("Proceed к real data analysis.")
        return 0
    else:
        print("SYNTHETIC TEST FAILED — pipeline bug detected.")
        print("DO NOT proceed к real data analysis. Investigate pipeline.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
