# RU-PlumeScan — Algorithm v2.2

**Версия:** 2.2  
**Дата:** 2026-04-25  
**Статус:** Формальная техническая спецификация Configurable Detection Surface  
**Соответствие DNA:** v2.1  
**Замена:** Algorithm.md v2.1 (archived)

**Изменения v2.1 → v2.2** (по результатам verification через GPT-5.5 на peer-reviewed источниках):

1. **§3.1 CH₄ framing** — переписан. Наш regional climatological background **не воспроизводит** Schuit per-scene normalization. Честное rephrasing: «threshold-based detection adapted from Schuit pre-ML logic with regional climatological background». Добавлена секция «Что мы заимствуем у Schuit и что отличается».
2. **§5 SO₂ алгоритм** — оставлен full nonlinear fit (3 параметра: A, σ_y, L) как primary; Fioletov simplified (`α/τ` с fixed σ, τ) добавлен как fallback preset.
3. **§5 SO₂ fitting window** — добавлен размер окна по magnitude: 30/50/90 km для <100/100-1000/>1000 kt/yr.
4. **§5 + §12.2 SO₂ detection limits** — явно прописаны: Norilsk (>1000 kt/yr) reliable, mid-size источники (~100 kt/yr) marginal.
5. **§6.4 IME U_eff** — defaults обновлены на Schuit 2023 TROPOMI calibration: `U_eff = 0.59·U10` для 10m wind (был Varon GHGSat `0.33·U10 + 0.45`). Региональные коэффициенты Западной Сибири — в Roadmap как future calibration.
6. **§9 Reference catalogs** — Lauvaux 2022 удалён (per-event catalog не публичен). Заменён на UNEP IMEO MARS (CC-BY-NC-SA, CSV/GeoJSON, более богатые поля).
7. **§3.9 + §4.5 + §12.2 Wind source** — single ERA5 declared explicitly как limitation. Schuit/CAMS используют ensemble ERA5+GEOS-FP, GEOS-FP в GEE недоступен. Добавлена честная декларация в known_limitations.
8. **§7 Multi-gas matching** — переформулировано как **novel component**, не reproduction. Peer-reviewed protocol для CH₄+NO₂/SO₂ event matching не существует. Это framing для tool-paper.
9. **NO₂ formula reference** — исправлена библиография: Beirle et al. **2019, Sci. Adv., doi:10.1126/sciadv.aax9800** (метод) + Beirle et al. **2021, ESSD, doi:10.5194/essd-13-2995-2021** (catalog), не «Beirle 2021 ACP».

Бывшая v2.0 (черновик внутри тех. записки пользователя 2026-04-25) и v2.1 архивированы.

**Источники методологии:**
- Schuit et al. 2023, ACP, doi:10.5194/acp-23-9071-2023 (CH₄ pre-ML logic, IME U_eff calibration)
- Varon et al. 2018, AMT, doi:10.5194/amt-11-5673-2018 (IME concept origin)
- Beirle et al. 2019, Sci. Adv., doi:10.1126/sciadv.aax9800 (NO₂ divergence method, τ=4h)
- Beirle et al. 2021, ESSD, doi:10.5194/essd-13-2995-2021 (NO₂ point source catalog, divergence-only)
- Fioletov et al. 2015 (plume model functional form)
- Fioletov et al. 2020, ACP, doi:10.5194/acp-20-5591-2020 (SO₂ TROPOMI application)
- Lorente et al. 2021, AMT, doi:10.5194/amt-14-665-2021 (TROPOMI XCH₄ QA, bias correction)

---

## 0. Структура документа

- §1: Принципы и инварианты
- §2: Доменная модель (Common Plume Schema, Configuration, Run)
- §3: Алгоритм CH₄ — regional threshold-based detection (adapted from Schuit pre-ML logic)
- §4: Алгоритм NO₂ — flux divergence following Beirle 2019/2021
- §5: Алгоритм SO₂ — wind rotation following Fioletov 2020
- §6: IME mass quantification (experimental, CH₄ only)
- §7: Multi-gas evidence и классификация (novel component)
- §8: Configuration Presets
- §9: Reference Catalog Adapter (RCA) — supported sources
- §10: Comparison Engine
- §11: Sensitivity analysis и synthetic injection
- §12: GEE implementation gotchas
- §13: Open questions и known limitations
- §14: Версионирование Algorithm

---

## 1. Принципы и инварианты

### 1.1. Архитектурные принципы

1. **Per-gas methodology.** CH₄, NO₂, SO₂ детектируются разными алгоритмами — у них разная физика, retrieval, lifetime и source types.
2. **Per-orbit, не composite.** Plumes — transient. Дневная медиана уничтожает signal. Анализируем каждую TROPOMI orbit (для CH₄) или multi-day stack для целей aggregation (NO₂/SO₂).
3. **Object-level detection.** Plume = связный объект, не одиночный пиксель.
4. **Wind-source validation.** Plume должен быть downwind от потенциального источника.
5. **Configurable parameters.** Все detection parameters — input через Configuration object, не hard-coded constants.
6. **Output traceability.** Каждое событие хранит полный config snapshot (params_hash + algorithm_version).
7. **Reproducible on GEE.** Никаких external compute (кроме RCA для reference catalogs), только GEE batch + UI.
8. **Region-agnostic implementation, region-tuned defaults.** Алгоритм работает на любом polygon AOI, defaults откалиброваны для Западной Сибири.

### 1.2. Что считается результатом алгоритма

**Plume Event Catalog** — FeatureCollection в GEE Asset со всеми Plume Events за period+AOI с заданным Configuration. Каждый Feature соответствует Common Plume Schema (см. §2.1) и содержит config snapshot.

**Persistence Map** — растровая поверхность плотности повторяющихся событий по сетке (опционально).

**Time Series для known sources** — temporal evolution counts/magnitude/confidence.

**Sensitivity Sweep** — выход multi-run analysis, FeatureCollection метрик по разным Configurations.

### 1.3. Что НЕ результат

- Single-pixel maxima без object structure
- Composite means без disaggregation
- Threshold values сами по себе (это параметры, не результаты)
- Z-score карты без object extraction
- IME quantification без явного uncertainty disclosure (см. §6)

---

## 2. Доменная модель

### 2.1. Common Plume Schema

Унифицированная структура для всех каталогов (наш + reference). Поля сгруппированы по назначению.

#### Идентификация
```
event_id          : string  (unique, format "<source>_<gas>_<YYYYMMDD>_<lat6>_<lon6>")
source_catalog    : string  (one of: "ours", "schuit2023", "imeo_mars", "cams_hotspot", ...)
source_event_id   : string  (original ID в reference catalog, если есть; иначе ours_id)
schema_version    : string  ("1.0")
ingestion_date    : date    (UTC, when ingested into our system)
```

#### Базовая атрибутика события
```
gas               : enum    ("CH4" | "NO2" | "SO2")
date_utc          : date    (date of TROPOMI overpass producing detection)
time_utc          : time    (overpass time; null if multi-day aggregate)
orbit             : int     (TROPOMI orbit number; null if reference catalog)
```

#### Геометрия
```
lon               : float   (centroid longitude, WGS84)
lat               : float   (centroid latitude, WGS84)
geometry          : Polygon (object boundary; null if point-only reference)
area_km2          : float   (object area; null if point-only)
n_pixels          : int     (число валидных пикселей при analysis_scale; null если N/A)
```

