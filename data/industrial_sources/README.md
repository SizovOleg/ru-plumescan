# `data/industrial_sources/`

GeoJSON-файлы с known industrial sources Западной Сибири — input для построения industrial proxy mask (DevPrompt P-00.1, [RNA.md §3.1](../../RNA.md)).

## Запланированные источники

| Файл | Содержание | Источник |
|---|---|---|
| `kuzbass_mines.geojson` | Угольные разрезы и шахты Кемеровской области | Manual digitization + OGIM |
| `khmao_yamal_oil_gas.geojson` | Нефтегазовые объекты ХМАО-Югры и ЯНАО | OGIM + manual |
| `norilsk_complex.geojson` | Норильский промышленный узел (Cu/Ni metallurgy) | Manual |
| `russia_power_plants.geojson` | ТЭЦ/ГРЭС России | GPPD subset (Global Power Plant Database) |

Дополнительные слои (формируются программно в P-00.1, не хранятся как GeoJSON):
- VIIRS Night Lights bright pixel mask (для пропущенных источников)

## Use

Скрипт `src/py/setup/build_industrial_proxy.py` (создаётся в P-00.1) загружает эти GeoJSON-ы, объединяет с GPPD и VIIRS, и публикует:
- `RuPlumeScan/industrial/source_points` (FeatureCollection)
- `RuPlumeScan/industrial/proxy_mask` (raster Image, 1=industrial, 0=clean)

## Лицензия

Данные в этой папке формируются из открытых источников (GPPD CC-BY-4.0, OGIM CC-BY-4.0, manual digitization). Атрибуция в каждом GeoJSON через `properties.source` и `properties.license`.
