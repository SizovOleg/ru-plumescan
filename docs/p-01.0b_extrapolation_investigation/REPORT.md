# Investigation Report — Reference baseline latitude-stratification extrapolation

**Run date:** 2026-04-29
**Trigger:** P-01.0b cross-check showed 38 ppb spread across non-industrial points — beyond `consistency_tolerance_ppb=30`. Researcher hypothesis: latitude-only stratification may produce extrapolation-distance-driven Δ artifacts.
**Source script:** `src/py/setup/investigate_reference_extrapolation.py`
**Raw data:** `docs/p-01.0b_extrapolation_investigation/stats.json`

---

## 1. Verdict — PROCEED NORMALLY

Per researcher's pre-stated decision criterion:

| R² (\|Δ\| vs lat_dist) | Action |
|------------------------|--------|
| > 0.5 | STOP — methodology revision (CHANGE-0018) |
| 0.2 – 0.5 | PROCEED with extended caveat |
| **< 0.2** | **PROCEED normally — Δ reflects biome differences, not extrapolation artifact** |

**Measured R² = 0.0023** (n=104 random clean points, M07).

Slope = −0.003 ppb/km (essentially zero), p-value = 0.629 (NOT statistically significant).

→ **GO для NO₂/SO₂ runs.**

---

## 2. Methodology

### 2.1 Reference baseline architecture (confirmed)

`build_reference_baseline_ch4.py` lines 226–247 implement **pure-latitude stratification**:

```
для каждого pixel:
    для каждой zone:
        lat_dist = |pixel.lat − zone.centroid_lat|
    pixel.ref = baseline of zone where lat_dist минимально
    pixel.lat_dist_band = тот lat_dist
```

NO longitude weighting. Three active zones (centroid lat°): Yugansky 60.5, Verkhne-Tazovsky 63.5, Kuznetsky-Alatau 54.5.

### 2.2 Test design

**Sample population:** 120 random points в AOI (60-95°E, 50-75°N), filtered к 104 valid pairs after:
- masking via `industrial_clean_mask=1` (excludes 30 km industrial buffer)
- excluding NaN points (no ref or no reg value)

**Metric:** Δ = reg_M07 − ref_M07 в ppb. Independent variable: `lat_dist_M07` band (km, ×111.32 from degrees).

**Plot:** `02_delta_vs_distance.png`.

### 2.3 Auxiliary deliverables

- `01_zone_map.png` — coarse zone assignment + lat-distance heatmap (local compute, не GEE).
- `03_latitude_transect.png` — transect at fixed lon=75°E, lat 50-75 step 0.5°.
- `stats.json` — все sampled rows + regression numbers.

---

## 3. Δ vs distance findings

| Statistic | Value |
|-----------|-------|
| n valid pairs | 104 |
| Pearson r | −0.0480 |
| **R²** | **0.0023** |
| slope | −0.0025 ppb/km |
| intercept | 20.46 ppb |
| p-value | 0.6289 |
| max \|Δ\| | 54.03 ppb |
| mean \|Δ\| | 19.80 ppb |
| median \|Δ\| | 15.82 ppb |
| max lat_dist | 1240 km (75°N pixel) |

**Interpretation:** absolute deviation \|Δ\| is **NOT** explained by distance к zone centroid (R² < 0.005). Points 1200 km away have similar \|Δ\| distribution as points 0-100 km away.

**Implication:** if distance-driven extrapolation were the dominant uncertainty source, we'd expect mostly small Δ near centroids and large Δ far away. We don't see that — Δ scatter is roughly homogeneous across distances. So latitude stratification doesn't introduce systematic distance bias.

The non-zero \|Δ\| **does** exist — mean ~20 ppb, max 54 ppb — but its source is **not** extrapolation distance. Likely sources (not directly measured here):
- Real biome variation within latitude bands (longitude effect)
- Period mismatch (reference 7-year mean vs regional climatology median)
- Wetland-vs-non-wetland fraction within reference zones (zone polygons include mixed land cover)

---

## 4. Latitude transect at lon=75°E (M07)

`03_latitude_transect.png` shows two important features:

**Top panel — ref vs reg lines:**
- ref shows **three discrete plateaus** at lat=50-57° (~1846 ppb, Kuznetsky), 57-62° (~1880 ppb, Yugansky), 62-75° (~1863 ppb, Verkhne-Tazovsky). Step changes are sharp (degrees-thick) at zone boundaries (57° and 62°).
- reg смоothly varies, mostly 1865-1890 ppb, с industrial-buffered NaN gaps around 64°N (compressor stations region).

