# RU-PlumeScan — Project DNA v2.1

**Дата фиксации v2.1:** 2026-04-25  
**Предыдущая версия:** v2.0 (2026-04-25, архивирована в `DNA_v2.0_archived.md`)  
**Изменения v2.0 → v2.1:**
- §1: добавлены сущности `Configurable Detection Surface`, `Configuration`, `Reference Catalog`, `Common Plume Schema`, `Comparison Run`
- §2.1: добавлены запреты «Reference catalog ≠ ground truth», «Run без config snapshot», «Configuration без Preset»
- §3.1: добавлены приоритеты «Configurability > optimal defaults», «Output traceability > catalog completeness», «Cross-source agreement > single-catalog recall»
- §3.2: переписаны success criteria — успех = configurable tool + tool-paper в СПДЗЗ
- §4.1: Reference Catalog Adapter (RCA) и Comparison Engine как first-class модули
- §4.2: cross-source agreement как источник labels для v2 ML (удешевляет накопление корпуса)

**Источники синтеза:** domain_scouting.md, domain_scouting_addendum.md, LitReview.md, Algorithm.md, тех. записка от 2026-04-25

**Назначение документа:** зафиксировать инварианты проекта — то, что не меняется без явной мутации DNA. Параметры алгоритма, конкретные пороги, реализационные решения и стек — НЕ в этом документе.

---

## 1. Онтология

### 1.1. Что является объектом исследования

**RU-PlumeScan** — региональный **настраиваемый workbench** для детекции и кросс-сопоставления атмосферных аномалий газов TROPOMI/Sentinel-5P над Западной Сибирью, реализованный в Google Earth Engine с дополнительным Python-ingestion слоем для reference catalogs.

**Главный объект работы — Configurable Detection Surface**: параметризованная вычислительная поверхность, выходом которой являются множественные артефакты (event catalogs, persistence maps, time series, comparison reports). Каталог событий — один из выходов поверхности, а не самоцель.

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

**Configuration Preset** — сохранённый Configuration с явным назначением (`schuit_equivalent`, `lauvaux_equivalent`, `sensitive_screening`, `conservative`, `custom`). Хранится как Asset/файл, версионируется.

**Run** — конкретное исполнение pipeline с фиксированным Configuration на фиксированном временном окне и AOI. Каждый Run воспроизводим — повтор с тем же Configuration на тех же входах даёт идентичный output.

#### Сущности reference catalogs

**Reference Catalog** — внешний размеченный каталог событий, нормализованный в Common Plume Schema. Источник для cross-validation и benchmark, **но не ground truth** (сам имеет detection limits и false positives).

Поддерживаемые источники v1.0 (минимум):
- Schuit et al. 2023 (Zenodo 8087134) — ML-based, 2974 plumes 2021
- Lauvaux et al. 2022 (Science supplementary) — manual + dispersion modeling, ~1800 plumes 2019-2020
- CAMS Methane Hotspot Explorer (API) — operational, weekly updates

Расширяемые источники (планируются):
- UNEP IMEO MARS (API)
- Carbon Mapper (API/web)
- Cherepanova 2023 Кузбасс (по запросу авторам)
- Fioletov SO₂ catalog (Zenodo)
- Beirle NO₂ source catalog (Zenodo)

**Common Plume Schema** — унифицированная структура полей для cross-catalog comparison. Минимальный набор: `event_id, source_catalog, source_event_id, gas, date_utc, lon, lat, geometry (optional), magnitude_proxy, quality_flag, source_attribution, ingestion_date, schema_version`.

Все каталоги (наш + reference) приводятся к этой схеме через source-specific Ingester.

**Reference Catalog Adapter (RCA)** — модуль импорта reference catalogs в Common Schema. Состоит из set of Ingesters, по одному на источник.

**Comparison Run** — параметризованное сопоставление двух каталогов. Параметры: `R_match` (spatial radius), `T_match` (temporal window), `gas_filter`, `region_filter`. Выход: matched events, unmatched events, recall, precision (с явной декларацией baseline), spatial disagreement maps.

#### Сущности выходов

**Plume Event Catalog** — FeatureCollection в GEE Asset со всеми Plume Events за period+AOI с заданным Configuration. Каждый Feature содержит config snapshot.

**Persistence Map** — растровая поверхность плотности повторяющихся событий по сетке за длительный период.

**Time Series** — temporal evolution для known industrial source: counts, magnitude proxy, confidence по времени.