#### Detection metrics (наш source)
```
max_z             : float   (max Z-score over object; null если ours=false)
mean_z            : float   (mean Z-score)
max_delta         : float   (max Δ over background, в исходных единицах газа)
mean_delta        : float   (mean Δ)
detection_method  : string  ("regional_threshold" | "beirle_divergence" | "fioletov_rotation")
```

#### Wind context (ERA5 hourly, ближайший hour к overpass)
```
wind_u                 : float   (m/s)
wind_v                 : float   (m/s)
wind_speed             : float   (sqrt(u²+v²), m/s)
wind_dir_deg           : float   (atan2(v,u) · 180/π + 180, °N)
plume_axis_deg         : float   (direction of plume axis; null если объект < 3 пикселей)
wind_alignment_score   : float   (|cos(plume_axis - wind_dir)|, [0,1]; null если plume_axis null)
wind_source            : string  ("ERA5_HOURLY" — single source, declared limitation)
```

#### Source attribution
```
nearest_source_id              : string
nearest_source_distance_km     : float   
nearest_source_type            : enum    ("coal_mine" | "oil_gas" | "power_plant" | "metallurgy" | "urban" | null)
```

#### Magnitude proxy
```
magnitude_proxy        : float
magnitude_proxy_unit   : string  ("ppb" | "µmol/m²" | "t/h")
```

#### Quantification (experimental, см. §6)
```
ime_kg                       : float   (Integrated Methane Enhancement; null для NO₂/SO₂)
q_kg_h_experimental          : float   (Q estimate; ALWAYS with disclaimer)
q_uncertainty_factor         : float   (multiplicative, e.g. 1.5 = ±50%)
quantification_method        : string  ("schuit2023_ime_10m" | "schuit2023_ime_pbl" | 
                                         "fioletov_full_fit" | "fioletov_simplified" | null)
quantification_disclaimer    : string  (text для UI display)
```

#### Classification
```
class                  : enum    (см. DNA §1.3)
confidence             : enum    ("low" | "medium" | "high" | "very_high")
confidence_score       : float   ([0,1], числовой confidence перед discretization)
qa_flags               : string  (comma-separated)
```

#### Cross-source agreement (заполняются Comparison Engine)
```
matched_schuit2023        : bool
schuit_event_id           : string
matched_imeo_mars         : bool
imeo_event_id             : string
matched_cams              : bool
cams_event_id             : string
agreement_score           : int     (0..N matched references)
last_comparison_date      : date
```

#### Configuration provenance (обязательно для ours)
```
algorithm_version    : string  ("2.2")
config_id            : string  ("default" | "schuit_eq" | "imeo_eq" | "sensitive" | "conservative" | "custom_<sha8>")
params_hash          : string
run_id               : string  ("<config_id>_<YYYYMMDD>_<sha8>")
run_date             : date
```

#### ML-readiness slots (NULL в v1, заполняются позже)
```
expert_label             : enum    (null | "confirmed_plume" | "artifact" | "wetland" | "wind_ambiguous" | ...)
label_source             : string
label_date               : date
label_confidence         : int     ([1..5])
feature_vector           : string  (JSON-encoded)
```

### 2.2. Configuration object

```json
{
  "config_id": "default",
  "algorithm_version": "2.2",
  "gas": "CH4",
  
  "qa": {
    "qa_value_min": 0.5,
    "solar_zenith_max_deg": 70,
    "sensor_zenith_max_deg": 60,
    "uncertainty_max_ppb": 15,
    "aod_max": 0.5,
    "physical_range_min_ppb": 1700,
    "physical_range_max_ppb": 2200,
    "snow_mask_source": "MODIS_NDSI",
    "snow_mask_threshold": 40
  },
  
  "background": {
    "mode": "hybrid_climatology",
    "climatology": {
      "history_years_min": 2019,
      "history_years_max_offset": -1,
      "doy_window_half_days": 30,
      "industrial_buffer_exclude_km": 30,
      "min_count_per_pixel": 5
    },
    "annulus": {
      "inner_km": 50,
      "outer_km": 150
    },
    "lambda_climatology": 0.5,
    "robust_sigma_method": "MAD",
    "sigma_floor_units": 15
  },
  
  "anomaly": {
    "z_min": 3.0,
    "delta_min_units": 30,
    "relative_threshold_min_units": 15,
    "percentile_min": 0.95
  },
  
  "object": {
    "min_pixels": 2,
    "min_area_km2": 50,
    "max_area_km2": 5000,
    "connectedness": "4",
    "max_size": 256
  },
  
  "wind": {
    "source": "ERA5_HOURLY",
    "u_band": "u_component_of_wind_10m",
    "v_band": "v_component_of_wind_10m",
    "min_speed_m_s": 2.0,
    "max_speed_m_s": 12.0,
    "alignment_max_deg": 45,
    "ambiguous_speed_threshold_m_s": 1.5
  },
  
  "source_attribution": {
    "industrial_buffer_km": 30,
    "max_attribution_distance_km": 30,
    "sources_asset": "RuPlumeScan/industrial/source_points"
  },
  
  "confidence": {
    "high_z": 4.0,
    "high_n_pixels": 4,
    "high_alignment": 0.7,
    "high_distance_km": 20,
    "weights": {
      "stat": 0.30,
      "geom": 0.20,
      "wind": 0.25,
      "coverage": 0.15,
      "multi": 0.10
    }
  },
  
  "ime": {
    "enabled": false,
    "u_eff_method": "schuit2023_10m",
    "u_eff_a": 0.59,
    "u_eff_b": 0.00,
    "uncertainty_factor": 1.5,
    "min_n_pixels_for_ime": 4
  },
  
  "so2_specific": {
    "fit_method": "full_nonlinear",
    "fitting_window_km": 50,
    "fitting_window_auto_select": true,
    "buffer_km": 150
  },
  
  "no2_specific": {
    "tau_hours": 4.0,
    "no2_to_nox_ratio": 1.32,
    "period_min_months": 1,
    "period_recommended_months": 3,
    "min_observations_per_pixel": 25,
    "min_wind_speed_m_s": 2.0
  },
  
  "analysis_scale_m": 7000,
  "spatial_resolution_native_m": 7000,
  
  "params_hash": "<computed at run start>"
}
```

### 2.3. Run lifecycle

```
1. User selects Configuration Preset (или custom)
2. System computes params_hash, generates run_id
3. System logs run start
4. Pipeline executes per-gas algorithm (§3, §4 или §5)
5. Append config snapshot to each Feature
6. Export to Asset
7. Log run end
```

---

## 3. Алгоритм CH₄: regional threshold-based detection (adapted from Schuit pre-ML logic)

### 3.1. Framing (важно для публикации)

**Что мы заимствуем у Schuit 2023:**
- Общую логику threshold-based pre-ML detection (filtering → background-subtracted anomaly → object extraction)
- QA filtering parameters (qa_value, AOD thresholds, physical range)
- Concept Z-score + delta dual threshold
- IME quantification logic (§6) с TROPOMI-specific U_eff calibration

