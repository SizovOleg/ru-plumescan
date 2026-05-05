# Phase 2A CH₄ Detection — Architecture RFC v2 (Consensus)

**Status:** RFC v2 — CONSENSUS REACHED, ready для formal DevPrompt
**Authors:** architect (Claude.ai) + Claude Code Desktop review iteration
**Created:** 2026-05-05 (post v1 review iteration)
**Predecessors:** Phase 1 (P-00 through P-01.0d) ✅ done, Phase 2A RFC v1 (reviewed)

---

## Changes from v1

Этот документ замещает v1 RFC. Major changes:

1. **Compute scope corrected** (15-30× pessimistic → realistic ~20h sequential)
2. **Z-score mask completed** — three-condition mask (z + delta floor + annulus relative) per Algorithm §3.6
3. **Wind altitude pinned** — 850hPa primary (was vague "ERA5")
4. **Wetland classification finalized** — empirical threshold determination + reference zone auto-override
5. **Repeatability winter bias** — qa_flag tag, не hard-fail
6. **Output format finalized** — per-year sharded + master index
7. **TD-0017/0021** — specific Phase 2A integrations defined
8. **IME quantification scope** — explicit experimental disclaimer
9. **Class breakdown** added к success criteria
10. **TD-0028 deferral** — informed audit AFTER first detection run

---

## I. Phase 2A scope and goals

### Goal

Implement **CH₄ plume event detection** workflow producing Common Plume Schema events catalog over Western Siberia AOI 2019-2025.

### In scope

- CH₄ detection engine (per-orbit z-score + cluster + wind validation + source attribution)
- Event catalog (per-year sharded + master index)
- Three-tier validation (synthetic, regression, false positive)
- Class assignment via Algorithm §3.12 heuristics
- Light TD-0017 transboundary integration (qa_flag tagging)

### Out of scope

- NO₂/SO₂ detection (Phase 2B/2C)
- Multi-gas event matching (Phase 4)
- UI App (Phase 5)
- IME quantification production-grade (DNA §2.1.2 — defer indefinitely)
- HYSPLIT full transboundary attribution (Phase 6)
- Field validation (Phase 6 Mukhrino collaboration)

### Deliverables

1. **CH₄ Detection Engine**
   - `src/py/setup/build_ch4_event_catalog.py` (Python orchestrator + Provenance)
   - `src/js/modules/detection_ch4.js` (JS algorithm primitives)
   - `src/py/setup/validate_detection_synthetic.py`
   - `src/py/setup/validate_detection_regression.py`
2. **Event Catalog Assets:**
   - 7 annual: `RuPlumeScan/catalog/CH4/events_2019` ... `events_2025`
   - Master index: `RuPlumeScan/catalog/CH4/events_master_2019_2025`
3. **Validation report** (`docs/p-02.0a_validation_report.md`)
4. **Tool-paper Figure 2** (detection examples)

### Success criteria

**Methodology coverage:**
- ✅ At least 3 EVENT_CLASSES represented в catalog (e.g., `CH4_only` industrial + `diffuse_CH4` wetland + `repeatable_event` confirmed)
- ✅ Detection covers methodology breadth, не just industrial bias

**Quality metrics:**
- ✅ Synthetic injection at Δ=50 ppb → recovery rate ≥80% (production-grade claim)
- ✅ Synthetic injection at Δ=30 ppb → recovery rate reported (sensitivity boundary)
- ✅ False positive rate в reference zones <5%
- ✅ Known events regression: 2-3 documented events (Kuzbass 2022-09-20, Bovanenkovskoye summer 2022, +Norilsk SO₂-major event если CH₄ co-emission documented) detected при default parameters

**Infrastructure:**
- ✅ Schema v1.1 compliance — все events have dual baseline fields + provenance triple
- ✅ Provenance audit passes для all catalog assets
- ✅ Per-year reproducibility — same year regenerable bit-identically

**Number target:**
- ✅ ≥10 valid events для AOI/period (per DNA §3.4 success criteria minimum)

---

## II. Architectural decisions — CONSENSUS

### Decision 1: Per-orbit detection — CONFIRMED

L3_CH4 IS per-orbit (each image = one orbit re-gridded к 0.01°), не daily-aggregated despite "L3" name. Per-orbit processing aligns с DNA §2.1.3.

