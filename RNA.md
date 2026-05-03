# RU-PlumeScan — RNA v1.2

**Версия:** 1.2  
**Дата:** 2026-04-26  
**Статус:** Stack-specific operationalization of Algorithm v2.3  
**Соответствие:** DNA v2.2, CLAUDE.md v1.0, Algorithm.md v2.3  
**Замена:** RNA.md v1.1 (archived)

**Изменения v1.1 → v1.2 (CHANGE-0017):**

- §3.1 Asset structure: добавлены `RuPlumeScan/reference/` (protected_areas FeatureCollection + protected_areas_mask) и `RuPlumeScan/baselines/` (reference_<gas>_<period>, regional_<gas>_<period>)
- §7.1 default preset: добавлены секции `reference_baseline` и `background.mode = "dual_baseline"`
- §7.3 presets: добавлены `regional_only` и `reference_only` диагностические presets
- §11 NEW: Python module `src/py/setup/build_protected_areas_mask.py` для ingestion заповедников
- §11 NEW: JS module `src/js/modules/reference_baseline.js` для baseline construction
- §13 SO₂ Python fit module остаётся с v1.1
- §6.1 naming: добавлены reference baseline asset patterns

---

## 0. Структура документа

- §1: Стек и среда выполнения
- §2: Файловая структура репозитория
- §3: GEE Asset structure
- §4: GEE JavaScript module conventions
- §5: Python RCA module conventions
- §6: Naming conventions
- §7: Default values
- §8: Tile sizes, scales, projections
- §9: Logging и reproducibility
- §10: GEE-specific operational patterns
- §11: **Reference Baseline Builder implementation** (новая секция в v1.2)
- §12: Python-GEE integration patterns
- §13: UI App структура
- §14: Testing infrastructure
- §15: Quotas и performance management

---

## 1. Стек и среда выполнения

### 1.1. Основной стек

| Компонент | Версия | Назначение |
|---|---|---|
| GEE JavaScript API | current (2026) | Detection Engine, Comparison Engine, Reference Baseline Builder, UI App |
| GEE Python API | ≥ 0.1.380 | RCA upload, batch operations, automation, **protected areas ingestion** |
| `geemap` | ≥ 0.32 | Python interactive layer |
| Python | 3.10+ | RCA ingesters, SO₂ plume fit, **protected areas mask build** |
| `geopandas` | ≥ 0.14 | Loading Russian zapovedniks polygons (новое в v1.2) |
| Node.js | 18+ | dev tooling |

### 1.2. Среда выполнения по компоненту

| Компонент | Где |
|---|---|
| Detection Engine (CH₄/NO₂) | GEE Code Editor / Batch |
| Detection Engine (SO₂ rotation) | GEE Code Editor |
| SO₂ plume fit (full nonlinear) | Python (scipy.optimize) |
| Comparison Engine | GEE Code Editor / Batch |
| **Reference Baseline Builder** | **GEE Code Editor (per-zone climatology) + Python (Алтайский QA test)** |
| **Protected areas ingestion** | **Python (load polygons from data/, upload as GEE Asset)** |
| UI App | `users/<account>/RuPlumeScan` |
| RCA — Schuit, IMEO MARS, CAMS | Local Python → GEE Asset |
| Validation tests | GEE + Python |

### 1.3. Что НЕ в стеке

Без изменений с v1.1.

### 1.4. GEE проект

- **Project ID:** `nodal-thunder-481307-u1`
- **Asset root:** `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/`

---

## 2. Файловая структура репозитория

```
ru-plumescan/
├── DNA.md                          # v2.2
├── CLAUDE.md                       # v1.0
├── Algorithm.md                    # v2.3
├── RNA.md                          # этот файл (v1.2)
├── Roadmap.md                      # v1.1
├── OpenSpec.md
├── README.md
├── LICENSE
├── CITATION.cff
│
├── DevPrompts/
│   ├── P-00.0_repo_init.md          # done
│   ├── P-00.1_industrial_and_reference_proxy.md   # CHANGED v1.1 → v1.2 (dual scope)
│   ├── P-00.2_schema_validation.md
│   ├── P-00.3_presets_storage.md
│   ├── P-01.0a_reference_baseline.md     # NEW в v1.2
│   ├── P-01.0b_regional_climatology.md   # CHANGED (was P-01.0)
│   ├── P-01.1_kernels.md
│   ├── P-01.2_dual_baseline_validation.md   # NEW в v1.2
│   ├── P-02.0_detection_ch4.md
│   ├── P-02.1_detection_ch4_ime.md
│   ├── P-03.0_detection_no2.md
│   ├── P-04.0_detection_so2.md
│   ├── P-04.1_so2_python_fit.md
│   ├── P-05.0_rca_schuit.md
│   ├── P-05.1_rca_imeo_mars.md
│   ├── P-05.2_rca_cams.md
│   ├── P-06.0_comparison_engine.md
│   ├── P-07.0..4_ui_app.md
│   ├── P-08.0..4_validation.md
│   └── P-09.0..1_release.md
│
├── src/
│   ├── js/
│   │   ├── modules/
│   │   │   ├── config.js
│   │   │   ├── presets.js
│   │   │   ├── qa.js
│   │   │   ├── background.js                  # major rework в v1.2
│   │   │   ├── reference_baseline.js          # NEW в v1.2
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
│   │       └── unit/
│   │
│   └── py/
│       ├── rca/
│       │   ├── __init__.py
│       │   ├── common_schema.py
│       │   ├── base_ingester.py
│       │   ├── ingesters/
│       │   │   ├── schuit2023.py
│       │   │   ├── imeo_mars.py
│       │   │   ├── cams_hotspot.py
│       │   │   ├── carbon_mapper.py        # placeholder
│       │   │   └── cherepanova2023.py      # placeholder
│       │   ├── upload_to_gee.py
│       │   └── verify_ingestion.py
│       │
│       ├── setup/                          # NEW в v1.2 (extended)
│       │   ├── __init__.py
│       │   ├── build_industrial_proxy.py   # P-00.1 industrial part
│       │   ├── build_protected_areas_mask.py   # NEW в v1.2 (P-00.1 reference part)
│       │   ├── build_industrial_mask.py
│       │   ├── altaisky_qa_test.py         # NEW в v1.2 (Algorithm §11.4)
│       │   └── init_gee_assets.py
│       │
│       ├── so2_fit/                        # existing с v1.1
│       │   ├── __init__.py
│       │   ├── plume_models.py
│       │   ├── fit_engine.py
│       │   └── gee_integration.py
│       │
│       ├── synthetic/
│       ├── analysis/
│       ├── tests/
│       │   ├── test_schuit_ingester.py
│       │   ├── test_imeo_mars_ingester.py
│       │   ├── test_so2_fit.py
│       │   ├── test_protected_areas.py     # NEW в v1.2
│       │   └── test_synthetic_injection.py
│       ├── requirements.txt
│       └── pyproject.toml
│
├── docs/
│   ├── usage.md
│   ├── presets_guide.md
│   ├── reference_ingestion_guide.md
│   ├── reference_baseline_methodology.md   # NEW в v1.2
│   └── publication_methods.md
│
├── data/
│   ├── industrial_sources/
│   │   ├── kuzbass_mines.geojson
│   │   ├── khmao_yamal_oil_gas.geojson
│   │   ├── norilsk_complex.geojson
│   │   └── README.md
│   │
│   └── protected_areas/                    # NEW в v1.2
│       ├── yugansky.geojson                # 60.5°N, 74.5°E, 6500 km²
│       ├── verkhnetazovsky.geojson         # 63.5°N, 84.0°E, 6313 km²
│       ├── kuznetsky_alatau.geojson        # 54.5°N, 88.0°E, 4019 km²
│       ├── altaisky.geojson                # 51.5°N, 88.5°E, 8810 km² (optional)
│       ├── metadata.json                   # zone configs (internal_buffer_km, latitude_band, etc.)
│       └── README.md                        # source attribution + license info
│
└── .github/workflows/
    ├── lint.yml
    └── test.yml
```

