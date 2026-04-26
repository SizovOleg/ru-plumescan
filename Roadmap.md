# RU-PlumeScan — Roadmap v1.0

**Версия:** 1.0  
**Дата:** 2026-04-25  
**Соответствие:** DNA v2.1, Algorithm v2.2, RNA v1.1, OpenSpec v1.0

**Назначение документа:** план фазового развития проекта от текущего состояния (документация готова) до публикации tool-paper в СПДЗЗ и далее. Конкретные milestones, validation criteria, publication timeline.

**Различение Roadmap / OpenSpec:**
- **Roadmap** — что будет сделано когда (forward-looking phases, milestones, deliverables)
- **OpenSpec** — что было/будет изменено в документах и почему (traceability of decisions)

---

## 0. Текущее состояние (baseline)

**Готово к 2026-04-25:**
- ✅ Architectural documentation complete (DNA v2.1, CLAUDE.md, Algorithm v2.2, RNA v1.1, OpenSpec v1.0)
- ✅ Methodology verified через GPT-5.5 на peer-reviewed sources
- ✅ Reference catalog choices finalized (Schuit 2023, IMEO MARS, CAMS Hotspot)
- ✅ DevPrompts naming convention established
- ✅ GEE проект существует (`projects/nodal-thunder-481307-u1`)
- ✅ Архивированы baseline pc_test1_scan.js регрессии (Кузбасс 2022-09-20, Z=3.96)

**НЕ готово:**
- ❌ Repository initialization (GitHub)
- ❌ Industrial proxy mask GEE Asset
- ❌ Background climatologies для CH₄/NO₂/SO₂
- ❌ Detection modules (CH₄, NO₂, SO₂)
- ❌ Reference Catalog Adapter (RCA) ingesters
- ❌ Comparison Engine
- ❌ UI App
- ❌ Validation campaign

**Total estimated effort до v1.0 release:** 4-6 месяцев при solo development с поддержкой Claude Code Desktop.

---

## 1. Phase Structure Overview

```
Phase 0: Foundation              [месяц 0]      → repo + schema + industrial proxy
   ↓
Phase 1: Backgrounds              [месяц 0-1]    → climatologies для CH4/NO2/SO2
   ↓
Phase 2: Detection (parallel)     [месяц 1-3]
   ├─ 2A: CH4 detection
   ├─ 2B: NO2 divergence
   └─ 2C: SO2 rotation + Python fit
   ↓
Phase 3: RCA (parallel с Phase 2) [месяц 1-2]
   ├─ 3A: Schuit2023 ingester
   ├─ 3B: IMEO MARS ingester
   └─ 3C: CAMS Hotspot ingester
   ↓
Phase 4: Comparison Engine        [месяц 2-3]    → matching + cross-source agreement
   ↓
Phase 5: UI App                   [месяц 3-4]    → GEE Code Editor App с UI
   ↓
Phase 6: Validation Campaign      [месяц 4-5]    → regression + synthetic + cross-source
   ↓
Phase 7: Tool-paper preparation   [месяц 5-6]    → manuscript + Zenodo + GitHub release
   ↓
v1.0 RELEASE                      [месяц 6]      → СПДЗЗ submission
```

**Параллельная разработка** Detection + RCA — критична. Без RCA нельзя validate Detection. Без Detection нет outputs для Comparison.

---

## 2. Phase 0: Foundation (1-2 weeks)

### Goal
Заложить repository, Common Plume Schema, industrial proxy mask. Инфраструктура для всего следующего.

### Deliverables

**0.1. GitHub repository initialization**
- Public repo `ru-plumescan/ru-plumescan-tool` (или similar account)
- LICENSE: MIT для кода
- CITATION.cff с placeholder DOI
- README с overview, badges, links на DNA/Algorithm
- File structure per RNA §2

**0.2. Common Plume Schema implementation**
- `src/js/modules/schema.js` — JS validation
- `src/py/rca/common_schema.py` — Python validation + Pydantic models
- Tests: schema validation для valid/invalid examples