**Compute reality:**
- ~34,662 orbits over 2019-2025
- ~2 sec per orbit (verified benchmark)
- ~20h sequential, ~3-5h parallel via Option C

**No POC needed** — full archive feasible single overnight run.

### Decision 2: Three-condition anomaly mask (CORRECTED from v1)

Per Algorithm §3.6 — pixel selected if **ALL THREE** conditions met:

```
z_test = z_pixel >= z_min                                              # statistical
delta_test = delta_primary >= delta_min_units                           # absolute floor
annulus_test = (delta_primary - annulus_median(50-150 km)) >= relative_min  # relative-to-local
mask = z_test AND delta_test AND annulus_test
```

**Rationale:**
- z_test: standard z-score statistical test
- delta_test: prevents detection of statistical anomalies that are physically negligible (e.g., Δ=2 ppb с low sigma → high z, но не plume)
- annulus_test: protects против "noisy area appears anomalous" false positives (sigma low в clean zones, normal в noisy zones; without annulus, noisy zones produce systematic false positives)

**Parameters (CH₄ default):**
- z_min: per-region adaptive (3.0 default, 4.0 для Kuzbass region lat∈[53,55] lon∈[86,88] per TD-0018)
- delta_min: 30 ppb (per Algorithm §3.5 default)
- relative_min: 15 ppb (per Algorithm §3.6 default)
- annulus inner radius: 50 km
- annulus outer radius: 150 km

**Z-score directional:** ONE-SIDED POSITIVE (sources emit, не absorb). Negative anomalies suppressed (likely retrieval artifacts).

### Decision 3: Pixel clustering к plume objects — CONFIRMED

GEE `connectedComponents`:
- connectedness: 8 (default)
- maxSize: 256 pixels
- min_cluster_px: 5 pixels (~245 km² minimum)

Per cluster compute via reduceConnectedComponents:
- Centroid (lat, lon)
- Area (km²)
- N pixels
- Max z within cluster
- Mean z within cluster
- Max Δ, Mean Δ within cluster

### Decision 4: Wind validation — 850hPa PRIMARY

**Wind altitude:** 850hPa (~1500m, top of typical PBL).

**Rationale:**
- 10m wind: surface-only, не representative для column-integrated XCH₄
- 850hPa: top of boundary layer, matches column-weighted measurement
- 100m: near-surface, possibly too low для plume transport
- 500hPa: free troposphere, может differ значительно от plume layer

**Implementation:**
- ERA5/HOURLY collection (NOT ERA5_LAND/HOURLY which has only 10m)
- Sample wind (u, v) at cluster centroid + ±3h window around orbit time
- Mean wind direction via vector averaging (not directional averaging, prevents 359°→0° wrap issues)
- Plume axis from cluster geometry (eigendecomposition of pixel coordinates covariance)
- Alignment check: |plume_axis - wind_dir| < ±30° (tighter than ±45° для 10m wind, since 850hPa flow more coherent)

**Recorded в metadata:**
- `wind_level_hPa`: 850 (default), allow override
- `wind_u_850hPa`, `wind_v_850hPa`, `wind_speed_850hPa`, `wind_dir_850hPa`
- `wind_alignment_score`: numeric (0-1, based на |angle_diff|)
- `wind_consistent`: bool (alignment_score >= 0.5 default)

**Q4.2 wind speed minimum:** Stationary plumes (low wind) may не показывать elongation. Threshold: skip alignment check if wind_speed < 2 m/s, set `wind_consistent = null` (insufficient data) instead of false.

**Q4.4 ERA5 hourly matching:** Nearest-hour к TROPOMI overpass (typically 12:00-15:00 local).

**Algorithm v2.3.1 patch needed:** §3.9 currently says "ERA5" без level. Update к specify 850hPa default + record level в metadata. Filed как TD-0031.

### Decision 5: Source attribution — CONFIRMED

50 km radius search для каждый cluster. Ranking:
1. Distance к centroid (closer better)
2. Wind alignment (upwind sources favored when wind data present)
3. Source type relevance for CH₄:
   - Priority 1: gas_field
   - Priority 2: oil_gas (viirs_flare_high) — major flares emit CH₄
   - Priority 3: coal_mine (mine ventilation CH₄)
   - Priority 4: tpp_gres (lower CH₄ emission, but possible)
   - Priority 5: viirs_flare_low (smaller signature)
   - Priority 6: smelter (minimal CH₄)