**Что отличается от Schuit 2023:**
- **Background construction.** Schuit использует **per-scene 32×32 normalization** ((X̄_scene − σ_scene) → 0, (X̄_scene + 100ppb − σ_scene) → 1). Их background — это локальная sceneмerized normalization для подготовки CNN input.
- **Наш подход:** **regional climatological background** (multi-year median per pixel, ±30 day DOY window, with industrial buffer exclusion) **+ local annulus correction**. Обоснование: для Западной Сибири сезонная и ландшафтная вариабельность (болота, snow, taiga) делает per-scene нормализацию недостаточной — теряется regional context.
- **Detection logic.** Schuit делает CNN classification поверх normalized scenes. Мы используем threshold-based detection поверх Z-score карт. CNN/SVC stages Schuit (Sections 2.3.2, 2.4) **не воспроизводим** — нет открытых весов, нет training data.
- **Source attribution.** Schuit attribution через 0.7°×0.7° window вокруг detected source с inventory matching. Мы используем явный industrial mask с buffer + nearest source distance.

**Корректное цитирование в публикации:**

> «Detection follows a regional threshold-based approach informed by the pre-ML processing logic of Schuit et al. (2023, Sect. 2.2): QA filtering, background-subtracted anomaly, and connected component object extraction. Unlike Schuit, who normalize per-scene 32×32 patches for CNN input, we construct a regional climatological background (multi-year per-pixel median with industrial buffer exclusion) augmented by local annulus correction. The CNN+SVC machine learning stages of Schuit are not reproduced; v2.0 of our tool will introduce ML classification trained on accumulated cross-source agreement labels (DNA §4.1).»

### 3.2. Входные данные

```javascript
const collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4');
const band = 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected';
```

Дополнительные коллекции:
- ERA5 для ветра: `ECMWF/ERA5/HOURLY` (полный reanalysis, не -Land — см. §13.1)
- Snow mask: `MODIS/061/MOD10A1` (NDSI)
- Industrial proxy: `RuPlumeScan/industrial/proxy_mask`

### 3.3. QA filtering (Lorente 2021)

```javascript
function applyCH4_QA(img, qa_config) {
  let masked = img;
  
  if (img.bandNames().contains('qa_value')) {
    masked = masked.updateMask(
      masked.select('qa_value').gte(qa_config.qa_value_min)
    );
  }
  
  if (img.bandNames().contains('aerosol_optical_depth')) {
    masked = masked.updateMask(
      masked.select('aerosol_optical_depth').lte(qa_config.aod_max)
    );
  }
  
  if (img.bandNames().contains('solar_zenith_angle')) {
    masked = masked.updateMask(
      masked.select('solar_zenith_angle').lt(qa_config.solar_zenith_max_deg)
    );
  }
  
  // Physical range
  masked = masked.updateMask(
    masked.select(band).gte(qa_config.physical_range_min_ppb)
        .and(masked.select(band).lte(qa_config.physical_range_max_ppb))
  );
  
  // Snow mask (MODIS NDSI > 40 = snow-covered, exclude)
  const snow = ee.ImageCollection('MODIS/061/MOD10A1')
    .filterDate(img.date(), img.date().advance(1, 'day'))
    .select('NDSI_Snow_Cover')
    .first();
  if (snow) {
    masked = masked.updateMask(
      snow.unmask(0).lt(qa_config.snow_mask_threshold)
    );
  }
  
  return masked;
}
```

**Note (per Lorente 2021 + Schuit 2023):** bias-corrected XCH₄ необходим, но недостаточен для high-albedo (snow) и very low-albedo (dark wetland) поверхностей. Snow mask + low-albedo filter + AOD filter — все обязательны. См. §13.1 для honest_limitations.

### 3.4. Background construction (regional hybrid)

#### 3.4.1. Climatological seasonal background

Per pixel (x,y), для месяца m, по архиву [2019, target_year-1]:

```
C(x,y,m) = median{X(x,y,t) : year(t) ∈ [2019, target_year-1], 
                              |DOY(t) - DOY_target| ≤ doy_window_half_days,
                              x not in industrial_buffer}
σ_clim(x,y,m) = 1.4826 · MAD{X(x,y,t)}
count_clim(x,y,m) = |{valid observations in window}|
```

**Industrial buffer exclusion (наша конструкция, не из Schuit).** При построении climatology исключаются пиксели в `industrial_buffer_exclude_km` от любого known source. Без этого persistent emissions (Норильск, Кузбасс, Уренгой) становятся частью «фона» и Z-score над ними занижается. Это известная проблема aliasing (см. Varon 2023 на тему Liu 2021 divergence: «aliased Permian enhancements into the background field»).

GEE-implementation:

```javascript
function buildClimatology(gas, target_year, target_month, bg_config) {
  const collection = ee.ImageCollection(gasCollections[gas])
    .select(gasBands[gas]);
  
  const ind_mask = ee.Image('RuPlumeScan/industrial/proxy_mask')
    .focal_max({radius: bg_config.climatology.industrial_buffer_exclude_km * 1000, 
                units: 'meters'})
    .not();
  
  const filtered = collection
    .filter(ee.Filter.calendarRange(
      bg_config.climatology.history_years_min, 
      target_year + bg_config.climatology.history_years_max_offset, 
      'year'
    ))
    .filter(ee.Filter.calendarRange(
      target_month - 1, target_month + 1, 'month'
    ))
    .map(function(img) { return img.updateMask(ind_mask); });
  
  const median = filtered.reduce(ee.Reducer.median()).rename('bg_climatology');
  
  const mad = filtered
    .map(function(img) { return img.subtract(median).abs(); })
    .reduce(ee.Reducer.median())
    .multiply(1.4826)
    .rename('sigma_climatology');
  
  const count = filtered.count().rename('count_climatology');
  
  return median.addBands(mad).addBands(count);
}
```

#### 3.4.2. Local annulus correction

Для конкретного дня t:

```
R(x,y,t) = X(x,y,t) - C(x,y,m)
S(x,y,t) = focal_median(R, annulus(r_in, r_out))
```

Annulus реализуется через `ee.Kernel.fixed()` с явной матрицей весов (см. §12.1).

#### 3.4.3. Hybrid background

```
B(x,y,t) = C(x,y,m) + (1-λ) · S(x,y,t)
```

При `λ=1`: чистая climatology. При `λ=0`: climatology + annulus correction. По умолчанию `λ=0.5`.

### 3.5. Anomaly metrics

```
ΔX(x,y,t) = X(x,y,t) - B(x,y,t)
σ_local(x,y,t) = 1.4826 · MAD_annulus(R - S)
σ_eff(x,y,t) = max(σ_local, σ_clim, σ_floor)
Z(x,y,t) = ΔX(x,y,t) / σ_eff(x,y,t)
```

`σ_floor` (config: `sigma_floor_units`) = 15 ppb для CH₄ (соответствует TROPOMI XCH₄ retrieval noise).

### 3.6. Pixel-level mask

```javascript
function ch4PixelMask(anomaly, config) {
  const z_test = anomaly.select('z').gte(config.anomaly.z_min);
  const delta_test = anomaly.select('delta').gte(config.anomaly.delta_min_units);
  
  const local_med = anomaly.select('y').focal_median({
    kernel: makeAnnulusKernel(50000, 150000, 7000)
  });
  const relative = anomaly.select('y').subtract(local_med);
  const rel_test = relative.gte(config.anomaly.relative_threshold_min_units);
  
  return z_test.and(delta_test).and(rel_test).selfMask();
}
```

### 3.7. Object construction

```javascript
function buildObjects(mask, config) {
  const kernel = config.object.connectedness === '4' 
    ? ee.Kernel.plus(1) 
    : ee.Kernel.square(1);
  
  const labeled = mask.connectedComponents({
    connectedness: kernel,
    maxSize: config.object.max_size
  });
  
  const sizeOk = mask.connectedPixelCount({
    maxSize: config.object.max_size,
    eightConnected: config.object.connectedness === '8'
  }).gte(config.object.min_pixels);
  
  return labeled.updateMask(sizeOk);
}
```

