# Phase 2A CH₄ Detection — Architecture RFC Draft

**Status:** RFC (Request for Comment) — NOT implementation spec
**Authors:** architect (Claude.ai), pending review by Claude Code Desktop + researcher
**Created:** 2026-05-05 (post Phase 1 hardening closure)
**Predecessors:** Phase 1 (P-00 through P-01.0d) all ✅ done

---

## Purpose of this document

Этот документ — **collaborative architecture discussion**, не implementation DevPrompt. Researcher и Claude Code приглашены challenge assumptions, request verification, propose alternatives до того как formal implementation начнётся.

**Workflow:**

1. Researcher reads draft → comments on architectural decisions
2. Claude Code reads draft + accesses repo + verifies assumptions against actual codebase state → flags gaps, errors, questions
3. Iteration cycle — revise draft based на feedback
4. Когда consensus reached → architect writes formal implementation DevPrompt P-02.0a с specific technical spec
5. Claude Code executes implementation

**Этот RFC ОЧЕРЕДНОЙ deliverable не является — it's the design conversation that produces the implementation spec.**

---

## Reminder for Claude Code session

Перед review этого RFC ПОЛНОСТЬЮ перечитай:

1. `DNA.md` (v2.2) — все 16 запретов §2.1, §1.5 dual baseline, §3.4 success criteria
2. `Algorithm.md` (v2.3) — особенно §3 (CH₄ detection), §3.7 connectedComponents, §4-5 (NO₂/SO₂ для context)
3. `RNA.md` (v1.2) — §3.1 Assets, §7.1 default preset, §11 reference baseline
4. `OpenSpec.md` — все MC entries Phase 0/1
5. `KNOWN_TODOS.md` — все open TDs especially TD-0017, TD-0018, TD-0021
6. `docs/p-01.2_phase_2a_handoff.md` — concrete parametric recommendations
7. Этот RFC

Подтверди все 16 запретов. Особенно critical для Phase 2A:

- **Запрет 1:** candidate ≠ plume без structural verification
- **Запрет 3:** no compositing для CH₄ plume detection
- **Запрет 6:** no single absolute threshold для AOI
- **Запрет 10:** no source attribution без infrastructure+wind+repeatability
- **Запрет 12:** canonical Provenance pattern from build start (TD-0024/0025)

---

## I. Phase 2A scope and goals

### Goal

Implement **CH₄ plume event detection** workflow producing Common Plume Schema events catalog over Western Siberia AOI 2019-2025.

### Out of scope (Phase 2A)

- NO₂ detection (Phase 2B)
- SO₂ detection (Phase 2C)
- UI App (Phase 5)
- Multi-gas event matching (Phase 4)
- Quantification production-grade (DNA §2.1.2 — defer indefinitely)

### Deliverables

1. **CH₄ Detection Engine** (`src/js/modules/detection_ch4.js` + Python orchestrator)
2. **CH₄ Event Catalog Asset** (`RuPlumeScan/catalog/CH4/events_2019_2025`)
3. **Validation report** против synthetic injections
4. **Known events regression test suite** (Kuzbass 2022-09-20, etc.)
5. **Tool-paper Figure 2** (detection examples)

### Success criteria (per DNA §3.4 success enums)

- ✅ Detection produces ≥10 valid events для AOI/period
- ✅ Synthetic injection recovery rate ≥80%
- ✅ False positive rate в reference zones <5%
- ✅ Schema v1.1 compliance — все events have dual baseline fields
- ✅ Provenance audit passes для catalog asset
- ✅ Known events regression detected (Kuzbass 2022-09-20 при reasonable threshold)

---

## II. Architectural decisions — DRAFT

Этот section содержит decisions которые я draftил. Каждая decision имеет rationale + alternatives + open questions для discussion.

### Decision 1: Per-orbit detection vs daily/monthly compositing

**Draft choice:** Per-orbit detection (DNA §2.1 запрет 3 forbids compositing для CH₄).

**Rationale:** TROPOMI CH₄ plumes — transient events (hours-days). Compositing суппрессирует transient signals ~30× (per project DNA observation). Per-orbit approach Schuit-style.

