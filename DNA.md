# RU-PlumeScan — Project DNA v2.2

**Дата фиксации v2.2:** 2026-04-26  
**Предыдущая версия:** v2.1 (2026-04-25, archived as `DNA_v2.1_archived.md`)

**Изменения v2.1 → v2.2:**

- §1.2: добавлена сущность **Reference Clean Zone** (protected nature reserves используемые для positive-space baseline construction)
- §1.4: добавлен новый класс выходов `Reference Baseline` (отдельно от Detection Surface outputs)
- §1.5: добавлено различение **Positive baseline ≠ Negative buffer exclusion**
- §2.1: добавлен запрет «Не строить detection baseline только через industrial buffer exclusion (negative space) когда possible использовать reference clean zones (positive space)»
- §3.1: добавлен приоритет **«Positive baseline definition > negative buffer exclusion»** на позицию 5 (между «Cross-source agreement» и «Honest limitations»)
- §3.2: success criteria v1.0 обновлены — reference baseline coverage обязательна
- §4.1: Phase 0 deliverables дополнены protected areas ingestion

**Источник изменения:** методологическое улучшение предложено пользователем 2026-04-26 — вместо industrial buffer exclusion (negative space approach с unknown unknowns) использовать positive-space approach через protected nature reserves где industrial activity запрещена законом.

**Источники синтеза:** все предыдущие + research about Юганский, Верхнетазовский, Кузнецкий Алатау, Алтайский заповедники.

**Назначение документа:** зафиксировать инварианты проекта — то, что не меняется без явной мутации DNA. Параметры алгоритма, конкретные пороги, реализационные решения и стек — НЕ в этом документе.

---

## 1. Онтология

### 1.1. Что является объектом исследования

**RU-PlumeScan** — региональный **настраиваемый workbench** для детекции и кросс-сопоставления атмосферных аномалий газов TROPOMI/Sentinel-5P над Западной Сибирью, реализованный в Google Earth Engine с дополнительным Python-ingestion слоем для reference catalogs.

**Главный объект работы — Configurable Detection Surface**: параметризованная вычислительная поверхность, выходом которой являются множественные артефакты (event catalogs, persistence maps, time series, comparison reports, reference baselines). Каталог событий — один из выходов поверхности, а не самоцель.

### 1.2. Базовые сущности

#### Сущности детекции

**Pixel anomaly** — единичный пиксель TROPOMI L3, для которого наблюдаемое значение статистически значимо превышает фоновое. Не имеет физической интерпретации сам по себе.

**Cluster anomaly** — группа пространственно связных pixel anomalies в одном снимке. Имеет геометрию, площадь, центроид, число пикселей.

**Candidate detection** — cluster anomaly, прошедший базовые фильтры качества. Это **гипотеза о плюме**, не плюм.

**Plume Event** — главная сущность каталога. Candidate detection, обогащённый ветровой согласованностью, источниковой атрибуцией, индексом доверия, мультигазовой evidence, классом, и **config snapshot** — полным набором параметров детекции на момент создания.

**Persistent Source** — пространственная позиция, для которой Plume Events детектируются регулярно за длительный период.

**Diffuse Enhancement** — крупная пространственно протяжённая аномалия без plume-like geometry. Для CH₄ в Западной Сибири это типично болотный/синоптический фон. Отдельный класс (`diffuse_CH4`), не отвергнутый plume.

**Verified Plume** — Plume Event, прошедший внешнюю верификацию. RU-PlumeScan v1 **не выдаёт** verified plumes как отдельный класс.

**Industrial Source** — проксированная локация антропогенного источника (GPPD, OGIM, manual points, VIIRS night light bright pixels).

#### Сущности конфигурируемости

**Configuration** — структурированный набор параметров детекции (thresholds, background mode, wind filter, object filter), полностью описывающий run. Имеет `params_hash` (SHA-256 от сериализованного config), `config_id` (human-readable).