**0.3. Industrial proxy mask GEE Asset**
- `data/industrial_sources/*.geojson` files (Kuzbass mines, Norilsk, KhMAO/Yamal oil&gas, Russian power plants from GPPD)
- Python script: load GeoJSONs + GPPD subset + VIIRS night lights threshold → upload `RuPlumeScan/industrial/source_points` (FeatureCollection) и `RuPlumeScan/industrial/proxy_mask` (raster Image)

**0.4. Configuration Presets storage**
- `src/js/modules/presets.js` с full DEFAULT_PRESET + 4 named presets (`schuit_eq`, `imeo_eq`, `sensitive`, `conservative`)
- Upload preset Features в `RuPlumeScan/presets/built_in/*`

**0.5. Logging infrastructure**
- `src/js/modules/logging.js` — Run lifecycle logging
- `RuPlumeScan/runs/` Asset folder для run metadata

### Phase 0 Exit Criteria
- [ ] GitHub repo public, README readable
- [ ] Common Plume Schema validation passes на 5+ test examples
- [ ] Industrial proxy mask Asset visible на map в GEE Code Editor
- [ ] All 5 Configuration Presets exist as Assets
- [ ] Test run-id generation работает (params_hash deterministic)

### Phase 0 DevPrompts
- `P-00.0_repo_init.md` — repository setup + README + LICENSE
- `P-00.1_industrial_proxy.md` — industrial mask construction
- `P-00.2_schema_validation.md` — Common Plume Schema implementation + tests
- `P-00.3_presets_storage.md` — built-in Configuration Presets

---

## 3. Phase 1: Backgrounds (2-3 weeks, частично параллельно с Phase 0)

### Goal
Построить climatological backgrounds для трёх газов. Это входные данные для всех Detection modules.

### Deliverables

**1.1. CH₄ climatology**
- `src/js/modules/background.js` — `buildClimatology(gas, target_year, target_month, bg_config)`
- Algorithm v2.2 §3.4.1: per-pixel median + MAD + count, ±30 day DOY window, leave-one-year-out, industrial buffer exclusion 30 km
- Asset: `RuPlumeScan/backgrounds/CH4/climatology_2019_2025` (Image, monthly bands × 12)

**1.2. NO₂ climatology**
- Same pipeline, NO₂ specific QA (qa_value≥0.75)
- Asset: `RuPlumeScan/backgrounds/NO2/climatology_2019_2025`

**1.3. SO₂ climatology**
- Same pipeline, SO₂ specific (negative floor -0.001)
- Asset: `RuPlumeScan/backgrounds/SO2/climatology_2019_2025`

**1.4. Annulus kernel utilities**
- `src/js/modules/kernels.js` с `makeAnnulusKernel(inner_m, outer_m, scale_m)` per Algorithm §3.4.2
- Tests на synthetic image

### Phase 1 Exit Criteria
- [ ] Climatologies для всех трёх газов в Assets
- [ ] Visual sanity check: climatology XCH4 baseline ~1880 ppb для centre Yamal
- [ ] Industrial buffer exclusion работает: pixel в Норильске не имеет «фон»
- [ ] Annulus kernel produces correct ring pattern на test image

### Phase 1 DevPrompts
- `P-01.0_bg_climatology.md` — generic climatology builder + 3 parallel Assets
- `P-01.1_kernels_utility.md` — annulus + helper kernels

---

## 4. Phase 2: Detection (parallel A/B/C, 6-8 weeks)

### Phase 2A: CH₄ Detection (3-4 weeks)

**Goal:** working CH₄ detection module producing Plume Event Catalog для одного config + period.

**Deliverables:**
- `src/js/modules/detection_ch4.js` — full pipeline per Algorithm §3
  - QA filtering (snow mask, AOD, qa_value, physical range)
  - Hybrid background (climatology + annulus correction)
  - Anomaly Z + relative threshold mask
  - Connected components → vectorize
  - Object metrics (centroid, max_z, max_delta, plume_axis_deg)
  - Wind attribution (ERA5)
  - Source attribution (industrial mask)
  - Confidence scoring
  - Class assignment (CH4_only / diffuse_CH4 / wind_ambiguous)
- Optional IME module (`ime.js`) per Algorithm §6
- Output: FeatureCollection `RuPlumeScan/catalog/CH4/<config_id>_<period>`

