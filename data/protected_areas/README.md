# Protected Areas — Reference Clean Zones

Polygons и metadata для четырёх особо охраняемых природных территорий
(государственных природных заповедников, ООПТ федерального значения, IUCN Ia)
используемых RU-PlumeScan как **enforced clean reference zones** для positive-space
baseline construction (DNA v2.2 §1.2 «Reference Clean Zone»).

> **Важно (DNA v2.2 §1.5):** positive-space baseline (заповедники)
> ≠ negative-space buffer exclusion (industrial buffer). Это два разных
> baseline; используются **в комбинации** через dual baseline approach
> (Algorithm v2.3 §3.4). Reference baseline anchored в federal-protected zones,
> defensible перед reviewers, не зависит от полноты industrial inventory.

## Сводная таблица зон

| zone_id | Заповедник | Centroid | doc км² | Internal buffer | quality_status | Established |
|---|---|---|---|---|---|---|
| `yugansky` | Юганский | 60.5°N, 74.5°E | 6500 | **10 km** (oil&gas близко) | `active` | 1982 |
| `verkhnetazovsky` | Верхне-Тазовский | 63.5°N, 84.0°E | 6313 | 5 km | `active` | 1986 |
| `kuznetsky_alatau` | Кузнецкий Алатау | 54.5°N, 88.0°E | 4019 | 5 km | `active` | 1989 |
| `altaisky` | Алтайский | 51.5°N, 88.5°E | 8810 | 5 km | **`optional_pending_quality`** | 1932 |

`quality_status` definitions (RNA §11.3):
- `active` — используется в production reference baseline
- `optional_pending_quality` — нуждается в QA test (Algorithm §11.4) перед
  использованием. До прохождения test — НЕ использовать в production
- `unreliable_for_xch4_baseline` — QA test не пройден, исключён из baseline

## Почему Алтайский — `optional_pending_quality`

Алтайский — единственная высокогорная zone в наборе. TROPOMI XCH4
column retrieval над сложной горной топографией (high altitude alpine,
сильные variations в orography) исторически менее надёжен, чем над
равнинными зонами. До прогона **Algorithm §11.4 QA test** он не должен
включаться в production reference baseline.

**QA test (Algorithm v2.3 §11.4)** сравнивает mean XCH4 inside Алтайский
vs Кузнецкий Алатау после seasonal correction (оба находятся на похожих
широтах ~52-54°N).

Pass criteria:
- `|mean_alt_summer - mean_kuz_summer| < 30 ppb`
- `|mean_alt_winter - mean_kuz_winter| < 30 ppb`
- `|seasonal_diff_alt - seasonal_diff_kuz| < 20 ppb`

При passing → пользователь обновляет `quality_status` на `active` в этом
файле metadata + повторяет `python -m setup.build_protected_areas_mask upload`.

При failing → `quality_status` обновляется на `unreliable_for_xch4_baseline`,
zone исключается из baseline. См. **DNA v2.2 §2.1 запрет 16:** использовать
Алтайский в production без QA test — нарушение методологии.

QA test реализован в `src/py/setup/altaisky_qa_test.py` (RNA §11 + P-01.0a).

## Источники полигонов

Per researcher R1 priority: WDPA (PRIMARY) → OSM Overpass → OOPT info → Wikipedia
coords (verification only).

В этой ingestion использован **OSM** как primary (WDPA bulk download требует
accept terms через web UI и не доступен через unauthenticated WebFetch).
Все 4 zone polygons retrieved из OpenStreetMap relations, license `OSM-ODbL-1.0`.