**Configuration Preset** — сохранённый Configuration с явным назначением (`schuit_equivalent`, `imeo_equivalent`, `sensitive_screening`, `conservative`, `custom`). Хранится как Asset/файл, версионируется.

**Run** — конкретное исполнение pipeline с фиксированным Configuration на фиксированном временном окне и AOI. Каждый Run воспроизводим.

#### Сущности reference data (extended in v2.2)

**Reference Clean Zone (НОВОЕ в v2.2)** — особо охраняемая природная территория (заповедник) где промышленная деятельность **запрещена федеральным законом**, используемая для positive-space baseline construction. В отличие от industrial buffer exclusion (которая определяет clean as `NOT(known industrial)`), Reference Clean Zone определяет clean as `enforced protected status`.

Поддерживаемые reference zones для Западной Сибири (v1.0):
- **Юганский заповедник** (60.5°N, 74.5°E, 6500 км²) — средняя тайга + Васюганские болота, ХМАО. Primary wetland baseline.
- **Верхнетазовский заповедник** (63.5°N, 84.0°E, 6313 км²) — северная тайга, мерзлота, ЯНАО. Permafrost zone baseline.
- **Кузнецкий Алатау заповедник** (54.5°N, 88.0°E, 4019 км²) — горная тайга, Кемеровская область. Reference для Кузбасс детекций.
- **Алтайский заповедник** (51.5°N, 88.5°E, 8810 км², optional) — высокогорье, Республика Алтай. Optional southern reference (column XCH4 в горах может быть unreliable; используется только если quality test passes).

Каждая Reference Clean Zone имеет:
- Polygon boundary (federal protected area boundary)
- Internal buffer (5-10 km от границы для исключения edge effects от внешней активности)
- Latitude band assignment (для zone-stratified baseline construction)
- Quality status (`active` для primary references, `optional_pending_quality` для Алтайский)

**Reference Baseline (НОВОЕ в v2.2)** — climatology computed **только** из pixels внутри Reference Clean Zones (после internal buffer). Per-month median + MAD + count, stratified по latitude bands. Это **positive-space clean baseline** — anchored в law-enforced clean zones, не в negative space «not-industrial».

**Reference Catalog** — внешний размеченный каталог событий, нормализованный в Common Plume Schema. Источник для cross-validation и benchmark, **но не ground truth**.

Поддерживаемые reference catalogs v1.0:
- Schuit et al. 2023 (Zenodo 8087134)
- UNEP IMEO MARS (monthly snapshots)
- CAMS Methane Hotspot Explorer (weekly snapshots)

**Common Plume Schema** — унифицированная структура полей для cross-catalog comparison.

**Reference Catalog Adapter (RCA)** — модуль импорта reference catalogs в Common Schema.

**Comparison Run** — параметризованное сопоставление двух каталогов.

#### Сущности выходов

**Plume Event Catalog** — FeatureCollection в GEE Asset со всеми Plume Events за period+AOI с заданным Configuration.

**Persistence Map** — растровая поверхность плотности повторяющихся событий.

**Time Series** — temporal evolution для known industrial source.

**Comparison Report** — output Comparison Run.

**Sensitivity Sweep** — multi-run output.

**Reference Baseline Asset (НОВОЕ в v2.2)** — отдельный output: climatological baseline computed из Reference Clean Zones, доступный как Asset для использования другими исследователями. Это **standalone scientific contribution** — независимый от detection pipeline reference dataset для Western Siberia clean atmospheric conditions.

### 1.3. Классы событий (multi-gas evidence)

Без изменений с v2.1.

### 1.4. Что является результатом vs артефактом процедуры

**Результаты (v1):**
- Configurable Detection Surface — сам инструмент с UI и API
- Plume Event Catalog Asset(s) — для разных Configurations
- Persistence Maps
- Per-source time series для known industrial sources
- Comparison Reports против reference catalogs
- Sensitivity Sweeps
- **Reference Baseline Asset (НОВОЕ)** — standalone clean atmosphere reference dataset для Western Siberia
- Open code (GitHub) + open assets (Zenodo DOI)

