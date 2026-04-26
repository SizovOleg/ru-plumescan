# RU-PlumeScan — RNA v1.1

**Версия:** 1.1  
**Дата:** 2026-04-25  
**Статус:** Stack-specific operationalization of Algorithm v2.2  
**Соответствие:** DNA v2.1, CLAUDE.md v1.0, Algorithm.md v2.2  
**Замена:** RNA.md v1.0 (archived)

**Изменения v1.0 → v1.1:**
- §7.1 default preset: `wind.source` изменён `ECMWF/ERA5_LAND/HOURLY` → `ECMWF/ERA5/HOURLY` (full reanalysis, не land-surface replay; per Schuit 2023, ERA5-Land не эквивалентен ERA5 для plume direction)
- §7.1 default preset: `ime.u_eff_a` изменён `0.33` → `0.59`, `ime.u_eff_b` изменён `0.45` → `0.00` (Schuit 2023 TROPOMI 10m calibration вместо Varon 2018 GHGSat)
- §7.1 default preset: `ime.u_eff_method` изменён `"varon2018_ghgsat"` → `"schuit2023_10m"`
- §7.1 default preset: добавлены новые секции `so2_specific` и `no2_specific` с per-gas параметрами
- §7.2 per-gas overrides: добавлены SO₂ specific params (fit_method, fitting_window auto-select)
- §7.3 presets: `lauvaux_eq` заменён на `imeo_eq` (Lauvaux 2022 catalog не доступен публично)
- §3.1 Asset structure: `RuPlumeScan/refs/lauvaux2022_v1` → `RuPlumeScan/refs/imeo_mars_<YYYY-MM>` (monthly snapshots)
- §5 RCA: `Lauvaux2022Ingester` → `ImeoMarsIngester` (полная замена с CSV/GeoJSON download)
- §10.3 NO₂ reproject: формулы emission rate уточнены (Beirle 2019 Sci. Adv.: `E = D + N/τ`, `L = NOx/NO₂ = 1.32`, `τ = 4h`)
- §13.1 regression test: `lauvaux_eq` baseline заменён на `imeo_eq`

---

## 0. Структура документа

- §1: Стек и среда выполнения
- §2: Файловая структура репозитория
- §3: GEE Asset structure
- §4: GEE JavaScript module conventions
- §5: Python RCA module conventions
- §6: Naming conventions
- §7: Default values для всех параметров Algorithm
- §8: Tile sizes, scales, projections
- §9: Logging и reproducibility
- §10: GEE-specific operational patterns
- §11: Python-GEE integration patterns
- §12: UI App структура
- §13: Testing infrastructure
- §14: Quotas и performance management

---

## 1. Стек и среда выполнения

### 1.1. Основной стек

| Компонент | Версия | Назначение |
|---|---|---|
| GEE JavaScript API | current (2026) | Detection Engine, Comparison Engine, UI App |
| GEE Python API (`earthengine-api`) | ≥ 0.1.380 | RCA upload, batch operations, automation |
| `geemap` | ≥ 0.32 | Python interactive layer |
| Python | 3.10+ | RCA ingesters, analysis scripts, SO₂ plume fit |
| Node.js | 18+ | dev tooling (linting, testing JS), не runtime |

### 1.2. Среда выполнения по компоненту

| Компонент | Где выполняется |
|---|---|
| Detection Engine (CH₄/NO₂) | GEE Code Editor / GEE Batch tasks |
| Detection Engine (SO₂ — coordinate rotation) | GEE Code Editor |
| **SO₂ plume fit (full nonlinear)** | **Python (scipy.optimize) — JS не поддерживает nonlinear fit** |
| Comparison Engine | GEE Code Editor / GEE Batch tasks |
| UI App | `users/<account>/RuPlumeScan` published as GEE App |
| RCA — CSV ingesters (Schuit) | Local Python → GEE Asset upload |
| RCA — API ingesters (CAMS, IMEO MARS) | Local Python (cron) → GEE Asset upload |
| Validation tests | GEE Code Editor (regression) + Python (synthetic injection) |

### 1.3. Что НЕ в стеке

- **AWS, Google Cloud Compute** — не используются. Все вычисления в GEE + локальный Python.
- **GEOS-Chem, GEOS-FP моделирование** — не используется.
- **GEOS-FP wind data** — недоступен в GEE. Используем только ERA5 (declared limitation).
- **HARP / harpconvert** — не используется в v1.
- **PyTorch, TensorFlow, sklearn** — запрещено в v1 (DNA §2.1, ML только в v2).
- **Local L2 download** — не используется в v1.
- **Docker / containers** — не используется. Python окружение — venv или conda.

### 1.4. GEE проект

- **Project ID:** `nodal-thunder-481307-u1`
- **Asset root:** `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/`
- **App publishing:** `users/<account>/RuPlumeScan` (account TBD)

---

## 2. Файловая структура репозитория

