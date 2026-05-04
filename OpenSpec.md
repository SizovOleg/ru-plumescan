# RU-PlumeScan — OpenSpec v1.0

**Версия:** 1.0  
**Дата создания:** 2026-04-25  
**Соответствие:** DNA v2.1, Algorithm v2.2, RNA v1.1

**Назначение документа:** журнал changes — proposed, applied, archived. Обеспечивает traceability «что изменилось когда и почему» для всех документов и компонентов проекта.

**Структура:** каждое изменение имеет ID, статус, дату, инициатора, обоснование, list документов которые меняются, и references на findings/sources которые мотивировали change.

**Различение change types:**
- **DNA mutation** — изменение инвариантов проекта (требует явного approval от человека, см. DNA §2.3)
- **Algorithm patch** — изменение в методологии (новый метод, изменение формулы, исправление алгоритма)
- **RNA patch** — изменение в стеке (новые defaults, новые dataset IDs, naming conventions)
- **Asset structure change** — изменение GEE Asset hierarchy (breaking для existing users)
- **Schema change** — изменение Common Plume Schema (breaking для всех ingesters и comparison runs)

---

## 0. Структура entries

Каждый change запись имеет формат:

```
### CHANGE-XXXX [STATUS] — Title
- Date proposed: YYYY-MM-DD
- Date applied: YYYY-MM-DD (или N/A)
- Initiator: <name/role>
- Type: DNA mutation | Algorithm patch | RNA patch | Asset change | Schema change
- Affected documents: <list>
- Affected code: <list of modules/files, если применимо>
- Reason: <короткое обоснование>
- Source: <reference to literature, GPT findings, lessons learned>
- Alternatives considered: <если применимо>
- Decision: <финальное решение>
- Verification: <как проверим что change работает>
```

Статусы:
- `PROPOSED` — предложено, не внедрено
- `APPLIED` — внедрено в актуальные документы/код
- `REJECTED` — рассмотрено и отклонено (с обоснованием)
- `ARCHIVED` — было APPLIED, но потом superseded более новым change
- `BLOCKED` — ожидает внешнего события (например, accumulation корпуса для v2 ML)

---

## 1. Applied changes

### CHANGE-0001 [APPLIED] — Полная переработка после V1 fail

- Date proposed: 2026-04-13
- Date applied: 2026-04-25
- Initiator: Researcher (после анализа V1 fail)
- Type: DNA mutation (v0.x → v2.0)
- Affected documents: DNA.md, всё новое (CLAUDE, Algorithm, RNA пишутся с нуля)
- Reason: V1 имел концептуальную ошибку — monthly composites + threshold 3.0 не детектируют plumes (transient events часы-сутки, median подавляет сигнал ~30×). Парадигма CAMS/UNEP IMEO MARS/Schuit/Lauvaux — каталог дискретных событий, не композиты.
- Source: domain_scouting.md разведка области, обзор methodology Schuit/Lauvaux/Beirle/Fioletov
- Alternatives considered:
  - A) Оставить composite approach с лучшими порогами — отвергнуто (концептуальная ошибка)
  - B) Полная переработка под per-orbit detection — выбрано
- Decision: Per-gas methodology. Three published methods (Schuit pre-ML для CH₄, Beirle divergence для NO₂, Fioletov rotation для SO₂). Object-level detection. Wind validation. ML deferred to v2.
- Verification: Algorithm v2.0 черновик в тех. записке пользователя 2026-04-25.

---

### CHANGE-0002 [APPLIED] — V2 баг-ревью и исправления

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT review V2 implementation
- Type: Algorithm patch (concrete bug fixes)
- Affected documents: Algorithm.md (черновик v2.0)
- Affected code: V2 implementation pre-mortem
- Reason: GPT-ревью V2 implementation выявил критические баги:
  - `unmask(0)` для CH4 даёт фон 0 ppb → ложные +1900 ppb anomalies
  - `ee.Kernel.circle().add(...).multiply(-1)` — несуществующий API
  - `w=0.7` константа = не shrinkage
  - `map(filterImage)` не передаёт gasKey
  - `bestEffort:true` меняет scale между регионами
  - Нет snow/ice mask для Сибири
  - Нет QA для NO2/SO2
- Source: GPT review log
- Decision: Все 7 багов исправлены в DNA §2.1 (запреты) и Algorithm §11 (implementation gotchas).
- Verification: Algorithm.md §11 содержит все 9 implementation patterns (added 2 more: edge handling, snow mask).

---

### CHANGE-0003 [APPLIED] — Configurable Detection Surface как главный объект

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: Researcher (после обсуждения цели tool-paper в СПДЗЗ)
- Type: DNA mutation (v2.0 → v2.1)
- Affected documents: DNA.md (§1.1, §1.2, §3.1, §3.2, §4.1)
- Reason: Цель проекта — не «найти все плюмы Западной Сибири», а **«получить настраиваемый детектор, который можно сравнивать с известными каталогами и адаптировать под свои задачи»**. Plume catalog — proxy, не самоцель. Это меняет акценты: Configurability + Reproducibility выходят на первый план.
- Source: пользовательское решение по итогам architectural review
- Alternatives considered:
  - A) Оставить «каталог как главный output» — отвергнуто как несоответствие реальной цели
  - B) Configurable Detection Surface с multiple outputs — выбрано
- Decision: Configurable Detection Surface = главная сущность. Catalog, Persistence Map, Time Series, Comparison Report — все equal-status outputs. Tool-paper в СПДЗЗ как target.
- Verification: DNA v2.1 §1.1 явно фиксирует Configurable Detection Surface; §3.1 добавляет приоритеты «Configurability > optimal defaults», «Output traceability > catalog completeness».

---

### CHANGE-0004 [APPLIED] — Reference Catalog Adapter (RCA) как first-class модуль

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: Researcher (после обсуждения validation workflow)
- Type: DNA mutation (v2.0 → v2.1) + Algorithm patch
- Affected documents: DNA.md (§1.2, §2.1, §3.1, §4.1, §4.2), Algorithm.md (§9), RNA.md (§5)
- Reason: Validation против известных каталогов = use case инструмента, не отдельная фаза. Нужен модуль для нативной загрузки datasets reference catalogs + automatic comparison.
- Source: пользовательское решение
- Alternatives considered:
  - A) Manual comparison «один раз для статьи» — отвергнуто (не воспроизводимо)
  - B) RCA как first-class модуль с Common Plume Schema — выбрано
- Decision: RCA + Comparison Engine разрабатываются параллельно с Detection Engine, не последовательно. Common Plume Schema унифицирует все каталоги (наш + reference).
- Verification: DNA v2.1 §1.2 содержит сущности Reference Catalog, Common Plume Schema, Comparison Run; §4.1 содержит трёхпараллельный development plan.

---

### CHANGE-0005 [APPLIED] — Forward-compatibility v1 → v2 ML через cross-source agreement labels

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: Claude (предложение по итогам RCA decision)
- Type: DNA enhancement (v2.0 → v2.1)
- Affected documents: DNA.md (§4.2)
- Reason: Cross-source agreement (наш v1 + 2+ reference catalogs detected event) даёт high-confidence labels автоматически, без необходимости manual review для всех 500+ events. Это удешевляет накопление корпуса для v2 ML.
- Source: пользовательское решение
- Decision: Каждое событие v1 catalog имеет slots для cross-source agreement (matched_schuit, matched_imeo, matched_cams, agreement_score). Эти поля заполняются Comparison Engine автоматически. v2 ML training labels = events с agreement_score ≥ 2.
- Verification: DNA v2.1 §4.2 явно описывает forward-compatibility schema.