**Phase 2A Exit Criteria:**
- [ ] Detection runs без errors на Кузбасс 2022-Q3 (target: ≥1 high-confidence event на 2022-09-20)
- [ ] Output FeatureCollection соответствует Common Plume Schema
- [ ] Каждое Event содержит config snapshot
- [ ] IME (when enabled) выдаёт Q estimates с disclaimer
- [ ] Diffuse_CH4 класс работает: large blob over central wetlands → diffuse, не CH4_only

**Phase 2A DevPrompts:**
- `P-02.0_detection_ch4.md` — main module
- `P-02.1_detection_ch4_ime.md` — IME quantification

---

### Phase 2B: NO₂ Divergence (2-3 weeks)

**Goal:** NO₂ point source detection через flux divergence.

**Deliverables:**
- `src/js/modules/detection_no2.js` per Algorithm §4
  - Multi-month NO₂ averaging
  - ERA5 wind averaging
  - Reproject в UTM 42N (critical: Algorithm §11.4)
  - Flux computation
  - Divergence через `translate()` в metric coordinates
  - Beirle 2019 emission formula `E = D + N/τ`
  - Local maxima detection
  - Output: FeatureCollection point sources с emission rates
- Output: `RuPlumeScan/catalog/NO2/<config_id>_<period>`

**Phase 2B Exit Criteria:**
- [ ] Detection runs на 2022 квартал
- [ ] Cities (Tyumen, Surgut, Novokuznetsk) детектируются как NO₂ sources
- [ ] Power plants из GPPD матчатся с NO₂ peaks (recall > 50%)
- [ ] Calm wind regions (U10 < 2 m/s) skipped per Beirle 2021

**Phase 2B DevPrompts:**
- `P-03.0_detection_no2.md` — main module

---

### Phase 2C: SO₂ Rotation + Python Fit (3-4 weeks, более сложная)

**Goal:** SO₂ per-source detection с full nonlinear plume fit.

**Deliverables:**
- `src/js/modules/detection_so2.js` per Algorithm §5 — GEE side
  - QA filtering (negative floor)
  - Per-source workflow (filter by buffer)
  - Wind rotation в rotated UTM frame
  - Stack mean
  - Sample на rotated grid → export sampled points
- `src/py/so2_fit/` — Python side
  - `plume_models.py` — `gaussian_exp_plume()`, full nonlinear fit, Fioletov simplified
  - `fit_engine.py` — scipy.optimize.curve_fit wrappers
  - `gee_integration.py` — fetch sampled points → fit → upload result back to GEE
- Output: `RuPlumeScan/catalog/SO2/<config_id>_<period>` с Q estimates + uncertainties

**Phase 2C Exit Criteria:**
- [ ] Norilsk SO₂ stable detection (any summer day 2020-2024)
- [ ] Q estimate для Norilsk in range 1000-2500 kt/yr (literature 1500-2000)
- [ ] Fitting window auto-select работает (90 km для Norilsk, 30 km для small TPPs)
- [ ] Python fit recovery test passes (synthetic plume → recovered params within 20%)
- [ ] Fioletov simplified fallback работает при failed full fit

**Phase 2C DevPrompts:**
- `P-04.0_detection_so2.md` — GEE side rotation + sampling
- `P-04.1_so2_python_fit.md` — Python plume fit module
- `P-04.2_so2_integration.md` — end-to-end pipeline test

---

## 5. Phase 3: Reference Catalog Adapter (parallel with Phase 2, 3-4 weeks)

### Phase 3A: Schuit2023 Ingester (1 week)

**Goal:** ingest Schuit 2023 catalog в GEE Asset через Common Plume Schema.

**Deliverables:**
- `src/py/rca/ingesters/schuit2023.py` per RNA §5.2
  - Fetch CSV from Zenodo
  - Validate (n=2974, time range 2021)
  - Map to Common Plume Schema
  - Upload as `RuPlumeScan/refs/schuit2023_v1`

**Exit Criteria:**
- [ ] Asset exists с n=2974 features
- [ ] All required Common Schema fields populated
- [ ] Validation log shows deviation < 5%

**DevPrompt:** `P-05.0_rca_schuit.md`

---

### Phase 3B: IMEO MARS Ingester (2 weeks — более сложная из-за API uncertainty)