**Артефакты процедуры (НЕ результаты):**
- Single-pixel maxima без object structure
- Composite means без disaggregation
- Threshold values сами по себе
- Z-score карты без object extraction
- «Мой recall vs Lauvaux» как self-standing claim
- **Industrial buffer exclusion sole approach без reference baseline cross-check (НОВОЕ)** — это negative-space baseline, который inherently имеет unknown unknowns

### 1.5. Различения, которые нельзя нарушать

**Pixel anomaly ≠ Plume.** Plume имеет downwind extent, направление совпадает с местным ветром, intensity спадает с расстоянием.

**Detection ≠ Quantification.** Detection: «здесь candidate выше threshold». Quantification: «source rate = X ± Y kg/h».

**TROPOMI L3 GEE ≠ TROPOMI L2 SRON.** L3 в GEE = операционный v02.04. Литература использует re-processed v18_17.

**GEE L3 grid ≠ TROPOMI native footprint.** Analysis scale в RNA фиксируется на ≥ 7 km.

**Anthropogenic ≠ Natural.** Без context layers разделить нельзя.

**Reference Catalog ≠ Ground Truth.** Recall vs reference = «согласие методов», не «точность нашего метода».

**Configuration ≠ Result.** Параметры — input, не output.

**Positive baseline ≠ Negative buffer exclusion (НОВОЕ в v2.2).** 
- **Negative space approach** (industrial buffer exclusion): «всё что не industrial → assumed clean». Имеет unknown unknowns: undocumented sources, missed flares, temporary venting. Background contains unaccounted contamination.
- **Positive space approach** (reference clean zones): «protected by law → certified clean». Bounded uncertainty, enforceable, scientifically defensible.
- **Эти подходы дают разные baselines** и должны использоваться **в комбинации** (dual baseline cross-check), не как взаимозаменяемые.

**Reference Clean Zone ≠ Industrial Source (НОВОЕ в v2.2).** Reference zones и Industrial sources — это **разные сущности с разными ролями**:
- Industrial Source: используется для source attribution Plume Events (Algorithm §3.10), в industrial buffer exclusion (deprecated as primary baseline), в multi-gas matching context
- Reference Clean Zone: используется только для baseline construction (positive-space approach), не для source attribution

---

## 2. Деонтика

### 2.1. Безусловные запреты

**Не присваивать candidate detection статус «plume» без структурной проверки.**

**Не выдавать quantification (kg/h, t/h) на основе TROPOMI L3 GEE как production-grade.**

**Не использовать compositing (monthly/yearly median + threshold) для CH₄ plume detection.**

**Не применять `unmask(0)` к XCH4.**

**Не выполнять арифметику над `ee.Kernel`.**

**Не применять единый абсолютный порог концентрации для всей Западной Сибири.**

**Не выбрасывать отрицательные SO₂ значения автоматически.**

**Не сравнивать напрямую CH₄ ppb, NO₂ mol/m², SO₂ mol/m².**

**Не выдавать NO₂/SO₂ column burden за emission rate без lifetime model.**

**Не утверждать источник plume без проверки инфраструктурой, ветром и повторяемостью.**

**Не использовать ML-модули в v1.**

**Не выдавать Run без полного config snapshot.**

**Не интерпретировать Reference Catalog как ground truth.**

**Не применять Configuration без явной декларации Preset.**

**Не строить detection baseline только через industrial buffer exclusion (НОВОЕ в v2.2).**
Если Reference Clean Zones доступны (что верно для нашей AOI — Юганский, Верхнетазовский, Кузнецкий Алатау покрывают три природных зоны Западной Сибири), background construction обязательно использует **dual baseline approach**: positive-space reference baseline + regional climatology с industrial buffer exclusion. Single-source baseline (только industrial buffer без reference) — нарушение методологии.