```
ru-plumescan/
├── DNA.md                          # v2.1
├── CLAUDE.md                       # v1.0
├── Algorithm.md                    # v2.2
├── RNA.md                          # этот файл (v1.1)
├── Roadmap.md
├── OpenSpec.md
├── README.md
├── LICENSE
├── CITATION.cff
│
├── DevPrompts/
│   ├── P-00.0_repo_init.md
│   ├── P-00.1_industrial_proxy.md
│   ├── P-01.0_bg_climatology.md
│   ├── P-02.0_detection_ch4.md
│   ├── P-03.0_detection_no2.md
│   ├── P-04.0_detection_so2.md
│   ├── P-04.1_so2_python_fit.md      # NEW — Python wrapper for SO2 plume fit
│   ├── P-05.0_rca_schuit.md
│   ├── P-05.1_rca_imeo_mars.md       # CHANGED v1.0 (was rca_lauvaux)
│   ├── P-05.2_rca_cams.md
│   ├── P-06.0_comparison_engine.md
│   ├── P-07.0_ui_app.md
│   ├── P-08.0_validation_synthetic.md
│   └── P-09.0_validation_regression.md
│
├── src/
│   ├── js/
│   │   ├── modules/
│   │   │   ├── config.js
│   │   │   ├── presets.js
│   │   │   ├── qa.js
│   │   │   ├── background.js
│   │   │   ├── kernels.js
│   │   │   ├── detection_ch4.js
│   │   │   ├── detection_no2.js
│   │   │   ├── detection_so2.js
│   │   │   ├── ime.js
│   │   │   ├── multi_gas.js
│   │   │   ├── confidence.js
│   │   │   ├── wind.js
│   │   │   ├── source_attribution.js
│   │   │   ├── comparison.js
│   │   │   ├── schema.js
│   │   │   ├── logging.js
│   │   │   └── ui.js
│   │   ├── main.js
│   │   ├── batch_runner.js
│   │   └── tests/
│   │       ├── regression/
│   │       │   ├── kuzbass_2022_09_20.js
│   │       │   ├── norilsk_so2.js
│   │       │   └── bovanenkovo_ch4.js
│   │       └── unit/
│   │           ├── test_kernels.js
│   │           ├── test_background.js
│   │           └── test_schema.js
│   │
│   └── py/
│       ├── rca/
│       │   ├── __init__.py
│       │   ├── common_schema.py
│       │   ├── base_ingester.py
│       │   ├── ingesters/
│       │   │   ├── schuit2023.py
│       │   │   ├── imeo_mars.py        # CHANGED — replaces lauvaux2022.py
│       │   │   ├── cams_hotspot.py
│       │   │   ├── carbon_mapper.py    # placeholder
│       │   │   └── cherepanova2023.py  # placeholder
│       │   ├── upload_to_gee.py
│       │   └── verify_ingestion.py
│       ├── so2_fit/                    # NEW — Python wrapper for SO2 plume fit
│       │   ├── __init__.py
│       │   ├── plume_models.py         # full_nonlinear + fioletov_simplified
│       │   ├── fit_engine.py           # scipy.optimize wrappers
│       │   └── gee_integration.py      # sample → fit → upload back
│       ├── synthetic/
│       │   ├── __init__.py
│       │   ├── plume_injection.py
│       │   └── recovery_test.py
│       ├── analysis/
│       │   ├── sensitivity_sweep.py
│       │   └── catalog_export.py
│       └── tests/
│           ├── test_schuit_ingester.py
│           ├── test_imeo_mars_ingester.py    # CHANGED
│           ├── test_so2_fit.py               # NEW
│           └── test_synthetic_injection.py
│
├── docs/
│   ├── usage.md
│   ├── presets_guide.md
│   ├── reference_ingestion_guide.md
│   ├── developer_guide.md
│   └── publication_methods.md
│
├── data/
│   └── industrial_sources/
│       ├── kuzbass_mines.geojson
│       ├── khmao_yamal_oil_gas.geojson
│       ├── norilsk_complex.geojson
│       └── README.md
│
└── .github/
    └── workflows/
        ├── lint.yml
        └── test.yml
```

### 2.1. Justification для разделения JS / Python

- **JS** — всё что выполняется в GEE: detection (CH₄, NO₂, SO₂ rotation), comparison, UI.
- **Python** — четыре use cases:
  1. RCA: ingest reference catalogs (CSV/API → GEE Asset)
  2. **SO₂ full nonlinear plume fit** (scipy.optimize не доступен в GEE JS)
  3. Synthetic plume generation для validation
  4. Sensitivity sweep automation (запуск множественных JS Runs через Python API)

---

## 3. GEE Asset structure

### 3.1. Полная иерархия