**Goal:** ingest UNEP IMEO MARS catalog (replaces Lauvaux 2022 per CHANGE-0012).

**Deliverables:**
- `src/py/rca/ingesters/imeo_mars.py` per RNA §5.3
  - Verify актуальные API endpoints на methanedata.unep.org (URL может отличаться от placeholder)
  - Fetch plumes + sources CSVs/GeoJSONs
  - Validation (min 100 events expected)
  - Map to Common Plume Schema, preserve IMEO-specific fields (`_imeo_*` prefix)
  - Monthly snapshot Asset: `RuPlumeScan/refs/imeo_mars_<YYYY-MM>`
- Cron-script для monthly auto-update (optional, можно manual в v1)

**Exit Criteria:**
- [ ] First snapshot имеет ≥ 100 events
- [ ] Validation passes
- [ ] IMEO-specific fields (persistency, sector, notified) сохранены

**DevPrompt:** `P-05.1_rca_imeo_mars.md`

---

### Phase 3C: CAMS Hotspot Ingester (1 week)

**Goal:** ingest CAMS Methane Hotspot Explorer catalog.

**Deliverables:**
- `src/py/rca/ingesters/cams_hotspot.py`
- Weekly snapshot Asset: `RuPlumeScan/refs/cams_<YYYY-MM-DD>`

**Exit Criteria:**
- [ ] CSV download works
- [ ] First snapshot ingested
- [ ] Common Schema mapping correct

**DevPrompt:** `P-05.2_rca_cams.md`

---

## 6. Phase 4: Comparison Engine (3-4 weeks)

### Goal
Spatial-temporal matching между нашим catalog и reference catalogs. Cross-source agreement scoring.

### Deliverables

**4.1. Matching primitives**
- `src/js/modules/comparison.js` per Algorithm §10
  - `matchEvents(catalog_a, catalog_b, matching_config)` — spatial buffer + temporal window
  - Configurable R_match (default 25 km), T_match (default 1 day)
  - Output: matched_events, unmatched_a, unmatched_b FeatureCollections

**4.2. Metrics computation**
- Recall, precision, F1 (с явным «agreement, not validation» disclaimer)
- Disagreement spatial map (raster of density)

**4.3. Cross-source agreement**
- Per-event `agreement_score = sum(matched_schuit, matched_imeo, matched_cams)`
- Update нашего catalog с new fields (matched_*, agreement_score, last_comparison_date)
- Backfill для existing catalogs

**4.4. Comparison Report storage**
- `RuPlumeScan/comparisons/ours_vs_<ref>/<config_id>_<period>_<date>/` структура
- Sub-assets: matched_events, unmatched_a, unmatched_b, metrics, disagreement_density

### Phase 4 Exit Criteria
- [ ] Comparison run ours_vs_schuit2023 на 2021 период работает
- [ ] Matched events имеют correct spatial-temporal proximity
- [ ] Agreement scores корректно вычислены для всех catalog events
- [ ] Disagreement maps визуально понятны
- [ ] Cross-source agreement labels пишутся в catalog backfill

### Phase 4 DevPrompts
- `P-06.0_comparison_engine.md` — main matching + metrics
- `P-06.1_cross_source_agreement.md` — backfill catalog с agreement scores

---

## 7. Phase 5: UI App (3-4 weeks)

### Goal
Interactive GEE App для exploration детекций, comparison, exports.

### Deliverables

**5.1. UI Layout** per RNA §12
- Header + side panel + map + bottom timeseries chart
- Side panel sections (collapsible): AOI / Gas / Date / Configuration / Display / References / Export / Run Info

**5.2. Configuration UI**
- Preset dropdown (default, schuit_eq, imeo_eq, sensitive, conservative)
- "Show parameters" expand для editing custom values
- Custom configuration → automatic save as `custom_<sha8>` Preset

**5.3. Map layers**
- Anomaly raster (toggleable)
- Plume Event polygons (color по confidence)
- Reference catalog points (Schuit/IMEO/CAMS, toggleable)
- Industrial sources points
- Persistence map (опционально)

**5.4. Comparison panel**
- Trigger Comparison Run button
- Display recall/precision metrics inline
- Highlight matched vs unmatched events