**Не использовать Reference Clean Zone которая не прошла quality test (НОВОЕ в v2.2).**
Алтайский заповедник имеет статус `optional_pending_quality` — горный высокогорный biome может давать TROPOMI XCH4 column values несопоставимые с равнинными reference zones. Перед использованием в baseline — обязательный QA test (mean column XCH4 vs Кузнецкий Алатау после seasonal correction). При расхождении > 30 ppb → mark as `unreliable_for_xch4_baseline`, не использовать в production baseline. Использование без QA test запрещено.

### 2.2. Утверждения, требующие внешнего подтверждения

Без изменений с v2.1.

### 2.3. Изменения, требующие явной мутации DNA

- Расширение scope (добавление газов, регионов вне Западной Сибири)
- Снижение standards (например, разрешить ML до накопления корпуса)
- Изменение фундаментальных классов (Plume Event, Configurable Detection Surface, Reference Catalog, **Reference Clean Zone (НОВОЕ)**)
- Изменение приоритетов (см. аксиологию)
- Включение quantification в основной каталог
- Изменение Common Plume Schema
- **Изменение списка primary Reference Clean Zones (НОВОЕ в v2.2)** — добавление новых reserves, исключение существующих, изменение latitude band assignments

Локальная настройка параметров, добавление нового Reference Ingester, добавление нового Configuration Preset — НЕ требует мутации DNA.

---

## 3. Аксиология

### 3.1. Иерархия приоритетов

При конфликтах решает порядок:

**1. Воспроизводимость > новизна.**

**2. Configurability > optimal defaults.**

**3. Output traceability > catalog completeness.**

**4. Cross-source agreement > single-catalog recall.**

**5. Positive baseline definition > negative buffer exclusion (НОВОЕ в v2.2).**  
Когда возможен positive-space approach (reference clean zones doc enforced by law) — он предпочтительнее negative-space approach (industrial buffer exclusion с unknown unknowns). Reference baseline — anchored в enforced clean status, defensible перед reviewers, не зависит от completeness нашего industrial inventory.

**6. Honest limitations > pseudo-precision.**

**7. Verifiability > complexity.**

**8. Per-gas correctness > unified pipeline.**

**9. Catalog quality > catalog size.**

**10. Reproducibility > responsiveness.**

**11. Region adaptation > global universality.**

### 3.2. Что считается успехом проекта

**v1.0 успех (publication-ready tool):**
- Configurable Detection Surface реализована
- Минимум 4 named Configuration Presets работают (`default`, `schuit_eq`, `imeo_eq`, `sensitive`)
- RCA импортирует минимум 3 reference catalogs (Schuit 2023, IMEO MARS, CAMS)
- **Reference Baseline Asset построен из 3 primary zones (НОВОЕ)** — Юганский + Верхнетазовский + Кузнецкий Алатау; Алтайский включён если QA test passed
- **Dual baseline approach реализован (НОВОЕ)** — каждый Run produces оба baselines с cross-check
- Comparison Engine выдаёт cross-source comparison reports
- Каждый Run полностью воспроизводим
- Sanity-check passed: Норильск SO₂ persistent, Кузбасс CH₄ candidates, Бованенково CH₄
- Synthetic plume injection test пройден (recovered/injected > 0.7 для plumes ≥ 30 ppb)
- **Reference baseline validation passed (НОВОЕ)** — XCH4 inside Юганский показывает characteristic seasonal cycle (зимой ~1850-1880 ppb, летом ~1900-1930 ppb с wetland enhancement); если значения вне этого range → reference zone build flawed
- Открытый код на GitHub (MIT) + Asset с DOI на Zenodo (CC-BY 4.0)
- Опубликована tool-paper в СПДЗЗ или эквивалентный ВАК Q1
- Каталог использован в собственной публикации/диссертации

