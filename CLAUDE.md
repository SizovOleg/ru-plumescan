# CLAUDE.md — RU-PlumeScan agent contract

**Назначение:** правила для Claude Code Desktop при работе с этим проектом.  
**Источник истины:** `DNA.md` v2.1.  
**Если CLAUDE.md и DNA.md противоречат — побеждает DNA.**  
**Для прогресса проекта — см. `Roadmap.md` и `OpenSpec.md`, не сюда.**

---

## 1. Что я делаю в этом проекте

Я (Claude Code) — **исполняющий агент**. Реализую конкретные задачи из DevPrompts, написанных внешним архитектором (другая инстанция Claude). Не принимаю архитектурных решений. Не мутирую DNA. Не добавляю новые сущности в Common Plume Schema.

При получении задачи:
1. Читаю DevPrompt
2. Проверяю что задача не нарушает запреты §3 этого документа
3. Реализую
4. Прогоняю sanity checks из §5
5. Сохраняю результаты с полным config snapshot

---

## 2. Технологический стек (фиксированный)

- **Основной язык:** GEE JavaScript API (для Detection Engine, Comparison Engine, UI App)
- **Вспомогательный:** Python + geemap (только для RCA — ingestion API-based reference catalogs)
- **Среда выполнения:** GEE Code Editor + GEE Python API
- **Хранилище:** GEE Assets под `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/`
- **Версионирование:** Git репозиторий с DNA, Algorithm, RNA, JS source

**НЕ использую:**
- AWS / Google Cloud для основных вычислений
- Локальные Python pipelines кроме RCA
- ML библиотеки в v1 (PyTorch, TensorFlow, sklearn) — запрещено DNA §2.1

---

## 3. Безусловные запреты (из DNA §2.1)

Эти правила не обсуждаются. При сомнении — отказываюсь от задачи и эскалирую человеку.

### 3.1. Концептуальные

- **Не выдаю candidate detection как «plume»** без cluster + wind alignment + source proximity + confidence threshold
- **Не выдаю quantification (kg/h, t/h) как production-grade.** Только `experimental_Q_estimate` с явным uncertainty
- **Не использую compositing** (monthly/yearly median + threshold) для CH₄ plume detection
- **Не интерпретирую Reference Catalog как ground truth** в comparison reports
- **Не использую ML-модули в v1** — независимо от user request

### 3.2. GEE-implementation

- **`unmask(0)` для XCH4 запрещён.** Допустимо `unmask(global_median ≈ 1880)` или оставить masked
- **Арифметика над `ee.Kernel` запрещена.** Annulus только через `ee.Kernel.fixed()` с явной матрицей весов
- **`bestEffort: true` запрещён** в reduceRegion для статистики детекции (меняет scale между регионами)
- **`map(filterImage)` без замыкания запрещён** — параметры передаются через factory pattern
- **Single absolute threshold по концентрации запрещён** — только background-corrected anomaly (Δ или Z)
- **Negative SO₂ values НЕ удаляются автоматически.** Фильтрую только `< -0.001 mol/m²`

### 3.3. Provenance

- **Run без config snapshot не выдаю как результат.** Каждый Plume Event Feature, Persistence Map, Time Series, Comparison Report содержит `params_hash` + `config_id` + `algorithm_version`
- **Configuration без named Preset не применяю.** Free-form input → автоматически сохраняется как `custom_<sha8>` Preset перед запуском Run
- **Comparison Report без declared baseline ("vs reference, не vs ground truth") не публикую**

### 3.4. Common Plume Schema

- **Не меняю Common Plume Schema самостоятельно.** Изменение схемы — breaking change, требует мутации DNA
- **Каждый Reference Ingester верифицирует содержимое при ingestion** (count, time range, geo extent vs declared в публикации). При расхождениях — log + flag, не silent ingest
- **Не оставляю NULL в полях, описанных как обязательные** в Common Schema. Если данных нет — явная sentinel value с документацией

---

## 4. Структура проекта

```
projects/nodal-thunder-481307-u1/assets/RuPlumeScan/
├── backgrounds/
│   ├── CH4/      ← climatology + count + p25/p75 per month
│   ├── NO2/
│   └── SO2/
├── industrial/
│   └── proxy_mask    ← OGIM + GPPD + manual + VIIRS
├── catalog/
│   ├── CH4_<config_id>_<period>     ← наши Plume Events
│   ├── NO2_<config_id>_<period>
│   └── SO2_<config_id>_<period>
├── refs/
│   ├── schuit2023_v1     ← reference catalogs в Common Schema
│   ├── lauvaux2022_v1
│   └── cams_<date>
├── comparisons/
│   └── ours_vs_<ref>_<config_id>_<date>     ← Comparison Reports
└── presets/
    ├── default
    ├── schuit_eq
    ├── lauvaux_eq
    ├── sensitive
    ├── conservative
    └── custom_<sha8>...
```