---

## 3. GEE Asset structure

### 3.1. Полная иерархия (extended in v1.2)

```
projects/nodal-thunder-481307-u1/assets/RuPlumeScan/
│
├── backgrounds/                       # legacy V1 archived в _legacy_v1_archive/
│   ├── CH4/
│   ├── NO2/
│   └── SO2/
│
├── industrial/
│   ├── proxy_mask                     # Image (1=industrial buffered, 0=clean)
│   └── source_points                  # FeatureCollection (manual + GPPD + VIIRS proxy)
│
├── reference/                         # NEW в v1.2
│   ├── protected_areas                # FeatureCollection (4 zone polygons + metadata)
│   │                                   # properties: zone_id, zone_name_ru, internal_buffer_km,
│   │                                   #   centroid_lat, centroid_lon, area_km2_total, area_km2_useable,
│   │                                   #   natural_zone, latitude_band_min, latitude_band_max,
│   │                                   #   quality_status, established_year, iucn_category, official_url
│   └── protected_areas_mask           # Image (1 inside any zone, 0 outside)
│
├── baselines/                         # NEW в v1.2
│   ├── reference_CH4_2019_2025        # Image (per-month bands × 12)
│   │                                   # bands: ref_M01, ..., ref_M12, sigma_M01, ..., 
│   │                                   #        count_M01, ..., zone_id_M01, ...
│   ├── reference_NO2_2019_2025        # placeholder for v2 future
│   ├── reference_SO2_2019_2025        # placeholder for v2 future
│   ├── regional_CH4_2019_2025         # Image (existing с industrial buffer exclusion)
│   ├── regional_NO2_2019_2025
│   └── regional_SO2_2019_2025
│
├── catalog/
│   ├── CH4/
│   │   ├── default_2021               # уже с algorithm_version=2.3
│   │   ├── schuit_eq_2021
│   │   ├── imeo_eq_2021
│   │   ├── regional_only_2021         # diagnostic preset
│   │   ├── reference_only_2021        # diagnostic preset
│   │   ├── sensitive_2022
│   │   └── custom_<sha8>_2022
│   ├── NO2/
│   └── SO2/
│
├── refs/
│   ├── schuit2023_v1
│   ├── imeo_mars_2026-04
│   ├── cams_2026-04-25
│   └── ...
│
├── comparisons/
│   ├── ours_vs_schuit2023/
│   ├── ours_vs_imeo_mars/
│   └── cross_source_agreement_2021
│
├── presets/
│   ├── built_in/
│   │   ├── default_v2.3
│   │   ├── schuit_eq_v2.3
│   │   ├── imeo_eq_v2.3
│   │   ├── sensitive_v2.3
│   │   ├── conservative_v2.3
│   │   ├── regional_only_v2.3        # diagnostic
│   │   └── reference_only_v2.3       # diagnostic
│   └── custom/
│
├── runs/
└── validation/
    ├── synthetic_injection/
    ├── regression/
    └── altaisky_qa/                   # NEW в v1.2 — результаты QA test
        └── test_<date>                # Feature with pass/fail + metrics
```

### 3.2. Asset access permissions

Без изменений с v1.1.

### 3.3. Asset versioning

При обновлении Algorithm version (2.2 → 2.3):
- Новые runs пишутся в `RuPlumeScan/catalog/<gas>/<config>_v2.3_<period>`
- Старые runs остаются как `RuPlumeScan/catalog/<gas>/<config>_v2.2_<period>` (immutable)

При обновлении reference zones (новый zone, обновлённые boundaries):
- Versioned: `RuPlumeScan/reference/protected_areas_v1`, `_v2`, ...
- При active version change — full DNA mutation (DNA §2.3)

