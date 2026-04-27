# RU-PlumeScan — Roadmap v1.1

**Версия:** 1.1  
**Дата:** 2026-04-26  
**Соответствие:** DNA v2.2, Algorithm v2.3, RNA v1.2, OpenSpec v1.0  
**Замена:** Roadmap v1.0 (archived)

**Изменения v1.0 → v1.1 (CHANGE-0017):**
- Phase 0 deliverables expanded: P-00.1 теперь имеет dual scope (industrial + protected areas reference)
- Phase 1 split в три подфазы: 1a (reference baseline) + 1b (regional climatology) + 1c (dual baseline cross-check validation)
- Phase 2A CH₄ detection теперь использует dual baseline output из Phase 1
- Phase 6 validation campaign включает Алтайский QA test и dual baseline divergence analysis
- Phase 7 tool-paper structure обновлена: добавлен второй novelty argument (reference-anchored baseline approach)
- Effort estimate skewed slightly (Phase 1 удлинён на 1-2 недели из-за protected areas ingestion)

---

## 0. Текущее состояние (baseline 2026-04-26)

**Готово:**
- ✅ Architectural documentation complete (DNA v2.2, CLAUDE.md, Algorithm v2.3, RNA v1.2, OpenSpec v1.0)
- ✅ Methodology verified через GPT-5.5 на peer-reviewed sources
- ✅ Reference catalog choices finalized (Schuit 2023, IMEO MARS, CAMS Hotspot)
- ✅ **Reference Clean Zones identified** (CHANGE-0017): Юганский, Верхнетазовский, Кузнецкий Алатау + optional Алтайский
- ✅ DevPrompts naming convention established
- ✅ GEE проект существует (`projects/nodal-thunder-481307-u1`)
- ✅ **P-00.0 завершён** — repo + Common Plume Schema + 30 unit tests + 22 GEE folders
- ✅ **Step 0 (V1 archival) завершён** — 25 V1 climatology Images перенесены в `RuPlumeScan_v1_archived/`
- ✅ Архивированы baseline pc_test1_scan.js регрессии (Кузбасс 2022-09-20, Z=3.96)

**В прогрессе:**
- 🔄 Phase 0 — P-00.1 (industrial + protected areas reference, переписан под dual scope)

**НЕ готово:**
- ❌ Industrial proxy mask GEE Asset (P-00.1 industrial part)
- ❌ Protected areas reference mask + FeatureCollection (P-00.1 reference part, NEW в v1.1)
- ❌ Configuration Presets storage (P-00.3)
- ❌ Reference baselines для CH₄/NO₂/SO₂ (P-01.0a, NEW в v1.1)
- ❌ Regional climatologies (P-01.0b)
- ❌ Detection modules (CH₄, NO₂, SO₂)
- ❌ RCA ingesters
- ❌ Comparison Engine
- ❌ UI App
- ❌ Validation campaign
- ❌ Алтайский QA test (Phase 1 deliverable)

**Total estimated effort до v1.0 release:** 6-7 месяцев при solo development с поддержкой Claude Code Desktop. (Was 4-6 в v1.0; +1-2 weeks for protected areas ingestion + reference baseline build).

---

## 1. Phase Structure Overview

```
Phase 0: Foundation                      [месяц 0]      → repo + schema + dual proxy (industrial + reference)
   ↓
Phase 1: Backgrounds (parallel)          [месяц 1-2]
   ├─ 1a: Reference baseline (NEW)
   ├─ 1b: Regional climatology
   └─ 1c: Dual baseline cross-check validation (NEW)
   ↓
Phase 2: Detection (parallel)            [месяц 2-4]
   ├─ 2A: CH4 detection (uses dual baseline)
   ├─ 2B: NO2 divergence
   └─ 2C: SO2 rotation + Python fit
   ↓
Phase 3: RCA (parallel с Phase 2)        [месяц 2-3]
   ├─ 3A: Schuit2023 ingester
   ├─ 3B: IMEO MARS ingester
   └─ 3C: CAMS Hotspot ingester
   ↓
Phase 4: Comparison Engine               [месяц 3-4]
   ↓
Phase 5: UI App                          [месяц 4-5]
   ↓
Phase 6: Validation Campaign             [месяц 5-6]    → includes Altaisky QA + dual baseline divergence
   ↓
Phase 7: Tool-paper preparation          [месяц 6-7]    → two novelty arguments
   ↓
v1.0 RELEASE                             [месяц 7]      → СПДЗЗ submission
```