**Comparison Report** — output Comparison Run: матрица согласия, recall/precision metrics, matched/unmatched events tables, sensitivity analysis по параметрам matching.

**Sensitivity Sweep** — multi-run output: множество Runs с разными Configurations, агрегированные metrics для оценки робастности detection.

### 1.3. Классы событий (multi-gas evidence)

- `CH4_only` — CH₄ candidate без NO₂/SO₂ совпадения
- `NO2_only` — NO₂ source без CH₄/SO₂ совпадения
- `SO2_only` — SO₂ source без CH₄/NO₂ совпадения
- `CH4_NO2` — oil&gas сигнатура
- `NO2_SO2` — energy/combustion сигнатура
- `CH4_NO2_SO2` — highest priority
- `diffuse_CH4` — крупный CH₄ enhancement без plume geometry (вероятный болотный/синоптический фон)
- `wind_ambiguous` — событие при U10 < threshold

Расширение в v2: cross-source labels (`high_confidence_3sources`, `our_only`, `reference_only`, etc.).

### 1.4. Что является результатом vs артефактом процедуры

**Результаты (v1):**
- Configurable Detection Surface — сам инструмент с UI и API
- Plume Event Catalog Asset(s) — для разных Configurations
- Persistence Maps
- Per-source time series для known industrial sources
- Comparison Reports против reference catalogs
- Sensitivity Sweeps
- Open code (GitHub) + open assets (Zenodo DOI)

**Артефакты процедуры (НЕ результаты):**
- Single-pixel maxima без object structure
- Composite means без disaggregation
- Threshold values сами по себе (порог Z=3 — не «правильный», он `parameter в Configuration`)
- Z-score карты без object extraction
- «Мой recall vs Lauvaux» как self-standing claim — это всегда **agreement**, не точность

### 1.5. Различения, которые нельзя нарушать

**Pixel anomaly ≠ Plume.** Plume имеет downwind extent, направление совпадает с местным ветром, intensity спадает с расстоянием.

**Detection ≠ Quantification.** Detection: «здесь candidate выше threshold». Quantification: «source rate = X ± Y kg/h». Без LES-калиброванного Ueff и spatially-resolved plume — quantification нельзя.

**TROPOMI L3 GEE ≠ TROPOMI L2 SRON.** L3 в GEE = операционный v02.04. Литература использует re-processed v18_17 с destriping. Результаты сопоставимы по порядку, не идентичны.

**GEE L3 grid ≠ TROPOMI native footprint.** L3 grid 0.01° (~1.1 km), native footprint 7×5.5 km. Object statistics на 1 km scale интерпретируются неверно. Analysis scale в RNA фиксируется на ≥ 5 km.

**Anthropogenic ≠ Natural.** Без context layers разделить нельзя.

**Reference Catalog ≠ Ground Truth.** Schuit/Lauvaux/CAMS — peer-reviewed системы с собственными detection limits и false positive rates. Recall vs reference = «согласие методов», не «точность нашего метода». Истинная validation требует ground stations или high-resolution satellite confirmation.

**Configuration ≠ Result.** Параметры детекции — это **input**, не output. Изменение параметров производит другой Run с другим выходом, но не делает один Run «правильнее» другого. Все Runs одинаково валидны при условии reproducibility.

---

## 2. Деонтика

### 2.1. Безусловные запреты

**Не присваивать candidate detection статус «plume» без структурной проверки.**
Plume = cluster + wind alignment + source proximity + confidence threshold.

**Не выдавать quantification (kg/h, t/h) на основе TROPOMI L3 GEE как production-grade.**
Quantification может присутствовать как `experimental_Q_estimate` с явным указанием ±50% uncertainty. Не как основное число каталога.

**Не использовать compositing (monthly/yearly median + threshold) для CH₄ plume detection.**
Плюм — transient event. Median за месяц подавляет сигнал ~30 раз.

**Не применять `unmask(0)` к XCH4.**
0 ppb для метана физически невозможно. Замаскированные пиксели остаются masked или заполняются climatological median.

**Не выполнять арифметику над `ee.Kernel`.**
Annulus реализуется через `ee.Kernel.fixed()` с явной матрицей весов.

**Не применять единый абсолютный порог концентрации для всей Западной Сибири.**
Threshold всегда относится к background-corrected anomaly (Δ или Z), не к абсолютной концентрации.

**Не выбрасывать отрицательные SO₂ значения автоматически.**
Фильтруется только сильный outlier `< -0.001 mol/m²`.