---

### CHANGE-0006 [APPLIED] — Verification через GPT-5.5 на peer-reviewed источниках

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: Researcher (целевые technical questions для blocking review)
- Type: Algorithm patch (multiple) + RNA patch (multiple)
- Affected documents: Algorithm.md (v2.1 → v2.2), RNA.md (v1.0 → v1.1)
- Reason: После написания Algorithm v2.1 и RNA v1.0 — целевая verification 3 запросами к GPT-5.5: (1) точные формулы из Beirle/Fioletov/Schuit, (2) availability reference catalogs для ingestion, (3) методологические gaps (multi-gas matching, wind sources, bias corrections).
- Source: GPT-5.5 verification responses, конкретные секции peer-reviewed publications
- Decision: Применены 9 sub-changes (CHANGE-0007 через CHANGE-0015 ниже). Каждое имеет точное обоснование от peer-reviewed источника.
- Verification: Algorithm v2.2 §0 change log + RNA v1.1 changes section.

---

### CHANGE-0007 [APPLIED] — CH₄ framing rephrased: regional ≠ Schuit per-scene

- Date proposed: 2026-04-25
- Date applied: 2026-04-25 (в Algorithm v2.2)
- Initiator: GPT verification finding
- Type: Algorithm patch
- Affected documents: Algorithm.md §3.1
- Reason: Schuit 2023 использует **per-scene 32×32 normalization** для подготовки CNN input, а не climatology+annulus. Наш regional climatological approach — другая методология, не reproduction Schuit pre-ML stages.
- Source: GPT finding C1 — Schuit Section 2.2 background construction is per-scene, not climatology.
- Alternatives considered:
  - A) Переписать наш approach под per-scene normalization (как Schuit) — отвергнуто, теряется regional context для болот/снега Западной Сибири
  - B) Оставить наш approach с честным rephrasing — выбрано
- Decision: Algorithm §3.1 явно объясняет: «threshold-based detection adapted from Schuit pre-ML logic with regional climatological background». Подсекция «Что мы заимствуем у Schuit и что отличается». Цитирование в публикации образец предоставлен.
- Verification: Algorithm v2.2 §3.1 содержит framing section.

---

### CHANGE-0008 [APPLIED] — SO₂ full nonlinear fit primary + Fioletov simplified fallback

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification + Researcher decision
- Type: Algorithm patch
- Affected documents: Algorithm.md §5, RNA.md §7.1 (so2_specific)
- Reason: Fioletov 2020 использует упрощённый fit (`α/τ` с fixed σ ≈ 15 km, τ ≈ 6 h) **for production-scale efficiency** (тысячи источников globally). Для Западной Сибири у нас 5-10 SO₂ sources — можем себе позволить full nonlinear fit (3 параметра: A, σ_y, L).
- Source: GPT finding B1 — Fioletov 2020 explicit: «to reduce nonlinear-fit uncertainty, the 2020 paper fixes mean τ and σ, fitting only α».
- Decision: 
  - Primary method: full nonlinear fit (4 params: A, σ_y, L, B) через scipy.optimize в Python wrapper
  - Fallback: Fioletov simplified (1 param: α, fixed σ=15km, τ=6h) для quick screening или если full fit не сходится
  - Configurable via `so2_specific.fit_method`
- Verification: Algorithm v2.2 §5.6 (primary) + §5.8 (fallback) with code examples; RNA v1.1 §7.1 содержит `so2_specific.fit_method = "full_nonlinear"` default.

---

### CHANGE-0009 [APPLIED] — SO₂ fitting window auto-select по magnitude

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification
- Type: Algorithm patch + RNA patch
- Affected documents: Algorithm.md §5.4, RNA.md §7.1
- Reason: Fioletov 2020 использует разные fitting windows по magnitude: 30 km (<100 kt/yr), 50 km (100-1000 kt/yr), 90 km (>1000 kt/yr).
- Source: GPT finding B3.
- Decision: Configuration field `so2_specific.fitting_window_auto_select = true` (default). При true — auto-select по `source.estimated_kt_per_year`. При false — используется `fitting_window_km` value (default 50 km).
- Verification: Algorithm v2.2 §5.4 содержит auto-select логику; RNA v1.1 §7.1 default включает auto_select=true.

---

### CHANGE-0010 [APPLIED] — SO₂ detection limits explicitly declared

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification
- Type: Algorithm patch
- Affected documents: Algorithm.md §5.10, §13.1
- Reason: Fioletov 2020 явно reports limits: >1000 kt/yr reliable, 100-1000 kt/yr moderate (criterion >5σ), 50-100 kt/yr marginal, <50 kt/yr below reliable. Для Кузбасс ТЭЦ (~100 kt/yr) — на границе reliable detection.
- Source: GPT finding B3.
- Decision: Algorithm §5.10 содержит таблицу detection limits с reliability tiers. Известное ограничение declared в §13.1 honest_limitations.
- Verification: Algorithm v2.2 §5.10 содержит таблицу.

---

### CHANGE-0011 [APPLIED] — IME U_eff defaults обновлены на Schuit 2023 TROPOMI calibration

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding
- Type: Algorithm patch + RNA patch
- Affected documents: Algorithm.md §6.4, RNA.md §7.1 (ime section)
- Reason: Я использовал в v2.1 Varon 2018 GHGSat values `a=0.33, b=0.45`. Это калибровка для GHGSat 50m. Schuit 2023 публикует **TROPOMI-specific calibration**: `U_eff = 0.59·U10 + 0.00` (r²=0.77) или `U_eff = 0.47·U_PBL + 0.31` (r²=0.78). Schuit values корректнее для TROPOMI 7km plumes.
- Source: GPT finding C4 — Schuit 2023 §2.5.1 explicit U_eff calibrations.
- Decision: 
  - Default: `u_eff_method = "schuit2023_10m"`, `a = 0.59`, `b = 0.00`
  - Configurable: `"schuit2023_pbl"` (a=0.47, b=0.31), `"varon2018_ghgsat"` (legacy)
  - Future: `"regional_calibrated"` для v2 после калибровки на Западную Сибирь (см. CHANGE-0017)
- Verification: Algorithm v2.2 §6.4 и RNA v1.1 §7.1.

---

### CHANGE-0012 [APPLIED] — Lauvaux 2022 заменён на UNEP IMEO MARS

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding
- Type: Algorithm patch + RNA patch + Asset structure change
- Affected documents: Algorithm.md §9, RNA.md §3.1, §5.3, §7.3 (preset names)
- Affected code: `src/py/rca/ingesters/imeo_mars.py` (replaces lauvaux2022.py)
- Reason: Lauvaux et al. 2022 **per-event catalog не доступен публично**. Только PDF supplement без machine-readable CSV. Kayrros API коммерческий. Замена на UNEP IMEO MARS — открытый, CC-BY-NC-SA, CSV/GeoJSON, более богатые поля (persistency, sector, notified status).
- Source: GPT finding R2-A.
- Alternatives considered:
  - A) Contact authors Lauvaux 2022 для CSV — оставлено как future extension, не блокер
  - B) IMEO MARS как primary replacement — выбрано