**Alternative considered:** Daily compositing (max или 90-th percentile)
- Faster compute
- Smoothes pixel-level noise
- BUT — DNA prohibits для CH₄ specifically

**Open questions для review:**
- Q1.1: Per-orbit means processing **каждого** TROPOMI orbit individually. ~14 orbits/day × 365 days × 7 years = ~36,000 orbits. Compute scope?
- Q1.2: Filter orbits с insufficient AOI coverage (% pixels valid)? Threshold?
- Q1.3: Multiple orbits per day overlap region — combine multiple-orbit signals или treat each independently?

### Decision 2: Anomaly detection algorithm

**Draft choice:** Z-score against dual baseline.

```
z_pixel = (obs_pixel - baseline_pixel) / sigma_pixel

где:
- obs_pixel: per-orbit XCH₄ value
- baseline_pixel: from reference_CH4_v1 (latitude stratified) или regional_CH4 (если pixel в clean region)
- sigma_pixel: from baseline asset sigma band
```

Dual baseline check (Algorithm §3.4.3):
- delta_vs_reference = obs - reference_baseline
- delta_vs_regional = obs - regional_baseline
- consistency_flag = |delta_ref - delta_reg| < tolerance_ppb (30 ppb default)

**Rationale:** Standard approach (Schuit 2023, IMEO methodology). Z-score normalizes pixel-specific noise. Dual baseline cross-check distinguishes real anomaly от undocumented industrial contamination в regional baseline.

**Alternatives considered:**
- Constant threshold (DNA запрет 6 — forbidden)
- ML-based anomaly detection (DNA запрет 11 — forbidden v1)
- Spatial outlier detection (Local Indicators of Spatial Association, LISA) — possible Phase 2A enhancement, defer

**Open questions:**
- Q2.1: Z-min threshold для CH₄? Algorithm §3.5 default = 3.0. Phase 1c handoff suggests z_min=4.0 для Kuzbass (TD-0018). Per-region adaptive threshold?
- Q2.2: Sigma scaling — какой sigma для z computation: reference baseline sigma или regional? Or max(both)?
- Q2.3: Tolerance_ppb=30 для consistency_flag — universally OK или per-region?

### Decision 3: Pixel clustering к plume objects

**Draft choice:** GEE `connectedComponents` с min_cluster_px parameter.

```javascript
var anomaly_mask = z_image.gte(z_min);
var clusters = anomaly_mask.connectedComponents({
    connectedness: 8,  // 8-neighborhood
    maxSize: 256
});
var cluster_areas = clusters.reduceConnectedComponents({
    reducer: ee.Reducer.count()
});
var significant_clusters = cluster_areas.gte(min_cluster_px);
```

Per cluster compute attributes:
- Centroid (lat, lon)
- Area (km²)
- N pixels
- Max z within cluster
- Mean Δ within cluster

**Rationale:** Algorithm §3.7 specifies. DNA §2.1.5 forbids ee.Kernel arithmetic. connectedComponents is Earth Engine native.

**Alternatives considered:**
- Manual clustering (Python sklearn DBSCAN) — would require download data, bypass GEE compute, slow
- Hot-spot analysis (Getis-Ord) — possible enhancement, defer

**Open questions:**
- Q3.1: min_cluster_px = 5 (Algorithm default) — represents ~250 km² minimum signal area. Is это правильно для Western Siberia industrial sources?
- Q3.2: Maximum cluster size limit? Some sources may produce very large plumes (Norilsk SO₂ analog для CH₄?). Cap или allow?
- Q3.3: Connectedness 8 vs 4? Diagonal pixels — count or not?

### Decision 4: Wind validation

**Draft choice:** ERA5 wind data + plume-axis alignment check.

For каждый candidate cluster:
1. Sample ERA5 wind (u, v) at cluster centroid + ±3h window around orbit time
2. Compute mean wind direction
3. Check plume elongation axis aligns с wind direction (within ±45°)
4. If aligned — flag wind_consistent=true

**Rationale:** DNA §2.1.10 — source attribution requires infrastructure+wind+repeatability. Wind validation distinguishes real plumes (advected from source) от random noise spikes.

**Alternatives considered:**
- Skip wind validation в v1 — not acceptable per DNA
- Use NCEP/NCAR reanalysis instead of ERA5 — ERA5 finer resolution
- Use TROPOMI wind product если available — research scope