**v1.0 неуспех:**
- Каталог содержит wetland-driven false positives без класса diffuse_CH4
- Configurability нарушена
- RCA имеет silent ingestion failures
- Run без config snapshot выдан как результат
- Cross-source comparison reports содержат recall/precision без declared «vs reference, не vs ground truth»
- ML-модуль добавлен до накопления корпуса
- **Reference baseline не построен (НОВОЕ)** — fall back на industrial-buffer-only approach без явного обоснования
- **Алтайский использован в production baseline без QA test (НОВОЕ)** — нарушение деонтики

### 3.3. Калибровка значимости

RU-PlumeScan не претендует превосходить SRON/Kayrros. Это **региональный воспроизводимый инструмент**.

**Уникальная ниша (расширена в v2.2):** первый открытый GEE-нативный configurable workbench для российской территории с **встроенным cross-source validation + reference-anchored baseline approach**. 

**Reference-anchored baseline — отдельный методологический contribution.** Tool-paper в СПДЗЗ может включать это как novelty argument: «We introduce a positive-space baseline approach using Russian Federation strict nature reserves (zapovedniks) as enforced clean reference zones for atmospheric column anomaly detection. Unlike industrial buffer exclusion (negative space, susceptible to undocumented sources), the reserve-anchored approach provides legally-enforced clean baselines with bounded methodological uncertainty.»

Это инкремент с **двумя novelty arguments**: multi-gas matching + reference-anchored baseline.

---

## 4. Праксеология

### 4.1. Этапы развития проекта

**v0.5 — Implementation phase (текущая)**

Параллельная разработка четырёх first-class модулей (расширено с трёх в v2.1):

```
Detection Engine    Reference Catalog Adapter    Reference Baseline Builder    Comparison Engine
├─ BG (background)  ├─ Schuit2023Ingester        ├─ Protected areas ingestion  ├─ spatial matching
├─ IND (industrial) ├─ ImeoMarsIngester          ├─ Internal buffer apply      ├─ temporal matching
├─ PC-CH4           ├─ CAMS_HotspotIngester      ├─ Latitude stratification    ├─ recall/precision
├─ PC-NO2           ├─ Common Schema validator    ├─ Per-zone baseline build    ├─ cross-source agreement
└─ PC-SO2           └─ versioned ref Assets       ├─ QA test Алтайский          └─ disagreement maps
                                                  └─ Dual baseline cross-check
        ↓                       ↓                          ↓                          ↓
        └────────────  Configurable Detection Surface  ───────────────────────────────┘
                                          ↓
                              UI App + Python API + Exports
```

**Reference Baseline Builder (НОВОЕ в v2.2)** — отдельный модуль, выход которого (Reference Baseline Asset) используется и в Detection Engine (как primary baseline cross-check), и публикуется как standalone scientific artifact.

**Phase 0 deliverables (расширены в v2.2):**
- Repository + Common Plume Schema + Industrial proxy (P-00.1) **+ Protected Areas reference mask (P-00.1)** — теперь one combined DevPrompt с dual scope
- Configuration Presets storage (P-00.3)

**Phase 1 deliverables (изменены в v2.2):**
- Reference Baseline construction (P-01.0a NEW) — primary baseline из 3-4 zapovedniks
- Regional climatology с industrial buffer (P-01.0b) — secondary baseline
- Annulus kernel utilities (P-01.1)
- Dual baseline cross-check validation (P-01.2 NEW)

**v1.0 — Validated Configurable Tool**

**v2.0 — ML-augmented detection** (после corpus accumulation, см. CHANGE-B001).

**v3.0 — Integration phase** (требует мутации DNA).

### 4.2. Forward-compatibility v0.5 → v1 → v2

Без изменений с v2.1, плюс:

**ML-readiness slots (расширены в v2.2):**
```
matched_inside_reference_zone     : bool   (был ли candidate detected внутри границ Reference Clean Zone — это автоматический false positive flag для будущей ML training)
deviation_from_reference_baseline : float  (Δ vs reference baseline, дополнительно к Δ vs regional climatology)
baseline_consistency_flag         : bool   (true = оба baselines дали similar Δ, false = diverge → contamination suspected)
```

Эти поля предоставляют additional training signal для v2 ML — если candidate detected inside protected zone, это almost certainly false positive (industrial activity там запрещена), perfect negative training sample.

### 4.3. Роли человек / AI agents

Без изменений с v2.1, плюс:

**Решения о добавлении новых Reference Clean Zones** — только researcher, требует подтверждения что zone имеет federal protected status и не имеет documented industrial activity within boundaries.

### 4.4. Контуры обратной связи и валидация

Без изменений с v2.1, плюс:

**Sanity checks (расширены в v2.2):**
- XCH4 internal Юганский показывает expected seasonal cycle?
- Reference baseline и regional climatology converge для clean регионов?
- Если diverge — есть ли systematic pattern (e.g., регионы вокруг oil&gas always show regional > reference)?
- Алтайский XCH4 quality test pass/fail?

### 4.5. Критерии для voluntary остановки проекта

Без изменений с v2.1, плюс:

- **Reference baseline и regional climatology systematically diverge > 50 ppb для clean регионов** — указывает на fundamental methodological problem в одном из baselines, требует диагностики до продолжения
- **Все Reference Clean Zones показывают anomalous XCH4 patterns** — может означать TROPOMI retrieval issue над субарктикой specific, требует переосмысления methodology

### 4.6. Change management

Без изменений с v2.1.

---

## 5. Тест качества DNA

> Убери из этого документа все технические детали реализации, конкретные параметры, упоминания GEE, TROPOMI, Schuit, Beirle, Fioletov. Остался ли смысл?

Должно остаться:
- Объект работы — настраиваемая поверхность детекции с множественными выходами, не просто каталог
- Различения candidate / plume / persistent / verified
- Различение Reference Catalog ≠ Ground Truth
- Различение Configuration ≠ Result
- **Различение Positive baseline ≠ Negative buffer exclusion (НОВОЕ)**
- **Различение Reference Clean Zone ≠ Industrial Source (НОВОЕ)**
- Запреты на conflation pixel anomaly = plume, detection = quantification
- Приоритеты: configurability, output traceability, cross-source agreement, **positive baseline (НОВОЕ)**, honest limitations
- Этапность: формальный детектор + RCA + comparison + **reference baseline builder (НОВОЕ)** → корпус через cross-source agreement → ML
- Forward-compatibility данных
- Роли человек / AI с финальной ответственностью на человеке
- Эпистемический журнал и адверсариальная проверка обязательны

Это и есть DNA. Технические детали — в Algorithm.md и RNA.md.

---

## 6. Журнал изменений

| Версия | Дата | Изменение |
|--------|------|-----------|
| 0.1–1.x | 2026-04-11 → 2026-04-13 | Первая версия (deprecated, концептуальная ошибка с monthly composites) |
| 2.0 | 2026-04-25 | Полная переработка после консолидации 5 источников. Per-gas methodology, three published methods, forward-compatibility к ML, явные деонтические запреты по урокам V2 fail. |
| 2.1 | 2026-04-25 | Минорная мутация: добавлены Configurable Detection Surface, Reference Catalog Adapter, Comparison Engine как first-class сущности. Цель проекта: tool-paper в СПДЗЗ. Configurability + cross-source agreement — приоритеты. |
| 2.2 | 2026-04-26 | Добавлена Reference Clean Zone как first-class entity. Reference Baseline Builder как четвёртый параллельный модуль. Positive baseline definition приоритет (rank 5). Dual baseline approach обязателен при availability reference zones. Tool-paper получает второй novelty argument: reference-anchored baseline approach. |