- Decision: 
  - Primary CH₄ reference: UNEP IMEO MARS (monthly snapshots)
  - Secondary: Schuit 2023 (статичный 2021 catalog)
  - Tertiary: CAMS Hotspot Explorer (weekly, since 2024-05)
  - Lauvaux 2022 — extension если получим CSV от authors
- Verification: 
  - Algorithm v2.2 §9.1 содержит IMEO MARS как primary, Lauvaux в extensions
  - RNA v1.1 §5.3 содержит ImeoMarsIngester implementation
  - Preset `lauvaux_eq` переименован в `imeo_eq` во всех документах

---

### CHANGE-0013 [APPLIED] — Single ERA5 wind как declared limitation

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding
- Type: Algorithm patch (clarification)
- Affected documents: Algorithm.md §3.9, §4.5, §5.5, §13.1
- Reason: Schuit 2023 и CAMS Hotspot Explorer используют **ensemble ERA5 + GEOS-FP 10m + GEOS-FP PBL**, усредняя три quantifications. GEOS-FP в GEE недоступен → мы используем только ERA5. Это не reproduction error, это explicit limitation.
- Source: GPT finding R3-Q2 — peer-reviewed practice usually uses ensemble.
- Decision: Honest declared в §13.1 honest_limitations. Декларация в публикации образец предоставлен.
- Verification: Algorithm v2.2 §13.1 содержит declaration.

---

### CHANGE-0014 [APPLIED] — ERA5-Land → ERA5 (full reanalysis)

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding
- Type: RNA patch
- Affected documents: RNA.md §7.1 (default preset wind.source)
- Reason: ERA5-Land — это land-surface replay forced by ERA5, не full reanalysis. Для plume direction attribution **не эквивалентна** ERA5. ERA5 имеет 137 vertical levels up to 80 km, 31 km grid; ERA5-Land — 11 km surface only. Для plume direction (upper-air relevance) ERA5 предпочтительнее, несмотря на более грубый grid.
- Source: GPT finding R3-Q2.
- Decision: Default `wind.source = "ECMWF/ERA5/HOURLY"` (был ERA5_LAND). При sampling — `scale: 31000` (ERA5 native) вместо 11000 (ERA5-Land).
- Verification: RNA v1.1 §7.1 содержит обновлённый default.

---

### CHANGE-0015 [APPLIED] — Multi-gas matching framed как novel component

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding (positive — это actually advantage)
- Type: Algorithm patch (framing only)
- Affected documents: Algorithm.md §7.1
- Reason: Peer-reviewed protocol для CH₄+NO₂/SO₂ event matching на TROPOMI **не существует**. Closest paper Ialongo 2021 — joint analysis, не event-by-event matching. Schuit/CAMS используют bottom-up inventories для source-type attribution, не gas-event matching.
- Source: GPT finding R3-Q1.
- Decision: Multi-gas matching layer — **novel methodological component**. Это advantage для tool-paper в СПДЗЗ. Framing для публикации образец предоставлен в Algorithm §7.1.
- Verification: Algorithm v2.2 §7.1 содержит «novel component» framing.

---

### CHANGE-0016 [APPLIED] — Bibliographic correction Beirle 2019/2021

- Date proposed: 2026-04-25
- Date applied: 2026-04-25
- Initiator: GPT verification finding
- Type: Algorithm patch (bibliographic)
- Affected documents: Algorithm.md §0 (sources), §4.1, RNA.md §10.3
- Reason: Я ошибочно атрибутировал NO₂ divergence method Beirle 2021 ACP. На самом деле метод опубликован в **Beirle et al. 2019, Sci. Adv., doi:10.1126/sciadv.aax9800**. **Beirle et al. 2021** — это **ESSD** (Earth System Science Data, doi:10.5194/essd-13-2995-2021), TROPOMI NOx point source catalog, modifies method (divergence-only без τ для strong sources, pixel-wise L).
- Source: GPT finding R1-A intro.
- Decision: Bibliographic correction в Algorithm v2.2 §0 (sources list) + §4 references. Beirle 2019 = method, Beirle 2021 ESSD = catalog.
- Verification: Algorithm v2.2 §4.1 corrected references.

---

### CHANGE-0017 [APPLIED] — Reference Clean Zone и dual baseline approach

- Date proposed: 2026-04-26
- Date applied: 2026-04-26
- Initiator: Researcher (методологическое улучшение)
- Type: DNA mutation (v2.1 → v2.2) + major Algorithm change + RNA change + Roadmap change + DevPrompt rework
- Affected documents: 
  - DNA.md (v2.1 → v2.2): §1.2, §1.4, §1.5, §2.1, §2.3, §3.1, §3.2, §3.3, §4.1, §4.2, §4.4, §4.5
  - Algorithm.md (v2.2 → v2.3): §3.4 fully rewritten, §3.5 extended, §13.1 wetland_CH4 limitation removed
  - RNA.md (v1.1 → v1.2): §3.1 Asset structure extended, §7.1 default preset extended, §11 reference baseline build module
  - Roadmap.md (v1.0 → v1.1): Phase 0 deliverables expanded, Phase 1 split into 1a (reference) + 1b (regional) + 1c (cross-check)
  - DevPrompts/P-00.1 fully rewritten (industrial proxy + protected areas reference mask combined)
- Affected code: 
  - `src/py/setup/build_protected_areas_mask.py` (NEW)
  - `src/py/setup/build_industrial_proxy.py` (existing P-00.1)
  - `src/js/modules/background.js` major rework (Algorithm §3.4 changes)
  - New module `src/js/modules/reference_baseline.js`
- Reason: Methodological improvement. Industrial buffer exclusion (negative space approach) имеет fundamental weakness — определяет clean as `NOT(known industrial)`, что включает unknown unknowns: undocumented compressor stations, missed flares, transient venting events. Persistent emissions от sources вне нашего inventory становятся частью «фона» → Z-score над ними занижается → false negatives для real plumes.

  Positive space approach через Reference Clean Zones (federal protected nature reserves where industrial activity is **prohibited by law**) даёт enforceable clean baseline. Российские заповедники имеют статус «строгой охраны» (IUCN category Ia) — никакая industrial activity внутри границ невозможна без federal-level violation.
  
  Identified primary reference zones для Западной Сибири:
  - **Юганский заповедник** (60.5°N, 74.5°E, 6500 км²) — middle taiga + Vasyugan wetlands, ХМАО — primary wetland baseline
  - **Верхнетазовский заповедник** (63.5°N, 84.0°E, 6313 км²) — northern taiga, permafrost, ЯНАО
  - **Кузнецкий Алатау заповедник** (54.5°N, 88.0°E, 4019 км²) — mountain taiga, Кемеровская область — Кузбасс reference
  - **Алтайский заповедник** (51.5°N, 88.5°E, 8810 км², optional) — high-mountain, Republic of Altai — pending QA test (column XCH4 в горах может быть unreliable)
  
  Total useable clean reference area: 16,832 км² primary (3 zones), плюс 8,810 км² optional Алтайский, в trzy-четырёх климатических зонах.