**Не сравнивать напрямую CH₄ ppb, NO₂ mol/m², SO₂ mol/m².**
Multi-gas совмещение — на нормализованных метриках.

**Не выдавать NO₂/SO₂ column burden за emission rate без lifetime model.**

**Не утверждать источник plume без проверки инфраструктурой, ветром и повторяемостью.**

**Не использовать ML-модули в v1.**
ML добавляется в v2 ПОСЛЕ накопления собственного размеченного корпуса. Импорт чужих ML моделей не воспроизводим.

**Не выдавать Run без полного config snapshot.**
Каждый Plume Event Feature, Persistence Map, Time Series, Comparison Report должен содержать `params_hash` и метаданные для bit-identical воспроизведения. Run без config snapshot не публикуется.

**Не интерпретировать Reference Catalog как ground truth.**
В comparison reports recall/precision приводятся как **agreement metrics**, не validation accuracy. В UI/публикациях это явно declared.

**Не применять Configuration без явной декларации Preset.**
В UI и API Run всегда стартует от named Preset (`default`, `schuit_eq`, `lauvaux_eq`, `custom_<id>`). Free-form parameter input возможен только через `custom_<id>` с автоматическим сохранением как новый Preset.

### 2.2. Утверждения, требующие внешнего подтверждения

- Любая ссылка на peer-reviewed работу — DOI верифицируется.
- Численные параметры из литературы — приводятся с источником и страницей/уравнением.
- Сравнение с published catalogs — требует cross-validation на конкретных событиях.
- **Reference catalog содержание — верифицируется при ingestion.** Перед использованием Ingester проверяет: количество записей, временной диапазон, географический охват. При расхождениях — flag и log, не silent ingest.

### 2.3. Изменения, требующие явной мутации DNA

- Расширение scope (добавление газов, регионов вне Западной Сибири)
- Снижение standards (например, разрешить ML до накопления корпуса)
- Изменение фундаментальных классов (Plume Event, Configurable Detection Surface, Reference Catalog)
- Изменение приоритетов
- Включение quantification в основной каталог (вместо experimental слоя)
- **Изменение Common Plume Schema — breaking change для всех ingesters и comparison runs**

Локальная настройка параметров, добавление нового Reference Ingester, добавление нового Configuration Preset — НЕ требует мутации DNA.

---

## 3. Аксиология

### 3.1. Иерархия приоритетов

При конфликтах решает порядок:

**1. Воспроизводимость > новизна.**  
Реализуем published method или придумываем «улучшение» — выбираем published.

**2. Configurability > optimal defaults.**  
Ценность — в том что параметры **можно менять и сохранять результат**, не в оптимальности defaults. Default — разумный starting point, не «правильный ответ».

**3. Output traceability > catalog completeness.**  
Каталог из 100 событий с полным config snapshot и provenance — лучше каталога из 10000 без attribution параметров.

**4. Cross-source agreement > single-catalog recall.**  
Согласие нашего инструмента с **2+ независимыми reference catalogs** на конкретном событии — сильнее высокого recall против одного reference. Акцент на cross-tabulation (наш + Schuit + Lauvaux + CAMS), не «recall vs X = Y%».

**5. Honest limitations > pseudo-precision.**  

**6. Verifiability > complexity.**  

**7. Per-gas correctness > unified pipeline.**  

**8. Catalog quality > catalog size.**  

**9. Reproducibility > responsiveness.**  

**10. Region adaptation > global universality.**  

### 3.2. Что считается успехом проекта

**v1.0 успех (publication-ready tool):**
- Configurable Detection Surface реализована: пользователь может выбрать газ + период + AOI + Configuration Preset → получить Plume Event Catalog за < 10 минут
- Минимум 4 named Configuration Presets работают (`default`, `schuit_eq`, `lauvaux_eq`, `sensitive`)
- RCA импортирует минимум 3 reference catalogs (Schuit 2023, Lauvaux 2022, CAMS)
- Comparison Engine выдаёт cross-source comparison reports
- Каждый Run полностью воспроизводим (config snapshot + bit-identical output на повторе)
- Sanity-check passed: Норильск SO₂ persistent, Кузбасс CH₄ candidates, Бованенково CH₄ во время gas season
- Synthetic plume injection test пройден (recovered/injected > 0.7 для plumes ≥ 30 ppb)
- Открытый код на GitHub (MIT) + Asset с DOI на Zenodo (CC-BY 4.0)
- Опубликована tool-paper в СПДЗЗ или эквивалентный ВАК Q1
- Каталог использован в собственной публикации/диссертации