**Параллельная разработка** Detection + RCA + Reference baseline Builder — критична. Без RCA нельзя validate Detection. Без Reference baseline нельзя cross-check Detection.

---

## 2. Phase 0: Foundation

**Goal:** repository, Common Plume Schema, dual proxy (industrial + reference protected areas).

**Deliverables (extended in v1.1):**

**0.1.** ✅ GitHub repository initialization (P-00.0 done)

**0.2.** ✅ Common Plume Schema implementation (P-00.0 done)

**0.3.** Industrial proxy mask GEE Asset (P-00.1 industrial part)
- Manual GeoJSONs (kuzbass_mines, khmao_yamal_oil_gas, norilsk_complex, additional)
- GPPD subset
- VIIRS bright pixels proxy
- Combined `RuPlumeScan/industrial/source_points` FeatureCollection
- `RuPlumeScan/industrial/proxy_mask` Image

**0.4.** **Protected areas reference mask GEE Asset (P-00.1 reference part, NEW в v1.1)**
- 4 manual GeoJSONs в `data/protected_areas/`: yugansky, verkhnetazovsky, kuznetsky_alatau, altaisky
- Zone metadata (centroid, internal_buffer, latitude_band, quality_status)
- `RuPlumeScan/reference/protected_areas` FeatureCollection
- `RuPlumeScan/reference/protected_areas_mask` Image

**0.5.** Configuration Presets storage (P-00.3)
- 7 presets теперь (было 5): default, schuit_eq, imeo_eq, sensitive, conservative + diagnostic regional_only + reference_only

**Phase 0 Exit Criteria:**
- [x] GitHub repo public
- [x] Common Plume Schema validation passes
- [ ] Industrial proxy mask Asset visible
- [ ] **Protected areas Asset visible — 4 zones отображаются на map (NEW)**
- [ ] All 7 Configuration Presets exist as Assets
- [ ] Test run-id generation works

**Phase 0 DevPrompts:**
- ✅ P-00.0_repo_init.md (done)
- 🔄 P-00.1_industrial_and_reference_proxy.md (revised для dual scope)
- P-00.2_schema_validation.md
- P-00.3_presets_storage.md

---

## 3. Phase 1: Backgrounds (split в 3 подфазы в v1.1)

**Goal:** построить **dual baseline** для трёх газов: reference (positive space) + regional (negative space) + cross-check validation.

### Phase 1a: Reference Baseline (NEW в v1.1)

**Goal:** построить reference baseline asset из protected areas.

**Deliverables:**
- `src/js/modules/reference_baseline.js` per RNA §11.2
- `src/py/setup/altaisky_qa_test.py` — runs QA test, decides Алтайский inclusion
- Reference baseline Assets для CH₄: `RuPlumeScan/baselines/reference_CH4_2019_2025`
- Алтайский QA test result: `RuPlumeScan/validation/altaisky_qa/test_<date>`

**Workflow:**
1. Запускаем Алтайский QA test (Algorithm v2.3 §11.4)
2. Update protected_areas FeatureCollection с обновлённым quality_status
3. Build reference baseline без/с Алтайским в зависимости от QA result
4. Sanity check: Юганский XCH4 в июле 2022 в range [1900, 1950] ppb

**Exit Criteria:**
- [ ] Reference baseline CH4 Asset существует
- [ ] Юганский summer XCH4 в expected range (sanity check passed)
- [ ] Алтайский QA test result documented (pass/fail с metrics)
- [ ] Latitude stratification works: pixel в Кузбассе берёт baseline от Кузнецкого Алатау