- Source: Researcher proposal during P-00.1 planning phase. Domain knowledge о российских заповедниках и их protected status. Web verification координат и площадей через ru.wikipedia.org, минприроды.рф, oopt.info.
- Alternatives considered:
  - **A. Continue with industrial buffer exclusion only** — отвергнуто. Negative space approach имеет fundamental unknown unknowns problem. 
  - **B. Replace industrial buffer entirely with reference baseline** — отвергнуто. Industrial buffer всё ещё useful для regional climatology (broader spatial coverage). 
  - **C. Dual baseline (выбран)** — reference baseline (primary, anchored) + regional climatology с industrial buffer (secondary, broader coverage) с cross-check между ними как QA mechanism. Если diverge → contamination suspect.
- Decision: 
  - Reference Clean Zone становится first-class entity в DNA §1.2
  - Reference Baseline Builder становится четвёртым параллельным модулем v0.5 implementation phase (наряду с Detection Engine, RCA, Comparison Engine)
  - Dual baseline approach обязателен (DNA §2.1 запрет на single-source baseline когда reference zones доступны)
  - Алтайский включается с QA test gate — если column XCH4 значимо diverge от Кузнецкий Алатау после seasonal correction (>30 ppb residual), помечается `unreliable_for_xch4_baseline`, не используется в production
  - Internal buffer per zone: Юганский 10 km (близость к oil&gas), Верхнетазовский 5 km, Кузнецкий Алатау 5 km, Алтайский 5 km
  - Latitude band stratification: Юганский → 58-65°N, Верхнетазовский → 62-68°N, Кузнецкий Алатау → 53-57°N, Алтайский → 51-54°N. Каждый pixel в AOI берёт baseline от ближайшего по широте reference zone
  - Reference Baseline Asset публикуется как **standalone scientific artifact** (CC-BY 4.0 на Zenodo)
- Verification:
  - DNA v2.2 §1.2 содержит Reference Clean Zone определение
  - DNA v2.2 §1.5 содержит «Positive baseline ≠ Negative buffer exclusion» distinction
  - DNA v2.2 §3.1 содержит приоритет «Positive baseline definition > negative buffer exclusion» (rank 5)
  - DNA v2.2 §2.1 содержит запрет на single-source baseline когда reference zones доступны
  - Algorithm v2.3 §3.4 переписан с reference-anchored approach
  - RNA v1.2 содержит protected_areas Asset structure + baseline build module
  - DevPrompt P-00.1 переписан с dual scope (industrial + reference)
- Tool-paper impact: добавляется второй novelty argument — «reference-anchored baseline approach» в дополнение к multi-gas matching. Это методологический contribution, который reviewer'ы СПДЗЗ оценят.

---

## 2. Proposed changes (not yet applied)

(Currently empty. New proposals будут добавляться сюда перед approval.)

---

## 3. Blocked changes (awaiting external events)

### CHANGE-B001 [BLOCKED] — v2 ML classifier activation

- Date proposed: 2026-04-25
- Status: BLOCKED awaiting corpus accumulation
- Initiator: DNA §4.1 plan
- Type: Major Algorithm extension
- Affected documents: Algorithm.md (новый §15+), DNA.md §4.1
- Reason: ML phase v2 требует accumulated corpus.
- Activation conditions (per DNA §4.1):
  - ≥ 500 events Западной Сибири с cross-source agreement labels
  - Минимум 4 классов размечены
  - Inter-rater agreement Cohen's kappa > 0.7 (если manual labeling)
  - Documented temporal train/test split
- Expected timeline: 2027+ после v1 release и regular Comparison Runs
- Verification: triggered automatically когда corpus criteria met.

---

### CHANGE-B002 [BLOCKED] — Regional U_eff calibration для Западной Сибири

- Date proposed: 2026-04-25
- Status: BLOCKED awaiting validation events
- Initiator: CHANGE-0011 future enhancement
- Type: Algorithm patch
- Affected documents: Algorithm.md §6.4 (future calibration), RNA.md §7.1
- Reason: Schuit 2023 calibration `U_eff = 0.59·U10` — global TROPOMI fit. Для subarctic continental conditions (низкая турбулентность зимой, frequent inversions, болотные конвективные слои летом) локальные коэффициенты могут отличаться значительно.
- Activation conditions:
  - ≥ 50 high-confidence CH4 events с matched Schuit/IMEO catalog quantifications (для regression)
  - Validation events Кузбасс/Норильск/Бованенково с independent estimates
- Expected output: regional `(a, b)` коэффициенты + uncertainty
- Potential publication contribution: «Calibrated effective wind speed parametrization for TROPOMI methane plume quantification over subarctic continental conditions»
- Verification: regression `Q_observed` против independent estimates → новый preset `regional_calibrated`.

---

### CHANGE-B003 [BLOCKED] — Lauvaux 2022 ingester (если получим CSV от authors)

- Date proposed: 2026-04-25
- Status: BLOCKED awaiting external response
- Initiator: CHANGE-0012 alternative
- Type: RCA extension
- Affected documents: RNA.md §5 (new ingester), Algorithm.md §9.2
- Reason: Lauvaux 2022 catalog богат historical data 2019-2020. Мы заменили его на IMEO MARS (CHANGE-0012), но если authors поделятся CSV — добавим как дополнительный reference.
- Activation conditions:
  - Email contact с Lauvaux team / Kayrros
  - Получение per-event CSV с открытой лицензией
- Verification: создание `Lauvaux2022Ingester`, comparison Run vs наш default.

---

### CHANGE-B004 [BLOCKED] — Pixel-wise L (NOx/NO2 ratio) per Beirle 2021 ESSD

- Date proposed: 2026-04-25
- Status: BLOCKED — low priority, future enhancement
- Initiator: GPT finding R1-A3
- Type: Algorithm patch
- Affected documents: Algorithm.md §4.9, RNA.md §7.1
- Reason: Beirle 2021 ESSD calculates L per pixel from photostationary steady state (mean global L=1.35 with regional variation: Riyadh 1.22, Germany 1.41). Pixel-wise L даёт более accurate emission estimates чем constant L=1.32.
- Activation conditions: после v1.0 release, при наличии validation evidence что constant L занижает accuracy
- Verification: side-by-side comparison constant vs pixel-wise L results.

---

### CHANGE-B005 [BLOCKED] — High-resolution Sentinel-2 follow-up для confirmed CH4 events

- Date proposed: 2026-04-25
- Status: BLOCKED — v3 phase per DNA §4.1
- Initiator: DNA §4.1 v3 directions
- Type: Major extension
- Affected documents: DNA.md (v3 mutation needed), Algorithm.md (new module)
- Reason: TROPOMI 7km plumes — coarse. Sentinel-2 / PRISMA / EnMAP позволяют high-res confirmation для plume source localization (per Irakulis-Loitxate et al. 2021).
- Activation conditions: v2 ML stable, активные user requests, отдельная DNA mutation
- Verification: TBD при activation.

---

### CHANGE-B006 [BLOCKED] — Variable τ для NO₂ через ERA5 boundary_layer_height

- Date proposed: 2026-04-25
- Status: BLOCKED — refinement, not blocker
- Type: Algorithm refinement
- Affected documents: Algorithm.md §4.9
- Reason: NO₂ lifetime в boundary layer зависит от mixing height. ERA5 содержит `boundary_layer_height` band. Variable τ улучшит accuracy для seasonal variations (летний BL ~ 1500m vs зимний ~ 200m в Сибири).
- Activation conditions: после baseline v1.0 release с constant τ=4h.
- Verification: comparison constant vs variable τ.