Векторизация:

```javascript
function vectorizeObjects(labeled, anomaly, region, config) {
  const reducer = ee.Reducer.count()
    .combine(ee.Reducer.mean(), '', true)
    .combine(ee.Reducer.max(), '', true);
  
  const stack = labeled.select('labels')
    .addBands(anomaly.select('y'))
    .addBands(anomaly.select('delta'))
    .addBands(anomaly.select('z'));
  
  return stack.reduceToVectors({
    geometry: region,
    scale: config.analysis_scale_m,
    geometryType: 'polygon',
    eightConnected: config.object.connectedness === '8',
    labelProperty: 'object_label',
    reducer: reducer,
    maxPixels: 1e10,
    tileScale: 4
  });
}
```

### 3.8. Object metrics

Для каждого Feature вычисляются: area_km2, centroid, max/mean Z, max/mean delta, n_pixels, plume_axis_deg.

**Plume axis direction** — centroid → max_z pixel direction (не PCA). Для объектов 2-4 пикселя PCA численно неустойчив. Centroid-to-max-z работает на любом объекте ≥ 2 пикселей.

### 3.9. Wind attribution (single ERA5 source)

```javascript
function attachWind(feature, t_start, t_end, config) {
  const era5 = ee.ImageCollection(config.wind.source)  // ECMWF/ERA5/HOURLY
    .filterDate(t_start, t_end)
    .select([config.wind.u_band, config.wind.v_band])
    .mean();
  
  const wind_at_centroid = era5.reduceRegion({
    reducer: ee.Reducer.first(),
    geometry: feature.geometry().centroid(),
    scale: 31000  // ERA5 grid ~31 km
  });
  
  const u = ee.Number(wind_at_centroid.get(config.wind.u_band));
  const v = ee.Number(wind_at_centroid.get(config.wind.v_band));
  const speed = u.pow(2).add(v.pow(2)).sqrt();
  const dir = v.atan2(u).multiply(180).divide(Math.PI).add(180);
  
  const plume_axis = ee.Number(feature.get('plume_axis_deg'));
  let alignment = null;
  if (plume_axis !== null) {
    const diff = plume_axis.subtract(dir).abs();
    const diff_modular = diff.min(ee.Number(180).subtract(diff));
    alignment = diff_modular.multiply(Math.PI).divide(180).cos().abs();
  }
  
  return feature.set({
    wind_u: u, wind_v: v,
    wind_speed: speed, wind_dir_deg: dir,
    wind_alignment_score: alignment,
    wind_source: 'ERA5_HOURLY',
    qa_flag_low_wind: speed.lt(config.wind.ambiguous_speed_threshold_m_s)
  });
}
```

**Limitation declared:** Single wind source (ERA5). Schuit (2023) и CAMS используют ensemble ERA5 + GEOS-FP 10m + GEOS-FP PBL, усредняя три quantifications. GEOS-FP в GEE недоступен, поэтому ensemble approach невозможен. См. §13.1.

### 3.10. Source attribution

См. v2.1, без изменений.

### 3.11. Confidence scoring

См. v2.1, без изменений.

### 3.12. Class assignment

См. v2.1, без изменений.

---

## 4. Алгоритм NO₂: flux divergence following Beirle 2019/2021

### 4.1. Framing

**Bibliographic correction vs v2.1:** метод опубликован в Beirle et al. **2019, Sci. Adv.** ("Pinpointing nitrogen oxide emissions from space"). Beirle et al. **2021, ESSD** (не ACP) публикует TROPOMI NOx point-source catalog с modifications: **divergence-only без τ correction** для strong point sources, плюс per-pixel L from photostationary steady state.

**Что мы реализуем:**
- Core divergence formula `E = D + N/τ` (Beirle 2019)
- Configurable: с τ correction (для emission map) или без (для point source detection)
- Default: full formula с τ=4h (более общий случай)

### 4.2. Входные данные

```javascript
const collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2');
const band = 'tropospheric_NO2_column_number_density';  // mol/m²
```

### 4.3. QA filtering

```
qa_value >= 0.75  (стандарт для NO₂, Eskes 2019)
cloud_fraction < 0.3
solar_zenith < 70°
```

### 4.4. Spatial averaging

```javascript
const period_avg = collection
  .filterDate(start, end)
  .filterBounds(roi)
  .map(applyNO2_QA)
  .select(band)
  .mean();
```

Минимальный период: 1 месяц. Рекомендуемый: 3 месяца.

### 4.5. Wind field averaging (ERA5 single source)

```javascript
const era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY')
  .filterDate(start, end)
  .select(['u_component_of_wind_10m', 'v_component_of_wind_10m']);

const u_mean = era5.select('u_component_of_wind_10m').mean();
const v_mean = era5.select('v_component_of_wind_10m').mean();
```

Calm winds filter per Beirle 2021: **skip wind speeds < 2 m/s** при averaging.

### 4.6. Reproject в локальную equal-area projection

`ee.Image.translate()` работает в географических координатах (градусах), не на плоской сетке. Для метрических dx/dy в divergence — обязательный reproject в локальную UTM.

Для Западной Сибири — UTM zone 42N (центр AOI ≈ 70°E):

```javascript
const utm42n = ee.Projection('EPSG:32642');

const no2_proj = period_avg.reproject({crs: utm42n, scale: 7000});
const u_proj = u_mean.reproject({crs: utm42n, scale: 7000});
const v_proj = v_mean.reproject({crs: utm42n, scale: 7000});
```

### 4.7. NO₂ flux

```javascript
const flux_x = no2_proj.multiply(u_proj).rename('flux_x');
const flux_y = no2_proj.multiply(v_proj).rename('flux_y');
// Units: (mol/m²) · (m/s) = mol/(m·s)
```

### 4.8. Divergence (finite differences in UTM)

```javascript
const dx = 7000;

const flux_x_plus = flux_x.translate(dx, 0, 'meters', utm42n);
const flux_x_minus = flux_x.translate(-dx, 0, 'meters', utm42n);
const dFx_dx = flux_x_plus.subtract(flux_x_minus).divide(2 * dx);

const flux_y_plus = flux_y.translate(0, dx, 'meters', utm42n);
const flux_y_minus = flux_y.translate(0, -dx, 'meters', utm42n);
const dFy_dy = flux_y_plus.subtract(flux_y_minus).divide(2 * dx);

const divergence = dFx_dx.add(dFy_dy).rename('divergence');
```

### 4.9. NOx emission (Beirle 2019 formula)

```
E = D + N/τ  (per pixel, mol NOx / (m²·s))
```

где:
- `D` — divergence
- `N = L · V_NO2` — NOx column (V_NO2 measured, L = NOx/NO2 ratio)
- `τ` — boundary layer NO2 lifetime

Default values (Beirle 2019):
- `τ = 4 h = 14400 s`
- `L = 1.32` (NOx/NO2 ratio)

```javascript
const tau_seconds = 14400;
const L = 1.32;

const N_nox = no2_proj.multiply(L);  // NOx column

const emission_rate = divergence
  .add(N_nox.divide(tau_seconds))
  .rename('emission_rate');
// Units: mol NOx / (m²·s)
```