**Open questions:**
- Q4.1: Wind threshold ±45° для alignment — too strict or too lenient?
- Q4.2: Mean wind speed minimum? Stationary plumes (low wind) may не показывать elongation.
- Q4.3: Boundary layer height correction — apply или not? (BL height affects column XCH₄ measurement)
- Q4.4: ERA5 hourly data → which time matches TROPOMI overpass? Nearest hour или interpolation?

### Decision 5: Source attribution

**Draft choice:** Nearest infrastructure search within 50 km of plume centroid.

For каждый detected cluster:
1. Query industrial/source_points (532 features) for sources within 50 km
2. If multiple sources — rank by:
   - Distance to centroid (closer better)
   - Wind alignment (upwind sources favored)
   - Source type relevance (gas_field > viirs_flare > tpp_gres for CH₄)
3. Assign nearest_source_id и distance_km
4. If no source within 50 km → nearest_source_id = null

**Rationale:** Algorithm §6 specifies attribution logic. 50 km radius covers reasonable downwind transport time at typical wind speeds.

**Alternatives considered:**
- Strict upwind-only attribution — too restrictive (wind direction может change between source emission and TROPOMI overpass)
- Distance-only ranking — ignores wind context
- 100 km radius — too permissive, attribution becomes ambiguous

**Open questions:**
- Q5.1: 50 km radius adequate? Phase 1c suspect cluster #4 (Tambeyskoye) was ~80 km west of nearest known source PRE-fix.
- Q5.2: Source type ranking specifically для CH₄ — gas_field highest priority. Coal_mine также emit CH₄ (mine ventilation). Ranking?
- Q5.3: Manual override mechanism для known events (regression tests)? Algorithm §6 mentions manual override.

### Decision 6: Repeatability requirement

**Draft choice:** Event recurrence ≥2 detections within 30 days at same location → flagged "repeatable".

Algorithm:
- Single detection: candidate_event
- ≥2 detections within 30 days, distance between centroids <20 km → repeatable_event
- Repeatable events promoted to confirmed (DNA §2.1.10 partial)

**Rationale:** DNA §2.1.10 — source attribution requires repeatability. Single detection insufficient (could be retrieval artifact).

**Alternatives considered:**
- Single detection accept — fails DNA
- Strict same-location requirement (<5 km) — too strict given TROPOMI 7 km pixel
- Time window 60 days — too long, allows unrelated events to confound

**Open questions:**
- Q6.1: 30-day time window adequate? Some sources have intermittent emissions (compressor maintenance) — 30 days catches?
- Q6.2: Single-detection events still publishable as "candidate_event" status — research interest? Or filter out entirely?
- Q6.3: How handle repeatability across boundary regions? Plume centroid moves 15 km between detections — same или different event?

### Decision 7: Temporal scope

**Draft choice:** 2019-2025 (full TROPOMI archive aligned с baselines).

**Rationale:** Baselines built на 2019-2025 climatology. Detection within same period gives consistent comparison.

**Open questions:**
- Q7.1: Process 7-year period sequentially (year by year) или all at once?
- Q7.2: Compute scope — ~36,000 orbits × per-pixel computation. Estimated GEE compute time?
- Q7.3: Output catalog — single asset с все events или per-year shards?

### Decision 8: Validation methodology

**Draft choice:** Three-tier validation.

1. **Synthetic injection:** Insert known plumes (Δ = 30, 50, 100 ppb at random AOI locations с known timing) → run detection → recovery rate ≥80%
2. **Known events regression:** Documented events list (Kuzbass 2022-09-20, etc.) → manually confirm detection при default parameters → 100% pass
3. **Reference zone false positive rate:** Run detection inside protected areas (zone polygons) → expect <5% FP rate

**Rationale:** Three-tier covers known unknowns (synthetic), known knowns (regression), и null tests (FP). Standard atmospheric detection methodology.

**Alternatives considered:**
- Cross-comparison с Schuit2023 catalog — defer Phase 4
- Cross-comparison с CAMS Methane Hotspot — defer Phase 4
- Field validation — defer Phase 6 (Mukhrino station collaboration)