---

## 4. Rejected changes

(Currently empty. Future rejected proposals будут логироваться здесь с обоснованием отклонения.)

---

## 4a. Minor clarifications (sub-implementation refinements, не CHANGE)

Не требуют formal CHANGE entry — это operational refinements в рамках
existing architectural decisions. Документируются здесь для traceability.

### MC-2026-04-27-A — Юганский useable-area escalation gate revised

- Date: 2026-04-27
- Initiator: Researcher (P-00.1 closure review)
- Type: sub-implementation clarification (не Algorithm patch, не RNA patch)
- Affected document: `data/protected_areas/README.md` (added section "Юганский: useable area & escalation gate")
- Reason: При P-00.1 ingestion обнаружено что Юганский useable area после
  10 km internal buffer = 2946 km² ≈ 60 TROPOMI pixels at 7 km grid. Initial
  concern: per-pixel threshold ≥100 obs/pixel-month рискованный.
- Clarification: Reference Baseline construction (Algorithm v2.3 §3.4.0)
  использует **zone-aggregate** approach (single value per month per zone),
  не per-pixel. Total obs contributing ≈ 60 px × 30 obs × 6 years ≈ 10,800/month.
  Revised escalation gate: minimum **1000 zone-aggregate obs per month per zone**.
- Decision:
  - Internal_buffer 10 km для Юганского — KEEP (защита от Самотлор/Salym advection критична).
  - Per-pixel threshold ≥100 obs/pixel-month сохраняется как secondary check
    для regional climatology (Algorithm §3.4.1).
  - Zone-aggregate threshold ≥1000 obs/month — primary gate для reference baseline.
- Verification: P-01.0a `validate_zone_baseline_observations()` проверит
  на real data, escalate если any zone fails.

### MC-2026-04-27-B — VIIRS proxy quantitative analysis deferred

- Date: 2026-04-27
- Initiator: Researcher (P-00.1 closure review)
- Type: TODO scheduling (post-merge, not blocker)
- Affected document: `docs/KNOWN_TODOS.md` (TD-0001 entry created)
- Reason: 474 VIIRS / 39 manual+GPPD = 12:1 ratio. Visual sanity passed
  (clusters in expected oil&gas regions, sparse в clean taiga). Quantitative
  refinement (full histogram, clustering metrics, false positive analysis)
  отложен до Phase 2A когда detection runs покажут real false positive rate.
- Trigger: revisit if false positive rate в clean regions > 5% по Phase 2A.
- Decision: not blocker for P-00.1 merge; tracked в `docs/KNOWN_TODOS.md`.

### MC-2026-04-27-C — Алтайский +4.5% area diagnostic note

- Date: 2026-04-27
- Initiator: Researcher (P-00.1 closure review)
- Type: diagnostic information for P-01.0a Алтайский QA test
- Affected document: `data/protected_areas/README.md` (added subsection
  "Алтайский +4.5% diagnostic note")
- Reason: Алтайский measured 8411 vs documented 8810 km² (+4.5%) — внутри
  R2 tolerance, но для `optional_pending_quality` zone это diagnostic signal,
  не just acceptable mismatch.
- Possible causes documented: boundary expansion 1980s-2010s, polygon
  simplification (Nominatim), Телецкое озеро аква inclusion/exclusion (water
  surface dramatically different TROPOMI XCH₄ signature).
- Trigger: P-01.0a Алтайский QA test (Algorithm §11.4) либо pass (включить
  без re-clipping) либо fail (investigate root cause, possibly TD-0004
  full-resolution polygon download).

### MC-2026-04-28-A — Algorithm §11.5 sanity expectations corrected against empirical data

- Date: 2026-04-28
- Initiator: Researcher (P-01.0a Yugansky validation review)
- Type: Algorithm sanity-check refinement (sub-implementation, не CHANGE)
- Affected document: `Algorithm.md` §3.4.0 «Sanity checks для Reference Baseline»
- Reason: Initial expectations (Yugansky July 1900-1950 ppb, amplitude
  30-80 ppb) were unverified projections from in-situ surface CH4 flux
  to TROPOMI column observations. Direct empirical validation against
  Sizov et al. in prep (Western Siberia methane wetland monitoring,
  7-year TROPOMI L3 climatology 2019-2025) showed:
  - Article wetland zone-mean July: 1854 ppb (not 1900-1950)
  - Article peak month: September (not July)
  - Article seasonal amplitude: ~15-25 ppb (not 30-80)
  - Annual trend: +9 ppb/year (matches global atmospheric CH4 increase)
- Empirical validation:
  - Yugansky measurements (concentrated wetland >70% useable area):
    Jul 1880, Sep 1887, Oct 1892 — 20-30 ppb HIGHER than article zone-mean
  - Difference explained by wetland fraction: Yugansky useable area
    ~70% wetland (Vasyugan bog interior after 10 km buffer trims taiga
    edges), article zone-4 only 28.5% wetland (rest forest at ~1849 ppb
    dilutes zone-mean)
- Decision:
  - Algorithm §3.4.0 sanity checks updated с revised ranges
  - Yugansky validation status: **PASSED** против revised expectations
  - Architecture working correctly — concentrated wetland baseline есть
    exactly engineered behaviour
  - Original expectations preserved в OpenSpec для historical context
    (column XCH4 ≠ surface flux scaling lesson learned)
- Verification: docs/p-01.0a_validation_report.md содержит side-by-side
  table наш vs article values + interpretation.
- Note: Это НЕ исправление архитектурного решения. Это коррекция
  expected sanity ranges, которая validates что dual baseline approach
  работает как designed.

### MC-2026-04-28-B — GEE memory limit mitigation (P-01.0a Phase A)

- Date: 2026-04-28
- Initiator: Claude (P-01.0a Phase A diagnostics encountered failures)
- Type: Implementation refinement (operational)
- Affected code: `src/py/setup/build_reference_baseline_ch4.py` (added
  `time.sleep(60)` between monthly compute calls)
- Reason: 4 of 12 monthly `getInfo()` calls failed с
  `User memory limit exceeded` в **deterministic** pattern M02/M05/M08/M11
  (Q-mid months — every 3rd month начиная с February). Initially suspected
  cumulative user-quota throttling.
- **Updated 2026-04-28 (после re-run):** sleep(60) **НЕ помог** — те же 4
  months failed. Pattern deterministic, не throttle:
  - Working months (M01, M03, M04, M06, M07, M09, M10, M12) — все имеют
    edge effects в `calendarRange(target_month-1, target_month+1, 'month')`
    (months 0, 13 partial filter → smaller dataset → fits memory)
  - Failing months (M02, M05, M08, M11) — Q-mid centred 3-month windows
    с full 3-month data → stack of `~6 years × 30 daily images = ~540` images
    triggers reduce memory limit
- Mitigation: 8/12 months sufficient для Yugansky validation (peak Oct,
  trough Apr — both в "working" list). Phase B Export через batch task
  (server-side, не interactive) обходит client memory limit.
- Future fix (deferred to TD-0008 в KNOWN_TODOS, **priority HIGH** после
  P-01.0a confirms deterministic pattern): refactor `compute_seasonal_mean`
  на per-month-per-year compute с aggregation в Python вместо single ee
  reducer over 540 images. Это уменьшит peak server-memory ~30×.