**5.5. Export tools**
- GeoJSON export (catalog)
- CSV export (table)
- GeoTIFF export (anomaly raster)
- Comparison Report PDF (опционально, basic)

**5.6. Time series chart**
- `ui.Chart.image.series` для AOI или selected source
- Configurable metric (mean Y / mean Δ / max Z / valid_pixel_fraction)

**5.7. Run info panel**
- Display current run_id, params_hash, algorithm_version
- "Reproduce this run" button (loads exact config + period)

### Phase 5 Exit Criteria
- [ ] App publishable как `users/<account>/RuPlumeScan`
- [ ] All 5 presets работают
- [ ] Custom configurations создают новые Presets
- [ ] Map layers корректно toggle
- [ ] Comparison Run триггерится из UI
- [ ] Exports работают
- [ ] Time series отрисовывается для known sources

### Phase 5 DevPrompts
- `P-07.0_ui_layout.md` — basic layout + side panel
- `P-07.1_ui_configuration.md` — preset management + custom config save
- `P-07.2_ui_map_layers.md` — layer toggling + styling
- `P-07.3_ui_comparison.md` — comparison trigger + metrics display
- `P-07.4_ui_export.md` — GeoJSON/CSV/GeoTIFF exports

---

## 8. Phase 6: Validation Campaign (3-4 weeks)

### Goal
Систематическая validation перед публикацией. Все sanity checks из CLAUDE.md §5 проходят. Cross-source agreement metrics зафиксированы для article.

### Deliverables

**6.1. Regression baselines**
- Run все три regression tests (Кузбасс 2022-09-20, Norilsk SO₂, Бованенково CH₄)
- Документировать expected outputs
- Asset baseline: `RuPlumeScan/validation/regression/baseline_2026-XX-XX`

**6.2. Synthetic plume injection campaign**
- Run injection sweep [10, 30, 50, 100, 200] ppb amplitudes × [2, 3, 4, 5] geometry pixels
- Pass criterion: recovered/injected ≥ 0.7 для amplitude ≥ 30 ppb
- Document detection limit per Configuration Preset
- Asset: `RuPlumeScan/validation/synthetic_injection/recovery_results_<date>`

**6.3. False positive control**
- Run detection на wetland-only zones (центр болот, no infrastructure within 50 km buffer) для periods 2021-2024
- Acceptable: < 5% candidates с high confidence в pure wetland zones
- Document ratio для каждого Preset

**6.4. Cross-source comparison runs**
- Ours_vs_Schuit2023 для CH₄ 2021 (full overlap period)
- Ours_vs_IMEO_MARS для CH₄ 2024-2026 (recent overlap)
- Ours_vs_CAMS для CH₄ 2024-2025
- Document recall/precision для каждого Preset
- Cross-tabulation table готова для article (Table 4)

**6.5. Sensitivity sweep documentation**
- z_min sweep [2.0, 2.5, 3.0, 3.5, 4.0, 4.5] для default Preset, period Kuzbass 2022-Q3
- delta_min sweep [10, 20, 30, 50, 80, 120] ppb
- Document ROC-like curves готовы для article (Figure 5)

**6.6. Configuration Preset validation**
- Each Preset run на full year 2022 (one gas at a time)
- Document n_events, mean_confidence, cross-source agreement по Preset
- Confirm presets дают expected behavior (sensitive → много candidates, conservative → мало high-confidence)

### Phase 6 Exit Criteria
- [ ] All 3 regression tests pass
- [ ] Synthetic plume recovery > 0.7 для amplitude ≥ 30 ppb
- [ ] False positive rate в wetland-only zones < 5%
- [ ] Cross-source agreement против ≥ 2 references > 30% (DNA §4.5 stop criterion check)
- [ ] All 5 Presets дают different but valid outputs

### Phase 6 DevPrompts
- `P-08.0_validation_synthetic.md` — synthetic injection campaign
- `P-08.1_validation_regression.md` — regression baselines + comparison
- `P-08.2_validation_sensitivity.md` — sensitivity sweeps
- `P-08.3_validation_false_positive.md` — wetland zone control
- `P-08.4_validation_cross_source.md` — full comparison campaign

---

## 9. Phase 7: Tool-paper preparation (4-6 weeks)