If multiple sources within 50 km — first by source type priority, then by distance.

If no source within 50 km → `nearest_source_id=null`. Cluster gets `class_='diffuse_CH4'` candidate (subject to other heuristics).

**Manual override:** Algorithm §6 mentions manual override mechanism для known events. Implementation: `event_overrides.json` file checked at attribution stage, applies to events с specific (lat, lon, date) coords matching override entries.

### Decision 6: Repeatability — CONFIRMED с winter caveat

**Default:** ≥2 detections within 30 days, distance between centroids <20 km → `repeatable_event` qa_flag.

**Winter bias mitigation (TD-0029 lesson):**
```
IF date_utc month ∈ [12, 1, 2]:  # DJF Northern Hemisphere winter
    extend window to 60 days
    track valid_retrievals_in_window / expected_retrievals
    IF coverage_fraction < 0.3:
        qa_flag.add('winter_sparse_sampling')
        repeatability_status = 'single_detection_winter_bias'
```

**Recorded fields:**
- `repeatability_status`: encoded in qa_flags string (per TD-0030 — formalize в schema v1.2 если used heavily)
- Values: `repeatable_event`, `single_detection_candidate`, `single_detection_winter_bias`

### Decision 7: Temporal scope — 2019-2025 sequential

Sequential year-by-year per Decision IV.B. Per-year intermediate checkpoints:
- Year completes → annual catalog asset live
- Validation на that year's results
- If issue → fix, regenerate that year only (не all 7)

**Output format:** Per-year sharded:
- `RuPlumeScan/catalog/CH4/events_2019` (FeatureCollection)
- `RuPlumeScan/catalog/CH4/events_2020`
- ...
- `RuPlumeScan/catalog/CH4/events_2025`

**Master index:**
- `RuPlumeScan/catalog/CH4/events_master_2019_2025`
- FeatureCollection of {year, asset_path, n_events, run_id, build_date}
- Used by downstream applications для catalog enumeration

### Decision 8: Validation methodology — CONFIRMED

**Tier 1 — Synthetic injection:**

Two-level test:
- Δ=50 ppb синтетических plumes, random AOI locations × random dates → recovery ≥80% (production-grade claim)
- Δ=30 ppb синтетических plumes → report recovery (sensitivity boundary, не threshold для tool claims)

Implementation:
- 100 synthetic plumes per level (50 each = 200 total tests)
- Inject in clean reference zones (avoid masking by industrial)
- Run detection с standard pipeline
- Recovery: synthetic plume cluster identified within 7 km centroid match

**Tier 2 — Known events regression:**

- Kuzbass 2022-09-20 (Schuit 2023 documented event)
- Bovanenkovskoye summer 2022 (project DNA mentioned)
- +Norilsk SO₂-major event с CH₄ co-emission (если documented research available)

Default parameters → events MUST be detected (100% pass).

If any miss — investigate:
- Parameters too strict?
- Mask coverage gap?
- Algorithm bug?

**Tier 3 — Reference zone false positive rate:**

Run detection inside Yugansky/Verkhne-Tazovsky/Kuznetsky Alatau zone polygons.

Expected: <5% FP rate.

Note: reference zones include natural wetland CH₄ sources. Detection algorithm may flag wetland emissions as anomalies. **This is acceptable when classified as `diffuse_CH4`** (not false positive in tool-paper sense — methodology classifies natural sources separately).

True FP: cluster passing 3-condition mask AND classified industrial AND inside protected zone → real false positive.

---

## III. Class assignment logic (Decision 8 detail)

Per DNA §1.3 EVENT_CLASSES + Algorithm §3.12:

**Classification cascade:**