При обновлении reference baseline (новый target_year):
- Versioned: `RuPlumeScan/baselines/reference_CH4_2019_2025`, `_2019_2026` после end of 2026
- Backwards compatibility: старые baselines не удаляются

---

## 4. GEE JavaScript module conventions

Без изменений с v1.1.

---

## 5. Python RCA module conventions

Без изменений с v1.1.

---

## 6. Naming conventions (extended in v1.2)

### 6.1. GEE Assets

```
RuPlumeScan/<module>/<gas>/<config_id>_<period>
```

**Reference zones и baselines (НОВОЕ в v1.2):**
- `RuPlumeScan/reference/protected_areas` — FeatureCollection (single, not per-gas)
- `RuPlumeScan/reference/protected_areas_mask` — Image (single)
- `RuPlumeScan/baselines/reference_<GAS>_<YYYY>_<YYYY>` — per-gas reference baseline
- `RuPlumeScan/baselines/regional_<GAS>_<YYYY>_<YYYY>` — per-gas regional climatology
- `RuPlumeScan/validation/altaisky_qa/test_<YYYYMMDD>` — Feature with QA test results

**Reference zone IDs (used in metadata, не в asset paths):**
- `yugansky` — Юганский заповедник
- `verkhnetazovsky` — Верхнетазовский заповедник
- `kuznetsky_alatau` — Кузнецкий Алатау заповедник
- `altaisky` — Алтайский заповедник (optional)

snake_case, ASCII-only, не русский в asset paths.

### 6.2-6.7. Без изменений с v1.1

---

## 7. Default values для всех параметров Algorithm

### 7.1. Configuration `default` preset (extended in v1.2)

```javascript
// src/js/modules/presets.js

exports.DEFAULT_PRESET = {
  config_id: "default",
  algorithm_version: "2.3",
  
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
  
  // CHANGED в v1.2: dual baseline mode
  background: {
    mode: "dual_baseline",                    // "dual_baseline" | "regional_only" | "reference_only"
    primary: "reference",                      // primary baseline source когда consistent
    consistency_tolerance_ppb: 30,             // |reg - ref| < tolerance → consistent
    
    regional: {
      enabled: true,
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
  
  // NEW в v1.2
  reference_baseline: {
    enabled: true,
    use_zones: ["yugansky", "verkhnetazovsky", "kuznetsky_alatau"],
    use_altaisky_if_quality_passed: true,
    altaisky_quality_threshold_ppb: 30,
    stratification: "by_latitude",
    asset_path_template: "RuPlumeScan/baselines/reference_{gas}_{years}"
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
  
  wind: {
    source: "ECMWF/ERA5/HOURLY",
    u_band: "u_component_of_wind_10m",
    v_band: "v_component_of_wind_10m",
    min_speed_m_s: 2.0,
    max_speed_m_s: 12.0,
    alignment_max_deg: 45,
    ambiguous_speed_threshold_m_s: 1.5,
    grid_native_m: 31000
  },
  
  source_attribution: {
    industrial_buffer_km: 30,
    max_attribution_distance_km: 30,
    sources_asset: "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/industrial/source_points",
    reference_zones_asset: "projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas"
  },
  
  // CHANGED в v1.2: добавлен weight для consistency
  confidence: {
    high_z: 4.0,
    high_n_pixels: 4,
    high_alignment: 0.7,
    high_distance_km: 20,
    weights: {
      stat: 0.25,           // was 0.30
      geom: 0.20,
      wind: 0.20,           // was 0.25
      coverage: 0.15,
      consistency: 0.10,    // NEW в v1.2 (baseline_consistency_flag bonus)
      multi: 0.10
    },
    inside_reference_zone_penalty: 0.3,    // NEW в v1.2: multiplier when matched_inside_reference_zone
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
  
  ime: {
    enabled: false,
    u_eff_method: "schuit2023_10m",
    u_eff_a: 0.59,
    u_eff_b: 0.00,
    uncertainty_factor: 1.5,
    min_n_pixels_for_ime: 4
  },
  
  no2_specific: {
    tau_hours: 4.0,
    no2_to_nox_ratio: 1.32,
    period_min_months: 1,
    period_recommended_months: 3,
    min_observations_per_pixel: 25,
    min_wind_speed_m_s: 2.0,
    pixel_wise_L: false
  },
  
  so2_specific: {
    fit_method: "full_nonlinear",
    fitting_window_km: 50,
    fitting_window_auto_select: true,
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

Без изменений с v1.1.

### 7.3. Preset modifications

#### Existing presets (`schuit_eq`, `imeo_eq`, `sensitive`, `conservative`)

Все наследуют `default` background и `reference_baseline` settings (dual_baseline mode), но различаются в detection thresholds. См. v1.1 §7.3 + Algorithm §8.

#### NEW в v1.2: `regional_only` (diagnostic)

```javascript
regional_only: deepMerge(DEFAULT_PRESET, {
  config_id: "regional_only",
  background: { 
    mode: "regional_only",
    primary: "regional"
  },
  reference_baseline: { 
    enabled: false 
  }
});
```

Назначение: диагностика. Что было бы если только industrial buffer без reference. Use case: понять value of reference baseline approach.

#### NEW в v1.2: `reference_only` (diagnostic)

```javascript
reference_only: deepMerge(DEFAULT_PRESET, {
  config_id: "reference_only",
  background: { 
    mode: "reference_only",
    primary: "reference"
  },
  reference_baseline: { 
    enabled: true 
  }
});
```

Назначение: pure reference approach. Use case: characterize reference baseline alone, без regional cross-check.

---

## 8. Tile sizes, scales, projections

### 8.1. Default scales

См. v1.1 §8.1, без изменений. Все статистические reductions на scale ≥ 7000 m.

### 8.2. Projections

Без изменений с v1.1.

### 8.3. AOI definition

Без изменений с v1.1.

**NEW в v1.2: Reference zone polygon coordinates** хранятся в WGS84 (EPSG:4326) в GeoJSON files. При reference baseline build — clip TROPOMI к zone geometry в EPSG:4326, scale 7000m.

---

## 9. Logging и reproducibility

### 9.1. Canonical Provenance Computation (NEW в v1.2, P-01.0c)

Use `src/py/rca/provenance.py::compute_provenance` для **ALL** Run lifecycles. Не recompute `params_hash` в other code paths (per TD-0024 lessons — каждое independent recomputation produced different hash from slightly different config dict).

**Required pattern:**
```python
from rca.provenance import compute_provenance, write_provenance_log