### Goal
Manuscript для СПДЗЗ + open release artifacts (GitHub, Zenodo).

### Deliverables

**7.1. Manuscript structure (target: СПДЗЗ)**

```
1. Введение (1-2 pages)
   - State of the art: CAMS, IMEO MARS, Carbon Mapper, SRON
   - Gap для российских исследователей: closed ML, Western-centric, no GEE-native open tool
   - Цель: открытый configurable workbench

2. Методы (4-6 pages)
   - 2.1. TROPOMI L3 в GEE — особенности и ограничения
   - 2.2. CH4 detection: regional threshold-based (adapted from Schuit pre-ML)
   - 2.3. NO2 divergence (Beirle 2019 method)
   - 2.4. SO2 wind rotation (Fioletov 2020 + full nonlinear fit)
   - 2.5. Multi-gas evidence aggregation (NOVEL)
   - 2.6. Reference Catalog Adapter (RCA) и cross-source comparison

3. Реализация инструмента (3-4 pages)
   - 3.1. Configurable Detection Surface architecture
   - 3.2. Configuration Presets и custom configurations
   - 3.3. UI и API
   - 3.4. Forward-compatibility v1 → v2 ML

4. Демонстрационные сценарии (5-7 pages)
   - 4.1. Sensitivity analysis параметров над Кузбассом 2022
   - 4.2. Cross-validation против reference catalogs
        - vs Schuit 2023 (recall, precision, agreement table)
        - vs IMEO MARS (recall на 2024-2026)
        - vs CAMS Hotspot (recall на overlap period)
        - Cross-source agreement matrix
   - 4.3. Time series Норильска SO₂ 2019-2026
   - 4.4. Multi-gas evidence для ХМАО oil&gas facilities (CH4+NO2 matching)
   - 4.5. Detection limit characterization (synthetic injection)

5. Обсуждение (2-3 pages)
   - Honest limitations (single ERA5, L3 vs L2, snow/wetland biases, IME ±50%)
   - Сравнение с established systems
   - Future development (v2 ML, regional U_eff calibration, L2 reprocessed)

6. Выводы (1 page)
   - Open tool для российского EO-сообщества
   - Configurability + reproducibility как key principles
   - Calls to action: contribute, validate
```

**7.2. Figures и tables**
- Figure 1: Architecture diagram (Detection + RCA + Comparison)
- Figure 2: Hybrid background construction (climatology + annulus example)
- Figure 3: CH₄ detection example (Кузбасс 2022-09-20)
- Figure 4: NO₂ divergence map (Yamal/HMAO oil&gas region)
- Figure 5: SO₂ rotated plume Norilsk
- Figure 6: Sensitivity curve (z_min sweep with recall vs precision)
- Figure 7: Synthetic recovery curves
- Figure 8: Cross-source agreement matrix (3 references × N events)
- Figure 9: Time series Norilsk SO₂ 2019-2026
- Figure 10: UI screenshot
- Table 1: Configuration Presets summary
- Table 2: Reference catalogs comparison (Schuit/IMEO/CAMS)
- Table 3: Detection limits per gas per source magnitude
- Table 4: Cross-source agreement statistics
- Table 5: Sensitivity sweep results

**7.3. Open release artifacts**
- GitHub release v1.0.0 (tagged, with CHANGELOG)
- Zenodo Asset DOI (для catalog)
- Zenodo software DOI (для code)
- Documentation website (GitHub Pages, optional)
- Announcement в community (RSL, Russian remote sensing forums)

**7.4. Submission**
- Cover letter с emphasis на novelty (multi-gas matching, GEE-native, открытость для российской территории)
- Suggested reviewers (Cherepanova, российские TROPOMI users)
- Response to anticipated reviewer questions (см. section 7.5)

**7.5. Anticipated reviewer questions (preparation)**

**Q: «Что нового по сравнению с зарубежными аналогами?»**
A: (1) Региональная адаптация для Западной Сибири с specific industrial buffer exclusion, snow mask, regional climatology; (2) **Multi-gas evidence aggregation** — first systematic event-level matching of TROPOMI gases для industrial source attribution at regional scale; (3) Open implementation в GEE — accessible для researchers без AWS; (4) Reference Catalog Adapter с cross-source comparison built-in.

