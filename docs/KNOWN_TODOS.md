# Known TODOs / Deferred Quality Refinements

Список задач, отложенных до явного triggering condition. Каждая запись имеет:
- **Trigger** — условие, при котором задачу нужно вернуть в active backlog
- **Origin** — где обнаружено (DevPrompt / phase / commit)
- **Owner** — кто отвечает (researcher / Claude / community)
- **Effort estimate** — порядок необходимой работы

Формат вдохновлён OpenSpec.md, но это отдельный документ для **operational
deferrals**, не для architectural changes.

---

## TD-0001 — VIIRS proxy comprehensive analysis

- **Origin:** P-00.1 v2 ingestion (commit `<merge SHA>`, branch `p-00.1-industrial-and-reference`)
- **Owner:** Claude (исполняющий) при triggering
- **Status:** deferred — visual sanity passed, quantitative refinement pending
- **Trigger:** revisit if false positive rate в clean regions (далеко от known
  industrial sources) > 5% по итогам Phase 2A detection runs.
- **What's deferred:**
  1. Full radiance histogram per spatial bin (5°×5° или finer) для
     identification clusters concentration vs scatter.
  2. Distance-to-nearest-manual-point metric — VIIRS points в > 50 km от любого
     manual industrial source (потенциальные unverified flares).
  3. False positive analysis — overlay VIIRS points c MODIS land cover
     `Cropland` / `Grasslands` (LC=12, 10) для detection agricultural lights
     которые могли пройти urban filter.
  4. Threshold sensitivity sweep — re-run `build_viirs_proxy --threshold {30,
     50, 70, 100}` с calibration_status comparison; document optimal threshold
     per region (north Yamal vs south Khanty).
  5. Spatial clustering metrics (Ripley's K, DBSCAN) — distinguish flares
     (clustered around facilities) от noise (scattered).
- **Effort:** 1-2 days (Python pandas/scipy analysis + visualization).
- **Output:** addendum в `data/industrial_sources/README.md` + figure для
  tool-paper Discussion section.

---

## TD-0002 — Lauvaux 2022 ingester (если получим CSV)

См. OpenSpec.md `CHANGE-B003`. Активируется при response от Lauvaux/Kayrros.

---

## TD-0003 — Pixel-wise L (NOx/NO2 ratio) per Beirle 2021 ESSD

См. OpenSpec.md `CHANGE-B004`. Активируется после v1.0 release при наличии
validation evidence что constant L=1.32 занижает accuracy.

---

## TD-0004 — Алтайский full-resolution polygon download

- **Origin:** P-00.1 v2 sub-agent ingestion
- **Owner:** Claude при triggering
- **Status:** deferred — current Nominatim-simplified polygon (4.5% area diff)
  прошёл R2 tolerance.
- **Trigger:** если P-01.0a Алтайский QA test fail и одна из root causes —
  inadequate polygon coverage (e.g., акватория Телецкого озера mishandled).
- **What's deferred:** download full-resolution Алтайский polygon через
  `polygons.openstreetmap.fr` (без WebFetch token limit) или WDPA API directly
  (требует registration / accept terms). Re-clip с MODIS Land Cover чтобы
  excluded water bodies если QA указывает.
- **Effort:** 0.5 day.

---

## TD-0005 — WDPA cross-verification of zapovednik polygons

- **Origin:** R1 from researcher (P-00.1 v2 polygon source priority)
- **Owner:** Claude при triggering
- **Status:** deferred — OSM polygons accepted as primary, WDPA as future
  cross-check. Sub-agent attempted WDPA bulk download, requires accept-terms
  через web UI which is not feasible without browser session.
- **Trigger:**
  1. Researcher provides WDPA bulk download manually (one-time UI accept), OR
  2. WDPA-OSM intersection diff > 10% обнаружен during P-01.0a QA, OR
  3. External reviewer requires WDPA-canonical boundaries для publication.
- **What's deferred:** WDPA dataset ingest, IoU vs OSM polygons, document any
  divergence > 5% intersection area.
- **Effort:** 1 day (assuming WDPA accessible).

---

## TD-0017 NEW — Transboundary transport contamination (Krasnoyarsk → western AOI)

- **Origin:** P-01.0b CR review CLAIM 3 fix 2026-04-29
- **Status:** documented caveat
- **Observation:** Krasnoyarsk industrial cluster (Krasnoyarskaya GRES-2 1250 MW
  + 3 более) в 90-95°E band added to `industrial/source_points` v2 (CLAIM 3
  fix). Industrial mask now excludes these points. Но при favorable easterly
  winds — CH₄/SO₂/NO₂ от этих sources может transport westward в KhMAO/Yamal
  и appear как increased baseline на pixels NOT covered industrial buffer.
- **Trigger:** Phase 2A detection sensitivity test — investigate
  false-positive rate в western AOI parts при detection runs covering periods
  с predominantly easterly transport.
- **Effort:** 2-3 days (HYSPLIT back-trajectory analysis или ERA5 wind
  climatology correlation).

---

## TD-0018 NEW — Kuzbass detection caveat (mask gap pre-fix + low Kuz-Alatau counts)

- **Origin:** P-01.0b CR review CLAIM 3 + MC-2026-04-29-I 2026-04-29
- **Status:** **HIGH severity для Phase 2A в Kuzbass region**
- **Observation:** Primary CH₄ detection target region (regression baseline
  Кузбасс 2022-09-20 per CLAUDE §5.1) has compounded uncertainty:
  - **Industrial mask gap pre-fix:** 4 major Kuzbass plants (Tom-Usinsk,
    Kuznetsk TES, Novo-Kemerovo, Kemerovo) missed в P-01.0b CH₄ regional
    baseline. Pixels near these plants могут содержать residual industrial
    signal в regional baseline. Mask fixed в same PR, но CH₄ regional Asset
    built на pre-fix mask (preserved per Option E).
  - **Reference baseline reliability:** Kuznetsky Alatau (lat 53-57°N,
    Kuzbass primary reference) imeет low TROPOMI counts 60-140/month vs
    5000+ для lowland zones (P-01.0a TD-0010). Mountain cloud cover + SWIR
    challenges.
  - **Cross-check unreliable:** Both baselines have elevated uncertainty
    в этой region. Dual baseline architecture's «one robust baseline»
    assumption not satisfied.
- **Phase 2A mitigation requirements:**
  - **Stricter z_min threshold** для Kuzbass-region plumes: z_min=4.0
    (vs default 3.0). Reduces false positive rate but also reduces sensitivity.
  - **Manual review trigger:** events с `nearest_source_id=null` near
    coordinate (86-88°E, 53-55°N) — likely missed Kuzbass industrial
    source. Compare с updated `industrial/source_points` v2 (post-fix).
  - **Document Phase 2A detection limit:** Kuzbass ~14 ppb sensitivity vs
    Yamal/Khanty ~30+ ppb sensitivity (proxy estimate).
- **Trigger:** Phase 2A CH₄ detection run on regression baseline Кузбасс
  2022-09-20.
- **Effort:** apply mitigation в Phase 2A DevPrompt (15 min config), then
  validate с regression test.

---

## TD-0019 — Reference baseline latitude-stratification: extrapolation quantitative impact **[RESOLVED 2026-04-29]**

- **Origin:** P-01.0b 6-point Ref vs Regional cross-check + researcher
  investigation request 2026-04-29.
- **Status (2026-04-29): RESOLVED — methodology bounded, distance not the
  driver.**
- **Trigger observation:** P-01.0b cross-check spread 38 ppb (-17.91 to
  +21.56) для non-industrial points — beyond `consistency_tolerance_ppb=30`.
  Hypothesis: latitude-only zone stratification (centroids 54.5/60.5/63.5°N,
  no longitude weight) extrapolates baselines unreliably на distant points.
- **Investigation deliverables:** `docs/p-01.0b_extrapolation_investigation/`
  - `01_zone_map.png` — zone assignment + lat-distance heatmap
  - `02_delta_vs_distance.png` — Δ scatter с linear fit (n=104 random clean
    points, M07)
  - `03_latitude_transect.png` — ref vs reg at lon=75°E
  - `REPORT.md` — full analysis
  - `stats.json` — raw numerical
- **Findings:**
  - **R² = 0.0023** (|Δ| vs lat_dist_km, n=104, p=0.629). NOT significant.
  - Slope -0.003 ppb/km — distance к centroid не predicts \|Δ\|.
  - \|Δ\|: max 54, mean 19.8, median 15.8 ppb. Substantial \|Δ\| exists
    но distance не explains it.
  - Visible step-change discretization artifact at zone boundaries
    (57°N, 62°N) — produces local Δ even for points close to centroid.
  - Zone 4 article t1 comparison: ref_mean=1873 vs article=1854 (Δ=+19).
    Plausible — period + biome (whole zapoved vs wetland-only) mismatch.
- **Verdict per researcher's pre-stated criterion (R² < 0.2):** PROCEED
  normally. \|Δ\| reflects biome/period differences, NOT extrapolation
  artifact.
- **Phase 2A guidance produced:**
  - Phase 2A `consistency_flag=false` triggers should record `lat_dist_km`
    per candidate as confidence-modifier — NOT a hard fallback rule.
  - Step-change boundaries (~57°N, ~62°N at lon=75°E) могут produce
    spurious cross-check disagreements; document для Phase 1c.
- **Future improvement (deferred, NOT blocker):** distance-weighted blend
  между nearest-2 zones смягчил бы step changes. Candidate для potential
  CHANGE-0018 после Phase 1c full cross-check map.

---

## TD-0021 NEW — Zone-boundary detection sensitivity (CH₄ Phase 2A)

- **Origin:** P-01.0b extrapolation investigation 2026-04-29 (TD-0019
  resolution + latitude transect at 75°E findings).
- **Status:** documented, deferred к Phase 2A CH₄ detection design.
- **Observation:** reference baseline shows discrete plateaus at latitude
  band boundaries: Kuznetsky↔Yugansky transition ~57°N (Δ ≈ 14 ppb step,
  1846→1880), Yugansky↔Verkhne-Tazovsky transition ~62°N (Δ ≈ 17 ppb step,
  1880→1863). Regional baseline continuous. Phase 2A CH₄ detection within
  ~50 km from these boundaries может trigger spurious
  `consistency_flag=false` (dual-baseline disagreement caused by reference
  discretization, не real anomaly).
- **NOT blocker для NO₂/SO₂ — they don't use reference baseline в v1**
  (single regional climatology only per RNA §11.1). Critical для Phase 2A
  CH₄ design.
- **Mitigation options (для Phase 2A DevPrompt or CHANGE-0018):**
  - **(a)** moving-average smoothing reference over neighbouring 100 km
    latitude — preserves architecture, smooths step changes
  - **(b)** distance-weighted blend nearest-2 zones — full
    methodology revision (CHANGE-0018 candidate)
  - **(c)** record `lat_dist_km_to_band_boundary` per CH₄ candidate and
    treat `consistency_flag=false` near boundaries как "ambiguous"
    requiring additional evidence (cluster + wind alignment)
- **Effort:** option (c) ≈ 1 hour (config flag в Phase 2A); options (a)/(b)
  ≈ 1-3 days each.

---

## TD-0022 NEW — Article t1 full zonal-stats comparison (Phase 1c validation)

- **Origin:** P-01.0b extrapolation investigation 2026-04-29 — partial
  comparison only (Zone 4 confirmed +19 ppb plausible per period+biome
  mismatch).
- **Status:** deferred к Phase 1c.
- **Need:** full t1 zonal stats for all 8 article zones (currently only
  Zone 4 = 1854 ppb provided). Specifically Zone 1 (Tundra 67-72°N) and
  Zone 8 (Steppe 52-55°N) needed to evaluate latitude-stratified
  reference assignments на extrapolated bands.
- **Phase 1c plan:** request adjacent project authors → extract all 8 zones
  → compare с our reference per latitude band → independent third-party
  validation для tool-paper.
- **Action:** capture in Phase 1c DevPrompt (P-01.2_dual_baseline_validation.md
  предположительно). Если authors недоступны — note as limitation, не
  blocker.
- **Effort:** depends on author response time + manual data extraction
  (~30 min once received).

---

## TD-0020 — Bovanenkovo test point coordinate error in cross-check labels

- **Origin:** P-01.0b validation report point 6 misnomer 2026-04-29
- **Status:** documented, low priority
- **Observation:** validation report labels point 6 «Bovanenkovo proxy»
  (70.5°E, 70.5°N), но actual Bovanenkovo NGKM centroid находится
  ≈(68.4°E, 70.4°N) — ~80 km west. Sampled coord falls в less-instrumented
  Yamal zone, NOT в proper Bovanenkovo gas field.
- **Impact:** misleading mask-coverage claim в PR #3 description and
  earlier P-01.0b summary. Real Bovanenkovo would be in 30 km industrial
  buffer (after CLAIM 3 fix), но sampled point may not be.
- **Action item:** при next sanity validation, replace point 6 с actual
  Bovanenkovo (68.4, 70.4) AND add fresh point at (70.5, 70.5) под
  honest label "Mid-Yamal east clean".
- **Effort:** 5 min config update + script re-run.

---

## TD-0008 — Refactor build_zone_baseline_single_month memory footprint (Q-mid months) **[RESOLVED 2026-04-30 — cross-gas verified]**

**Final outcome (2026-04-30):** Option C (12 separate batch tasks per gas) verified
across **all 3 gases**:
- CH₄ regional climatology 2026-04-29: 12/12 SUCCEEDED including Q-mid
- NO₂ regional climatology 2026-04-30: 12/12 SUCCEEDED including Q-mid
- SO₂ regional climatology 2026-04-30: 12/12 SUCCEEDED including Q-mid

Pattern documented в `build_regional_climatology.py` orchestrator. Hypothesis
empirically confirmed across 3 different gas pipelines + 3 different runs +
36 separate batch tasks total. TD-0008 closed с high confidence. См.
OpenSpec MC-2026-04-30-L.

---

## TD-0011 — Pre-computed mask Asset для NO₂/SO₂ optimization **[RESOLVED 2026-04-30]**

**Outcome:** `RuPlumeScan/industrial/proxy_mask_buffered_30km` Asset successfully
used for NO₂ + SO₂ regional climatology builds 2026-04-30. Saved ~1.5 hours
compute per gas (3 hours total) via skip of inline `focal_max(15km)` operation.
Pattern: `--use-prebuilt-mask` flag в orchestrator. См. MC-2026-04-30-J/K.

---

## TD-0012 — Mask consistency cross-gas verification **[RESOLVED 2026-04-30]**

**Outcome:** Same `proxy_mask_buffered_30km` asset used uniformly across CH₄
(post-build verification commit 589efaf), NO₂ (2026-04-30 closure), и SO₂
(2026-04-30 closure). Industrial pixel masking verified consistent в 3-gas
sanity tests:
- Norilsk Nadezhdinsky: masked в всех 3 gases ✓
- Tom-Usinsk GRES (Kuzbass): masked в NO₂ + SO₂ (CH₄ used pre-fix mask per
  Option E rationale, см. TD-0018)
- Yugansky reference centroid: masked (collocated с oil infrastructure) ✓

---

## TD-0008 archive note (kept для historical record)

- **Origin:** P-01.0a Phase A diagnostics (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Claude (исполняющий) при triggering
- **Status (2026-04-29): RESOLVED.** Option C verified в P-01.0b CH₄ run —
  все 12 monthly tasks COMPLETED including Q-mid M02/M05/M08/M11. 12 separate
  batch tasks (each own server-side memory allocation) bypass cumulative
  graph memory limit single-iteration approach. Hypothesis confirmed.
- **Outcome:** A (full success). См. OpenSpec MC-D + retroactive run log
  `default_2019_2025_d2e6362c` в `logs/runs.jsonl`.
- **Apply pattern для:** future regional baseline NO₂/SO₂ runs (built into
  build_regional_climatology.py orchestrator). И P-01.0a reference baseline
  if rebuild needed.

### Original concern (kept для historical record)
- **Trigger:** **BLOCKS Phase 2A** (CH4 detection) — must mitigate перед production
  detection runs. Любой из:
  - Refactor compute (preferred, 1 day work)
  - Temporal interpolation as Phase 2A Option A
  - Skip Q-mid detection runs as Phase 2A Option B

### TD-0008 fix hypothesis (researcher 2026-04-28)

Pattern **M02/M05/M08/M11 = months 2,5,8,11 = every 3rd modulo 12**.
Это suggests **GEE internal compute scheduling**, не data-related (data
same across all months — TROPOMI L3 daily mosaics evenly distributed).

**Option C (worth testing):** split full-year build на **12 separate
batch tasks** instead of single iteration в одном process. Each Export
task получает own server-side memory allocation, обходя cumulative
graph memory limit one process generates iterating over 12 months.

Implementation sketch:
```python
for month in range(1, 13):
    task = ee.batch.Export.image.toAsset(
        image=build_single_month_stratified(month),
        assetId=f"...reference_CH4_2019_2025_v1_M{month:02d}",
        ...
    )
    task.start()
# Затем merge 12 single-month assets в multi-band Image через
# ee.Image.cat() или одиночное reuploading combined.
```

**Trade-off:** 12 separate tasks vs 1 multi-band Image → finer error
isolation (one Q-mid month fail не блокирует others) + parallelizable.
**Risk:** orchestration complexity (waiting на 12 tasks, dealing с
partial failures, merging final asset).

**Effort estimate revised: 2-3 days** (hypothesis test + refactor +
re-run для CH4 + 4-band per-zone-id assets — also useful для other gases).
- **Root cause:** `filtered.reduce(median)` followed by `reduceRegion(mean)`
  on stack of ~540 daily images (6 years × 3 months × ~30 daily L3 mosaics)
  exceeds GEE user-side memory limit для interactive `getInfo()` calls.
  Working months (M01, M03, M04, M06, M07, M09, M10, M12) имеют edge effects
  (months 0, 13 partial filter → smaller stack).
- **Fix sketch:** refactor `compute_seasonal_mean` / `build_zone_baseline_single_month`
  на per-month-per-year compute (chunked) с aggregation в Python instead of
  single big server-side reduce. Reduces peak memory ~30×.
  ```python
  monthly_means = []
  for year in range(YEAR_MIN, YEAR_MAX):
      for m_offset in (-1, 0, 1):
          target_m = target_month + m_offset
          monthly_mean = (
              filter_year_month(year, target_m)
              .median()
              .reduceRegion(...).getInfo()
          )
          monthly_means.append(monthly_mean)
  zone_aggregate = python_median(monthly_means)
  ```
- **Effort:** 1 day refactor + re-test all 12 months.

---

## TD-0009 — Cross-biome shared October peak — regional synoptic signal (potential publication)

- **Origin:** P-01.0a validation (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Researcher (decision), Claude (analysis при triggering)
- **Status:** **deferred — not blocker** для current detection pipeline.
  Reference baseline functional с this peak (it's measured signal, не bug).
- **Observation:** All 3 reference zones share October peak — Yugansky 1892,
  Verkhne-Tazovsky 1894, Kuznetsky Alatau 1872. Three biomes (wetland /
  permafrost / mountain), three latitudes (60.5° / 63.5° / 54.5°N) — все
  показывают **synchronous** October peak. Suggests common atmospheric-
  column-level driver, не biotic emission cycle.
- **Trigger:** **HIGH-VALUE investigation** if researcher has cycles для:
  1. Confirm signal not artefact (e.g., MODIS snow filter edge case при
     NDSI 20-40 partial coverage в October)
  2. Cross-validate against in-situ tall-tower measurements (Karasevsky,
     Demyansky, ZOTTO towers)
  3. ERA5 boundary layer height time-series correlation
- **Hypotheses to test:**
  1. Autumn PBL collapse + surface accumulation (lowland-only — but Kuz-Alatau
     mountain forest also peaks → counter-evidence)
  2. MODIS snow filter edge case (NDSI 20-40 partial coverage bias)
  3. Soil-atmosphere shoulder season exchange (literature: Walter Anthony 2010,
     Sasakawa 2012 для Yamal lakes ebullition)
  4. Continental transport pattern shift (autumn jet stream rearrangement)
- **Potential publication:** «First systematic empirical observation of
  cross-biome synchronous October XCH₄ peak in Western Siberia from TROPOMI
  L3 reference baseline» — could be standalone short paper или figure
  для tool-paper Phase 7 Discussion section.
- **Effort:** 5-7 days analysis + literature comparison + figure preparation
  (если pursued seriously).

---

## TD-0010 — Kuznetsky Alatau retrieval count limitation

- **Origin:** P-01.0a validation (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Claude / Researcher
- **Status:** documented caveat, не actionable refactor.
- **Observation:** Kuznetsky Alatau monthly counts 60-140 (vs Yugansky
  ~5000-8000, Verkhne-Tazovsky ~10000-20000). Two orders of magnitude
  fewer valid TROPOMI observations. Cause: mountain cloud cover + SWIR
  retrieval challenges over snow / aspect-variable surfaces.
- **Implications для Phase 2A:**
  - Zone-aggregate baseline still computable (~80-140 valid pixels/month
    adequate для zone-mean median).
  - Sigma estimates noisier for low-N months (e.g., M01 sigma=2.78 ppb
    с count=18 likely artefact).
  - Reduced sensitivity для CH4 detection в latitude band 53-57°N
    (where Kuznetsky Alatau is primary reference per Algorithm §11.3
    Step 4 latitude stratification).
- **Trigger:** if Phase 2A detection в Кузбасс / Мариинск /
  Новокузнецк latitude band shows higher false-negative rate vs
  northern bands, revisit baseline coverage.
- **Mitigations:**
  1. Accept reduced sensitivity, document in tool-paper limitations.
  2. Consider alternative reference zones для southern band (Saian
     Mountains? Tomsk forest reserves? — would require DNA mutation
     per §2.3 для added zones).
  3. Composite baseline (Yugansky weighted partially для южной AOI)
     — alters latitude stratification methodology.
- **Effort:** 0.5 day documentation, или 3-5 days если adding new
  reference zone.

---

## TD-0007 — Yugansky October peak vs article September peak (1-month timing offset)

- **Origin:** P-01.0a Yugansky validation (commit `<merge SHA>`, 2026-04-28)
- **Owner:** Claude (исполняющий) при triggering
- **Status:** deferred — discrepancy между Yugansky measured peak month (October)
  и Sizov et al. in prep article zone-mean peak month (September). Both
  observations valid against revised Algorithm §3.4.0 expectations
  (peak month range August-October).
- **Trigger:** revisit if Phase 2A detection sensitivity shows artifacts
  associated with the October-vs-September timing (e.g., reference baseline
  systematically overestimates October XCH₄ → masks real Plume Events
  в October).
- **Hypotheses:**
  1. Internal buffer 10 km cuts off edge wetlands (which peak earlier in
     August-September) — concentrated bog interior peaks 1-2 weeks later
     due to thermal lag of permafrost-underlain peat.
  2. Year-to-year variability в 6-year (ours 2019-2024) vs 7-year
     (article 2019-2025) averaging windows — 2025 may have peaked earlier.
  3. Real spatial heterogeneity within zone — Yugansky zone is larger
     and more northerly than article zone-mean, possibly later snow-melt
     and freeze-up timing.
- **What's deferred:**
  1. Per-pixel monthly histogram inside Yugansky useable area (identify
     spatial gradient of peak timing).
  2. Year-by-year decomposition (separate 2019/2020/2021/2022/2023/2024
     monthly cycles — has any single year dragged the average).
  3. Consult article authors про zone-4 specific composition.
- **Effort:** 1 day analysis.

---

## TD-0006 — Юганский useable area dropdown (если P-01.0a покажет low count)

- **Origin:** P-00.1 v2 closure (researcher revised escalation gate 2026-04-27)
- **Owner:** Researcher (decision), Claude (implementation)
- **Status:** deferred — current useable area 2946 km² (~60 pixels) проходит
  revised threshold (zone-aggregate ≥ 1000 obs/month).
- **Trigger:** P-01.0a показывает zone-aggregate count < 1000 obs/month для
  Юганского. **Researcher decision required** before any reduction (per R5
  hard constraint: 10 km buffer защита от Самотлор/Salym advection критична).
- **What's deferred:** trade-off analysis reduce buffer 10→8 km vs accept low
  count vs use composite (Юганский + Верхне-Тазовский) baseline.
- **Effort:** 0.5 day analysis + escalation discussion.

---

## Process notes

- Перед закрытием fase / phase: scan этот файл, mark resolved entries как
  ARCHIVED (с датой и commit SHA где fix применён). Удалять не нужно —
  archived entries полезны как historical record.
- Если задача активирована — переместить в backlog (создать DevPrompt) и
  пометить status `ACTIVE` здесь.
- Этот документ обновляется при обнаружении новых deferrals; не требует
  formal CHANGE entry в OpenSpec (operational, не architectural).