**Configurable:** `no2_specific.tau_hours = 4.0`, `no2_specific.no2_to_nox_ratio = 1.32`.

**Optional pixel-wise L** (Beirle 2021 ESSD): для precision можно calculate L из photostationary steady state per pixel. В v1 используем constant L=1.32; pixel-wise L — future enhancement.

**Optional divergence-only mode:** для strong point source detection (Beirle 2021 catalog approach), `tau_hours = null` → формула становится `E ≈ D`.

### 4.10. Source detection

```javascript
const peaks = emission_rate.focal_max(10000, 'circle', 'meters')
  .eq(emission_rate)
  .selfMask();

const high_emission = emission_rate.gte(config.anomaly.delta_min_units);

const source_candidates = peaks.and(high_emission);

const sources = source_candidates.reduceToVectors({
  geometry: roi,
  scale: 7000,
  geometryType: 'centroid',
  reducer: ee.Reducer.first(),
  maxPixels: 1e10
});
```

### 4.11. Output as Plume Events

Каждая detected source → Plume Event с:
- `gas = "NO2"`
- `geometry` = точечный buffer (5 km) вокруг peak
- `magnitude_proxy` = emission_rate в µmol/(m²·s)
- `time` = середина period
- `class = "NO2_only"` (уточняется в multi-gas matching)
- `detection_method = "beirle_divergence"`

### 4.12. Filter: minimum observations per pixel

Per Beirle 2021: pixels с < 25 observations за period → set missing. Контроль coverage.

```javascript
const obs_count = collection
  .filterDate(start, end)
  .map(applyNO2_QA)
  .count();
const valid_coverage = obs_count.gte(config.no2_specific.min_observations_per_pixel);
emission_rate = emission_rate.updateMask(valid_coverage);
```

---

## 5. Алгоритм SO₂: wind-rotated oversampling following Fioletov 2020

### 5.1. Framing

SO₂ детекция в Западной Сибири — **per-source workflow** для known industrial sources (Norilsk dominant globally). Single-day detection ненадёжна (retrieval noise ~50% column).

**Что мы реализуем:** wind-rotated stacking + plume model fitting from Fioletov et al. 2015 (functional form) и Fioletov et al. 2020 (TROPOMI application).

**Two fit approaches:**
- **Primary: full nonlinear fit** (3 параметра: A amplitude, σ_y crosswind width, L decay length). Применимо для нашего случая (5-10 sources в Западной Сибири). Computationally expensive но более accurate.
- **Fallback: Fioletov simplified** (`α/τ` с fixed σ ≈ 15 km, fixed τ ≈ 6 h). Если full fit не сходится или для quick screening.

User выбирает через `so2_specific.fit_method = "full_nonlinear"` (default) или `"fioletov_simplified"`.

### 5.2. Входные данные

```javascript
const collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_SO2');
const band = 'SO2_column_number_density';  // mol/m²
```

### 5.3. QA filtering

```
qa_value >= 0.5
cloud_fraction < 0.3
solar_zenith < 70°
SO2 > -0.001 mol/m²  (фильтр сильных negative outliers, НЕ всех negative — per GEE doc)
```

### 5.4. Per-source workflow

Для каждого known SO₂ source `(lon₀, lat₀)` с estimated magnitude:

```javascript
function processSource(source, period, config) {
  // Auto-select fitting window per Fioletov 2020
  let L_window;
  const mag = source.get('estimated_kt_per_year');
  if (config.so2_specific.fitting_window_auto_select) {
    if (mag < 100) L_window = 30;
    else if (mag < 1000) L_window = 50;
    else L_window = 90;
  } else {
    L_window = config.so2_specific.fitting_window_km;
  }
  
  const buffer = source.geometry().buffer(config.so2_specific.buffer_km * 1000);
  
  const images = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_SO2')
    .filterDate(period.start, period.end)
    .filterBounds(buffer)
    .map(applySO2_QA);
  
  // Wind rotation per image (rotates pixel coordinates)
  const rotated_stack = images.map(function(img) {
    return rotateToSourceFrame(img, source);
  }).mean();
  
  // Fit plume model
  let fit_params;
  if (config.so2_specific.fit_method === 'full_nonlinear') {
    fit_params = fitFullPlumeModel(rotated_stack, source, L_window, config);
  } else {
    fit_params = fitSimplifiedPlumeModel(rotated_stack, source, L_window, config);
  }
  
  return ee.Feature(source.geometry(), fit_params);
}
```

### 5.5. Wind rotation

Для каждого image в день `t`:

```javascript
function rotateToSourceFrame(img, source) {
  const t = ee.Date(img.get('system:time_start'));
  
  // Wind at source location at overpass time
  const wind = ee.ImageCollection('ECMWF/ERA5/HOURLY')
    .filterDate(t, t.advance(1, 'hour'))
    .select(['u_component_of_wind_10m', 'v_component_of_wind_10m'])
    .first();
  
  const wind_at_source = wind.reduceRegion({
    reducer: ee.Reducer.first(),
    geometry: source.geometry(),
    scale: 31000
  });
  
  const u = ee.Number(wind_at_source.get('u_component_of_wind_10m'));
  const v = ee.Number(wind_at_source.get('v_component_of_wind_10m'));
  const wind_dir_rad = v.atan2(u);
  
  // Rotate via reprojection
  const proj = ee.Projection('EPSG:32642').rotate(wind_dir_rad.multiply(-1));
  
  return img.reproject({crs: proj, scale: 7000});
}
```

### 5.6. Full nonlinear plume model fit (primary)

Functional form (Fioletov 2015 Eq. 1, simplified для TROPOMI scale):

```
C(x', y') = A · exp(-x'/L) · exp(-y'²/(2·σ_y²)) + B
```

где `x'` — downwind distance, `y'` — crosswind distance, `B` — regional offset.

**Implementation:** GEE не поддерживает nonlinear fit напрямую. Pipeline:
1. Sample stacked image на rotated grid вдоль x'/y' axes
2. Export sampled points в Python  
3. Fit через `scipy.optimize.curve_fit` для 4 параметров (A, σ_y, L, B)
4. Save fit_params + R² + standard errors как Feature properties

**Это означает: SO₂ модуль требует Python wrapper**. JS-only невозможно.

### 5.7. Emission rate из fit

```
α = A · sqrt(2π) · σ_y · L  (integrated mass, mol)
Q = α / τ                    (emission rate, mol/s)
Q_kg_h = Q · M_SO2 · 3600    (kg/h)
```

где `M_SO2 = 64.07 g/mol`, `τ` — fitted decay time (через `L = U·τ`, U = mean wind speed).

Honestly declared uncertainty: **±50%** (Fioletov 2020).

### 5.8. Simplified fit (fallback, Fioletov 2020 production approach)

При `fit_method = "fioletov_simplified"`:
- Fix `σ_y = 15 km` (TROPOMI typical, или 10 km для real point sources)
- Fix `τ = 6 h` (Fioletov 2020 mean)
- Fit only `α` (total mass amplitude)
- `Q = α / τ`

Менее accurate, но faster и более robust к низкому signal/noise.

### 5.9. Output as Plume Events

Каждый source — один Plume Event с:
- `gas = "SO2"`
- `geometry` = source location + downwind plume polygon (reconstructed from fit)
- `q_kg_h_experimental` = Q estimate
- `q_uncertainty_factor = 1.5`
- `quantification_method = "fioletov_full_fit"` или `"fioletov_simplified"`
- `quantification_disclaimer = "TROPOMI SO2 retrieval uncertainty + plume fit ±50%"`