**Open questions:**
- Q8.1: Synthetic injection size — 30 ppb threshold or higher? Lower threshold = more challenging detection.
- Q8.2: Known events list — what specific events? Researcher provides?
- Q8.3: FP threshold 5% — acceptable for tool-paper claims?

---

## III. Workflow scaffold — DRAFT

Below is high-level workflow. Implementation details TBD после architecture review.

```
src/py/setup/build_ch4_event_catalog.py
├── Step 1: Initialize Provenance (canonical pattern, TD-0024/0025)
├── Step 2: For each year in [2019..2025]:
│     ├── 2a: Filter TROPOMI L3 CH4 collection by date range
│     ├── 2b: For each orbit:
│     │     ├── Apply QA (multi-band-select + cloud_fraction filter)
│     │     ├── Compute z_score against dual baseline
│     │     ├── Apply z_min threshold (per-region adaptive если TD-0018 confirmed)
│     │     ├── connectedComponents clustering
│     │     ├── Extract cluster attributes (centroid, area, max_z, etc.)
│     │     └── Append к year's candidate list
│     ├── 2c: Wind validation для year's candidates
│     ├── 2d: Source attribution для year's candidates
│     └── 2e: Export year's events FeatureCollection
├── Step 3: Combine annual catalogs → final asset
├── Step 4: Compute repeatability flags (cross-year analysis)
├── Step 5: Validation
│     ├── 5a: Synthetic injection tests
│     ├── 5b: Known events regression tests
│     └── 5c: Reference zone false positive analysis
└── Step 6: Final asset metadata + provenance log
```

**Estimated scope:**
- ~36,000 orbits (7 years × 365 days × ~14/day)
- Per-orbit compute: ~30-60 sec via Option C
- Total: ~300-600 hours wall-clock через GEE queue
- **Не practical** — needs optimization

**Optimization candidates:**
- Process orbits in batched groups (10-20 orbits per task) instead of individual
- Pre-filter empty/low-coverage orbits
- Year-by-year with intermediate checkpoints

---

## IV. Decision points для researcher review

Before formal DevPrompt — researcher confirm/adjust:

**A. Z-min threshold strategy:**
- Option 1: Single z_min=3.0 globally
- Option 2: Per-region adaptive (Kuzbass z_min=4.0, rest=3.0) per Phase 1c handoff
- Option 3: Per-source-type adaptive (gas_field z_min=4.0, isolated z_min=3.0)

**B. Compute orchestration:**
- Option 1: Sequential year-by-year (~7 weeks compute)
- Option 2: Year batches in parallel (~1-2 weeks compute, complex orchestration)
- Option 3: Subset first (1 year proof-of-concept, then scale)

Recommend Option 3 — proof-of-concept на 2025 single year (most recent, baselines aligned). Validate algorithm before full archive.

**C. Validation events list:**
Researcher provides specific events list для regression suite. Examples expected:
- Kuzbass 2022-09-20 (DevPrompt P-00 mentioned)
- Norilsk SO₂ analog event (если CH₄ also detectable)
- Other documented Russian methane releases

**D. Output catalog format:**
- Single FeatureCollection asset с все events
- Per-year sharded FeatureCollections с master index
- GeoJSON download для manual analysis

**E. TD integration priorities:**
- TD-0017 (transboundary transport) — investigate Phase 2A or defer?
- TD-0018 (Kuzbass z_min) — apply parameters from handoff?
- TD-0021 (zone-boundary smoothing) — apply parameters from handoff?

---

## V. Decision points для Claude Code review

Claude Code, проверь следующие assumptions против actual repo state и report:

**1. Verify infrastructure ready:**
- All 4 baseline assets canonical-provenance ✓ (verified в P-01.0d)
- Schema v1.1 supports detection events fields:
  - max_z, area_km2, n_pixels, centroid lat/lon, wind direction/speed
  - delta_vs_regional_climatology, delta_vs_reference_baseline
  - baseline_consistency_flag, matched_inside_reference_zone
  - nearest_reference_zone, nearest_source_id, distance_to_source_km
  - wind_consistent, repeatability_status
- Common Plume Schema validated в `src/py/rca/common_schema.py` и `src/js/modules/schema.js`