**v1.0 неуспех:**
- Каталог содержит wetland-driven false positives без класса diffuse_CH4
- Configurability нарушена: параметры зашиты в код, преsetы не работают
- RCA имеет silent ingestion failures
- Run без config snapshot выдан как результат
- Cross-source comparison reports содержат recall/precision без declared «vs reference, не vs ground truth»
- ML-модуль добавлен до накопления корпуса

### 3.3. Калибровка значимости

RU-PlumeScan не претендует превосходить SRON/Kayrros. Это **региональный воспроизводимый инструмент** опираясь на их методологии.

Сопоставление с distribution значимых работ:
- < CAMS Hotspot Explorer (нет ML, нет manual verification, регионально ограничен)
- ≈ MozhouGao Daily Screening Toolkit + IME extension + persistent source analysis + RCA
- > Cherepanova 2023 (более структурирован, multi-gas, configurable, open)

**Уникальная ниша**: первый открытый GEE-нативный configurable workbench для российской территории с встроенным cross-source validation. Цель — рабочий инструмент для собственных исследований + tool-paper в СПДЗЗ.

Это **gap-filling**: ниша между «студенческий проект» и «коммерческий operational tool».

---

## 4. Праксеология

### 4.1. Этапы развития проекта

**v0.5 — Implementation phase (текущая)**

Параллельная разработка трёх first-class модулей:

```
Detection Engine             Reference Catalog Adapter      Comparison Engine
├─ BG (background)           ├─ Schuit2023Ingester          ├─ spatial matching
├─ IND (industrial proxy)    ├─ Lauvaux2022Ingester         ├─ temporal matching
├─ PC-CH4                    ├─ CAMS_HotspotIngester        ├─ recall/precision
├─ PC-NO2                    ├─ Common Schema validator     ├─ cross-source agreement
└─ PC-SO2                    └─ versioned ref Assets         └─ disagreement maps
                ↓                          ↓                              ↓
                └────────  Configurable Detection Surface  ─────────────────┘
                                          ↓
                              UI App + Python API + Exports
```

Все три модуля разрабатываются вместе, не последовательно. Без RCA + Comparison инструмент не имеет validation pathway. Без Detection нет своего output. Все три необходимы для v1.0.

**v1.0 — Validated Configurable Tool (целевой релиз)**

После завершения v0.5 + validation campaign + написания tool-paper:
- Public GitHub release
- Zenodo Asset DOI
- Submission в СПДЗЗ
- Минимум 3 Configuration Presets validated на validation set

**v2.0 — ML-augmented detection (будущая фаза)**

Активируется ТОЛЬКО при выполнении всех условий:
- Накоплено ≥ 500 events Западной Сибири с **cross-source agreement labels** (events детектированные нашим v1 И минимум одним reference catalog)
- Размечены минимум 4 класса (confirmed plume / artifact / wetland / wind-ambiguous)
- Inter-rater agreement > 0.7 Cohen's kappa (если manual labeling добавлено)
- Documented temporal train/test split

**Источники labels для v2 (по убыванию confidence):**
1. Cross-source agreement: detected by us + 2+ reference catalogs → high-confidence positive
2. Disagreement: detected by us only / by reference only → review candidates
3. Manual expert review (если время позволит): supplemental labels

Cross-source agreement удешевляет накопление корпуса — не требуется ручная разметка для всех 500 events, agreement даёт baseline labels автоматически.

ML-задача v2: бинарный/multi-class classifier поверх v1 candidates. Не replacement v1, а уточнение confidence scoring.

**v3 — Integration phase (отдалённая, требует мутации DNA)**

Возможные направления:
- High-resolution follow-up через Sentinel-2 для confirmed v2 events
- Inversion для persistent sources (ограниченный IMI-style)
- Climate TRACE-style emission attribution

### 4.2. Forward-compatibility v0.5 → v1 → v2

Каждое событие v1 каталога проектируется как **training data для v2**. Структура Plume Event Feature:

**Detection поля (заполнены в v1):**
```
event_id, source_catalog="ours", gas, date_utc, geometry,
centroid_lon, centroid_lat, area_km2, n_pixels,
max_z, mean_z, max_delta, mean_delta,
wind_u, wind_v, wind_speed, wind_dir, wind_alignment_score,
nearest_source_id, nearest_source_distance_km,
class, confidence, qa_flags
```

**Configuration provenance (заполнены в v1):**
```
algorithm_version, params_hash, config_id, run_id, run_date
```