# Once at process start
prov = compute_provenance(
    config=full_config_dict,
    config_id="default",  # или другой preset name
    period="2019_2025",
)

# Pre-submission
write_provenance_log(prov, status="STARTED", gas="CH4", period="2019_2025",
                     asset_id="...")

# Post-completion
ee.data.setAssetProperties(asset_id, prov.to_asset_properties())
write_provenance_log(prov, status="SUCCEEDED", gas="CH4", period="2019_2025",
                     asset_id="...", extra={"n_tasks": 12, "outcome": "A_FULL_SUCCESS"})
```

**Frozen dataclass invariant:** `Provenance` is `@dataclass(frozen=True)`. Same Provenance object reference passes через STARTED → submit → SUCCEEDED → asset properties. Mutation prevented at construction.

**Existing baseline assets backfilled** via `src/py/setup/backfill_provenance.py` (P-01.0c, 2026-05-XX) для DNA §2.1 запрет 12 compliance restoration. Каждый backfilled asset имеет:
- `provenance_backfill_date`
- `provenance_backfill_caveat` (honest reconstruction limitations)
- `provenance_backfill_commit` (P-01.0c PR commit SHA)
- `provenance_backfill_source_commit` (build script source commit)
- `pre_backfill_params_hash` (если был)

Future runs: provenance native (no backfill needed). Audit script `tools/audit_provenance_consistency.py` runs в CI (`--no-gee` mode validates allowlist + log schema; full GEE audit requires service account credentials, currently local-only).

---

Без изменений с v1.1, плюс:

**Reference baseline runs логируются отдельно** в `RuPlumeScan/runs/baseline_<gas>_<period>_<run_id>` с metadata:
- `zones_used`: list of zone_ids included
- `altaisky_quality_passed`: bool/null
- `altaisky_qa_test_metrics`: dict with diff values
- `pixels_per_zone`: count valid pixels per zone
- `aggregation_method`: "by_latitude_nearest"

---

## 10. GEE-specific operational patterns

### 10.1-10.9. Без изменений с v1.1.

### 10.10. Negative buffer для protected areas (NEW в v1.2)

При apply internal buffer (`buffer(-internal_buffer_km * 1000)`) к polygon, есть risk создать invalid geometry если polygon имеет complex coastlines. Pre-simplify полигон:

```javascript
function applyInternalBufferSafe(geometry, buffer_km) {
  // Simplify geometry first (tolerance 100m)
  const simplified = geometry.simplify({maxError: 100});
  
  // Apply negative buffer
  const buffered = simplified.buffer(-buffer_km * 1000);
  
  // Validate result is non-empty
  return ee.Algorithms.If(
    buffered.area().gt(1e6),  // > 1 km² minimum
    buffered,
    simplified  // fallback на исходную если buffer too aggressive
  );
}
```

---

## 11. Reference Baseline Builder implementation (NEW в v1.2)

### 11.1. Module overview

`src/js/modules/reference_baseline.js` — JS module для построения reference baseline в GEE.

`src/py/setup/build_protected_areas_mask.py` — Python script для initial ingestion заповедников.

`src/py/setup/altaisky_qa_test.py` — Python script для QA test Алтайского.

### 11.2. JavaScript module: reference_baseline.js

```javascript
// src/js/modules/reference_baseline.js

/**
 * Reference Baseline construction module.
 * 
 * Implements Algorithm v2.3 §11.
 * 
 * @module reference_baseline
 */

/**
 * Load Reference Clean Zones from Asset, filtered by quality status.
 * 
 * @param {object} config - config.reference_baseline
 * @returns {ee.FeatureCollection}
 */
exports.loadReferenceZones = function(config) {
  const zones_fc = ee.FeatureCollection(
    'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
  );
  
  // Filter to active zones (excluding pending/unreliable)
  let active = zones_fc.filter(ee.Filter.eq('quality_status', 'active'));
  
  // Filter to zones in use_zones list
  active = active.filter(ee.Filter.inList('zone_id', config.use_zones));
  
  // Optionally include Altaisky if quality passed
  if (config.use_altaisky_if_quality_passed) {
    const altaisky = zones_fc.filter(ee.Filter.and(
      ee.Filter.eq('zone_id', 'altaisky'),
      ee.Filter.eq('quality_status', 'active')
    ));
    active = active.merge(altaisky);
  }
  
  return active;
};

/**
 * Apply per-zone internal buffer (negative buffer).
 * 
 * @param {ee.FeatureCollection} zones
 * @returns {ee.FeatureCollection}
 */
exports.applyInternalBuffers = function(zones) {
  return zones.map(function(zone) {
    const buffer_km = ee.Number(zone.get('internal_buffer_km'));
    const simplified = zone.geometry().simplify({maxError: 100});
    const buffered = simplified.buffer(buffer_km.multiply(-1000));
    return zone.setGeometry(buffered);
  });
};

/**
 * Build per-zone climatology values.
 * 
 * @param {ee.FeatureCollection} zones (after internal buffer)
 * @param {string} gas - "CH4" | "NO2" | "SO2"
 * @param {number} target_year
 * @param {number} target_month
 * @param {object} config
 * @returns {ee.FeatureCollection} - zones с added properties: baseline_ppb, sigma_ppb, count
 */
