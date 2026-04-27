# `data/industrial_sources/`

GeoJSON-файлы с known industrial sources Западной Сибири — input для построения industrial proxy mask (см. [DevPrompts/P-00.1_industrial_and_reference_proxy.md](../../DevPrompts/P-00.1_industrial_and_reference_proxy.md), [RNA.md §3.1](../../RNA.md)).

## Состав после P-00.1 ingestion

| Файл | Type | Count | Источник | License |
|---|---|---|---|---|
| `kuzbass_mines.geojson` | manual GeoJSON | 7 | 3 researcher CRITICAL ANCHORS + 4 OSM verified (`landuse=quarry`) | mixed (public domain + ODbL) |
| `khmao_yamal_oil_gas.geojson` | manual GeoJSON | 7 | 3 CRITICAL ANCHORS (Бованенково/Уренгой/Ямбург) + 1 OSM (Тазовское) + 3 manual fields (Самотлор/Заполярное/Приобское — не в OSM) | mixed |
| `norilsk_complex.geojson` | manual GeoJSON | 5 | researcher CRITICAL ANCHORS (4 facilities + 1 aggregate point) | public domain |
| `additional_western_siberia.geojson` | manual GeoJSON | 3 | OSM `landuse=industrial` (Сургутская ГРЭС-1, ГРЭС-2, Нижневартовская ГРЭС) | ODbL-1.0 |
| `viirs_bright_proxy.geojson` | auto-generated | 474 | VIIRS DNB monthly composite 2022-2024, threshold 50 nW/cm²/sr, urban-masked via MODIS LC | viirs_proxy_unverified |
| (GPPD subset) | runtime fetch | 17 | `WRI/GPPD/power_plants` filter `country=RUS` + AOI [60,55,90,75] | CC-BY-4.0 |
| **Total uploaded** | — | **513** | — | per-feature `data_license` field |

## Per-feature schema

См. `SCHEMA_FIELDS` в [`src/py/setup/build_industrial_proxy.py`](../../src/py/setup/build_industrial_proxy.py). Critical поля:
- `source_id` (unique), `source_type` (`coal_mine` / `oil_gas` / `power_plant` / `metallurgy` / `other`)
- `estimated_kt_per_year_so2` для Norilsk facilities (Algorithm v2.3 §5.4 fitting window auto-select)
- `decommissioned` flag (Никелевый завод 2016)
- `verification_status`: `manual_verified` / `gppd_official` / `viirs_proxy_unverified`
- `data_license`, `data_attribution`, `data_source_url` (per-feature, canonical)
- `coordinates_source`, `coordinates_verified_date`

## VIIRS calibration provenance

Detailed log в [`src/py/setup/build_viirs_proxy.py`](../../src/py/setup/build_viirs_proxy.py):

- Composite: median 2022-2024 of `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`
- Threshold: **50 nW/cm²/sr** (Variant B per researcher decision: high-specificity over high-sensitivity, dual baseline защищает от false negatives)
- Urban filter: `MODIS/061/MCD12Q1` LC_Type1==13 + 5 km `focal_max` buffer (исключает city light glow)
- Anchor triage (3-category — pass / masked_by_filter / below_threshold): 3 PASS + 1 BELOW_THRESHOLD = `CALIBRATION_VALID_WITH_NOTES`
  - PASS: Сабетта LNG (759 nW), Ванкор (362), Уренгой (52)
  - BELOW_THRESHOLD: Северо-Уренгойский ГПЗ (4.6 nW) — coord clean, low radiance — APG utilization expected
- Calibration thumbnail PNG: `viirs_calibration_th50_*.png` (committed for documentation)

## VIIRS bright proxy distribution (post-ingest analysis)

Quick statistics 474 VIIRS-derived points:

| Bin | Count | % | Comment |
|---|---|---|---|
| radiance ≥ 100 nW/cm²/sr | 168 | 35.4% | definite flares (Сабетта, Ванкор, Уренгой dense) |
| 50–100 nW/cm²/sr | 131 | 27.6% | ambiguous (small flares / bright industrial) |
| < 50 nW/cm²/sr | 175 | 36.9% | edge effect of multi-pixel clusters — central pixel passes 50, edge mean lowers `viirs_radiance_mean` |
| **median / max / min** | **60.4 / 6042.2 / 4.0** | — | Сабетта LNG dominates max |

Spatial top bins (5°×5°):
- 60-65°N, 75-80°E: 112 points (Уренгой узел)
- 60-65°N, 70-75°E: 108 points (KhMAO центр, Сургут+Ноябрьск region)
- 65-70°N, 75-80°E: 78 points (северный Уренгой / Заполярное)
- 60-65°N, 65-70°E: 38 points (западный KhMAO, Ноябрьск)
- 65-70°N, 80-85°E: 34 points (Тазовский, Ванкорский кластер)

**Heat zones совпадают с expected oil&gas regions** — sanity OK. Sparse coverage в central wetlands и таёжных Юганских / Верхне-Тазовских регионах (≈ 0 points в 60-65°N × 80-85°E — там Юганский/Верхнетазовский заповедники, expected clean).

## Visual Verification of VIIRS Bright Pixels Distribution

Spatial distribution of 474 VIIRS proxy points visually inspected on 2026-04-27. Clusters in expected oil&gas regions (Сабетта, Уренгой, Ванкор). Sparse coverage in clean taiga. No major false-positive clusters in city centers (MODIS urban filter работает correctly). Manual industrial points overlay correctly with infrastructure.

VIIRS quantitative refinement (full histogram, clustering metrics, false-positive rate analysis) deferred to Phase 2A — см. [`docs/KNOWN_TODOS.md`](../../docs/KNOWN_TODOS.md).

## Use

```bash
# build manual GeoJSON inputs (этот шаг — manual editing of files в этой папке)

# generate VIIRS proxy (calibration + commit)
cd src/py
python -m setup.build_viirs_proxy --threshold 50 --calibrate  # check anchor triage + thumbnail
python -m setup.build_viirs_proxy --threshold 50 --commit     # save GeoJSON

# upload to GEE (manual + GPPD + VIIRS in one Asset)
python -m setup.build_industrial_proxy

# build raster mask
python -m setup.build_industrial_mask
```

## Лицензия

Данные сформированы из mixed-license sources. Per-feature `data_license` поле — canonical. Summary table в [LICENSE](../../LICENSE) Data Licensing section.

- `OSM-ODbL-1.0` — © OpenStreetMap contributors (Bachatsky, Kirov, Taldinsky, Erunakovsky, Krasnobrodsky, Mokhovsky, Тазовское, Сургутская ГРЭС-1/2, Нижневартовская ГРЭС)
- `GPPD-CCBY-4.0` — Global Power Plant Database (WRI) (17 Russian plants subset)
- `viirs_proxy_unverified` — derived from `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` (NOAA public domain), но caveat: **vectorized centroids являются proxy, не verified industrial sources**
- `researcher_contributed_public_domain` — CRITICAL ANCHORS от Сизова О. (ИПНГ РАН): Распадская, Бачатский, Кирова, Бованенково, Уренгой, Ямбург, Норильск per-facility, Самотлор, Заполярное, Приобское