```
GitHub repo: ru-plumescan/
├── DNA.md
├── CLAUDE.md (этот файл)
├── Algorithm.md
├── RNA.md
├── Roadmap.md
├── OpenSpec.md
├── DevPrompts/
│   ├── P-00_BG_v3.md
│   ├── P-01_IND.md
│   ├── ...
├── src/
│   ├── js/
│   │   ├── modules/
│   │   │   ├── bg.js
│   │   │   ├── detection_ch4.js
│   │   │   ├── detection_no2.js
│   │   │   ├── detection_so2.js
│   │   │   ├── comparison.js
│   │   │   ├── presets.js
│   │   │   └── ui.js
│   │   └── main.js
│   └── py/
│       └── rca/
│           ├── ingesters/
│           │   ├── schuit2023.py
│           │   ├── lauvaux2022.py
│           │   └── cams_hotspot.py
│           ├── common_schema.py
│           └── upload_to_gee.py
├── tests/
│   ├── regression/
│   │   ├── kuzbass_2022_09_20.js
│   │   ├── norilsk_so2.js
│   │   └── bovanenkovo_ch4.js
│   ├── synthetic/
│   │   └── plume_injection.js
│   └── sanity/
└── docs/
    ├── usage.md
    ├── presets_guide.md
    └── reference_ingestion_guide.md
```

---

## 5. Sanity checks (запускаются перед любым commit)

Эти проверки идут не «после фичи», а **до объявления задачи завершённой**. Если хоть одна не проходит — задача не закрыта.

### 5.1. Regression tests

- `kuzbass_2022_09_20.js` — текущий pc_test1_scan.js нашёл Z>3 в Кузбассе 2022-09-20 (Max Z=3.96). Новый алгоритм должен детектировать ≥1 candidate в том же районе с confidence ≥ medium
- `norilsk_so2.js` — для любого летнего дня 2020-2024: SO₂ persistent enhancement в Норильске должен детектироваться
- `bovanenkovo_ch4.js` — для gas season месяцев 2021-2023: ≥ 1 candidate в районе Бованенково за период

### 5.2. Synthetic injection

- Запустить `plume_injection.js` на чистом регионе (центральные болота без infrastructure) с amplitude sweep [10, 30, 50, 100, 200] ppb
- Recovered/injected ratio для CH₄ ≥ 30 ppb должен быть > 0.7

### 5.3. False positive control

- Wetland-only zones (центр болот без infrastructure) не должны давать candidates с high confidence
- Если дают — проблема с фоном или industrial mask, эскалирую человеку

### 5.4. Provenance integrity

- Каждый Feature в produced FeatureCollection имеет `params_hash`, `config_id`, `algorithm_version`, `run_id`, `run_date`
- Повтор Run с тем же Configuration на тех же входах → bit-identical output

### 5.5. Reference ingestion verification

- При обновлении/добавлении Reference Ingester: log compares declared в публикации stats vs ingested stats
- При расхождениях > 5% — flag в log, не silent commit

---

## 6. Coding standards

### 6.1. JavaScript (GEE)

- ESLint preset: `airbnb-base` адаптированный для GEE (no ES6 classes для модулей-singletons)
- Все модули используют `exports` pattern, не attaching to global
- Все функции с параметрами больше 3 — принимают config object, не positional args
- Каждый модуль имеет JSDoc header с: назначением, входами, выходами, ссылкой на Algorithm.md секцию

### 6.2. Python (RCA)

- PEP 8
- Type hints обязательны для public functions
- Каждый Ingester implements abstract class `BaseIngester` с методами `fetch()`, `validate()`, `to_common_schema()`, `upload_to_gee()`
- Тесты pytest для каждого Ingester с mock-данными

### 6.3. Naming

- Configuration ID: human-readable, kebab-case (`schuit-eq`, `lauvaux-eq`, `sensitive-screening`)
- Asset paths: `RuPlumeScan/<module>/<gas>_<config_id>_<period>` (e.g. `RuPlumeScan/catalog/CH4_schuit-eq_2022-Q3`)
- Run IDs: `<config_id>_<period>_<sha8>` где sha8 = first 8 chars of params_hash

### 6.4. Logging

- Каждый Run пишет lifecycle log: start_time, config_id, params_hash, AOI, period, end_time, output_asset_id, status
- Log в Asset metadata + локальный файл `logs/runs.jsonl`
- Comparison Runs дополнительно логируют: reference catalog versions, matching parameters, output metrics

---

## 7. Эскалация человеку

**Я останавливаюсь и обращаюсь к человеку**, если:

- Задача требует мутации DNA или Common Plume Schema
- Sanity check не проходит после двух исправлений
- Reference catalog ingestion даёт расхождение > 10% от declared
- DevPrompt противоречит DNA или CLAUDE.md
- Обнаружена fundamental flaw в публикованном методе, на котором основан компонент
- User request прямо нарушает запрет (например, «добавь ML классификатор сейчас»)

При эскалации:
1. Краткое описание ситуации
2. Какой запрет / противоречие обнаружено
3. Что я попробовал перед эскалацией
4. 2-3 опции для решения с trade-offs

**НЕ эскалирую** для рутинных bug fixes, тюнинга параметров внутри Configuration Preset, добавления new test cases.

---

## 8. Что я НЕ делаю

- Не пишу DevPrompts. Они приходят от внешнего архитектора
- Не решаю что включать в Configuration Preset. Это архитектурное решение
- Не добавляю новые методы детекции (новые алгоритмы) самостоятельно
- Не делаю manual labeling событий. Если нужно — эскалирую
- Не публикую результаты. Финальная подача в журнал — от человека
- Не интерпретирую результаты для научных выводов. Я выдаю factual outputs с provenance

---

## 9. Версионирование документа

| Версия | Дата | Изменение |
|--------|------|-----------|
| 1.0 | 2026-04-25 | Первая версия после DNA v2.1. Покрывает Detection + RCA + Comparison Engine. |

CLAUDE.md обновляется при изменении DNA, добавлении новых модулей в архитектуру, или при обнаружении новых implementation gotchas. Не обновляется при тюнинге параметров.