**Q: «Как валидировано?»**
A: 4 independent validation paths:
- Regression baselines на known events (Кузбасс 2022-09-20, Норильск SO₂, Бованенково CH₄)
- Synthetic plume injection с amplitude characterization
- Cross-source agreement против Schuit 2023, IMEO MARS, CAMS Hotspot
- False positive control на pure wetland zones (Западная Сибирь имеет >40% wetland coverage)

**Q: «Каковы ограничения?»**
A: Honest table в Discussion: single ERA5 wind (vs ensemble Schuit/CAMS), TROPOMI L3 vs reprocessed L2, IME ±50% uncertainty, SO₂ marginal detection для <100 kt/yr sources, single-day NO₂ detection невозможна, ML deferred to v2.

**Q: «Воспроизводимо ли?»**
A: Полный config snapshot в каждом Plume Event Feature (params_hash, algorithm_version, run_id). Open code (MIT). Open catalog (CC-BY 4.0). Bit-identical reproducibility test проходит.

### Phase 7 Exit Criteria
- [ ] Manuscript draft v1 готов
- [ ] Internal review pass (ideally от знакомых researchers)
- [ ] All figures/tables generated через scripts (не manual)
- [ ] GitHub v1.0.0 release tagged
- [ ] Zenodo DOIs assigned
- [ ] Manuscript submitted в СПДЗЗ

### Phase 7 DevPrompts
- `P-09.0_figure_generation.md` — automated figure scripts
- `P-09.1_release_preparation.md` — GitHub + Zenodo release
- (Manuscript pisanie — human-driven, не DevPrompt)

---

## 10. v1.0 Release (target: 2026-10 — 2026-12)

### v1.0 Definition

v1.0 = **Validated Configurable Tool** ready для public use:

- ✅ Detection Engine для CH4/NO2/SO2 working
- ✅ RCA с 3 reference catalogs ingested
- ✅ Comparison Engine functional
- ✅ UI App published как public GEE App
- ✅ Validation campaign passed
- ✅ Tool-paper submitted в СПДЗЗ
- ✅ GitHub v1.0.0 + Zenodo DOIs

**Release artifacts:**
- GitHub: `github.com/<user>/ru-plumescan` v1.0.0 tagged
- GEE App: `users/<account>/RuPlumeScan` published
- Zenodo: code DOI + catalog DOI
- СПДЗЗ submission ID

---

## 11. Post-v1.0 Roadmap

### v1.1 (3-6 months после v1.0): refinements based on reviews

- Address СПДЗЗ reviewer comments
- Bug fixes from community feedback
- Additional Configuration Presets если запрошены
- Optional: Lauvaux 2022 ingester (если получим CSV от authors — CHANGE-B003)

### v2.0 (12-18 months после v1.0): ML-augmented detection

**Activation conditions** (per DNA §4.1, CHANGE-B001):
- ≥ 500 events с cross-source agreement labels накоплено
- Минимум 4 классов размечены
- Inter-rater agreement > 0.7 (если manual labeling)
- Documented temporal train/test split

**Deliverables:**
- ML classifier поверх v1 candidates (binary: plume / artifact, или multi-class)
- Training pipeline через cross-source agreement labels (high-confidence positive samples)
- Optional: manual expert labeling для ambiguous cases
- Updated UI с ML confidence overlay

### v2.1: Regional U_eff calibration (CHANGE-B002)

После accumulation 50+ matched events с independent quantification estimates → regression `Q_observed` против Schuit/IMEO catalog quantifications → regional `(a, b)` coefficients для Западной Сибири.

**Potential publication contribution:** «Calibrated effective wind speed parametrization for TROPOMI methane plume quantification over subarctic continental conditions»

### v3.0 (отдалённая, требует мутации DNA): Integration phase

Possible directions (per DNA §4.1, CHANGE-B005):
- High-resolution Sentinel-2 follow-up для confirmed v2 events
- Inversion для persistent sources (limited IMI-style)
- Climate TRACE-style emission attribution
- Real-time alerts через Pub/Sub

---

## 12. Effort estimates summary