### 5.10. Detection limits (Fioletov 2020)

Honest declared limits:

| Source magnitude | Detection reliability |
|---|---|
| > 1000 kt/yr SO₂ (Norilsk) | High reliability, robust agreement with OMI/OMPS (correlation ~0.97) |
| 100-1000 kt/yr (large smelters, big TPPs) | Moderate, formal criterion: emission/uncertainty > 5 |
| 50-100 kt/yr (mid-size TPPs) | Marginal, criterion 3.6-5 + clear hotspot + downwind tail |
| < 50 kt/yr | Below reliable detection (low correlation ~0.3 vs OMI) |

Норильск (~1500-2000 kt/yr SO₂) — well above detection limit.  
Кузбасс ТЭЦ типичных (~100 kt/yr SO₂) — на границе reliable detection.  
Это явно declared в каталоге через `confidence` field.

---

## 6. IME mass quantification (experimental, CH₄ only)

### 6.1. Framing

Varon et al. 2018 IME формула разработана для high-resolution instruments (GHGSat 50×50 m). Для TROPOMI 7×5 km применение даёт **±50% uncertainty в лучшем случае**.

**Important update vs v2.1:** Schuit et al. 2023 явно адаптируют IME для TROPOMI и публикуют **TROPOMI-specific U_eff calibration** (Section 2.5.1):
- 10m wind: `U_eff = 0.59 · U10 + 0.00` (r²=0.77)
- PBL wind: `U_eff = 0.47 · U_PBL + 0.31` (r²=0.78)

Это **более правильная calibration** для TROPOMI чем Varon 2018 GHGSat values (`a=0.33, b=0.45`). Default обновлён.

**Schuit ensemble:** они усредняют 3 quantifications (ERA5 10m, GEOS-FP 10m, GEOS-FP PBL). Мы используем только ERA5 10m → больше uncertainty, declared.

### 6.2. Условия применения

IME вычисляется ТОЛЬКО если:
- `gas == "CH4"`
- `confidence == "high"` или `"very_high"`
- `n_pixels >= ime.min_n_pixels_for_ime` (default 4)
- `wind_speed >= 2 m/s`
- `wind_alignment_score >= 0.7`

Иначе `ime_kg = null, q_kg_h_experimental = null`.

### 6.3. Расчёт IME

Per Schuit 2023 §2.5.1: local background = median XCH₄ scene pixels вне plume mask.

```
IME = Σ_{j ∈ plume_mask} ΔΩ_j
ΔΩ_j = (X_j - B_local) · M_CH4/M_air · p_s_j / g · A_j
```

где:
- `M_CH4 = 16.04 g/mol`
- `M_air = 28.97 g/mol`
- `p_s` — surface pressure из ERA5
- `g = 9.80665 m/s²`
- `A_j` — площадь пикселя
- `X_j - B_local` — anomaly в molar mixing ratio (из ppb / 10⁹)

### 6.4. Q estimate (Schuit 2023 calibration)

```
L = sqrt(area_km2 · 1e6)              // m, plume length proxy
U_eff = a · U10 + b                    // Schuit 2023 TROPOMI 10m wind calibration
                                       //   default: a=0.59, b=0.00
Q = U_eff · IME / L                    // kg/s
Q_kg_h = Q · 3600
```

**Configurable:**
- `ime.u_eff_method = "schuit2023_10m"` (default) | `"schuit2023_pbl"` | `"varon2018_ghgsat"` | `"regional_calibrated"` (для v2 после калибровки)
- `ime.u_eff_a = 0.59` (Schuit 10m default)
- `ime.u_eff_b = 0.00`

**Honest disclaimer в Feature:**

```
{
  ime_kg: ...,
  q_kg_h_experimental: ...,
  q_uncertainty_factor: 1.5,
  quantification_method: "schuit2023_ime_10m",
  quantification_disclaimer: "Experimental: TROPOMI 7km pixels not spatially resolved; single-source wind (ERA5, no GEOS-FP ensemble); ±50% uncertainty; regional calibration pending v2"
}
```

### 6.5. Future regional calibration (v2 deliverable)

В Roadmap milestone: после накопления validation events Кузбасс/Норильск/Бованенково — regression `Q_observed` против independent estimates (Schuit catalog matched events, IMEO MARS persistency-derived rates) → региональные коэффициенты `a, b` для Западной Сибири.

Это потенциальный **scientific contribution в tool-paper**: «Calibrated effective wind speed parametrization for TROPOMI methane plume quantification over subarctic continental conditions». Не главное, но добавляет научной плотности.

---

## 7. Multi-gas evidence и классификация (novel component)

### 7.1. Framing — это novel contribution, не reproduction

**Important honest framing:** peer-reviewed protocol для CH₄+NO₂/SO₂ event matching на TROPOMI **не существует**. Closest paper — Ialongo et al. 2021 (joint analysis CH₄+NO₂ over Russian oil fields), но не event-by-event matching algorithm с фиксированными параметрами.

Schuit/CAMS source-type attribution использует **bottom-up inventories в 0.7°×0.7° window**, не gas-event matching.

**Это означает:** наш multi-gas matching layer — **novel methodological component**. Это framing для tool-paper:

> «We introduce a multi-gas evidence aggregation layer that matches CH₄/NO₂/SO₂ candidates spatially and temporally to derive composite emission signatures (oil&gas, energy/combustion, multi-pollutant). To our knowledge, this is the first systematic event-level matching of TROPOMI gases for industrial source attribution at regional scale. Matching parameters (R_match=25 km, T_match=1 day) are inferred from TROPOMI footprint geometry and overpass timing, not from prior peer-reviewed protocols.»

Это **усиливает** novelty argument для статьи в СПДЗЗ.

### 7.2. Spatial-temporal matching

Два события совпадают, если:
- `dist(centroid_A, centroid_B) ≤ R_match`
- `|date_A - date_B| ≤ T_match`
- `gas_A != gas_B` (для multi-gas; cross-source same-gas — отдельный matcher §10)

Defaults:
- `R_match = 25 km` (TROPOMI footprint × 3)
- `T_match = 1 day` (within ±1 day, not strict same-day)

### 7.3. Class assignment cascade

```
matched_gases = {gas for gas in [CH4, NO2, SO2] if event_in_gas matches in (R_match, T_match)}

if len(matched_gases) == 3:
    class = "CH4_NO2_SO2"
elif matched_gases == {CH4, NO2}:
    class = "CH4_NO2"
elif matched_gases == {NO2, SO2}:
    class = "NO2_SO2"
elif matched_gases == {CH4, SO2}:
    class = "CH4_SO2"  # rare combination
elif len(matched_gases) == 1:
    if gas == "CH4" and is_diffuse(event):
        class = "diffuse_CH4"
    elif wind_speed < threshold:
        class = "wind_ambiguous"
    else:
        class = f"{gas}_only"
```

### 7.4. Multi-gas evidence score

```
S_multi = w_CH4 · I(CH4) + w_NO2 · I(NO2) + w_SO2 · I(SO2)
```

Default weights (oil&gas focus):
- `w_CH4 = 0.45`
- `w_NO2 = 0.35`
- `w_SO2 = 0.20`

Configurable в `confidence.weights`.

### 7.5. Diffuse CH4 detection

