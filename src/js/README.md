# `src/js/` — Earth Engine JavaScript modules

Этот каталог содержит JavaScript-код, исполняемый в Google Earth Engine (Code Editor / GEE App). См. [RNA.md §4](../../RNA.md) для conventions.

## Структура

| Подкаталог | Назначение |
|---|---|
| `modules/` | Переиспользуемые модули, импортируемые через `require('users/<account>/RuPlumeScan:modules/<name>')`. |
| `tests/regression/` | Регрессионные тесты на known events (Кузбасс 2022-09-20, Норильск SO₂, Бованенково CH₄) — см. [CLAUDE.md §5.1](../../CLAUDE.md). |
| `tests/unit/` | Unit-тесты модулей. |

## Запланированные модули (RNA §2)

- `schema.js` — валидация Common Plume Schema
- `presets.js` — Configuration Presets (default, schuit_eq, imeo_eq, sensitive, conservative)
- `qa.js`, `kernels.js`, `background.js` — общая инфраструктура
- `detection_ch4.js`, `detection_no2.js`, `detection_so2.js` — per-gas детекторы
- `ime.js`, `multi_gas.js`, `confidence.js`, `wind.js`, `source_attribution.js`
- `comparison.js`, `logging.js`, `ui.js`
- `main.js`, `batch_runner.js`

## Coding conventions

- ESLint preset: `airbnb-base` (адаптировано под GEE — без ES6-классов).
- Все модули экспортируют через `exports.<name>`, без global state.
- Параметры функций > 3 — через config object, не positional args.
- Factory pattern для closures внутри `.map()` (см. [DNA §2.1](../../DNA.md), [Algorithm §12](../../Algorithm.md)).
- JSDoc на каждой публичной функции с указанием раздела Algorithm.md.