**DevPrompt:** `P-01.0a_reference_baseline.md` (NEW в v1.1)

### Phase 1b: Regional Climatology

**Goal:** построить regional climatology с industrial buffer exclusion (как было в v1.0).

**Deliverables:**
- `src/js/modules/background.js` — `buildRegionalClimatology()` 
- Regional climatology Assets для CH₄/NO₂/SO₂: `RuPlumeScan/baselines/regional_<gas>_2019_2025`

**Exit Criteria:**
- [ ] Regional climatologies для всех трёх газов в Assets
- [ ] Industrial buffer exclusion работает (Норильск pixel не имеет ‘фон’)
- [ ] Climatology XCH4 baseline в Yamal centre ~1880 ppb

**DevPrompt:** `P-01.0b_regional_climatology.md` (renamed)

### Phase 1c: Dual Baseline Cross-check Validation (NEW в v1.1)

**Goal:** валидировать что reference и regional baselines дают consistent results для clean regions.

**Tests:**
1. **Convergence test:** для clean regions (вне industrial buffer, вне reference zones) — distribution |reference - regional| должен иметь mean < 20 ppb, std < 30 ppb. Иначе один из baselines flawed.
2. **Industrial divergence test:** для regions внутри industrial buffer — `regional > reference + 30 ppb` ожидаемо (regional contains contamination, reference нет).
3. **Reference zone consistency test:** для regions внутри reference zones (после internal buffer) — `|reference - regional|` должен быть minimal (< 15 ppb), потому что regional там не должен иметь industrial contamination.

**Deliverables:**
- Test report Asset: `RuPlumeScan/validation/dual_baseline_check/<date>`
- Histogram plots: divergence distribution
- Map: spatial pattern of divergence

**Exit Criteria:**
- [ ] Convergence test passes для clean regions
- [ ] Industrial divergence pattern observed (regional > reference around known sources)
- [ ] Reference zone consistency holds

**DevPrompt:** `P-01.2_dual_baseline_validation.md` (NEW в v1.1)

### Phase 1 общие deliverables

- `src/js/modules/kernels.js` — `makeAnnulusKernel()` (P-01.1)

**Phase 1 Exit Criteria (overall):**
- [ ] Reference baselines для CH₄ (Phase 1a)
- [ ] Regional climatologies для CH₄/NO₂/SO₂ (Phase 1b)
- [ ] Dual baseline cross-check validation passes (Phase 1c)
- [ ] Annulus kernel utility works

---

## 4. Phase 2: Detection (parallel A/B/C, 6-8 weeks)

### Phase 2A: CH₄ Detection (3-4 weeks)

**Goal:** working CH₄ detection с **dual baseline approach**.

**Deliverables (extended in v1.1):**
- `src/js/modules/detection_ch4.js` per Algorithm §3 (v2.3)
  - QA filtering
  - **Dual baseline construction (reference + regional + annulus)**
  - **delta_vs_regional + delta_vs_reference + baseline_consistency_flag**
  - Anomaly Z + relative threshold mask (использует delta_primary)
  - Connected components → vectorize
  - Object metrics + plume axis
  - Wind attribution (ERA5)
  - Source attribution (industrial mask)
  - **matched_inside_reference_zone check (NEW)**
  - Confidence scoring (с consistency weight + inside_zone penalty)
  - Class assignment
- Optional IME module per Algorithm §6
- Output FeatureCollection per Common Plume Schema v1.1 (extended)

**Phase 2A Exit Criteria:**
- [ ] Detection runs на Кузбасс 2022-Q3 (≥1 high-confidence event на 2022-09-20)
- [ ] Output FeatureCollection соответствует Common Plume Schema v1.1
- [ ] **Каждое Event содержит delta_vs_regional, delta_vs_reference, baseline_consistency_flag, matched_inside_reference_zone (NEW)**
- [ ] Diffuse_CH4 класс работает
- [ ] Confidence scoring downgrades events inside reference zones (sanity test: artificial event внутри Юганского → confidence ≤ low)