```
is_diffuse(event) := 
    (n_pixels > diffuse_pixel_threshold) AND
    (wind_alignment_score < diffuse_alignment_threshold OR wind_alignment_score is null)
```

Defaults: `diffuse_pixel_threshold = 30`, `diffuse_alignment_threshold = 0.3`.

Diffuse_CH4 события **остаются в каталоге**, но имеют `confidence ≤ "medium"`, `qa_flag` includes `"diffuse"`, не учитываются в Persistence Maps для point sources.

---

## 8. Configuration Presets

### 8.1. Required presets для v1.0

#### `default`
Сбалансированные defaults для типичных условий Западной Сибири (см. §2.2 для full Configuration).

#### `schuit_eq`
Параметры близкие к Schuit 2023 production thresholds.

```json
{
  "config_id": "schuit_eq",
  "anomaly": {"z_min": 3.0, "delta_min_units": 50, "relative_threshold_min_units": 20, "percentile_min": 0.97},
  "object": {"min_pixels": 4, "min_area_km2": 100},
  "wind": {"min_speed_m_s": 2.5, "alignment_max_deg": 45},
  "background": {"lambda_climatology": 0.6}
}
```

Note: точные thresholds Schuit не опубликованы, это approximation на основе reported `~25 t/h detection limit`.

#### `imeo_eq`
Параметры близкие к UNEP IMEO MARS detection threshold (новое в v2.2 — заменяет `lauvaux_eq`).

IMEO MARS использует операционно ML-based detection (через mix sources: SRON, GHGSat, Carbon Mapper). Точные пороги не публичны. Approximation:

```json
{
  "config_id": "imeo_eq",
  "anomaly": {"z_min": 3.5, "delta_min_units": 60, "relative_threshold_min_units": 25, "percentile_min": 0.98},
  "object": {"min_pixels": 5, "min_area_km2": 150},
  "wind": {"min_speed_m_s": 3.0, "alignment_max_deg": 30}
}
```

#### `sensitive`
Низкие пороги, много candidates, для discovery / exploratory analysis.

```json
{
  "config_id": "sensitive",
  "anomaly": {"z_min": 2.5, "delta_min_units": 20, "relative_threshold_min_units": 10, "percentile_min": 0.90},
  "object": {"min_pixels": 2, "min_area_km2": 30},
  "wind": {"min_speed_m_s": 1.5, "alignment_max_deg": 60}
}
```

#### `conservative`
Высокие пороги, только надёжные события.

```json
{
  "config_id": "conservative",
  "anomaly": {"z_min": 4.0, "delta_min_units": 80, "relative_threshold_min_units": 30, "percentile_min": 0.99},
  "object": {"min_pixels": 6, "min_area_km2": 200},
  "wind": {"min_speed_m_s": 3.0, "alignment_max_deg": 30}
}
```

### 8.2. Custom Configurations

Free-form parameter input через UI. При запуске Run:
1. Compute `params_hash`
2. Generate `config_id = "custom_" + first_8_chars(params_hash)`
3. Save Configuration в `RuPlumeScan/presets/custom_<sha8>` Asset
4. Use as Preset для будущих Runs

Каждый custom run автоматически становится reproducible Preset.

### 8.3. Preset versioning

При изменении Algorithm version (2.2 → 2.3), все built-in Presets могут потребовать обновления. Versioning в asset path: `default_v2.2`, `default_v2.1` (archived).

---

## 9. Reference Catalog Adapter (RCA) — supported sources

### 9.1. Primary references (v1.0 deliverables)

#### Schuit 2023 (Zenodo 8087134)
- **Type:** ML-based, 2974 plumes 2021
- **Format:** CSV from Zenodo
- **License:** CC-BY-4.0 (open)
- **Ingestion:** simple CSV download via Python
- **Comparison gas:** CH₄ only

#### UNEP IMEO MARS (replaces Lauvaux 2022 in v2.2)

**Critical update vs v2.1:** Lauvaux et al. 2022 per-event catalog **не доступен публично** — только PDF supplement без machine-readable CSV. Замена на IMEO MARS:

- **URL:** methanedata.unep.org / Eye on Methane platform
- **Type:** Operational ML+manual detection through SRON, GHGSat, Carbon Mapper, others
- **Format:** CSV, GeoJSON, XLSX, JSON
- **Per-plume fields:** `id_plume, source_name, satellite, tile_date, lat, lon, actionable, notified, country, sector, detection_institution, quantification_institution, ch4_fluxrate, ch4_fluxrate_std, wind_u, wind_v, total_emission, total_emission_std, wind_speed, last_update, insert_date`
- **Per-source fields:** `source_name, lon, lat, country, sector, persistency, persistency_std, persistency_category, n_plumes_detected, last_plume_date, feedback_operator, feedback_government`
- **Update frequency:** monthly
- **License:** CC-BY-NC-SA 4.0 (non-commercial only, attribution required)
- **Comparison gas:** CH₄

**Note: IMEO MARS преимущества над Lauvaux 2022:**
- Свежие данные (2023+) ближе по времени к нашему target period (2019-2026), чем Lauvaux 2019-2020
- Богаче поля (persistency, sector, notified status, feedback)
- Открыт публично с CSV/GeoJSON
- Continuously updated (monthly), не статичный snapshot

#### CAMS Methane Hotspot Explorer
- **URL:** atmosphere.copernicus.eu (single CSV file)
- **Type:** Operational, ML-based
- **Format:** CSV bulk download
- **Fields:** `date, time_UTC, lat, lon, source_rate_t/h, uncertainty_t/h, source_type, source_country`
- **Update frequency:** weekly
- **License:** Copernicus attribution required
- **Coverage:** since 2024-05-01
- **Comparison gas:** CH₄

### 9.2. Extension references (post-v1.0)

- **Lauvaux 2022** — by request to authors (Kayrros team), если получим CSV → можем добавить Ingester
- **Carbon Mapper** — API доступ, требует регистрации
- **Cherepanova 2023 Кузбасс** — request to authors
- **Fioletov SO₂ catalog** — Zenodo, для NO₂/SO₂ extensions
- **Beirle 2021 ESSD NOx catalog** — для NO₂ comparison

### 9.3. Reference Catalog ≠ Ground Truth

Per DNA §1.5 и §2.1: comparison metrics declared как **agreement metrics**, не validation accuracy. Reference catalogs имеют свои detection limits и false positive rates.

---

## 10. Comparison Engine

См. v2.1, без существенных изменений. Замена `Lauvaux2022` → `IMEO_MARS` в reference list, остальное идентично.

### 10.1. Metrics output

```
recall_a_vs_b = N_matched_a / N_b
precision_a_vs_b = N_matched_a / N_a  (если b ≈ ground truth proxy)
f1 = 2 · recall · precision / (recall + precision)
```

Все metrics в Comparison Report **всегда** declared с disclaimer:
> "Metrics are agreement metrics, not validation accuracy. Reference catalog is not ground truth."

### 10.2. Cross-source agreement

```
event.agreement_score = sum([
  matched_schuit2023, matched_imeo_mars, matched_cams
])
```

Events с `agreement_score >= 2` — high-confidence cross-validated, кандидаты на v2 ML training labels.

---

## 11. Sensitivity analysis и synthetic injection

См. v2.1, без изменений. Sensitivity sweep по любому параметру Configuration с output `(n_events, mean_confidence, recall_vs_ref, precision_vs_ref)`. Synthetic plume injection с amplitude sweep [10, 30, 50, 100, 200] ppb для CH₄.