```
projects/nodal-thunder-481307-u1/assets/RuPlumeScan/
│
├── backgrounds/
│   ├── CH4/
│   │   └── climatology_2019_2025      # Image, monthly bands + sigma + count
│   ├── NO2/
│   │   └── climatology_2019_2025
│   └── SO2/
│       └── climatology_2019_2025
│
├── industrial/
│   ├── proxy_mask                     # Image (raster, 1=industrial, 0=clean)
│   └── source_points                  # FeatureCollection
│                                       # properties включают: source_id, source_type,
│                                       #   source_name, country, region,
│                                       #   estimated_kt_per_year (для SO2 fitting window)
│
├── catalog/
│   ├── CH4/
│   │   ├── default_2021                # FeatureCollection (Plume Events)
│   │   ├── default_2022
│   │   ├── schuit_eq_2021
│   │   ├── imeo_eq_2021                # CHANGED (was lauvaux_eq)
│   │   ├── sensitive_2022
│   │   └── custom_<sha8>_2022
│   ├── NO2/
│   │   └── default_2022                # multi-month aggregate
│   └── SO2/
│       └── default_2022
│
├── refs/                               # Reference catalogs in Common Plume Schema
│   ├── schuit2023_v1                   # FeatureCollection (2974 plumes 2021)
│   ├── imeo_mars_2026-04                # CHANGED — monthly snapshot (was lauvaux2022)
│   ├── imeo_mars_2026-05                # next monthly snapshot
│   ├── cams_2026-04-25                 # weekly snapshot
│   ├── cams_2026-05-02
│   └── ...
│
├── comparisons/
│   ├── ours_vs_schuit2023/
│   │   ├── default_2021_<date>
│   │   │   ├── matched_events
│   │   │   ├── unmatched_a
│   │   │   ├── unmatched_b
│   │   │   ├── metrics
│   │   │   └── disagreement_density
│   │   └── ...
│   ├── ours_vs_imeo_mars/              # CHANGED
│   ├── ours_vs_cams/
│   └── cross_source_agreement_2021     # per-event agreement_score
│
├── presets/
│   ├── built_in/
│   │   ├── default_v2.2
│   │   ├── schuit_eq_v2.2
│   │   ├── imeo_eq_v2.2                # CHANGED (was lauvaux_eq)
│   │   ├── sensitive_v2.2
│   │   └── conservative_v2.2
│   └── custom/
│       └── custom_<sha8>...
│
├── runs/                               # Run lifecycle logs
│   └── <run_id>
│
└── validation/
    ├── synthetic_injection/
    │   └── recovery_results_<date>
    └── regression/
        └── baseline_<date>
```

### 3.2. Asset access permissions

- **Public read** для всех под `RuPlumeScan/` после v1.0 release
- **Write** только владелец GEE проекта
- При публикации в Zenodo — экспорт catalog FeatureCollections в GeoJSON

### 3.3. Asset versioning

При обновлении Algorithm version (2.1 → 2.2):
- Новые runs пишутся в `RuPlumeScan/catalog/<gas>/<config>_v2.2_<period>`
- Старые runs остаются как `RuPlumeScan/catalog/<gas>/<config>_v2.1_<period>` (immutable)

При обновлении Reference Catalog:
- IMEO MARS — monthly snapshot: `RuPlumeScan/refs/imeo_mars_<YYYY-MM>`
- CAMS — weekly snapshot: `RuPlumeScan/refs/cams_<YYYY-MM-DD>`
- Старые snapshots не удаляются (для reproducibility прошлых comparisons)

---

## 4. GEE JavaScript module conventions

### 4.1. Module structure

См. v1.0 §4.1, без изменений. Каждый модуль — отдельный `.js` файл, экспортирующий объект через `exports`. JSDoc обязательны. Factory pattern для closures в `.map()`.

### 4.2. Modules import path

```javascript
var bg = require('users/<account>/RuPlumeScan:modules/background');
var detection_ch4 = require('users/<account>/RuPlumeScan:modules/detection_ch4');
```

### 4.3. Coding standards

- No ES6 classes для GEE modules
- Factory pattern для closures
- JSDoc обязательно
- No global state
- Server-side only в hot paths
- Explicit `ee.Number()` / `ee.String()` casts

### 4.4. Error handling

GEE не имеет try/catch на server-side. Defensive coding через `ee.Algorithms.If()`.

### 4.5. Linting

- ESLint config: `airbnb-base`
- Pre-commit hook: lint + JSDoc presence check
- CI на PR

---

## 5. Python RCA module conventions

### 5.1. BaseIngester abstract class

```python
# src/py/rca/base_ingester.py

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

class BaseIngester(ABC):
    SOURCE_NAME: str
    DECLARED_STATS: dict
    
    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Fetch raw data from source."""
        pass
    
    @abstractmethod
    def validate(self, raw: pd.DataFrame) -> dict:
        """Verify against DECLARED_STATS. Raise ValidationError if discrepancy > 5%."""
        pass
    
    @abstractmethod
    def to_common_schema(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Convert to Common Plume Schema."""
        pass
    
    def ingest(self, asset_id: str) -> str:
        raw = self.fetch()
        validation = self.validate(raw)
        common = self.to_common_schema(raw)
        return self.upload_to_gee(common, asset_id)
    
    def upload_to_gee(self, common: pd.DataFrame, asset_id: str) -> str:
        from .upload_to_gee import dataframe_to_gee_asset
        return dataframe_to_gee_asset(common, asset_id, source=self.SOURCE_NAME)
```

### 5.2. Schuit2023 ingester (CSV from Zenodo)

