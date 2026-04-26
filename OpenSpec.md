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