**Action:** confirm схема ready, report missing fields.

**2. Verify pipeline components:**
- Multi-band-select pattern works for TROPOMI L3 collections (verified в P-01.0d)
- Option C orchestrator handles non-baseline tasks (untested — was used для baselines only)
- ERA5 wind data accessible через GEE (`ECMWF/ERA5_LAND/HOURLY` or `ECMWF/ERA5/HOURLY`)

**Action:** verify ERA5 access, report band availability.

**3. Compute feasibility:**
- 36,000 orbits — actual GEE compute time per orbit?
- Run quick benchmark: 5 random orbits, time их processing
- Report estimated total time scale

**Action:** run benchmark, report results.

**4. Algorithm sanity:**
- Z-score formula symmetric (positive AND negative anomalies?) или only positive?
- For CH₄ plume detection — only positive (sources emit, не absorb). Confirm.
- consistency_flag computation за полным cluster или per-pixel?

**Action:** clarify algorithm details, propose specific implementation.

**5. Outstanding TDs integration:**
- TD-0017 (transboundary transport) — investigate via HYSPLIT analysis в Phase 2A or defer?
- TD-0021 (zone-boundary smoothing) — implement as preprocessing of reference baseline или as per-detection adjustment?

**Action:** propose specific implementation для each.

**6. Code locations:**
- Detection engine — `src/js/modules/detection_ch4.js` (JS for GEE Code Editor) или Python в `src/py/setup/`?
- Recommend Python orchestrator + JS module hybrid (per existing pattern)
- Confirm.

---

## VI. Open architectural concerns

Claude Code, please challenge any of these:

**Concern 1: Per-orbit processing scale**
- 36,000 orbits × per-pixel z-score × ~600,000 pixels = 2×10¹⁰ pixel-evaluations
- Even с Option C parallelization — это major compute effort
- **Question:** is per-orbit really required by DNA §2.1.3, или per-day acceptable если **no compositing within day**?

**Concern 2: Wind validation rigor**
- ERA5 grid ~9 km, TROPOMI 7 km — comparable resolution
- BUT — ERA5 wind at single height (10m or 100m) vs column-integrated CH₄ measurement
- Wind direction at 10m может differ от mid-troposphere wind direction
- **Question:** does this introduce systematic bias? Worth investigation в pre-implementation phase?

**Concern 3: Repeatability statistical power**
- 30-day window for repeatability requires multiple TROPOMI overpasses на same pixel
- AOI revisit time ~daily, but cloud cover reduces valid observations
- Russian winter has very few valid retrievals (snow + low sun + clouds)
- **Question:** repeatability requirement may bias against winter detections. Compensate?

**Concern 4: False positive baseline**
- Reference zones expected <5% FP — but our reference zones include known wetland CH₄ sources
- Wetlands ARE emission sources (just not industrial)
- Will detection algorithm FLAG natural wetland emissions as false positives?
- **Question:** how distinguish natural wetland CH₄ от industrial CH₄? Or accept that detection methodology not specific to industrial sources?

---

## VII. Next steps

1. **Researcher reviews** (sections II-IV) — confirm/adjust decisions
2. **Claude Code reviews** (sections V-VI) — verify assumptions, run benchmarks, propose specifics
3. **Iteration** — revise RFC based on feedback
4. **Consensus** — все architectural decisions clear, all assumptions verified
5. **Formal implementation DevPrompt P-02.0a** — written by architect с specific spec
6. **Implementation** — Claude Code executes
7. **Validation** — three-tier test suite
8. **PR + merge** — Phase 2A complete

---

## VIII. What this RFC is NOT

- **Not a final spec** — это draft for discussion
- **Not implementation orders** — Claude Code не должен start coding на основе этого
- **Not finalized commitment** — decisions can be revised with rationale
- **Not exhaustive** — additional considerations may emerge during review

---

## Status

**RFC posted:** awaiting researcher comments + Claude Code verification + benchmarking.

**Estimated time для review iteration:** 1-2 days (researcher decisions + Claude Code investigations + iteration cycle).

**После consensus:** formal DevPrompt P-02.0a written, implementation begins.

**Phase 2A implementation effort estimate:** 5-10 days (depends на decisions, compute scope, complexity wind validation).