```python
# src/py/rca/ingesters/schuit2023.py

import pandas as pd
import requests
from datetime import date
from ..base_ingester import BaseIngester

class Schuit2023Ingester(BaseIngester):
    SOURCE_NAME = "schuit2023"
    DECLARED_STATS = {
        "n_events": 2974,
        "time_range": (date(2021, 1, 1), date(2021, 12, 31)),
        "doi": "10.5281/zenodo.8087134",
        "paper_doi": "10.5194/acp-23-9071-2023"
    }
    ZENODO_URL = "https://zenodo.org/records/8087134/files/all_plumes_2021.csv"
    
    def fetch(self) -> pd.DataFrame:
        response = requests.get(self.ZENODO_URL)
        response.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(response.text))
    
    def validate(self, raw: pd.DataFrame) -> dict:
        n_actual = len(raw)
        n_expected = self.DECLARED_STATS["n_events"]
        deviation = abs(n_actual - n_expected) / n_expected
        if deviation > 0.05:
            raise ValueError(f"Schuit2023: deviation {deviation:.1%} > 5%")
        return {"n_actual": n_actual, "deviation": deviation}
    
    def to_common_schema(self, raw: pd.DataFrame) -> pd.DataFrame:
        common = pd.DataFrame()
        common['event_id'] = raw.apply(
            lambda r: f"schuit2023_CH4_{r['date'].replace('-','')}_{r['lat']:.4f}_{r['lon']:.4f}",
            axis=1
        )
        common['source_catalog'] = "schuit2023"
        common['source_event_id'] = raw.index.astype(str)
        common['schema_version'] = "1.0"
        common['ingestion_date'] = pd.Timestamp.utcnow().date()
        common['gas'] = "CH4"
        common['date_utc'] = pd.to_datetime(raw['date'])
        common['time_utc'] = raw['time_UTC']
        common['lat'] = raw['lat']
        common['lon'] = raw['lon']
        common['magnitude_proxy'] = raw['source_rate_t/h']
        common['magnitude_proxy_unit'] = "t/h"
        common['nearest_source_type'] = raw['estimated_source_type']
        common['quality_flag'] = "ml_classified"
        return common
```

### 5.3. ImeoMars ingester (CHANGED in v1.1 — replaces Lauvaux2022)

```python
# src/py/rca/ingesters/imeo_mars.py

import pandas as pd
import requests
from datetime import date
from ..base_ingester import BaseIngester

class ImeoMarsIngester(BaseIngester):
    """
    UNEP IMEO MARS / Eye on Methane data ingester.
    
    Replaces Lauvaux2022Ingester (per-event catalog не доступен публично, 
    only PDF supplement). IMEO MARS provides richer fields, monthly updates, 
    open license CC-BY-NC-SA 4.0.
    
    URL: methanedata.unep.org
    """
    SOURCE_NAME = "imeo_mars"
    DECLARED_STATS = {
        # IMEO MARS обновляется monthly, точное число events не constant
        "min_events_expected": 100,        # baseline sanity check
        "license": "CC-BY-NC-SA-4.0",
        "attribution_required": "UNEP IMEO"
    }
    
    PLUMES_CSV_URL = "https://methanedata.unep.org/api/plumes_export.csv"
    SOURCES_CSV_URL = "https://methanedata.unep.org/api/sources_export.csv"
    
    def fetch(self) -> pd.DataFrame:
        """Fetch both plumes and sources."""
        plumes_resp = requests.get(self.PLUMES_CSV_URL)
        plumes_resp.raise_for_status()
        from io import StringIO
        plumes = pd.read_csv(StringIO(plumes_resp.text))
        return plumes
    
    def validate(self, raw: pd.DataFrame) -> dict:
        n_actual = len(raw)
        if n_actual < self.DECLARED_STATS["min_events_expected"]:
            raise ValueError(
                f"IMEO MARS: only {n_actual} events fetched, "
                f"expected ≥ {self.DECLARED_STATS['min_events_expected']}. "
                f"Check API availability."
            )
        
        # Verify required fields present
        required = ['id_plume', 'lat', 'lon', 'tile_date', 'ch4_fluxrate', 
                   'wind_u', 'wind_v', 'sector', 'country']
        missing = [c for c in required if c not in raw.columns]
        if missing:
            raise ValueError(f"IMEO MARS: missing fields {missing}")
        
        return {"n_actual": n_actual, "fields_validated": True}
    
    def to_common_schema(self, raw: pd.DataFrame) -> pd.DataFrame:
        common = pd.DataFrame()
        common['event_id'] = raw.apply(
            lambda r: f"imeo_mars_CH4_{pd.to_datetime(r['tile_date']).strftime('%Y%m%d')}_{r['lat']:.4f}_{r['lon']:.4f}",
            axis=1
        )
        common['source_catalog'] = "imeo_mars"
        common['source_event_id'] = raw['id_plume'].astype(str)
        common['schema_version'] = "1.0"
        common['ingestion_date'] = pd.Timestamp.utcnow().date()
        common['gas'] = "CH4"
        common['date_utc'] = pd.to_datetime(raw['tile_date'])
        common['lat'] = raw['lat']
        common['lon'] = raw['lon']
        common['magnitude_proxy'] = raw['ch4_fluxrate']
        common['magnitude_proxy_unit'] = "t/h"
        common['nearest_source_type'] = raw['sector']
        common['wind_u'] = raw['wind_u']
        common['wind_v'] = raw['wind_v']
        common['quality_flag'] = raw['actionable'].apply(
            lambda x: "actionable" if x else "informational"
        )
        # Custom IMEO fields (kept for downstream analysis)
        common['_imeo_persistency'] = None  # filled from sources join
        common['_imeo_notified'] = raw['notified']
        common['_imeo_detection_institution'] = raw['detection_institution']
        return common
```