**DevPrompts:** P-02.0_detection_ch4.md, P-02.1_detection_ch4_ime.md

### Phase 2B: NO₂ Divergence (2-3 weeks)

Без изменений с v1.0. Reference baseline для NO₂ — future enhancement, не v1.0.

### Phase 2C: SO₂ Rotation + Python Fit (3-4 weeks)

Без изменений с v1.0.

---

## 5. Phase 3: Reference Catalog Adapter (3-4 weeks)

Без изменений с v1.0. Schuit + IMEO MARS + CAMS.

---

## 6. Phase 4: Comparison Engine (3-4 weeks)

Без изменений с v1.0.

---

## 7. Phase 5: UI App (3-4 weeks)

**Extended в v1.1:**
- Add layer toggles для reference baseline + regional climatology + divergence map
- Add background mode selector (dual_baseline / regional_only / reference_only)
- Add reference zones polygon overlay с popup metadata
- Add diagnostic presets (regional_only, reference_only) в dropdown

DevPrompts расширены соответственно.

---

## 8. Phase 6: Validation Campaign (3-4 weeks)

**Extended в v1.1:**

### 8.1. Existing tests из v1.0
- Regression baselines (Кузбасс 2022-09-20, Norilsk SO₂, Бованенково CH₄)
- Synthetic plume injection campaign
- False positive control (wetland-only zones)
- Cross-source comparisons (vs Schuit, IMEO MARS, CAMS)
- Sensitivity sweeps
- Configuration Preset validation

### 8.2. NEW в v1.1: Reference baseline validations

**8.2.1. Reference baseline temporal stability test**
- Build reference baselines для каждого года 2020-2025
- Test: year-to-year variation in zone-aggregated baseline value < 10 ppb
- Если diverge → suggesting либо TROPOMI calibration drift, либо changing wetland conditions

**8.2.2. Dual baseline divergence analysis**
- Run detection с dual_baseline preset на full year 2022 для Yamal+KhMAO
- Distribution analysis: pixels с consistency_flag=false
- Spatial analysis: где divergence сосредоточена → возможные undocumented industrial sources
- Это потенциально discovery of new persistent sources (publication asset)

**8.2.3. Reference vs Regional comparison runs**
- Run detection с regional_only preset
- Run detection с reference_only preset
- Run detection с dual_baseline preset (default)
- Compare event counts, confidence distributions
- Document the "value of reference baseline" quantitatively

**8.2.4. Inside-zone false positive check**
- Run detection с default preset на Yamal+KhMAO 2022
- Filter events inside Юганский (after internal buffer)
- Expected: < 1% events should be inside zone (если zone truly clean)
- Если > 5% — методологическая проблема

### Phase 6 Exit Criteria (extended):
- [ ] All 3 regression tests pass
- [ ] Synthetic recovery > 0.7 для amplitude ≥ 30 ppb
- [ ] False positive rate в wetland-only zones < 5%
- [ ] Cross-source agreement > 30%
- [ ] **Reference baseline temporal stability < 10 ppb year-to-year (NEW)**
- [ ] **Dual baseline divergence analysis report готов (NEW)**
- [ ] **Reference vs Regional comparison documented (NEW)**
- [ ] **Inside-zone false positive < 1% (NEW)**

DevPrompts: P-08.0..4 + новые P-08.5_reference_validation.md (NEW в v1.1)

---

## 9. Phase 7: Tool-paper preparation (4-6 weeks)

### Manuscript structure (updated в v1.1)