**Pass criterion:** для amplitude ≥ 30 ppb, recovered amplitude / injected ≥ 0.7.

---

## 12. GEE implementation gotchas

См. v2.1 §11, без изменений. Девять реализационных ловушек:

1. Annulus kernel arithmetic — только через `ee.Kernel.fixed()`
2. Analysis scale ≥ 7000 m (не 1000)
3. `unmask(0)` для XCH4 запрещён
4. `ee.Image.translate()` projection trap — обязательный reproject в UTM для NO₂ divergence
5. `bestEffort: true` запрещён для detection statistics
6. `map(closure)` parameter passing — factory pattern
7. Memory limits на export — chunked per gas-month
8. Edge of ROI handling — buffer + clip
9. Snow mask source — MODIS NDSI

---

## 13. Open questions и known limitations

### 13.1. Known limitations (declared в публикациях)

**Single wind source (ERA5).** Schuit 2023 и CAMS Hotspot Explorer используют **ensemble ERA5+GEOS-FP 10m+GEOS-FP PBL**, усредняя три quantifications. GEOS-FP в GEE недоступен → мы используем только ERA5. Это increases plume direction и quantification uncertainty.

> Declared в publication: «Wind direction and quantification rely on ERA5 reanalysis only; the multi-source ensemble approach used by SRON and CAMS (ERA5 + GEOS-FP 10m + GEOS-FP PBL) is not feasible in pure GEE implementation. This adds uncertainty to plume axis attribution and IME quantification, particularly under unstable boundary layer conditions.»

**TROPOMI L3 vs L2.** L3 в GEE — operational v02.04 daily mosaic. Schuit/Lauvaux используют re-processed L2 v18_17 с destriping. Несовпадение приводит к разнице detection limits.

> Declared: «Detection uses TROPOMI L3 product as available in Earth Engine; published catalogs (Schuit, Lauvaux) use re-processed L2 with custom destriping. Direct numerical comparison should account for this difference.»

**TROPOMI XCH₄ bias_corrected — необходим но недостаточен.** Lorente 2021 явно указывает: low- и high-albedo scenes и snow-covered scenes остаются challenging. Bias_corrected решает большую часть, но не всё. Для Западной Сибири с её специфическими albedo conditions нужны:
- Snow mask (MODIS NDSI > 40 → exclude)
- SWIR low-albedo filter (>0.02)
- Mixed albedo filter (<0.95)
- AOD filter (<0.5)
- Optionally: blended-albedo threshold 0.85 для snow/ice removal (per Lorente)

> Declared: «Despite the use of TROPOMI bias-corrected XCH₄ product, residual systematic biases over snow-covered surfaces and dark wetlands persist (Lorente et al., 2021). Filters on AOD, SWIR albedo, and snow cover are applied to mitigate but not eliminate these biases.»

**Wetland CH₄ background.** Climatology включает естественные emissions. Industrial buffer exclusion помогает, но wetland-only zones имеют elevated baseline. Это adresses через `diffuse_CH4` class (§7.5), не через filtering.

**Snow/ice for CH₄ in Arctic winter.** Snow mask exclude winter scenes → no detection для cold-season events. Это ограничение known.

**Single-day NO₂ detection недоступна.** Beirle 2019 explicit требует multi-month average. Single-day NO₂ plumes not detectable our methodology.

**SO₂ outside known sources.** Fioletov 2020 per-source approach. Discovery новых SO₂ sources вне `industrial_proxy_mask` не работает в v1.

**SO₂ detection limits.** Norilsk (>1000 kt/yr) reliable. Mid-size sources (~100 kt/yr) marginal — на границе reliable detection. <50 kt/yr — below reliable detection limit.

**Quantification accuracy.** ±50% best case для CH₄ IME (TROPOMI 7km plumes not spatially resolved). ±50% для SO₂ rotation fit. NO₂ emission rate from divergence — accuracy зависит от lifetime correctness, ±factor 2 typically.

**GEE compute quotas.** Длительные batches могут упереться в noncommercial quotas в 2026. Mitigation: chunked exports, off-peak scheduling.

**No L2 access via GEE JS.** Python-only path для L2 ingest, добавляет complexity для users без Python skills.

### 13.2. Open questions

**Q1: Optional Beirle 2021 ESSD divergence-only mode.**  
Beirle 2021 ESSD catalog approach — divergence-only без τ correction для strong point sources. Можем добавить как Configuration option (`no2_specific.tau_hours = null`). Default остаётся full formula.

**Q2: Pixel-wise L (NOx/NO2 ratio).**  
Beirle 2021 calculates L per pixel from photostationary steady state. Default v2.2: constant L=1.32. Future: pixel-wise computation.

**Q3: ERA5 vs ERA5-Land vs GEOS-FP wind comparison.**  
Per literature consensus: not equivalent. ERA5 (full reanalysis, 137 levels, 31 km grid) — стандарт. ERA5-Land — surface replay, не подходит для plume attribution. GEOS-FP недоступен в GEE. Решение: ERA5 default, declared limitation.

**Q4: Multi-gas matching strict vs loose.**  
Same-day (T_match=0) строже но теряет события на границе суток. ±1 day более inclusive но допускает spurious matches. v2.2: `T_match=1 day` default, configurable.

**Q5: Regional U_eff calibration для Западной Сибири.**  
Schuit 2023 calibration `U_eff = 0.59·U10` — global TROPOMI fit. Для subarctic continental conditions локальные коэффициенты могут отличаться. Roadmap milestone: после accumulation validation events → regression `Q_observed` против independent estimates → региональные `a, b`. Потенциальный contribution в tool-paper.

### 13.3. Что в Roadmap но не в Algorithm v2.2

- v2 ML classifier поверх v1 candidates (после corpus accumulation)
- L2 re-processed input через external Python pipeline
- Variable τ для NO₂ через ERA5 boundary_layer_height
- High-resolution Sentinel-2 follow-up для confirmed CH₄ events
- Real-time alerts через Pub/Sub
- Pixel-wise L для NO₂ (Beirle 2021 ESSD method)
- Regional U_eff calibration для Западной Сибири

См. `Roadmap.md`.

---

## 14. Версионирование Algorithm

| Версия | Дата | Изменение |
|---|---|---|
| 1.x | до 2026-04-13 | v1 deprecated (monthly composites concept error) |
| 2.0 | 2026-04-25 (черновик в тех. записке) | Per-gas approach, Schuit/Beirle/Fioletov |
| 2.1 | 2026-04-25 | Configurable Detection Surface, full Common Plume Schema, поправки v2.0 |
| 2.2 | 2026-04-25 | Verification через GPT-5.5 на peer-reviewed источниках. 9 точечных уточнений: CH₄ framing rephrased (regional не reproduces Schuit per-scene); SO₂ full nonlinear fit primary + Fioletov simplified fallback; SO₂ fitting window auto-select 30/50/90 km; SO₂ detection limits explicitly declared; IME U_eff defaults обновлены на Schuit 2023 TROPOMI calibration (0.59·U10); Lauvaux 2022 заменён на UNEP IMEO MARS; single ERA5 wind declared limitation; multi-gas matching framed как novel component; bibliographic correction Beirle 2019 Sci.Adv. + 2021 ESSD. |

Algorithm обновляется при добавлении новых методов детекции (новые газы, новые алгоритмы) или критических исправлений. Не обновляется при добавлении новых Presets или тюнинге defaults.