```python
def classify_event(cluster, attribution_result):
    # Priority 1: Reference zone auto-override
    if cluster.matched_inside_reference_zone:
        return 'diffuse_CH4'  # by definition non-industrial (federal law)
    
    # Priority 2: Wetland heuristic (3 of 4 conditions)
    wetland_conditions = [
        cluster.area_km2 > 1000,
        cluster.max_z_to_area_ratio < THRESHOLD_TBD,  # empirical
        cluster.date_utc.month in [6, 7, 8, 9],  # JJAS peak
        cluster.nearest_source_distance_km > 100 or cluster.nearest_source_id is None
    ]
    if sum(wetland_conditions) >= 3:
        return 'diffuse_CH4'
    
    # Priority 3: Wind ambiguity check
    if cluster.wind_consistent is False:
        return 'wind_ambiguous'
    
    # Priority 4: Industrial classification
    if cluster.nearest_source_id is not None:
        return 'CH4_only'  # CH4-only industrial detection (no NO2/SO2 in Phase 2A)
    
    # Default
    return 'wind_ambiguous'  # no source, no wetland pattern, wind-only signal
```

**Wetland heuristic max_z_to_area_ratio threshold determination:**

Phase 2A first run produces unclassified events (status='unclassified'). After ≥100 events accumulated:

1. Profile distribution of `max_z / sqrt(area_km2)` (proxy для compactness)
2. Look for bimodal pattern:
   - Compact peaks (industrial) — high ratio
   - Diffuse peaks (wetland) — low ratio
3. Pick threshold separating bimodal pattern
4. Apply retroactively к full catalog
5. Document threshold в Algorithm v2.3.2 patch

**Алгоритм this iteration:**
- Phase 2A first 1-2 years run без classification (events all 'unclassified')
- Profile distribution after sufficient sample
- Determine threshold empirically
- Re-classify catalog с finalized threshold
- Subsequent years use established threshold

**Reference zone auto-override (per Claude Code recommendation):**

`matched_inside_reference_zone == true` is stronger signal than 4-condition heuristic. Reference zones are protected federal lands — by definition no industrial activity. Any detection inside MUST be natural (wetland, geological seep, natural fires, etc.).

Override applied first в classification cascade.

This aligns с Algorithm §3.11 confidence scoring («matched_inside_reference_zone == true → C_total *= 0.3») — same logic family applied к classification stage.

---

## IV. Workflow scaffold — FINALIZED

```
src/py/setup/build_ch4_event_catalog.py

Step 0: Configuration
├── Load preset (default): z_min mapping, delta_min, annulus radii, etc.
├── Compute canonical Provenance (TD-0024 pattern, ONCE)
└── Log STARTED entry

Step 1-7: Per-year processing (sequential 2019..2025)
├── Step 1: Filter TROPOMI L3 CH4 by date range
├── Step 2: For each orbit:
│     ├── 2.1: Apply QA (multi-band-select + cloud_fraction)
│     ├── 2.2: Compute z-score against dual baseline
│     ├── 2.3: Apply 3-condition mask (z + delta + annulus)
│     ├── 2.4: connectedComponents clustering (min 5 px)
│     ├── 2.5: Extract cluster attributes
│     └── 2.6: Append к year's candidate list
├── Step 3: Wind validation для year's candidates
│     ├── 3.1: Sample ERA5 850hPa wind at cluster centroids
│     ├── 3.2: Compute plume axis (eigendecomp)
│     ├── 3.3: Alignment check (±30°)
│     └── 3.4: Set wind_consistent + wind_alignment_score
├── Step 4: Source attribution для year's candidates
│     ├── 4.1: Spatial join к industrial/source_points
│     ├── 4.2: Filter within 50 km radius
│     ├── 4.3: Rank by source type + distance + wind
│     └── 4.4: Set nearest_source_id, distance_km, source_type
├── Step 5: TD-0017 transboundary check (CONDITIONAL: lat∈[53,56] AND lon≥92)
│     ├── 5.1: Fetch ERA5 24h-back wind history
│     ├── 5.2: Check dominant easterly transport
│     └── 5.3: Set qa_flag('transboundary_easterly_transport_suspected')
├── Step 6: TD-0021 zone-boundary adjustment
│     ├── 6.1: For events centroids near 57.5°N or 62°N (±100 km)
│     ├── 6.2: Inflate consistency_tolerance_ppb (base + step_size)
│     └── 6.3: Recompute baseline_consistency_flag
├── Step 7: Year's annual catalog
│     ├── 7.1: Apply Provenance к year's events FC
│     ├── 7.2: Export к RuPlumeScan/catalog/CH4/events_{year}
│     └── 7.3: Year intermediate checkpoint

Step 8: Cross-year repeatability analysis
├── 8.1: Match events across all 7 years
├── 8.2: Apply 30-day window (60 days winter)
├── 8.3: Set repeatability_status в qa_flags
└── 8.4: Update annual catalogs in place

Step 9: Master index
├── 9.1: Build FC of {year, asset_path, n_events, run_id, build_date}
└── 9.2: Export к RuPlumeScan/catalog/CH4/events_master_2019_2025

Step 10: Classification (initial)
├── 10.1: For first 1-2 years processed: events all 'unclassified'
├── 10.2: After sufficient sample (≥100 events): profile max_z/sqrt(area)
├── 10.3: Determine THRESHOLD_TBD empirically
└── 10.4: Re-classify all annual catalogs с finalized threshold

Step 11: Validation
├── 11.1: Synthetic injection (50 ppb + 30 ppb)
├── 11.2: Known events regression (2-3 events)
└── 11.3: Reference zone FP analysis

Step 12: Documentation + provenance log SUCCEEDED
```