exports.buildZoneBaselines = function(zones, gas, target_year, target_month, config) {
  const collections = {
    CH4: { 
      id: 'COPERNICUS/S5P/OFFL/L3_CH4', 
      band: 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected' 
    },
    NO2: { 
      id: 'COPERNICUS/S5P/OFFL/L3_NO2', 
      band: 'tropospheric_NO2_column_number_density' 
    },
    SO2: { 
      id: 'COPERNICUS/S5P/OFFL/L3_SO2', 
      band: 'SO2_column_number_density' 
    }
  };
  
  const ds = collections[gas];
  
  return zones.map(function(zone) {
    const zone_geom = zone.geometry();
    
    const filtered = ee.ImageCollection(ds.id)
      .select(ds.band)
      .filter(ee.Filter.calendarRange(2019, target_year - 1, 'year'))
      .filter(ee.Filter.calendarRange(target_month - 1, target_month + 1, 'month'))
      .map(function(img) { return img.clip(zone_geom); });
    
    // Per-pixel median within zone
    const median_image = filtered.reduce(ee.Reducer.median());
    const mad_image = filtered
      .map(function(img) { return img.subtract(median_image).abs(); })
      .reduce(ee.Reducer.median())
      .multiply(1.4826);
    const count_image = filtered.count();
    
    // Aggregate to single value per zone (mean over zone pixels)
    const baseline_value = median_image.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: zone_geom,
      scale: 7000,
      maxPixels: 1e8
    }).values().get(0);
    
    const sigma_value = mad_image.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: zone_geom,
      scale: 7000,
      maxPixels: 1e8
    }).values().get(0);
    
    const count_value = count_image.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: zone_geom,
      scale: 7000,
      maxPixels: 1e8
    }).values().get(0);
    
    return zone.set({
      'baseline_ppb': baseline_value,
      'sigma_ppb': sigma_value,
      'count_avg': count_value,
      'target_year': target_year,
      'target_month': target_month,
      'gas': gas
    });
  });
};

/**
 * Build latitude-stratified baseline image для AOI.
 * 
 * Server-side approach: для каждого pixel находим nearest zone by centroid latitude.
 * 
 * @param {ee.Geometry} aoi
 * @param {ee.FeatureCollection} zone_baselines (with baseline_ppb property)
 * @param {number} scale_m
 * @returns {ee.Image} с bands: reference_baseline, reference_sigma, zone_id_assignment
 */
exports.buildStratifiedBaseline = function(aoi, zone_baselines, scale_m) {
  // Convert zones list to per-zone images using painted polygons
  // Approach: для каждой zone create constant image with baseline value, 
  // weighted by inverse latitude distance
  
  const lat_image = ee.Image.pixelLonLat().select('latitude');
  
  // Use reduceRegions or feature-iteration approach
  // Simplified version: nearest zone by centroid latitude
  
  // Build images: для каждой zone — distance image
  const zones_list = zone_baselines.toList(zone_baselines.size().min(10));
  
  // Initialize: very large distance, default baseline = NaN
  const init_image = ee.Image.cat([
    ee.Image.constant(99999).rename('min_lat_distance'),
    ee.Image.constant(0).rename('reference_baseline'),
    ee.Image.constant(0).rename('reference_sigma'),
    ee.Image.constant('').rename('zone_id_assignment')
  ]);
  
  // Iterate zones: для каждой compute lat_distance, where smaller — update
  const result = ee.List.sequence(0, zones_list.size().subtract(1)).iterate(
    function(idx, accum) {
      const zone = ee.Feature(zones_list.get(idx));
      const zone_lat = ee.Number(zone.get('centroid_lat'));
      const zone_baseline = ee.Number(zone.get('baseline_ppb'));
      const zone_sigma = ee.Number(zone.get('sigma_ppb'));
      const zone_id = ee.String(zone.get('zone_id'));
      
      const lat_dist = lat_image.subtract(zone_lat).abs();
      const accum_img = ee.Image(accum);
      const closer_mask = lat_dist.lt(accum_img.select('min_lat_distance'));
      
      return accum_img
        .addBands(lat_dist.where(closer_mask.not(), accum_img.select('min_lat_distance'))
                          .rename('min_lat_distance'), null, true)
        .addBands(ee.Image.constant(zone_baseline)
                  .where(closer_mask.not(), accum_img.select('reference_baseline'))
                  .rename('reference_baseline'), null, true)
        .addBands(ee.Image.constant(zone_sigma)
                  .where(closer_mask.not(), accum_img.select('reference_sigma'))
                  .rename('reference_sigma'), null, true);
    },
    init_image
  );
  
  return ee.Image(result).reproject({crs: 'EPSG:4326', scale: scale_m}).clip(aoi);
};

/**
 * Full pipeline: load zones → buffer → build baselines → stratify
 * 
 * @param {string} gas
 * @param {number} target_year
 * @param {number} target_month
 * @param {ee.Geometry} aoi
 * @param {object} config
 * @returns {ee.Image}
 */
exports.buildReferenceBaseline = function(gas, target_year, target_month, aoi, config) {
  const zones = exports.loadReferenceZones(config.reference_baseline);
  const buffered = exports.applyInternalBuffers(zones);
  const zone_baselines = exports.buildZoneBaselines(buffered, gas, target_year, target_month, config);
  const stratified = exports.buildStratifiedBaseline(aoi, zone_baselines, config.analysis_scale_m);
  
  return stratified;
};

/**
 * Check if pixel is inside any reference zone (для matched_inside_reference_zone flag).
 * 
 * @param {ee.Geometry} pixel_or_geom
 * @returns {ee.String} zone_id или 'none'
 */