```
1. Введение
   - State of the art: CAMS, IMEO MARS, Carbon Mapper, SRON
   - Gap для российских исследователей
   - Цель: открытый configurable workbench

2. Методы
   - 2.1. TROPOMI L3 в GEE — особенности и ограничения
   - 2.2. CH4 detection: regional threshold-based с dual baseline (NEW emphasis)
       - 2.2.1 Reference baseline from protected nature reserves (NOVEL CONTRIBUTION 1)
       - 2.2.2 Regional climatology с industrial buffer (complementary)
       - 2.2.3 Dual baseline cross-check
   - 2.3. NO2 divergence (Beirle 2019 method)
   - 2.4. SO2 wind rotation (Fioletov 2020)
   - 2.5. Multi-gas evidence aggregation (NOVEL CONTRIBUTION 2)
   - 2.6. Reference Catalog Adapter и cross-source comparison

3. Реализация инструмента
   - 3.1. Configurable Detection Surface architecture
   - 3.2. Configuration Presets (default + diagnostic regional_only/reference_only)
   - 3.3. UI и API
   - 3.4. Forward-compatibility v1 → v2 ML

4. Демонстрационные сценарии
   - 4.1. Reference baseline characterization (Юганский seasonal cycle, etc.)
   - 4.2. Dual baseline divergence map для Yamal+KhMAO
   - 4.3. CH4 detection example Кузбасс 2022-09-20
   - 4.4. NO2 divergence map (Yamal/HMAO oil&gas region)
   - 4.5. SO2 rotated plume Norilsk
   - 4.6. Cross-validation против reference catalogs
   - 4.7. Sensitivity analysis

5. Обсуждение
   - 5.1. Honest limitations
   - 5.2. **Value of reference-anchored baseline approach (NEW SECTION)**
       - Comparison vs industrial-buffer-only approach (regional_only preset results)
       - Detection of undocumented sources via divergence (если найдено)
   - 5.3. Сравнение с established systems
   - 5.4. Future development

6. Выводы
   - **Two methodological novelties: multi-gas matching + reference-anchored baseline**
   - Open tool для российского EO-сообщества
```

### NEW в v1.1: Figures на reference baseline

- Figure: Reference Clean Zones map (4 заповедника + boundaries + internal buffers)
- Figure: Юганский seasonal cycle of XCH4 baseline (validation evidence)
- Figure: Dual baseline divergence histogram (clean regions ~0, industrial regions skewed positive)
- Figure: Spatial divergence map (где regional > reference → contamination suspect)
- Table: Reference Clean Zones summary (zone, area, latitude band, quality_status)

---

## 10. v1.0 Release

**v1.0 Definition (extended in v1.1):**

- ✅ Detection Engine для CH4/NO2/SO2 working
- ✅ **Dual baseline approach реализован для CH4 (CHANGE-0017)**
- ✅ RCA с 3 reference catalogs ingested
- ✅ Comparison Engine functional
- ✅ UI App published
- ✅ Validation campaign passed (включая reference baseline validations)
- ✅ Tool-paper submitted в СПДЗЗ
- ✅ GitHub v1.0.0 + Zenodo DOIs
- ✅ **Reference Baseline Asset published как standalone scientific artifact с Zenodo DOI (NEW в v1.1)**

---

## 11. Post-v1.0 Roadmap

### v1.1 (3-6 months после v1.0): refinements

- Address СПДЗЗ reviewer comments
- Bug fixes from community feedback
- **Reference baseline для NO₂ и SO₂ (extension)**
- Optional Lauvaux 2022 ingester

### v2.0 (12-18 months): ML-augmented detection

- Activation per DNA §4.1, CHANGE-B001
- ML training labels включая `matched_inside_reference_zone` как negative samples (NEW в v1.1)

### v2.1: Regional U_eff calibration (CHANGE-B002)

### v3.0 (отдалённая, требует мутации DNA): Integration phase

- Extension reference zones за пределы Западной Сибири — другие regions РФ имеют свои заповедники

---

## 12. Effort estimates summary (revised в v1.1)