**Estimated wall-clock:**
- Per-year detection: ~3-5 hours (per V.3 benchmark)
- 7 years sequential: ~24-35 hours
- Wind/source/TD post-processing: ~1-2 hours per year
- Validation: ~4-6 hours
- Total: ~30-45 hours wall-clock

**Compute can run overnight 2-3 nights if not parallel.**

---

## V. Implementation specifics for DevPrompt P-02.0a

After RFC v2 consensus, formal DevPrompt will specify:

**Code organization:**
- `src/py/setup/build_ch4_event_catalog.py` — orchestrator
- `src/js/modules/detection_ch4.js` — algorithm primitives:
  - `computeZScore(orbit, reference, regional)`
  - `applyThreeConditionMask(z_image, delta_image, annulus_radii)`
  - `extractClusters(mask, min_size)`
  - `validateWind(cluster, era5_collection)`
  - `attributeSource(cluster, source_points)`
- `src/py/setup/validate_detection_synthetic.py`
- `src/py/setup/validate_detection_regression.py`
- `src/py/setup/classify_events.py`

**Tests:**
- Unit tests для каждый JS primitive (Python-side mock GEE calls)
- Integration test: 1 known event end-to-end (Kuzbass 2022-09-20)
- Validation tests: synthetic + regression suites

**Documentation updates needed:**
- Algorithm.md §3.9 wind level specification (TD-0031)
- Algorithm.md §3.12 classification cascade с reference zone override
- Algorithm.md v2.3.2 patch notes
- RNA.md §3.1 add catalog asset structure
- OpenSpec MC entries

---

## VI. Open items для researcher confirmation в RFC v2

Before formal DevPrompt — researcher confirm:

1. **Wetland heuristic threshold determination strategy** — empirical post-hoc OK?
2. **Norilsk SO₂-major event с CH₄ co-emission** — documented research available? Or skip from regression list?
3. **Manual override mechanism format** — JSON file `event_overrides.json` OK? Or alternative?

---

## VII. TD board updated

**RESOLVED (post-Phase 1):**
- TD-0008/0011/0012/0019/0020/0023/0024/0025/0026/0027

**Phase 2A integration (per RFC v2):**
- TD-0017: Step 5 transboundary check (light implementation, qa_flag)
- TD-0018: z_min=4.0 для Kuzbass region (Decision 2)
- TD-0021: Step 6 zone-boundary adjustment

**Phase 6 deferred:**
- TD-0022 (article t1 Zones 1+8 — comprehensive validation)
- TD-0029 (GEE gotchas appendix — LOW polish)

**Post-Phase 2A informed:**
- TD-0028 (inventory gap audit — informed by detection findings)

**New (formal closeout):**
- TD-0030: Schema v1.2 repeatability_status formalization (post-year-usage)
- TD-0031: Algorithm.md §3.9 wind level spec (v2.3.1 patch)

---

## VIII. Status

**RFC v2 CONSENSUS — researcher to review final flags + confirm 3 open items в section VI.**

After confirmation → formal DevPrompt P-02.0a written:
- Specific implementation spec
- Test coverage requirements
- Validation checkpoints
- Reporting requirements

Estimated DevPrompt P-02.0a writing: ~1 day.
Estimated implementation: 5-10 days (incl. validation iteration).

**Tool-paper научная работа Phase 2A — это где он actually делает что advertised.**