exports.checkInsideZone = function(pixel_or_geom) {
  const zones = ee.FeatureCollection(
    'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
  );
  
  const intersecting = zones.filterBounds(pixel_or_geom);
  
  return ee.Algorithms.If(
    intersecting.size().gt(0),
    intersecting.first().get('zone_id'),
    ee.String('none')
  );
};
```

### 11.3. Python module: build_protected_areas_mask.py

```python
"""
src/py/setup/build_protected_areas_mask.py

Build RuPlumeScan/reference/protected_areas FeatureCollection и protected_areas_mask Image
from manual GeoJSON files в data/protected_areas/.

Implements P-00.1 reference part (CHANGE-0017).
"""

import ee
import geopandas as gpd
import json
from pathlib import Path
from datetime import date

DATA_DIR = Path('data/protected_areas')

# Zone metadata (consistent with Algorithm v2.3 §2.2)
ZONE_METADATA = {
    'yugansky': {
        'zone_id': 'yugansky',
        'zone_name_ru': 'Юганский заповедник',
        'zone_name_en': 'Yugansky Strict Nature Reserve',
        'internal_buffer_km': 10,
        'centroid_lat': 60.5,
        'centroid_lon': 74.5,
        'area_km2_total': 6500,
        'natural_zone': 'middle_taiga_with_wetlands',
        'latitude_band_min': 58.0,
        'latitude_band_max': 65.0,
        'quality_status': 'active',
        'established_year': 1982,
        'iucn_category': 'Ia',
        'official_url': 'http://ugansky.ru'
    },
    'verkhnetazovsky': {
        'zone_id': 'verkhnetazovsky',
        'zone_name_ru': 'Верхне-Тазовский заповедник',
        'zone_name_en': 'Verkhne-Tazovsky Strict Nature Reserve',
        'internal_buffer_km': 5,
        'centroid_lat': 63.5,
        'centroid_lon': 84.0,
        'area_km2_total': 6313,
        'natural_zone': 'northern_taiga_permafrost',
        'latitude_band_min': 62.0,
        'latitude_band_max': 68.0,
        'quality_status': 'active',
        'established_year': 1986,
        'iucn_category': 'Ia',
        'official_url': 'https://oopt.info/index.php?oopt=125'
    },
    'kuznetsky_alatau': {
        'zone_id': 'kuznetsky_alatau',
        'zone_name_ru': 'Кузнецкий Алатау заповедник',
        'zone_name_en': 'Kuznetsky Alatau Strict Nature Reserve',
        'internal_buffer_km': 5,
        'centroid_lat': 54.5,
        'centroid_lon': 88.0,
        'area_km2_total': 4019,
        'natural_zone': 'mountain_taiga',
        'latitude_band_min': 53.0,
        'latitude_band_max': 57.0,
        'quality_status': 'active',
        'established_year': 1989,
        'iucn_category': 'Ia',
        'official_url': 'http://www.kuz-alatau.ru'
    },
    'altaisky': {
        'zone_id': 'altaisky',
        'zone_name_ru': 'Алтайский заповедник',
        'zone_name_en': 'Altaisky Strict Nature Reserve',
        'internal_buffer_km': 5,
        'centroid_lat': 51.5,
        'centroid_lon': 88.5,
        'area_km2_total': 8810,
        'natural_zone': 'high_mountain_with_alpine',
        'latitude_band_min': 51.0,
        'latitude_band_max': 54.0,
        'quality_status': 'optional_pending_quality',  # initial; updated после QA
        'established_year': 1932,
        'iucn_category': 'Ia',
        'official_url': 'https://www.altzapovednik.ru'
    }
}

def load_zone_polygon(zone_id: str) -> gpd.GeoDataFrame:
    """Load zone polygon from GeoJSON file."""
    path = DATA_DIR / f'{zone_id}.geojson'
    if not path.exists():
        raise FileNotFoundError(f'Missing: {path}. Run web verification.')
    return gpd.read_file(path)

def build_features():
    """Build list of ee.Feature for all zones."""
    ee.Initialize(project='nodal-thunder-481307-u1')
    
    features = []
    for zone_id, meta in ZONE_METADATA.items():
        gdf = load_zone_polygon(zone_id)
        
        if len(gdf) != 1:
            raise ValueError(f'{zone_id}: expected single polygon, got {len(gdf)}')
        
        # Convert geometry to ee.Geometry
        geom_json = json.loads(gdf.geometry.iloc[0].__geo_interface__) \
            if hasattr(gdf.geometry.iloc[0], '__geo_interface__') \
            else gdf.geometry.iloc[0].__geo_interface__
        
        ee_geom = ee.Geometry(geom_json)
        
        # Compute area_km2_useable (after internal buffer)
        useable_geom = ee_geom.simplify(100).buffer(-meta['internal_buffer_km'] * 1000)
        useable_area_m2 = useable_geom.area().getInfo()
        useable_area_km2 = useable_area_m2 / 1e6
        
        feature = ee.Feature(ee_geom, {
            **meta,
            'area_km2_useable': useable_area_km2,
            'ingestion_date': str(date.today())
        })
        features.append(feature)
    
    return features

def upload_protected_areas():
    """Upload protected_areas FeatureCollection to GEE."""
    features = build_features()
    fc = ee.FeatureCollection(features)
    
    asset_id = 'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
    
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description='upload_protected_areas',
        assetId=asset_id
    )
    task.start()
    print(f'Upload started: {task.id}')
    return task