| zone_id | OSM relation | Method | Simplification | Notes |
|---|---|---|---|---|
| `yugansky` | [3282537](https://www.openstreetmap.org/relation/3282537) | Nominatim API | `polygon_threshold=0.005` | Полная geometry exceeded WebFetch token limits. |
| `verkhnetazovsky` | [7009185](https://www.openstreetmap.org/relation/7009185) | polygons.openstreetmap.fr `params=0` | None (full resolution) | Source: Приказ Минприроды РФ № 234 от 31 мая 2018 г. (per OSM tags). |
| `kuznetsky_alatau` | [545334](https://www.openstreetmap.org/relation/545334) | polygons.openstreetmap.fr `params=0` | None (full resolution) | Текущая boundary OSM (после возможного boundary expansion 2010s). Documented area 4019 km² — original (1989); modern WDPA value ~4129 km². |
| `altaisky` | [1624131](https://www.openstreetmap.org/relation/1624131) | Nominatim API | `polygon_threshold=0.005` | MultiPolygon: основной массив + 3 малых island fragment. |

### License attribution

Все polygons распространяются под **OSM-ODbL-1.0**:
> © OpenStreetMap contributors. Data is licensed under the Open Data Commons
> Open Database License (ODbL). https://www.openstreetmap.org/copyright

Per-feature `data_license`, `data_source_url`, и `data_attribution` поля
заполнены в `<zone_id>.geojson` properties и переносятся в Asset.

При future re-ingestion, если WDPA bulk download станет доступен через CLI
(не web), приоритет следует переместить на WDPA per researcher R1 ordering.

## Verification log (area mismatch)

`area_km2_measured` будет вычислен Earth Engine `ee.Geometry.area()` при
upload (`build_protected_areas_mask.py upload` — `build_features()` пишет
field в Feature). Перед upload пользователь должен запустить:

```bash
cd src/py
python -m setup.build_protected_areas_mask validate
```

`validate` action использует local geodesic computation (Chamberlain-Duquette
formula, ~1% accuracy) и печатает таблицу:
```
zone_id              doc km²   meas km²   diff %  status
yugansky                 6500       ?       ?     ?
verkhnetazovsky          6313       ?       ?     ?
kuznetsky_alatau         4019       ?       ?     ?
altaisky                 8810       ?       ?     ?
```

R2 acceptable tolerance:
- **<5% diff**: OK, log only
- **5-10% diff**: WARN, document cause в этом README
- **10-20% diff**: ESCALATE — return для решения, НЕ commit Asset
- **>20% diff**: ESCALATE обязательно

**Особый случай Кузнецкого Алатау:** legitimate расхождение возможно (4019
documented vs ~4129 km² modern WDPA из-за boundary expansion 2010s). Используем
текущую OSM boundary как источник истины polygon. Если measured close to
~4019 — log without warning; если ~4129 — log warning «modern boundary
expansion accepted as canonical».

**Особый случай Юганского + Алтайского:** были применены Nominatim
simplification `polygon_threshold=0.005` (≈550m at these latitudes).
Simplification обычно даёт <2% area distortion для polygons >1000 км².
При diff > 5% — попробовать full-resolution download через polygons.openstreetmap.fr
напрямую (без WebFetch token limit).

## Schema fields per Feature (Common Reference Zone Schema)

Каждая `<zone_id>.geojson` содержит ровно один Feature со следующими fields
в `properties`:

| Field | Type | Source |
|---|---|---|
| `zone_id` | string | RNA §11.3 ZONE_METADATA |
| `zone_name_ru` | string | RNA §11.3 |
| `zone_name_en` | string | RNA §11.3 |
| `internal_buffer_km` | int | RNA §11.3 |
| `centroid_lat`, `centroid_lon` | float | RNA §11.3 |
| `area_km2_total` | int | RNA §11.3 (documented) |
| `area_km2_measured` | float | computed at ingestion (`build_protected_areas_mask.py upload`) |
| `area_km2_useable` | float | `measured - internal_buffer` (computed at ingestion) |
| `natural_zone` | string | RNA §11.3 |
| `latitude_band_min`, `latitude_band_max` | float | RNA §11.3 |
| `quality_status` | enum | `active` / `optional_pending_quality` / `unreliable_for_xch4_baseline` |
| `established_year` | int | OOPT records |
| `iucn_category` | string | `Ia` (Strict Nature Reserve) для всех 4 |
| `official_url` | URL | RNA §11.3 |
| `data_license` | string | `OSM-ODbL-1.0` |
| `data_source_url` | URL | OSM relation page |
| `data_attribution` | string | OSM contributor attribution |
| `coordinates_source` | string | `OSM` |
| `coordinates_verified_date` | date | `2026-04-26` |
| `ingestion_date` | date | computed at ingestion |
| `notes` | string | retrieval method, simplification details |

## Update procedure

1. **Updating polygon for existing zone** (e.g., boundary correction):
   - Replace `<zone_id>.geojson` с новой geometry, обновить `notes` field.
   - Запустить `python -m setup.build_protected_areas_mask validate`.
   - Если pass → запустить `upload`. Это создаст новую Asset version
     (RNA v1.2 §3.3 versioning rule).
   - Document в OpenSpec.md как minor change.

2. **Updating quality_status Алтайского** (после QA test):
   - Запустить `python -m setup.altaisky_qa_test` (создаётся в P-01.0a).
   - Read result: pass → `active`, fail → `unreliable_for_xch4_baseline`.
   - Edit `metadata.json` и `altaisky.geojson` properties.
   - Edit `ZONE_METADATA["altaisky"]["quality_status"]` в
     `build_protected_areas_mask.py`.
   - Re-run `upload` — создаст новую Asset version.

3. **Adding new zone or changing latitude bands** — требует **DNA mutation**
   per DNA v2.2 §2.3. Создавать как formal CHANGE entry в OpenSpec.md.

## References

- DNA.md v2.2 §1.2 — Reference Clean Zone entity
- DNA.md v2.2 §1.5 — Positive baseline ≠ negative buffer exclusion
- DNA.md v2.2 §2.1 — Запреты 15 (single-source baseline) и 16 (Алтайский без QA)
- Algorithm.md v2.3 §11 — Reference Baseline Builder
- Algorithm.md v2.3 §11.4 — Алтайский QA test
- RNA.md v1.2 §11.3 — Python implementation шаблон, ZONE_METADATA dict
- RNA.md v1.2 §3.1 — Asset structure (`reference/`, `baselines/`)
- DevPrompts/P-00.1_industrial_and_reference_proxy.md §2 — Часть 2 spec
- OpenSpec.md CHANGE-0017 — methodology rationale