- Verification: 8/12 monthly diagnostics complete с pacing OR без — same
  4 months fail. Phase B Export batch task TBD (FAIL on first attempt с
  null-constant error — fixed via valid-zones filter + `--phase-b-only` flag).

### MC-2026-05-03-M — TD-0024 provenance hardening (P-01.0c)

- Date: 2026-05-03
- Trigger: TD-0024 audit findings post-Phase 1b closure (PR #3, commit `9d4d9bd`).
- Type: Sub-implementation hardening (process improvement, не methodology change).
- Affected documents:
  - `Algorithm.md` §2.4.1 NEW — canonical provenance pattern documentation
  - `RNA.md` §9.1 NEW — required helpers + frozen dataclass invariant
  - `KNOWN_TODOS.md` — TD-0024 status RESOLVED
- Affected code:
  - `src/py/rca/provenance.py` — upgraded к immutable `Provenance` dataclass (frozen=True), `compute_provenance` returns it instead of dict, new `write_provenance_log(prov, status, ...)`, `canonical_serialize` made explicit single source of truth, `write_run_log` legacy API kept с DeprecationWarning
  - `src/py/setup/backfill_provenance.py` — NEW one-shot backfill script с per-asset reconstructed canonical config + honest backfill caveat fields
  - `src/py/setup/closeout_phase_1b.py` — updated к new write_provenance_log API
  - `src/py/tests/test_provenance.py` — NEW 16 tests (frozen invariant, hash determinism, dict-order-independence, run_id format, etc.)
  - `tools/audit_provenance_consistency.py` — NEW audit tool с two modes:
    - default: GEE asset checks (provenance fields + log hash equality)
    - `--no-gee`: schema-only audit для CI без credentials
  - `tools/provenance_audit_allowlist.json` — NEW allowlist mechanism для phased remediation; emptied after backfill done в same PR
  - `.github/workflows/audit.yml` — NEW CI workflow runs `--no-gee` audit on PR/push; full GEE audit gated on `workflow_dispatch` + `GEE_SERVICE_ACCOUNT_KEY` secret (escalation: secret not yet configured, see workflow header).
- Backfill outcomes (см. `docs/p-01.0c_backfill_report.json`):

  | Asset | Pre-backfill | Reconstructed canonical | Status |
  |---|---|---|---|
  | reference_CH4_2019_2025_v1 | (no params_hash) | `06f3bb6d...` | BACKFILLED + VERIFIED + logged |
  | regional_CH4_2019_2025 | `c8b6e97f...` | `c9e7d747...` | BACKFILLED + VERIFIED + logged |
  | regional_NO2_2019_2025 | `7c2f8b2b...` | `646b4e97...` | BACKFILLED + VERIFIED + logged |
  | regional_SO2_2019_2025 | `f669e1c8...` | `71f18f76...` | BACKFILLED + VERIFIED + logged |

- **NO₂ canonical reconstruction — unexpected stronger outcome (NOT mere deviation):**  
  DevPrompt classified NO₂ as «already OK, verify only» based on internally consistent runtime hash `7c2f8b2b` (STARTED=SUCCEEDED=asset). Dry-run reconstruction from `build_regional_climatology.py` source code state produced **different** canonical hash `646b4e97`. **This means**:
  - **All 4 baseline assets used non-canonical configs** (4 different Runs, 4 different config-dict assemblies). Asset/log internal consistency was NOT canonical correctness.
  - **Two separate code paths computed configs independently** для same Run: `build_regional_climatology.py` (runtime build, set partial metadata via `combined.set({...})`) и `closeout_phase_1b.py` (closure script computed hash from re-assembled config + `setAssetProperties` post-hoc).
  - The audit categorization of NO₂ as «OK» только caught log-asset internal consistency; не caught the deeper canonical-vs-runtime divergence.
  - Backfill standardized all 4 к canonical schema reconstructed from build script source. **Stronger outcome than DevPrompt scope anticipated** — full canonical alignment, not just compliance restoration.
  - Original runtime hashes preserved as `pre_backfill_params_hash` для forensic audit.
  - **Implication для Phase 2A:** TD-0025 NEW filed — `compute_provenance` MUST integrate directly into build scripts, no separate closure-script hash computation. Detection events need build-script-native provenance.
- **Honest reconstruction caveat** на каждом backfilled asset (`provenance_backfill_caveat` field):
  > "Reconstructed canonical config from build script source code at commit `<sha>` + RNA v1.2 defaults + algorithm_version 2.3 parameters. params_hash recomputed via centralized compute_provenance helper. KNOWN UNCERTAINTY: runtime config may have included parameters не captured в reconstruction. Original log entries preserved в logs/runs.jsonl. For bit-identical reproduction, refer к commit SHA + RNA version, не just params_hash."
- Audit gate enforcement: `python tools/audit_provenance_consistency.py` PASSED post-backfill (4/4 OK, allowlist empty). `--no-gee` mode also PASSED (allowlist + log schema valid).
- TD-0024 status: **RESOLVED 2026-05-03** (cumulative — backfill done, prevention pattern enforced via frozen dataclass + audit CI gate).
- TD-0024 escalation outstanding: full GEE audit в CI requires `GEE_SERVICE_ACCOUNT_KEY` secret. Per researcher escalation directive — не assumed, deferred к user setup. Local audit run остаётся primary gate until secret configured.

### MC-2026-04-30-J — NO₂ regional climatology completion (Phase 1b)

- Date: 2026-04-30
- Type: Phase 1b deliverable closure
- Affected: `RuPlumeScan/baselines/regional_NO2_2019_2025` (live)
- Outcome: **A — FULL SUCCESS, 12/12 monthly tasks SUCCEEDED, Option C verified**
- Run: `default_2019_2025_7c2f8b2b` (params_hash matches STARTED → SUCCEEDED →
  asset metadata)
- Pipeline: multi-band-select `[tropospheric_NO2_column_number_density,
  cloud_fraction]` → `cloud_fraction < 0.3` filter → reduce. Mask:
  `proxy_mask_buffered_30km` (prebuilt, ~1.5 h saved).
- Sanity validation:
  - Norilsk Nadezhdinsky (industrial): masked ✓
  - Tom-Usinsk GRES (Kuzbass post-fix mask test): masked ✓
  - Tyumen / Surgut / Novokuznetsk (cities with collocated TPPs):
    masked via 30 km buffer of nearby industrial proxy points ✓
  - Clean Yamal vacuum (71°N, 73°E) M07 = 6.4×10⁻⁶ mol/m² < 5×10⁻⁵ threshold ✓
- Asset metadata: 30 properties, full provenance triple, kuzbass_gap_caveat,
  qa_filter_caveat, cities_collocated_caveat, phase_1b_closure_date.

### MC-2026-04-30-K — SO₂ regional climatology completion (Phase 1b)

- Date: 2026-04-30
- Type: Phase 1b deliverable closure
- Affected: `RuPlumeScan/baselines/regional_SO2_2019_2025` (live)
- Outcome: **A — FULL SUCCESS, 12/12 monthly tasks SUCCEEDED**
- Run: `default_2019_2025_f669e1c8` (canonical config). Note: SO₂ STARTED
  log entry used `40f04025` hash (slightly different config dict at submission
  time) — process improvement filed; final asset uses canonical hash.
  DNA §2.1 запрет 12 satisfied (full provenance triple на final asset).
- Pipeline: same multi-band-select pattern + negative_floor = -0.001 mol/m²
  applied per DNA §2.1 запрет 7.
- Sanity validation:
  - Norilsk Nadezhdinsky (largest SO₂ source globally): masked ✓
  - Norilsk Medny: masked ✓
  - Clean Yamal vacuum M07 = 7.4×10⁻⁵ mol/m² (within [-1×10⁻³, 1×10⁻⁴] target) ✓
  - Mid-Yamal east clean M07 = 4.5×10⁻⁵ mol/m² ✓
  - Negative floor verification: `min(median_M01..M12) = -9.999×10⁻⁴ mol/m²`
    (≥ -0.001 floor target) ✓
- Asset metadata: 30 properties, full provenance, all closure caveats.

### MC-2026-04-30-L — TD-0008 Option C cumulative verification (3 gases)

- Date: 2026-04-30
- Type: Cross-gas hypothesis confirmation
- Affected document: `KNOWN_TODOS.md` (TD-0008 RESOLVED final)
- Reason: TD-0008 (Q-mid M02/M05/M08/M11 single-iteration memory limit
  pattern) hypothesis tested across all 3 gases в Phase 1b:
  - CH₄ (P-01.0b 2026-04-29): 12/12 SUCCEEDED including Q-mid
  - NO₂ (2026-04-30): 12/12 SUCCEEDED including Q-mid
  - SO₂ (2026-04-30): 12/12 SUCCEEDED including Q-mid
- Verdict: **Option C (12 separate batch tasks per gas) bypasses cumulative
  graph memory limit reliably.** Hypothesis empirically confirmed across
  3 different gas pipelines + 3 different month sets. TD-0008 RESOLVED with
  high confidence. Pattern documented в `build_regional_climatology.py`
  orchestrator для future regional baseline rebuilds.
- Phase 1b status: **CLOSED.** Phase 1c (dual baseline cross-check
  validation) ready: combines existing reference + regional CH₄ assets,
  no new compute.

### MC-2026-04-29-D — CLAIM 5 QA filter ordering bug remediation (P-01.0b)

- Date: 2026-04-29
- Initiator: Researcher (independent CR review)
- Type: Code refactor + caveat documentation
- Affected code: `src/py/setup/build_regional_climatology.py`,
  `src/js/modules/regional_climatology.js`
- Reason: Pipeline вызывает `.select(target_band)` BEFORE QA filter →
  cloud_fraction band lost → cloud filter never applied. Diagnostic test
  confirmed: NO₂ L3 имеет `cloud_fraction` band before .select(), но
  отсутствует after. Same SO₂.
- Severity (gas-specific):
  - **CH₄: functionally inert.** L3 v02.04 OFFL upstream-filtered
    (Lorente 2021); only `physical_range` (1700-2200 ppb) configured,
    targets target band which IS available after select. CH₄ regional
    baseline scientifically valid.
  - **NO₂: ACTIVE.** cloud_fraction filter (cf<0.3) skipped → cloudy
    pixels included в baseline → contaminated.
  - **SO₂: ACTIVE.** Same.
  - **P-01.0a Reference Baseline: NOT affected.** Different code path —
    `build_reference_baseline_ch4.py` doesn't call `apply_qa_filter`.
- Decision:
  - CH₄ regional Asset KEPT (built на pre-fix code; bug inert).
    Asset metadata `qa_filter_caveat` documents architectural bug + why
    inert для CH₄.
  - Pipeline FIXED для NO₂/SO₂: multi-band select pattern. Per-gas
    `qa_bands` list explicitly enumerates auxiliary bands needed для
    filter. Drop QA after filter via final `.select([target_band])`.
- Verification: NO₂/SO₂ runs (deferred) will use fixed pipeline; pre-flight
  test через bandNames() print check.

### MC-2026-04-29-E — CLAIM 2 Altaisky local source-of-truth conflict fix

- Date: 2026-04-29
- Type: Data correction (3 stale files)
- Affected files:
  - `data/protected_areas/metadata.json` (Altaisky quality_status)
  - `data/protected_areas/altaisky.geojson` (Feature properties)
  - `src/py/setup/build_protected_areas_mask.py` ZONE_METADATA dict line 123
- Reason: Algorithm v2.3 §11.4 QA test FAIL 2026-04-28 set Altaisky
  status="unreliable_for_xch4_baseline" в GEE Asset, но 3 local sources
  оставались с initial "optional_pending_quality". Re-upload через
  `build_protected_areas_mask.py` would have reverted Asset to stale value.
- Decision: All 3 sources updated to "unreliable_for_xch4_baseline".
  Each source now includes `quality_status_history` entry pair documenting
  initial state + QA result + reasoning (winter abs_diff +34.86 ppb,
  cycle_diff +14.25 ppb, high-altitude biome above winter PBL).
- Verification: live Asset = unreliable_for_xch4_baseline ✓; all 3 local
  sources updated ✓; reproducibility safe.

### MC-2026-04-29-F — CLAIM 3 canonical AOI fix + 18 GPPD plants добавлено

- Date: 2026-04-29
- Type: AOI standardization + asset rebuild
- Affected code: `build_industrial_proxy.py`, `build_viirs_proxy.py`
  (AOI 60-55-90-75 → canonical 60-50-95-75)
- Affected GEE Assets (rebuilt):
  - `industrial/source_points`: 513 → **531 features** (+18 GPPD plants)
  - `industrial/proxy_mask`: rebuilt with new sources
  - `industrial/proxy_mask_buffered_30km`: rebuilt
- Reason: 7 setup scripts had divergent AOI bbox. Industrial proxy + VIIRS
  scripts на narrow (60-55-90-75); mask + baseline scripts на wider
  (60-50-95-75). Diagnostic выявил **18 GPPD plants excluded** включая
  4 critical Kuzbass TPPs (Tom-Usinsk GRES 1345 MW, Kuznetsk TES,
  Novo-Kemerovo CHP, Kemerovo GRES) и Krasnoyarsk-region cluster (90-95°E).
- Verification (CLAIM 3 fix verified):
  - Tom-Usinsk GRES (87.59, 53.78): proxy_mask=1, buffered=0 (masked) ✓
  - Kuznetsk TES (87.11, 53.76): masked ✓
  - Novo-Kemerovo CHP (86.00, 55.35): masked ✓
  - Kemerovo GRES (86.07, 55.37): masked ✓
- CH₄ regional Asset built на pre-fix mask — Kuzbass gap documented в
  Asset `industrial_mask_caveat` metadata + KNOWN_TODOS TD-0018.

### MC-2026-04-29-G — CLAIM 4 schema v1.0 → v1.1 migration

- Date: 2026-04-29
- Type: Common Plume Schema breaking change (DNA §2.3 mutation OK because
  Algorithm v2.3 already specifies v1.1)
- Affected code:
  - `src/py/rca/common_schema.py` (SCHEMA_VERSION + 5 fields)
  - `src/js/modules/schema.js` (SCHEMA_VERSION + ALL_FIELDS + missingRequired
    server-side bug fix)
  - `src/py/tests/test_common_schema.py` (3 new tests, total 33/33 pass)
- v1.1 new fields per Algorithm v2.3 §2.1 + DNA v2.2 §4.2:
  - `delta_vs_regional_climatology` (float | null)
  - `delta_vs_reference_baseline` (float | null)
  - `baseline_consistency_flag` (bool | null)
  - `matched_inside_reference_zone` (bool | null)
  - `nearest_reference_zone` (string | null)
- JS bug fix: pre-fix `tagFeatureValidity()` server-side missingRequired
  filter incorrectly used `ee.List(REQUIRED_FIELDS).filter(notNull)` —
  filtered constants instead of properties. Post-fix: `ee.List.iterate()`
  over REQUIRED_FIELDS, checks `props.get(field)` for null. Same fix для
  REQUIRED_FOR_OURS provenance check.
- Verification: 33/33 pytest pass (3 new — fields present, fields optional,
  v1.0 input rejected).

### MC-2026-04-29-H — CLAIM 6 provenance helpers + logs/runs.jsonl

- Date: 2026-04-29
- Type: New module `src/py/rca/provenance.py` + `logs/runs.jsonl` initialization
- Affected code:
  - `src/py/rca/provenance.py` NEW: `compute_provenance(config, period)`,
    `compute_params_hash()`, `write_run_log()`, `read_run_log()`.
  - `logs/runs.jsonl` NEW: append-only JSONL, retroactively populated
    с P-01.0a + P-01.0b CH₄ runs.
- Reason: DNA §2.1 запрет 12 «Не выдавать Run без полного config snapshot».
  Pre-fix: Asset metadata had partial info (algorithm_version, build_date)
  but missing config_id/params_hash/run_id. No logs/runs.jsonl.
- Implementation:
  - `compute_params_hash(config)` — SHA-256 sorted-keys JSON serialization,
    deterministic, same config → same hash.
  - `compute_provenance(config, period)` — returns
    `{config_id, params_hash, run_id}`. run_id format
    `<config_id>_<period>_<sha8>`.
  - `write_run_log(...)` — append JSONL entry to `logs/runs.jsonl` (anchored
    to repo root, не cwd-dependent).
- Retroactive entries created:
  - `default_2019_2025_v1_1a89d4f6` — reference_CH4_2019_2025_v1 (P-01.0a)
  - `default_2019_2025_d2e6362c` — regional_CH4_2019_2025 (P-01.0b)
- CH₄ regional Asset metadata also includes `config_id`, `params_hash`,
  `run_id` direct в Image properties (verified post-build).

### MC-2026-04-29-I — Industrial mask completeness vs reference reliability tradeoff

- Date: 2026-04-29
- Type: Architectural caveat documentation (per Option E rationale)
- Affected document: KNOWN_TODOS.md (TD-0018 detailed)
- Reason: Per researcher Option E rationale: «Architecture mitigation
  (dual baseline) valid only when at least one baseline robust». For
  Kuzbass region:
  - Reference baseline (Kuznetsky Alatau, lat 53-57°N): low counts
    60-140/month → **higher uncertainty**
  - Regional baseline pre-fix: missing 4 major Kuzbass plants → **contamination**
  - Cross-check: **unreliable signal** в этой specific region
- Decision: Phase 2A detection в Kuzbass (lat 53-55°N, lon 86-88°E) requires:
  - Stricter detection threshold (z_min=4.0 vs default 3.0) per
    DevPrompt P-01.0b §5
  - Manual review для events `nearest_source_id=null` near (86-88°E, 53-55°N)
- Architectural learning: dual baseline architecture not auto-robust в all
  regions; needs per-region reliability assessment.

### MC-2026-04-28-C — Altaisky exclusion rationale documented (P-01.0a)

- Date: 2026-04-28
- Initiator: Researcher (P-01.0a closure review)
- Type: Defensibility documentation (sub-implementation refinement)
- Affected document: `Algorithm.md` §11.4.1 (NEW worked example subsection)
- Reason: P-01.0a Altaisky QA test failed (winter +34.86 ppb, cycle_diff
  +14.25 ppb). Per DNA §2.1 запрет 16 — Altaisky excluded from production
  baseline. Researcher review highlighted что raw "FAIL" verdict
  insufficient для Phase 7 tool-paper documentation; need physical
  explanation defensible перед reviewers.
- Decision: Algorithm §11.4.1 «Worked example — P-01.0a Altaisky FAIL»
  added с:
  - Full numerical metrics (alt/kuz summer + winter, abs_diff, seasonal_diff,
    cycle_diff, verdicts).
  - Physical interpretation: Altaisky elevation >1500 m places column
    above winter PBL inversion height (~500-1500 m континентальной
    Сибири). Summer match excellent (0.61 ppb) когда PBL deep, winter
    decoupling (+35 ppb) когда Altaisky free-tropospheric vs lowland
    surface-trapped.
  - Defensibility statement (quoted form) для tool-paper Phase 7 use.
- Verification: Algorithm §11.4.1 содержит full worked example;
  validation report cross-references; Asset
  `RuPlumeScan/validation/altaisky_qa/test_20260428` Feature имеет
  full metrics для programmatic reference.
- Note: Это НЕ override DNA §2.1 запрет 16. Altaisky остаётся
  `unreliable_for_xch4_baseline`; documentation establishes scientific
  defensibility for the exclusion decision.

---

## 5. Archived changes (superseded)

### CHANGE-A001 [ARCHIVED] — Composite-based detection (V1 approach)

- Date applied: 2026-04-11 (in V1)
- Date archived: 2026-04-25 (superseded by CHANGE-0001)
- Type: Algorithm (deprecated)
- Reason for archival: Концептуальная ошибка — composite median подавляет transient signal.
- Superseded by: CHANGE-0001 (per-orbit detection).
- Lesson: Этот change остался в журнале как explicit lesson learned для будущих инстанций Claude и researchers.

---

## 6. Process notes

### 6.1. Когда добавлять changes

**Любое изменение которое затрагивает Algorithm/RNA/DNA/CLAUDE документы — обязательно через OpenSpec.** Прямое редактирование документов без entry в OpenSpec — **запрещено** для traceability.

Исключения (не требуют OpenSpec entry):
- Опечатки и грамматические правки
- Уточнение формулировок без изменения смысла
- Добавление примеров без изменения semantics
- Markdown formatting

### 6.2. Workflow для нового change

1. Researcher или Claude (при review) формулирует proposed change
2. Создаётся entry в §2 (Proposed changes) с полным template
3. Discussion и approval
4. При approval: applied к актуальным документам, entry перемещается в §1 (Applied changes) с обновлённой `Date applied`
5. При rejection: entry перемещается в §4 (Rejected changes) с reason
6. При future supersedure: entry перемещается в §5 (Archived) с reference на superseding change

### 6.3. Когда блокировать change

Если change требует external событий (накопление корпуса, response от authors, technological availability) — entry создаётся в §3 (Blocked changes) с явными activation conditions.

### 6.4. OpenSpec versioning

OpenSpec.md — living document. Не имеет версий major/minor. Каждый change добавляет entry, документ растёт incrementally. Periodic cleanup только при breaking changes в OpenSpec format itself.

---

## 7. Журнал изменений OpenSpec.md

| Версия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-04-25 | Первая версия. Бэкфилл всех previous changes (CHANGE-0001 через CHANGE-0016) + 6 BLOCKED entries. |