**Cross-source agreement (заполняются по мере накопления reference catalogs):**
```
matched_schuit2023: bool/null, schuit_event_id: string/null,
matched_lauvaux2022: bool/null, lauvaux_event_id: string/null,
matched_cams: bool/null, cams_event_id: string/null,
agreement_score: int (0-N matched references)
```

**ML-readiness slots (NULL в v1, заполняются позже):**
```
expert_label, label_source, label_date, label_confidence,
feature_vector (pre-computed для будущего ML)
```

События 2024–2026 годов автоматически становятся training set для v2. Cross-source agreement labels накапливаются непрерывно по мере регулярных Comparison Runs.

### 4.3. Роли человек / AI agents

**Человек (исследователь):**
- Финальная ответственность за публикации
- Решения о mutate DNA
- Expert labeling (если применяется)
- Validation против ground truth
- Калибровка параметров на known events
- Принятие/отклонение AI suggestions
- Решения о добавлении новых Reference Ingesters

**Claude (внешний архитектор):**
- DNA / RNA / Algorithm formulation
- DevPrompts для Claude Code
- Литобзор и cross-checking источников
- Адверсариальный ревью
- НЕ пишет production код

**Claude Code Desktop (исполняющий агент):**
- Реализация GEE JS / Python скриптов
- Run validation tests
- Bug fixing на уровне реализации
- НЕ принимает архитектурных решений

**Эпистемическое разделение:** AI генерирует и проверяет, человек решает и берёт ответственность. AI факт без верификации = гипотеза.

### 4.4. Контуры обратной связи и валидация

**Адверсариальная проверка обязательна** перед каждым переходом фазы:
- v0.5 → v1.0: внешний review каталога, synthetic plume injection, cross-source comparison runs
- v1.0 → v2.0: внешний review корпуса, проверка cross-source agreement labels
- DNA mutation: эксплицитная защита почему мутация необходима
- Каждый release: regression test против предыдущего baseline

**Эпистемический журнал** ведётся непрерывно:
- DNA mutations log
- Algorithm versions log
- Configuration Presets log
- Reference Ingesters log
- Validation runs log
- "Слишком хорошо" log

**Sanity checks** перед любым публичным выводом:
- Норильск SO₂ детектирован?
- Бованенково CH₄ during gas season детектирован?
- Wetland-only zones дают candidates? Если да → false positive rate проблема
- Кузбасс CH₄ candidates коррелируют с известными шахтами?
- Comparison Run с Schuit/Lauvaux выдаёт adequate cross-source agreement?

### 4.5. Критерии для voluntary остановки проекта

DNA фиксирует условия, при которых проект приостанавливается для пересмотра:

- Cross-source agreement < 30% events with 2+ references — методология не согласуется с established
- > 50% candidates в каталоге попадают в wetland-only zones — false positive rate неприемлем
- Synthetic plume recovery < 0.5 для plumes ≥ 30 ppb — фон или фильтры съедают сигнал
- Reference catalog ingestion даёт inconsistent results между runs — Common Schema или RCA нарушены
- Discovered fundamental flaw in published method we rely on

Это не failure — это эпистемический triage.

### 4.6. Change management

**Алгоритмические изменения (не в DNA):**
- Patch (тюнинг параметров, новый Configuration Preset, новый Reference Ingester): RNA update
- Minor (новый фильтр, новая метрика, новый класс события): Algorithm.md update + version bump
- Major (новый метод детекции, замена компонента): требует Algorithm v2.X с обоснованием + regression test

**DNA mutations:**
- Любая — требует записи: дата, инициатор, причина, обсуждённые alternatives, кто согласовал
- DNA versioning: 2.1, 2.2 (minor clarification), 3.0 (структурный пересмотр)
- DNA mutations не делает Claude самостоятельно. Только по запросу человека с явным обоснованием.

---

## 5. Тест качества DNA

> Убери из этого документа все технические детали реализации, конкретные параметры, упоминания GEE, TROPOMI, Schuit, Beirle, Fioletov. Остался ли смысл?

Должно остаться:
- Объект работы — настраиваемая поверхность детекции с множественными выходами, не просто каталог
- Различения candidate / plume / persistent / verified
- Различение Reference Catalog ≠ Ground Truth
- Различение Configuration ≠ Result
- Запреты на conflation pixel anomaly = plume, detection = quantification
- Приоритеты: configurability, output traceability, cross-source agreement, honest limitations
- Этапность: формальный детектор + RCA + comparison → корпус через cross-source agreement → ML
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
