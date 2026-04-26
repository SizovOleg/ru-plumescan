# `src/py/` — Python-сторона RU-PlumeScan

Python используется только там, где GEE JavaScript недостаточно. См. [RNA.md §1.2 и §2.1](../../RNA.md) — четыре use-cases:

1. **RCA (Reference Catalog Adapter)** — ingest reference catalogs (Schuit 2023 CSV, UNEP IMEO MARS API, CAMS Hotspot CSV) → нормализация в Common Plume Schema → upload в GEE Asset.
2. **SO₂ full nonlinear plume fit** — `scipy.optimize.curve_fit` (4-параметрический Гауссов плюм). GEE JS не поддерживает nonlinear fit.
3. **Synthetic plume injection** — генерация синтетических плюмов для validation recovery test (DNA §4.4, CLAUDE §5.2).
4. **Sensitivity sweep automation** — запуск множественных GEE Runs через Earth Engine Python API.

## Структура

| Подкаталог | Содержимое |
|---|---|
| `rca/` | Reference Catalog Adapter — `common_schema.py`, `base_ingester.py`, `ingesters/`, `upload_to_gee.py` |
| `so2_fit/` | SO₂ Python plume fit (`plume_models.py`, `fit_engine.py`, `gee_integration.py`) — заполняется в DevPrompt P-04.1 |
| `synthetic/` | Синтетическая инъекция плюмов и recovery test — DevPrompt P-08.0 |
| `analysis/` | Sensitivity sweep, catalog export — DevPrompt P-08.2 |
| `setup/` | One-off скрипты: `init_gee_assets.py` (создание GEE Asset folders) |
| `tests/` | pytest |

## Установка

```bash
# Production runtime
pip install -r src/py/requirements.txt

# Development (включает pytest, ruff, black, mypy)
pip install -r src/py/requirements-dev.txt

# Аутентификация Earth Engine (один раз на машину)
earthengine authenticate
```

## Coding conventions ([RNA §5.6](../../RNA.md))

- PEP 8 strict, `black --line-length 100`, `ruff`.
- Type hints обязательны для public functions.
- Docstrings на русском в NumPy-стиле (CLAUDE.md global instructions: код на английском, комментарии — на русском).
- pytest для всех ingesters с mock-данными.

## Запуск тестов

```bash
pytest src/py/tests/ -v
```