**Note:** точные API endpoint URLs могут отличаться. При реализации DevPrompt P-05.1 — проверить актуальные URLs на methanedata.unep.org.

### 5.4. CAMS Hotspot ingester (CSV download)

```python
# src/py/rca/ingesters/cams_hotspot.py

class CamsHotspotIngester(BaseIngester):
    SOURCE_NAME = "cams_hotspot"
    DECLARED_STATS = {
        "min_events_since_2024_05": 50,
        "license": "Copernicus attribution required"
    }
    CSV_URL = "https://atmosphere.copernicus.eu/methane-plumes-export.csv"
    
    # Implementation similar to ImeoMars; CSV fields:
    # date, time_UTC, lat, lon, source_rate_t/h, uncertainty_t/h, source_type, source_country
```

### 5.5. CSV → GEE Asset upload

```python
# src/py/rca/upload_to_gee.py

import ee
import pandas as pd

def dataframe_to_gee_asset(df: pd.DataFrame, asset_id: str, source: str) -> ee.batch.Task:
    """Upload DataFrame as GEE FeatureCollection Asset."""
    ee.Initialize()
    
    features = []
    for _, row in df.iterrows():
        geom = ee.Geometry.Point([float(row['lon']), float(row['lat'])])
        props = {
            k: (None if pd.isna(v) else 
                v.isoformat() if isinstance(v, pd.Timestamp) else
                str(v) if not isinstance(v, (int, float, bool)) else v)
            for k, v in row.items() 
            if k not in ['lat', 'lon', 'geometry']
        }
        features.append(ee.Feature(geom, props))
    
    fc = ee.FeatureCollection(features)
    
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description=f"upload_{source}_{pd.Timestamp.utcnow().strftime('%Y%m%d')}",
        assetId=asset_id
    )
    task.start()
    return task
```

### 5.6. Python coding standards

- PEP 8 strict
- Type hints для public functions
- Docstrings в NumPy style
- pytest для всех ingesters с mock-данными

`requirements.txt`:
```
earthengine-api>=0.1.380
geemap>=0.32
pandas>=2.0
requests>=2.30
shapely>=2.0
pyproj>=3.6
scipy>=1.11        # для SO2 nonlinear fit
numpy>=1.24
```

---

## 6. Naming conventions

См. v1.0 §6, без изменений кроме:

- Reference catalog assets: `RuPlumeScan/refs/imeo_mars_<YYYY-MM>` (не `lauvaux2022_v1`)
- Comparison reports: `RuPlumeScan/comparisons/ours_vs_imeo_mars/...`
- Presets: `imeo_eq` вместо `lauvaux_eq`

---

## 7. Default values для всех параметров Algorithm

### 7.1. Configuration `default` preset (full, обновлённый в v1.1)

```javascript
// src/js/modules/presets.js

exports.DEFAULT_PRESET = {
  config_id: "default",
  algorithm_version: "2.2",
  
  qa: {
    qa_value_min: 0.5,
    solar_zenith_max_deg: 70,
    sensor_zenith_max_deg: 60,
    uncertainty_max_ppb: 15,
    aod_max: 0.5,
    cloud_fraction_max: 0.3,
    physical_range_min_ppb: 1700,
    physical_range_max_ppb: 2200,
    so2_negative_floor_mol_m2: -0.001,
    snow_mask_source: "MODIS/061/MOD10A1",
    snow_mask_band: "NDSI_Snow_Cover",
    snow_mask_threshold: 40
  },
  
  background: {
    mode: "hybrid_climatology",
    climatology: {
      history_years_min: 2019,
      history_years_max_offset: -1,
      doy_window_half_days: 30,
      industrial_buffer_exclude_km: 30,
      min_count_per_pixel: 5
    },
    annulus: {
      inner_km: 50,
      outer_km: 150
    },
    lambda_climatology: 0.5,
    robust_sigma_method: "MAD",
    sigma_floor_units: 15
  },
  
  anomaly: {
    z_min: 3.0,
    delta_min_units: 30,
    relative_threshold_min_units: 15,
    percentile_min: 0.95
  },
  
  object: {
    min_pixels: 2,
    min_area_km2: 50,
    max_area_km2: 5000,
    connectedness: "4",
    max_size: 256
  },
  
  // CHANGED v1.0 → v1.1: ERA5_LAND → ERA5 (full reanalysis, not land-surface replay)
  wind: {
    source: "ECMWF/ERA5/HOURLY",
    u_band: "u_component_of_wind_10m",
    v_band: "v_component_of_wind_10m",
    min_speed_m_s: 2.0,
    max_speed_m_s: 12.0,
    alignment_max_deg: 45,
    ambiguous_speed_threshold_m_s: 1.5,
    grid_native_m: 31000           // ERA5 native (~31 km)
  },
  
  source_attribution: {
    industrial_buffer_km: 30,
    max_attribution_distance_km: 30,
    sources_asset: "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/industrial/source_points"
  },
  
  confidence: {
    high_z: 4.0,
    high_n_pixels: 4,
    high_alignment: 0.7,
    high_distance_km: 20,
    weights: {
      stat: 0.30,
      geom: 0.20,
      wind: 0.25,
      coverage: 0.15,
      multi: 0.10
    },
    discretization: {
      very_high: 0.85,
      high: 0.65,
      medium: 0.35
    }
  },
  
  diffuse: {
    pixel_threshold: 30,
    alignment_threshold: 0.3
  },
  
  // CHANGED v1.0 → v1.1: Schuit 2023 TROPOMI 10m calibration вместо Varon 2018 GHGSat
  ime: {
    enabled: false,
    u_eff_method: "schuit2023_10m",
    u_eff_a: 0.59,
    u_eff_b: 0.00,
    uncertainty_factor: 1.5,
    min_n_pixels_for_ime: 4
  },
  
  // NEW в v1.1
  no2_specific: {
    tau_hours: 4.0,                    // Beirle 2019 Sci. Adv.
    no2_to_nox_ratio: 1.32,             // L = NOx/NO2 (Beirle 2019)
    period_min_months: 1,
    period_recommended_months: 3,
    min_observations_per_pixel: 25,
    min_wind_speed_m_s: 2.0,
    pixel_wise_L: false                 // future: Beirle 2021 ESSD steady state
  },
  
  // NEW в v1.1
  so2_specific: {
    fit_method: "full_nonlinear",       // primary: 3-param fit (A, sigma_y, L)
                                         // fallback: "fioletov_simplified"
    fitting_window_km: 50,
    fitting_window_auto_select: true,   // 30/50/90 km для <100/100-1000/>1000 kt/yr
    buffer_km: 150,
    fixed_sigma_km_simplified: 15,
    fixed_tau_hours_simplified: 6.0
  },
  
  multi_gas: {
    R_match_km: 25,
    T_match_days: 1,
    weights: { CH4: 0.45, NO2: 0.35, SO2: 0.20 }
  },
  
  analysis_scale_m: 7000,
  spatial_resolution_native_m: 7000,
  
  params_hash: null
};
```