def build_mask_raster():
    """Build protected_areas_mask Image (1 inside any zone, 0 outside).
    
    Run AFTER protected_areas FeatureCollection uploaded.
    """
    fc = ee.FeatureCollection(
        'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
    )
    
    # Apply internal buffers
    buffered_fc = fc.map(lambda f: ee.Feature(
        f.geometry().simplify(100).buffer(
            ee.Number(f.get('internal_buffer_km')).multiply(-1000)
        ),
        f.toDictionary()
    ))
    
    # Dissolve into single geometry
    dissolved = buffered_fc.union()
    
    # Convert to raster mask
    mask = ee.Image.constant(0).clip(dissolved.first().geometry()).paint(
        dissolved, 1
    )
    mask = mask.rename('protected_mask').uint8().reproject(
        crs='EPSG:4326', scale=7000
    )
    
    aoi = ee.Geometry.Rectangle([60, 55, 90, 75])
    
    task = ee.batch.Export.image.toAsset(
        image=mask,
        description='build_protected_areas_mask',
        assetId='projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas_mask',
        region=aoi,
        scale=7000,
        maxPixels=1e10
    )
    task.start()
    print(f'Mask export started: {task.id}')
    return task

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'mask':
        build_mask_raster()
    else:
        upload_protected_areas()
```

### 11.4. Python module: altaisky_qa_test.py

```python
"""
src/py/setup/altaisky_qa_test.py

QA test для Алтайского заповедника per Algorithm v2.3 §11.4.

Compares mean XCH4 inside Алтайский vs Кузнецкий Алатау after seasonal correction.
If diff > 30 ppb → flag as unreliable_for_xch4_baseline.
"""

import ee
import json
from datetime import date

ee.Initialize(project='nodal-thunder-481307-u1')

REFERENCE_FC = ee.FeatureCollection(
    'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
)

def get_zone_geometry(zone_id: str) -> ee.Geometry:
    zone = REFERENCE_FC.filter(ee.Filter.eq('zone_id', zone_id)).first()
    return zone.geometry().simplify(100)

def compute_seasonal_means(zone_geom, years_range, months):
    """Compute mean XCH4 over zone for given months across years range."""
    coll = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4') \
        .select('CH4_column_volume_mixing_ratio_dry_air_bias_corrected') \
        .filter(ee.Filter.calendarRange(years_range[0], years_range[1], 'year')) \
        .filter(ee.Filter.calendarRange(months[0], months[1], 'month'))
    
    mean_img = coll.reduce(ee.Reducer.mean())
    mean_value = mean_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=zone_geom,
        scale=7000,
        maxPixels=1e8
    ).values().get(0)
    
    return ee.Number(mean_value).getInfo()

def run_qa_test():
    """Algorithm v2.3 §11.4 QA test."""
    
    altaisky_geom = get_zone_geometry('altaisky')
    kuz_alatau_geom = get_zone_geometry('kuznetsky_alatau')
    
    # Internal buffers
    altaisky_buf = altaisky_geom.buffer(-5000)
    kuz_buf = kuz_alatau_geom.buffer(-5000)
    
    print('Computing seasonal means (this takes a few minutes)...')
    
    alt_summer = compute_seasonal_means(altaisky_buf, [2019, 2025], [6, 8])
    alt_winter = compute_seasonal_means(altaisky_buf, [2019, 2025], [12, 12])
    kuz_summer = compute_seasonal_means(kuz_buf, [2019, 2025], [6, 8])
    kuz_winter = compute_seasonal_means(kuz_buf, [2019, 2025], [12, 12])
    
    print(f'\nResults (XCH4 ppb):')
    print(f'  Altaisky summer:        {alt_summer:.1f}')
    print(f'  Altaisky winter:        {alt_winter:.1f}')
    print(f'  Kuznetsky Alatau summer: {kuz_summer:.1f}')
    print(f'  Kuznetsky Alatau winter: {kuz_winter:.1f}')
    
    abs_diff_summer = abs(alt_summer - kuz_summer)
    abs_diff_winter = abs(alt_winter - kuz_winter)
    seasonal_diff_alt = alt_summer - alt_winter
    seasonal_diff_kuz = kuz_summer - kuz_winter
    cycle_diff = abs(seasonal_diff_alt - seasonal_diff_kuz)
    
    print(f'\nDiagnostics:')
    print(f'  |alt_summer - kuz_summer|: {abs_diff_summer:.1f} ppb (threshold 30)')
    print(f'  |alt_winter - kuz_winter|: {abs_diff_winter:.1f} ppb (threshold 30)')
    print(f'  Seasonal cycle diff:       {cycle_diff:.1f} ppb (threshold 20)')
    
    # Pass criteria
    pass_summer = abs_diff_summer < 30
    pass_winter = abs_diff_winter < 30
    pass_cycle = cycle_diff < 20
    overall_pass = pass_summer and pass_winter and pass_cycle
    
    print(f'\nResults:')
    print(f'  Summer test: {"PASS" if pass_summer else "FAIL"}')
    print(f'  Winter test: {"PASS" if pass_winter else "FAIL"}')
    print(f'  Cycle test:  {"PASS" if pass_cycle else "FAIL"}')
    print(f'  Overall:     {"PASS — Алтайский useable" if overall_pass else "FAIL — Алтайский unreliable"}')
    
    # Save result
    result = {
        'test_date': str(date.today()),
        'altaisky_summer_ppb': float(alt_summer),
        'altaisky_winter_ppb': float(alt_winter),
        'kuznetsky_alatau_summer_ppb': float(kuz_summer),
        'kuznetsky_alatau_winter_ppb': float(kuz_winter),
        'abs_diff_summer_ppb': float(abs_diff_summer),
        'abs_diff_winter_ppb': float(abs_diff_winter),
        'cycle_diff_ppb': float(cycle_diff),
        'pass_summer': bool(pass_summer),
        'pass_winter': bool(pass_winter),
        'pass_cycle': bool(pass_cycle),
        'overall_pass': bool(overall_pass),
        'recommended_status': 'active' if overall_pass else 'unreliable_for_xch4_baseline'
    }
    
    # Upload result to Asset
    feature = ee.Feature(None, result)
    fc = ee.FeatureCollection([feature])
    
    asset_id = f'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/validation/altaisky_qa/test_{date.today().strftime("%Y%m%d")}'
    
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description='altaisky_qa_test',
        assetId=asset_id
    )
    task.start()
    
    print(f'\nResult uploaded: {asset_id}')
    
    if overall_pass:
        print('\nNext step: update Алтайский quality_status to "active" в protected_areas Asset')
    else:
        print('\nNext step: keep Алтайский quality_status as "unreliable_for_xch4_baseline"')
    
    return result