| Phase | Duration | Complexity | Dependencies |
|---|---|---|---|
| 0: Foundation | 1-2 weeks | Low | None |
| 1: Backgrounds | 2-3 weeks | Medium | Phase 0 |
| 2A: CH4 Detection | 3-4 weeks | High | Phase 1 |
| 2B: NO2 Detection | 2-3 weeks | Medium-High | Phase 1 |
| 2C: SO2 + Python Fit | 3-4 weeks | High (Python integration) | Phase 1 |
| 3A: Schuit Ingester | 1 week | Low | Phase 0 |
| 3B: IMEO MARS Ingester | 2 weeks | Medium (API uncertainty) | Phase 0 |
| 3C: CAMS Ingester | 1 week | Low | Phase 0 |
| 4: Comparison Engine | 3-4 weeks | High | Phase 2 + Phase 3 |
| 5: UI App | 3-4 weeks | Medium | Phase 4 |
| 6: Validation Campaign | 3-4 weeks | Medium | Phase 5 |
| 7: Manuscript | 4-6 weeks | High (writing) | Phase 6 |
| **Total to v1.0** | **6 months** | **High** (solo + Claude Code) | All sequential except 2/3 parallel |

**Risk factors:**
- IMEO MARS API endpoints могут быть unstable → backup plan: manual download
- SO₂ Python fit может потребовать tuning для real TROPOMI data → buffer week
- GEE quota constraints для batch tasks → mitigation: chunked processing
- Reviewer round-trip может добавить 3-6 месяцев до publication

**Mitigation: parallel work tracks.** Phase 3 (RCA) запускается параллельно с Phase 2 (Detection), потому что они independent. Это сжимает critical path с 6+1+8+4+4+4+6 = 33 weeks до ~24 weeks (6 months).

---

## 13. Critical path и blockers

### Critical path
```
Phase 0 → Phase 1 → Phase 2A (CH4) → Phase 4 (Comparison) → Phase 5 (UI) → Phase 6 (Validation) → Phase 7 (Paper)
```

CH₄ detection — главный critical path. NO₂ и SO₂ можно делать параллельно.

### External blockers (out of our control)

- IMEO MARS API stability и documentation accuracy
- GEE platform availability и quota policies в 2026
- TROPOMI L3 reprocessing (если NRT product изменится)
- СПДЗЗ review timeline (typically 3-6 months)

### Internal blockers (мы контролируем)

- Quality DevPrompts → quality of Claude Code output
- Validation rigour → defensibility публикации
- Documentation discipline → reproducibility

---

## 14. Success metrics

### Quantitative (objective)

- v1.0 release к 2026-12 (target month 6 от 2026-04-25 baseline)
- Регистрация ≥ 1 high-confidence event в каждом regression test
- Synthetic recovery > 0.7 для amplitude ≥ 30 ppb CH₄
- Cross-source agreement > 30% против ≥ 2 references
- < 5% false positives в wetland-only zones
- 100% Plume Events содержат config snapshot

### Qualitative (judgment)

- Tool-paper accepted в СПДЗЗ (или эквивалентном Q1 ВАК журнале)
- Документация полна enough для independent reproduction researcher не из нашей team
- Configuration Presets cover practical use cases (screening, conservative, sensitive, reference equivalents)
- UI usable researcher без deep GEE knowledge

### Failure modes (DNA §4.5 voluntary stop)

- Cross-source agreement < 30% events with 2+ references → методология не согласуется с established → STOP, revise
- > 50% candidates в wetland-only zones → false positive rate неприемлем → STOP, revise
- Synthetic recovery < 0.5 для amplitude ≥ 30 ppb → фон или фильтры съедают сигнал → STOP, revise
- Reference catalog ingestion даёт inconsistent results → schema или RCA нарушены → STOP, fix

---

## 15. Версионирование Roadmap

| Версия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-04-25 | Первая версия. 7 phases с estimated effort 6 months solo. Critical path defined. v1.0 / v2.0 / v3.0 future versions. |

Roadmap обновляется при:
- Завершении phase (mark as DONE, document actual vs estimated)
- Discovery новых blockers
- Изменении DNA (новые fundamental directions)
- Изменении timeline (delays, accelerations)

Не обновляется при routine progress в текущих DevPrompts.