### 7.2. Per-gas overrides

```javascript
exports.GAS_OVERRIDES = {
  CH4: {
    qa: {
      qa_value_min: 0.5,
      uncertainty_max_ppb: 15,
      aod_max: 0.5,
      physical_range_min_ppb: 1700,
      physical_range_max_ppb: 2200
    },
    anomaly: {
      delta_min_units: 30,
      relative_threshold_min_units: 15
    },
    background: {
      sigma_floor_units: 15
    },
    ime: {
      enabled: false                    // opt-in для CH4 only
    }
  },
  
  NO2: {
    qa: {
      qa_value_min: 0.75,                // строже Schuit
      cloud_fraction_max: 0.3
    },
    anomaly: {
      delta_min_units: 0.00002,         // 20 µmol/m² в mol/m²
      relative_threshold_min_units: 0.00001,
      percentile_min: 0.95
    },
    background: {
      sigma_floor_units: 0.000001       // 1 µmol/m²
    },
    object: {
      min_pixels: 4,
      min_area_km2: 100
    },
    detection_method: "beirle_divergence"
  },
  
  SO2: {
    qa: {
      qa_value_min: 0.5,
      cloud_fraction_max: 0.3,
      so2_negative_floor_mol_m2: -0.001
    },
    anomaly: {
      delta_min_units: 0.0001,
      relative_threshold_min_units: 0.00005,
      percentile_min: 0.98
    },
    background: {
      sigma_floor_units: 0.00001
    },
    object: {
      min_pixels: 4,
      min_area_km2: 100
    },
    detection_method: "fioletov_rotation",
    requires_known_source: true
    // SO2-specific параметры в config.so2_specific (см. §7.1)
  }
};
```

### 7.3. Preset modifications

#### `schuit_eq` — близко к Schuit 2023 production thresholds

```javascript
schuit_eq: deepMerge(DEFAULT_PRESET, {
  config_id: "schuit_eq",
  anomaly: {
    delta_min_units: 50,
    relative_threshold_min_units: 20,
    percentile_min: 0.97
  },
  object: { min_pixels: 4, min_area_km2: 100 },
  background: { lambda_climatology: 0.6 }
})
```

#### `imeo_eq` — близко к UNEP IMEO MARS detection threshold (CHANGED v1.0 → v1.1)

```javascript
imeo_eq: deepMerge(DEFAULT_PRESET, {
  config_id: "imeo_eq",
  anomaly: {
    delta_min_units: 60,
    relative_threshold_min_units: 25,
    percentile_min: 0.98
  },
  object: { min_pixels: 5, min_area_km2: 150 },
  wind: { min_speed_m_s: 3.0, alignment_max_deg: 30 }
})
```

#### `sensitive` — низкие пороги для discovery

```javascript
sensitive: deepMerge(DEFAULT_PRESET, {
  config_id: "sensitive",
  anomaly: {
    z_min: 2.5,
    delta_min_units: 20,
    relative_threshold_min_units: 10,
    percentile_min: 0.90
  },
  object: { min_pixels: 2, min_area_km2: 30 },
  wind: { min_speed_m_s: 1.5, alignment_max_deg: 60 }
})
```