if __name__ == '__main__':
    result = run_qa_test()
    print('\n' + '='*60)
    print('JSON result:')
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 11.5. Reference Baseline Asset workflow

```
1. P-00.1 (revised): загружаем 4 zone polygons → protected_areas FeatureCollection + mask
   - 3 active по умолчанию (Юганский, Верхнетазовский, Кузнецкий Алатау)
   - 1 optional_pending_quality (Алтайский)

2. P-01.0a (NEW): для каждого target_year, target_month:
   - Run reference_baseline.buildReferenceBaseline для CH4
   - Export как RuPlumeScan/baselines/reference_CH4_<year>
   - ASYNC: run altaisky_qa_test.py (если ещё не запускался)

3. После Алтайский QA test:
   - Если pass: update protected_areas с altaisky.quality_status = 'active'
   - Если fail: keep status as is, log reason
   - Re-run reference baseline build (с/без Алтайского) если нужно

4. Detection runs (Phase 2A) используют reference_<gas>_<year> Asset как input.
```

---

## 12. Python-GEE integration patterns

Без изменений с v1.1.

---

## 13. UI App структура

Без изменений с v1.1, плюс:

**NEW в v1.2: Reference Baseline visualization layer**
- Toggle layer "Reference baseline" — отображает reference_<gas>_<year> Asset на map
- Toggle layer "Regional climatology" — отображает regional_<gas>_<year> Asset
- Toggle layer "Baseline divergence" — отображает |reference - regional| (для diagnostic)

**NEW в v1.2: Reference zone polygons overlay**
- Toggle layer "Protected areas" — показывает 4 zone boundaries на map
- Click on zone → popup с metadata (name, area, quality_status, baseline value for current month)

**Configuration UI extension:**
- Section "Background mode" с radio buttons: dual_baseline (default), regional_only (diagnostic), reference_only (diagnostic)
- Slider "Consistency tolerance (ppb)" в advanced settings (default 30)

---

## 14. Testing infrastructure

Без изменений с v1.1, плюс:

### 14.1. Reference baseline tests (NEW в v1.2)

`src/py/tests/test_protected_areas.py`:

```python
import pytest
import ee
from src.py.setup.build_protected_areas_mask import ZONE_METADATA, build_features

def test_zone_metadata_completeness():
    """All 4 zones have required metadata fields."""
    required_fields = [
        'zone_id', 'zone_name_ru', 'internal_buffer_km',
        'centroid_lat', 'centroid_lon', 'area_km2_total',
        'natural_zone', 'latitude_band_min', 'latitude_band_max',
        'quality_status', 'established_year', 'iucn_category'
    ]
    for zone_id, meta in ZONE_METADATA.items():
        for field in required_fields:
            assert field in meta, f'{zone_id} missing {field}'

def test_quality_status_values():
    """Quality status values are valid."""
    valid_statuses = {'active', 'optional_pending_quality', 'unreliable_for_xch4_baseline'}
    for zone_id, meta in ZONE_METADATA.items():
        assert meta['quality_status'] in valid_statuses

def test_latitude_bands_reasonable():
    """Latitude bands are reasonable for Western Siberia."""
    for zone_id, meta in ZONE_METADATA.items():
        assert 50 <= meta['latitude_band_min'] <= 70
        assert meta['latitude_band_min'] < meta['latitude_band_max']

def test_initial_altaisky_status():
    """Altaisky starts as optional_pending_quality."""
    assert ZONE_METADATA['altaisky']['quality_status'] == 'optional_pending_quality'

def test_internal_buffer_yugansky_larger():
    """Yugansky has larger internal buffer (close to oil&gas)."""
    assert ZONE_METADATA['yugansky']['internal_buffer_km'] >= 10
    assert all(
        ZONE_METADATA[z]['internal_buffer_km'] <= ZONE_METADATA['yugansky']['internal_buffer_km']
        for z in ['verkhnetazovsky', 'kuznetsky_alatau', 'altaisky']
    )
```

### 14.2. Regression baselines (extended)

Существующие из v1.1, плюс:

- **Reference baseline sanity check (NEW):** XCH4 inside Юганский в июле 2022 должен быть в range [1900, 1950] ppb. Если нет — baseline build flawed.
- **Cross-baseline consistency check (NEW):** для clean reference regions (not industrial), |reference_baseline - regional_climatology| < 30 ppb. Если diverge → contamination в regional suspect.

---

## 15. Quotas и performance management

Без изменений с v1.1.

**NEW в v1.2 considerations:**
- Reference baseline build добавляет ~10-15% к compute budget per Run (загрузка zones + per-zone reductions)
- Mitigation: cache reference baselines as Asset (built once per target_year, reused для всех months/configs)
- Reference baseline Asset размер: ~5 MB per gas per year (per-month bands)

---

## 16. Версионирование RNA

| Версия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-04-25 | Первая версия после Algorithm v2.1. |
| 1.1 | 2026-04-25 | Sync с Algorithm v2.2: ERA5_LAND→ERA5, IME defaults Schuit, IMEO MARS, no2_specific/so2_specific sections, SO2 Python plume fit. |
| 1.2 | 2026-04-26 | Sync с Algorithm v2.3 (CHANGE-0017): Reference Clean Zone support, protected_areas Asset structure, reference_baseline.js module, build_protected_areas_mask.py + altaisky_qa_test.py, dual_baseline mode default, regional_only/reference_only diagnostic presets, confidence weights включают consistency factor + inside_zone penalty. |

RNA обновляется при изменении Algorithm.md или Asset structure.