| Phase | Duration | Complexity | Dependencies |
|---|---|---|---|
| 0: Foundation | 2-3 weeks (was 1-2) | Low-Medium (added protected areas) | None |
| 1a: Reference baseline | 2 weeks (NEW) | Medium-High (Алтайский QA + stratification) | Phase 0 |
| 1b: Regional climatology | 2 weeks | Medium | Phase 0 |
| 1c: Dual baseline validation | 1 week (NEW) | Medium | Phase 1a + 1b |
| 2A: CH4 Detection | 3-4 weeks | High (dual baseline integration) | Phase 1 |
| 2B: NO2 Detection | 2-3 weeks | Medium-High | Phase 1b |
| 2C: SO2 + Python Fit | 3-4 weeks | High | Phase 1b |
| 3A: Schuit Ingester | 1 week | Low | Phase 0 |
| 3B: IMEO MARS Ingester | 2 weeks | Medium | Phase 0 |
| 3C: CAMS Ingester | 1 week | Low | Phase 0 |
| 4: Comparison Engine | 3-4 weeks | High | Phase 2 + Phase 3 |
| 5: UI App | 3-4 weeks | Medium (extended) | Phase 4 |
| 6: Validation Campaign | 4 weeks (was 3-4) | Medium-High | Phase 5 |
| 7: Manuscript | 4-6 weeks | High | Phase 6 |
| **Total to v1.0** | **6-7 months** (was 6) | **High** | All sequential except 2/3 parallel |

**Risk factors:**
- IMEO MARS API endpoints uncertainty
- SO₂ Python fit может потребовать tuning
- GEE quota constraints
- **Алтайский QA test может fail → Алтайский исключается, остаются 3 zones (acceptable, not blocker) (NEW в v1.1)**
- **Reference baseline temporal stability test может выявить TROPOMI calibration drift → требует investigation (NEW в v1.1)**

---

## 13. Critical path и blockers

### Critical path (extended в v1.1)
```
Phase 0 → Phase 1a (reference) → Phase 1b (regional) → Phase 1c (cross-check) →
Phase 2A (CH4 dual baseline) → Phase 4 → Phase 5 → Phase 6 → Phase 7
```

CH₄ detection с reference baseline — главный critical path. NO₂ и SO₂ параллельны.

### External blockers (out of our control)

- IMEO MARS API stability
- GEE platform availability
- TROPOMI L3 reprocessing
- СПДЗЗ review timeline

### Internal blockers (мы контролируем)

- Quality DevPrompts → quality of Claude Code output
- Validation rigour
- Documentation discipline
- **Reference zone polygon accuracy (NEW)** — wrong boundaries → wrong baseline. Mitigate через verification против oopt.info, mnr.gov.ru, ru.wikipedia.

---

## 14. Success metrics

### Quantitative

- v1.0 release к 2026-12 (target month 7 от 2026-04-26 baseline) — slightly slipped from v1.0 target (was month 6)
- Регистрация ≥ 1 high-confidence event в каждом regression test
- Synthetic recovery > 0.7 для amplitude ≥ 30 ppb CH₄
- Cross-source agreement > 30%
- < 5% false positives в wetland-only zones
- 100% Plume Events содержат config snapshot
- **Reference baseline temporal stability < 10 ppb year-to-year (NEW)**
- **Inside-zone false positive < 1% (NEW)**

### Qualitative

- Tool-paper accepted в СПДЗЗ
- Документация полна для independent reproduction
- **Reference baseline approach defensible перед reviewers (NEW)** — methodological contribution clear
- Configuration Presets cover practical use cases
- UI usable

### Failure modes (DNA §4.5)

- Cross-source agreement < 30% → STOP, revise
- > 50% candidates в wetland-only zones → STOP, revise
- Synthetic recovery < 0.5 → STOP, revise
- Reference catalog ingestion inconsistent → STOP, fix
- **Reference baseline и regional climatology systematically diverge > 50 ppb для clean regions (NEW)** → fundamental methodological problem, investigation required
- **All Reference Clean Zones показывают anomalous XCH4 patterns (NEW)** → may indicate TROPOMI subarctic retrieval issue

---

## 15. Версионирование Roadmap

| Версия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-04-25 | Первая версия. 7 phases, 6 months estimate. Critical path defined. |
| 1.1 | 2026-04-26 | Phase 0 expanded (P-00.1 dual scope). Phase 1 split в 1a/1b/1c. Phase 6 включает reference validations. Phase 7 manuscript структура с двумя novelty arguments. Effort estimate revised до 6-7 months. |