**Bottom panel — Δ:**
- 4 outliers above +30 ppb tolerance: at 53° (steppe-taiga transition), at 72-73° (high tundra). Both regions where reg is high (boreal forest summer / tundra wetlands) but the assigned ref baseline is low.
- Several outliers below 0 в Yugansky band (57-62°), where ref baseline 1880 is HIGH and reg drops near 1860.

**Step-change artifact:** at zone boundaries (57°, 62°), ref jumps by 14-17 ppb while reg is continuous. **This** creates spurious Δ even though distance-to-centroid isn't the driver. It's a *discretization* artifact, not an *extrapolation* artifact.

---

## 5. Article t1 zonal-stats comparison

Researcher provided partial reference (zone 4 only):

| Article zone | Lat band | Article t1 (ppb) | Our ref_mean (ppb) | n | Δ ours-article |
|--------------|----------|------------------|--------------------|---|----------------|
| Zone 1 (Tundra) | 67-72°N | N/A | 1863.354 | 11 | — |
| Zone 4 (Middle taiga) | 60-63°N | **1854** | **1873.08** | 7 | **+19.08** |
| Zone 8 (Steppe) | 52-55°N | N/A | 1845.527 | 7 | — |

**Zone 4 Δ vs article = +19 ppb.** Plausible explanations (not separable here):
- Article: wetland-only XCH₄ 7-year mean. Our ref: whole-zapoved-polygon (mixed wetland + boreal forest).
- Article period likely earlier/different from our 2019-2025.
- M07 only here vs annual mean в article.

Full assessment не возможен без полных article t1 data. **Action item for Phase 1c (deferred):** request authors provide tundra/steppe zone numbers для proper comparison.

Ref values на Tundra/Steppe identical to Verkhne-Tazovsky / Kuznetsky-Alatau respectively — not surprising given latitude stratification puts entire 67-72°N band на Verkhne-Tazovsky baseline (its centroid is south at 63.5°N).

---

## 6. What we now know about reference baseline quality

| Concern | Result |
|---------|--------|
| Distance-driven extrapolation creates large Δ | **NO** (R²=0.002) |
| Methodology produces *some* Δ | YES (mean 20, max 54 ppb) |
| Source of Δ is distance-к-centroid | NO |
| Source of Δ includes zone-boundary discretization | YES (visible в transect step changes) |
| Source of Δ includes biome variation within band | LIKELY (not measured directly) |
| Methodology safe для "secondary baseline" role | YES, with documented caveats |
| Methodology safe для primary-fallback в Phase 2A | YES, with `consistency_flag` properly used |

---

## 7. Conclusions and Phase 2A recommendations

1. **GO для NO₂/SO₂ regional climatology runs.** No methodology-changing finding.

2. **TD-0019 RESOLVED**: distance is not the driver. Filing as resolved (not blocking).

3. **New downstream caveat для Algorithm §3.4.3 / Phase 2A** (recommend documenting):
   - When `consistency_flag=false` AND nearest reference zone is far в latitude (e.g., > 5° = ~550 km), do not blindly fall back на reference. Instead, treat as "ambiguous" and require additional evidence (cluster size, wind alignment).
   - Discrete zone-boundary step changes can produce spurious `consistency_flag=false` near 57°N and 62°N at lon=75°E (and similar transitions elsewhere). Phase 2A detection should record `lat_dist_km` per candidate as confidence-modifier.

4. **Future improvement (deferred, не блокер)**: distance-weighted blending между nearest-2 zones смягчил бы step changes. Consider в potential `CHANGE-0018` future revision after Phase 1c full cross-check map.

5. **Article t1 comparison** — partial; deferred к Phase 1c.

---

## 8. Reproducibility

```bash
python src/py/setup/investigate_reference_extrapolation.py
# → docs/p-01.0b_extrapolation_investigation/01_zone_map.png
# → docs/p-01.0b_extrapolation_investigation/02_delta_vs_distance.png
# → docs/p-01.0b_extrapolation_investigation/03_latitude_transect.png
# → docs/p-01.0b_extrapolation_investigation/stats.json
```

Random seed = 42 → bit-identical samples on re-run. Single GEE init, ~3 getInfo() calls total.