#### `conservative` — высокие пороги, only reliable

```javascript
conservative: deepMerge(DEFAULT_PRESET, {
  config_id: "conservative",
  anomaly: {
    z_min: 4.0,
    delta_min_units: 80,
    relative_threshold_min_units: 30,
    percentile_min: 0.99
  },
  object: { min_pixels: 6, min_area_km2: 200 },
  wind: { min_speed_m_s: 3.0, alignment_max_deg: 30 }
})
```

---

## 8. Tile sizes, scales, projections

### 8.1. Default scales

См. v1.0 §8.1, без изменений. Все статистические reductions на scale ≥ 7000 m.

### 8.2. Projections

| Operation | Projection | Why |
|---|---|---|
| QA, masking | EPSG:4326 | Default GEE |
| Detection (CH₄) | EPSG:4326 | Anomaly is scalar |
| **NO₂ divergence** | **EPSG:32642 (UTM 42N)** | **Critical: метрические dx/dy** |
| **SO₂ rotation** | **EPSG:32642 + rotation** | Rotated frame |
| Vector outputs | EPSG:4326 | Standard для GeoJSON |

**ERA5 grid native: 31 km** (был ERA5-Land 11 km в v1.0). При sampling wind на feature centroid использовать `scale: 31000`.

### 8.3. AOI definition

См. v1.0 §8.3, без изменений.

---

## 9. Logging и reproducibility

См. v1.0 §9, без изменений. Run lifecycle log, Asset metadata с params_hash, bit-identical reproducibility test, params_hash через deterministic checksum.

---

## 10. GEE-specific operational patterns

### 10.1. Annulus kernel implementation

См. v1.0 §10.1, без изменений.

### 10.2. Snow mask attachment

См. v1.0 §10.2, без изменений.

### 10.3. Reproject pattern для NO₂ divergence (UPDATED in v1.1)

```javascript
// src/js/modules/detection_no2.js

exports.computeEmissionRate = function(no2_avg, u_mean, v_mean, config) {
  var utm42n = ee.Projection('EPSG:32642');
  var grid_m = config.analysis_scale_m;  // 7000
  
  // Reproject to UTM
  var no2_proj = no2_avg.reproject({crs: utm42n, scale: grid_m});
  var u_proj = u_mean.reproject({crs: utm42n, scale: grid_m});
  var v_proj = v_mean.reproject({crs: utm42n, scale: grid_m});
  
  // Compute fluxes
  var flux_x = no2_proj.multiply(u_proj).rename('flux_x');
  var flux_y = no2_proj.multiply(v_proj).rename('flux_y');
  
  // Divergence in UTM
  var dx = grid_m;
  var dFx_dx = flux_x.translate(dx, 0, 'meters', utm42n)
    .subtract(flux_x.translate(-dx, 0, 'meters', utm42n))
    .divide(2 * dx);
  var dFy_dy = flux_y.translate(0, dx, 'meters', utm42n)
    .subtract(flux_y.translate(0, -dx, 'meters', utm42n))
    .divide(2 * dx);
  
  var divergence = dFx_dx.add(dFy_dy).rename('divergence');
  
  // Beirle 2019 emission formula: E = D + N/τ
  // where N = L · V_NO2 (NOx column = L * NO2 vertical column)
  var L = config.no2_specific.no2_to_nox_ratio;        // 1.32 default
  var tau_seconds = config.no2_specific.tau_hours * 3600;  // 14400 default
  
  var N_nox = no2_proj.multiply(L);
  
  var emission_rate = divergence
    .add(N_nox.divide(tau_seconds))
    .rename('emission_rate');
  
  // Optional: divergence-only mode (Beirle 2021 ESSD catalog approach)
  if (config.no2_specific.tau_hours === null) {
    emission_rate = divergence.rename('emission_rate');
  }
  
  return emission_rate;
};
```

### 10.4. Edge handling

См. v1.0 §10.4, без изменений.

### 10.5. Closure-free `.map()`

См. v1.0 §10.5, без изменений.

### 10.6. Memory chunking

См. v1.0 §10.6, без изменений.

---

## 11. Python-GEE integration patterns

### 11.1. GEE init в Python

```python
# src/py/rca/__init__.py

import ee
import os

def init_gee():
    project = os.environ.get('GEE_PROJECT', 'nodal-thunder-481307-u1')
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)
```

### 11.2. CSV → FeatureCollection upload

См. v1.0 §11.2, без изменений.

### 11.3. SO₂ Python plume fit (NEW в v1.1)

```python
# src/py/so2_fit/plume_models.py

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import erfc

def gaussian_exp_plume(coords, A, sigma_y, L, B):
    """
    Simplified Gaussian × exponential plume model in rotated coords.
    
    C(x', y') = A · exp(-x'/L) · exp(-y'²/(2·σ_y²)) + B
    
    coords: (x_prime, y_prime) — rotated coordinates (downwind, crosswind)
    """
    x_prime, y_prime = coords
    return A * np.exp(-x_prime / L) * np.exp(-y_prime**2 / (2 * sigma_y**2)) + B

def fit_full_nonlinear(sampled_points: np.ndarray, initial_guess: dict) -> dict:
    """
    Full 4-parameter fit (A, sigma_y, L, B) using scipy.optimize.curve_fit.
    
    sampled_points: array of shape (N, 3) with columns [x', y', concentration]
    initial_guess: dict with starting values
    
    Returns: dict with fit_params, std_errors, r_squared, success
    """
    coords = (sampled_points[:, 0], sampled_points[:, 1])
    values = sampled_points[:, 2]
    
    p0 = [initial_guess['A'], initial_guess['sigma_y'], 
          initial_guess['L'], initial_guess['B']]
    
    try:
        popt, pcov = curve_fit(gaussian_exp_plume, coords, values, p0=p0,
                                bounds=([0, 1, 5, -np.inf], [np.inf, 100, 200, np.inf]),
                                maxfev=5000)
        
        # Compute R²
        y_pred = gaussian_exp_plume(coords, *popt)
        ss_res = np.sum((values - y_pred)**2)
        ss_tot = np.sum((values - np.mean(values))**2)
        r_squared = 1 - ss_res / ss_tot
        
        return {
            'success': True,
            'A': popt[0],
            'sigma_y_km': popt[1],
            'L_km': popt[2],
            'B': popt[3],
            'A_err': np.sqrt(pcov[0, 0]),
            'sigma_y_err': np.sqrt(pcov[1, 1]),
            'L_err': np.sqrt(pcov[2, 2]),
            'r_squared': r_squared
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fit_simplified_fioletov(sampled_points: np.ndarray, fixed_params: dict) -> dict:
    """
    Simplified Fioletov 2020 fit: only α (total mass) is free.
    Fixed: σ = 15 km, τ = 6 h.
    """
    # Implementation: 1-parameter fit для α
    # Q = α / τ, with τ fixed
    pass
```

```python
# src/py/so2_fit/gee_integration.py

import ee
from .plume_models import fit_full_nonlinear

def process_so2_source(source_id: str, period: tuple, config: dict):
    """
    Full SO2 per-source processing:
    1. GEE: rotate stack to source frame, sample on grid
    2. Python: fit plume model
    3. GEE: upload result as Feature
    """
    # Step 1: trigger GEE rotation + sampling task
    # Step 2: fetch sampled points
    # Step 3: Python fit
    # Step 4: upload result
    pass
```

### 11.4. Sensitivity sweep automation

См. v1.0 §11.3, без изменений.

### 11.5. Synthetic plume injection

См. v1.0 §11.4, без изменений.

---

## 12. UI App структура

См. v1.0 §12, без изменений кроме:
- `imeo_eq` preset вместо `lauvaux_eq` в dropdown
- Reference comparison checkbox: Schuit / IMEO MARS / CAMS (вместо Lauvaux)

---

## 13. Testing infrastructure

### 13.1. Regression tests

Без существенных изменений. Baselines:
- `kuzbass_2022_09_20.js` — ≥1 high-confidence CH4 event на эту дату с `default` preset
- `norilsk_so2.js` — persistent SO2 detection любой летний день 2020-2024
- `bovanenkovo_ch4.js` — ≥1 CH4 candidate в gas season

### 13.2. Synthetic injection tests

Без изменений.

### 13.3. SO₂ Python fit tests (NEW в v1.1)

```python
# src/py/tests/test_so2_fit.py

import pytest
import numpy as np
from so2_fit.plume_models import gaussian_exp_plume, fit_full_nonlinear

def test_synthetic_recovery():
    """Generate synthetic plume, verify fit recovers parameters within 20%."""
    # Generate ground truth
    true_A, true_sigma, true_L, true_B = 100, 15, 50, 5
    x = np.random.uniform(-50, 200, 500)
    y = np.random.uniform(-100, 100, 500)
    coords = (x, y)
    values_true = gaussian_exp_plume(coords, true_A, true_sigma, true_L, true_B)
    values_noisy = values_true + np.random.normal(0, 5, 500)
    
    sampled = np.column_stack([x, y, values_noisy])
    
    # Fit
    result = fit_full_nonlinear(sampled, {
        'A': 50, 'sigma_y': 10, 'L': 30, 'B': 0
    })
    
    assert result['success']
    assert abs(result['A'] - true_A) / true_A < 0.20
    assert abs(result['sigma_y_km'] - true_sigma) / true_sigma < 0.20
```

### 13.4. CI

Без изменений.

---

## 14. Quotas и performance management

См. v1.0 §14, без изменений.

---

## 15. Версионирование RNA

| Версия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-04-25 | Первая версия после Algorithm v2.1. |
| 1.1 | 2026-04-25 | Sync с Algorithm v2.2 после verification через GPT-5.5: ERA5_LAND → ERA5 в default; IME U_eff defaults обновлены на Schuit 2023 TROPOMI calibration (0.59·U10); Lauvaux2022 → IMEO MARS как primary reference catalog; добавлены `no2_specific` и `so2_specific` секции в default preset; SO2 Python plume fit module (scipy.optimize) с full nonlinear primary + Fioletov simplified fallback; Beirle 2019/2021 bibliographic correction. |

RNA обновляется при изменении Algorithm.md или Asset structure.
