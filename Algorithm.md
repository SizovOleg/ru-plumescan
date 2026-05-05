# RU-PlumeScan — Algorithm v2.3

**Версия:** 2.3  
**Дата:** 2026-04-26  
**Статус:** Формальная техническая спецификация Configurable Detection Surface  
**Соответствие DNA:** v2.2  
**Замена:** Algorithm.md v2.2 (archived)

**Изменения v2.2 → v2.3:**

1. **§3.4 Background construction полностью переписан** под dual baseline approach (CHANGE-0017):
   - §3.4.0 NEW: Reference Baseline construction from protected areas (positive space, primary)
   - §3.4.1 KEEP: Regional climatology с industrial buffer (secondary)
   - §3.4.2 KEEP: Local annulus correction
   - §3.4.3 NEW: Dual baseline cross-check (compute оба, flag divergence)
2. **§3.5 Anomaly metrics extended** — добавлены `delta_vs_reference`, `baseline_consistency_flag`
3. **§13.1 Known limitations** — REMOVE wetland_CH4 background limitation (решена через positive space approach), ADD reference zones quality limitations (Алтайский pending QA)
4. **Tool-paper framing** добавлен второй novelty argument: reference-anchored baseline approach
5. **Common Plume Schema extended** — добавлены поля `matched_inside_reference_zone`, `delta_vs_reference`, `baseline_consistency_flag`

**Источники методологии:**
- Schuit et al. 2023, ACP, doi:10.5194/acp-23-9071-2023 (CH₄ pre-ML logic, IME U_eff calibration)
- Varon et al. 2018, AMT, doi:10.5194/amt-11-5673-2018 (IME concept origin)
- Beirle et al. 2019, Sci. Adv., doi:10.1126/sciadv.aax9800 (NO₂ divergence method, τ=4h)
- Beirle et al. 2021, ESSD, doi:10.5194/essd-13-2995-2021 (NO₂ point source catalog)
- Fioletov et al. 2015, 2020 (SO₂ plume model + TROPOMI application)
- Lorente et al. 2021, AMT, doi:10.5194/amt-14-665-2021 (TROPOMI XCH₄ QA)

**Источник методологического contribution в v2.3 (НОВОЕ):** Использование российских заповедников как enforced clean baseline reference. Federal protected status (IUCN Ia category) гарантирует отсутствие industrial activity внутри границ. Это **positive-space approach** vs negative-space industrial buffer exclusion, имеющий unknown unknowns.

---

## 0. Структура документа

- §1: Принципы и инварианты
- §2: Доменная модель (Common Plume Schema, Configuration, Run, **Reference Clean Zone**)
- §3: Алгоритм CH₄ — regional threshold-based detection с **dual baseline approach**
- §4: Алгоритм NO₂ — flux divergence following Beirle 2019/2021
- §5: Алгоритм SO₂ — wind rotation following Fioletov 2020
- §6: IME mass quantification (experimental, CH₄ only)
- §7: Multi-gas evidence и классификация (novel component)
- §8: Configuration Presets
- §9: Reference Catalog Adapter (RCA) — supported sources
- §10: Comparison Engine
- §11: **Reference Baseline Builder** (новая секция в v2.3)
- §12: Sensitivity analysis и synthetic injection
- §13: GEE implementation gotchas
- §14: Open questions и known limitations
- §15: Версионирование Algorithm

---

## 1. Принципы и инварианты

### 1.1. Архитектурные принципы

1. **Per-gas methodology.** CH₄, NO₂, SO₂ детектируются разными алгоритмами.
2. **Per-orbit, не composite.** Plumes — transient.
3. **Object-level detection.**
4. **Wind-source validation.**
5. **Configurable parameters.**
6. **Output traceability.** Каждое событие хранит config snapshot.
7. **Reproducible on GEE.**
8. **Region-agnostic implementation, region-tuned defaults.**
9. **Positive-space baseline preferred over negative-space exclusion (НОВОЕ в v2.3).** Reference Clean Zones (заповедники) обеспечивают enforced clean baseline; industrial buffer exclusion остаётся как complementary (broader spatial coverage), не primary.

### 1.2. Что считается результатом алгоритма

- **Plume Event Catalog** — FeatureCollection в GEE Asset
- **Persistence Map** — растровая поверхность плотности повторяющихся событий
- **Time Series для known sources**
- **Sensitivity Sweep**
- **Reference Baseline Asset (НОВОЕ в v2.3)** — standalone clean atmosphere reference dataset для Western Siberia, computed из protected areas. Публикуется отдельно как scientific artifact.

### 1.3. Что НЕ результат

- Single-pixel maxima без object structure
- Composite means без disaggregation
- Threshold values сами по себе
- Z-score карты без object extraction
- IME quantification без явного uncertainty disclosure
- **Industrial-buffer-only baseline без reference cross-check (НОВОЕ в v2.3)** — это negative-space approach с unknown unknowns

---

## 2. Доменная модель

### 2.1. Common Plume Schema (extended in v2.3)

Группировка как в v2.2, плюс новые поля.

#### Идентификация
```
event_id          : string  (unique, format "<source>_<gas>_<YYYYMMDD>_<lat6>_<lon6>")
source_catalog    : string  ("ours", "schuit2023", "imeo_mars", "cams_hotspot", ...)
source_event_id   : string
schema_version    : string  ("1.1" — bumped due to v2.3 schema extension)
ingestion_date    : date
```

#### Базовая атрибутика
```
gas               : enum    ("CH4" | "NO2" | "SO2")
date_utc          : date
time_utc          : time
orbit             : int
```

#### Геометрия
```
lon, lat          : float
geometry          : Polygon
area_km2          : float
n_pixels          : int
```

#### Detection metrics (наш source)
```
max_z, mean_z              : float
max_delta, mean_delta      : float    (Δ vs hybrid background)
detection_method           : string   ("regional_threshold" | "beirle_divergence" | "fioletov_rotation")
```

#### Wind context
```
wind_u, wind_v             : float
wind_speed                 : float
wind_dir_deg               : float
plume_axis_deg             : float
wind_alignment_score       : float
wind_source                : string   ("ERA5_HOURLY")
```

#### Source attribution
```
nearest_source_id              : string
nearest_source_distance_km     : float   
nearest_source_type            : enum
```

#### Magnitude proxy
```
magnitude_proxy        : float
magnitude_proxy_unit   : string
```

#### Quantification (experimental)
```
ime_kg                       : float
q_kg_h_experimental          : float
q_uncertainty_factor         : float
quantification_method        : string
quantification_disclaimer    : string
```

#### Classification
```
class                  : enum
confidence             : enum
confidence_score       : float
qa_flags               : string
```

#### Reference baseline integration (НОВОЕ в v2.3)
```
delta_vs_regional_climatology  : float    (anomaly от regional baseline, CH4 specific)
delta_vs_reference_baseline    : float    (anomaly от reference baseline, primary)
baseline_consistency_flag      : bool     (true = оба baselines agree within tolerance,
                                            false = diverge → contamination suspected)
nearest_reference_zone         : string   ("yugansky" | "verkhnetazovsky" | "kuznetsky_alatau" | "altaisky" | null)
matched_inside_reference_zone  : bool     (true = candidate detected внутри границ заповедника →
                                            автоматический false positive flag)
```

`matched_inside_reference_zone = true` — это automatic red flag. Если detection произошёл inside law-protected clean zone, это либо:
- False positive (методологическая проблема в pipeline)
- Real anomaly которая bypassed protected status (например, transboundary advection, retrieval artifact)

В обоих случаях event требует review. Confidence автоматически снижается до `low`.

#### Cross-source agreement
```
matched_schuit2023        : bool
schuit_event_id           : string
matched_imeo_mars         : bool
imeo_event_id             : string
matched_cams              : bool
cams_event_id             : string
agreement_score           : int
last_comparison_date      : date
```

#### Configuration provenance
```
algorithm_version    : string  ("2.3")
config_id            : string
params_hash          : string
run_id               : string
run_date             : date
```

#### ML-readiness slots
```
expert_label             : enum
label_source             : string
label_date               : date
label_confidence         : int
feature_vector           : string
```

### 2.2. Reference Clean Zone object (НОВОЕ в v2.3)

```json
{
  "zone_id": "yugansky",
  "zone_name_ru": "Юганский заповедник",
  "zone_name_en": "Yugansky Strict Nature Reserve",
  "boundary": <Polygon>,
  "internal_buffer_km": 10,
  "centroid_lat": 60.5,
  "centroid_lon": 74.5,
  "area_km2_total": 6500,
  "area_km2_useable": 5000,  // total - internal buffer
  "natural_zone": "middle_taiga_with_wetlands",
  "latitude_band_min": 58.0,
  "latitude_band_max": 65.0,
  "quality_status": "active",  // "active" | "optional_pending_quality" | "unreliable_for_xch4_baseline"
  "established_year": 1982,
  "iucn_category": "Ia",
  "official_url": "http://ugansky.ru"
}
```

Hardcoded set in v1.0: 4 zones (Юганский, Верхнетазовский, Кузнецкий Алатау, Алтайский). Адаптация (изменение списка, изменение latitude bands) — требует мутации DNA per §2.3.

### 2.3. Configuration object (extended in v2.3)

Все поля из v2.2, плюс новая секция `reference_baseline`:

```json
{
  "config_id": "default",
  "algorithm_version": "2.3",
  "gas": "CH4",
  
  // ... все поля из v2.2 ...
  
  "reference_baseline": {
    "enabled": true,
    "use_zones": ["yugansky", "verkhnetazovsky", "kuznetsky_alatau"],
    "use_altaisky_if_quality_passed": true,
    "altaisky_quality_threshold_ppb": 30,
    "stratification": "by_latitude",
    "asset_path": "RuPlumeScan/baselines/reference_<gas>_<period>"
  },
  
  "background": {
    "mode": "dual_baseline",  // "dual_baseline" | "regional_only" | "reference_only"
    "primary": "reference",   // "reference" | "regional"
    "consistency_tolerance_ppb": 30,
    
    // Regional climatology (теперь secondary)
    "regional": {
      "enabled": true,
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
  
  // ... остальные секции из v2.2 ...
  
  "params_hash": "<computed at run start>"
}
```

### 2.4. Run lifecycle (extended in v2.3)

#### 2.4.1. Canonical Provenance Pattern (NEW в v2.3, P-01.0c)

Each Run следует этому pattern для DNA §2.1 запрет 12 compliance («Не выдавать Run без полного config snapshot»):

1. **Process start:** compute `provenance = compute_provenance(config, config_id, period)` ONCE.  
   Returns immutable `Provenance` dataclass (frozen=True) — same config dict ALWAYS produces same Provenance object.
2. **Pre-submission:** log STARTED entry с `write_provenance_log(provenance, status="STARTED", ...)`.
3. **Submission:** submit batch tasks (Provenance не recomputed — reused by reference).
4. **Post-completion:**
   - Apply `provenance.to_asset_properties()` к exported assets via `ee.data.setAssetProperties` immediately после combine task SUCCEEDED (не later — config could drift).
   - Log SUCCEEDED entry с `write_provenance_log(provenance, status="SUCCEEDED", ...)`.

**Critical invariant:** same Provenance object reference flows через все 4 шага. Hash drift impossible by construction (dataclass frozen=True).

**Helpers** (single source of truth — `src/py/rca/provenance.py`):
- `compute_provenance(config, config_id, period, algorithm_version, rna_version) → Provenance`
- `Provenance.to_asset_properties() → dict` (suitable для `setAssetProperties`)
- `Provenance.to_log_entry(event, **extra) → dict` (suitable для jsonl)
- `write_provenance_log(provenance, status, gas, period, asset_id, extra=...) → Path`
- `canonical_serialize(config) → str` (the ONLY allowed serialization для `params_hash`)

**Audit:** `tools/audit_provenance_consistency.py` CI gate enforces consistency:
- Каждый baseline/catalog asset имеет provenance triple
- Asset.params_hash matches at least one log entry с matching run_id
- Empty allowlist policy after P-01.0c — strict CI gate

#### Anti-patterns (prohibited — these caused TD-0024)

| ❌ Anti-pattern | ✓ Required pattern |
|-----------------|---------------------|
| **Calling `compute_provenance(...)` multiple times for the same Run** (e.g., once в build script, once в closure script) | Compute **ONCE** at process start. Pass returned `Provenance` object к все subsequent operations. |
| **Reassembling config dict в closure / monitoring / report scripts** with «similar» keys | Closure scripts MUST receive Provenance object из upstream pipeline (file, env var, or function argument). Never recompute hash from re-assembled config. |
| **Mutating config dict** between hash computation и asset metadata write | `Provenance` dataclass `frozen=True` enforces this structurally. Never bypass с `dataclasses.replace()` mid-Run. |
| **Calling `hashlib.sha256` или `json.dumps` directly на config** | Always use `compute_provenance` / `canonical_serialize`. Direct hashing skips order-normalization → drift. |
| **Computing `params_hash` for STARTED log с config A, then asset metadata с config B** ("close-but-different" dicts) | Same Provenance object flows through. STARTED, SUCCEEDED logs, и `setAssetProperties` все consume same instance. |
| Letting build script set asset metadata via `combined.set({...})` без provenance fields, then closure script bolts them on later | Build script must integrate `compute_provenance` natively. See TD-0025 follow-up. |

**Concrete code example** demonstrating canonical pattern:

```python
from rca.provenance import compute_provenance, write_provenance_log
import ee

# === ONCE at process start ===
config = build_config_from_preset_name(args.preset)  # full Configuration dict
prov = compute_provenance(config, config_id=args.preset, period="2019_2025")

# === STARTED log (immediately after) ===
write_provenance_log(prov, status="STARTED", gas=args.gas, period="2019_2025",
                     asset_id=final_asset_path)

# === Submission (Provenance не recomputed) ===
task = ee.batch.Export.image.toAsset(image=combined, assetId=final_asset_path, ...)
task.start()

# === Post-completion ===
ee.data.setAssetProperties(final_asset_path, prov.to_asset_properties())
write_provenance_log(prov, status="SUCCEEDED", gas=args.gas, period="2019_2025",
                     asset_id=final_asset_path, extra={"n_tasks": 12})
```

**Enforcement:** `tools/audit_provenance_consistency.py` runs на every PR (CI) и detects:
- Asset missing provenance triple → fail
- Asset hash не matches any log entry с same run_id → fail (suggests parallel computation drift)
- Allowlist mechanism для phased remediation; strict empty allowlist policy в production.

Per TD-0024 (resolved 2026-05-03): `params_hash` recomputation в parallel code paths is forbidden — it caused hash drift между runtime config dicts. Going forward, only the centralized helpers above are allowed. TD-0025 tracks integration of `compute_provenance` directly into build scripts (still pending для Phase 2A pre-implementation).

```
1. User selects Configuration Preset
2. System computes params_hash, generates run_id
3. System logs run start
4. Pipeline executes:
   a. Load TROPOMI L3 collection
   b. Apply QA filters
   c. Build/load Reference Baseline (если enabled, see §3.4.0)
   d. Build/load Regional Climatology с industrial buffer (см. §3.4.1)
   e. Compute hybrid background (regional + annulus correction)
   f. Compute anomaly metrics:
      - delta_vs_regional_climatology
      - delta_vs_reference_baseline
      - baseline_consistency_flag
   g. Build candidate mask
   h. Connected components → vectorize
   i. Object metrics + wind + source attribution
   j. Check matched_inside_reference_zone (auto-flag if inside)
   k. Compute confidence + class
   l. Optional IME для high-confidence CH4
   m. Append config snapshot to each Feature
5. Export to Asset
6. Log run end
```

---

## 3. Алгоритм CH₄: regional threshold-based detection с dual baseline approach

### 3.1. Framing (важно для публикации)

**Что мы заимствуем у Schuit 2023:**
- Общую логику threshold-based pre-ML detection (filtering → background-subtracted anomaly → object extraction)
- QA filtering parameters
- Concept Z-score + delta dual threshold
- IME quantification logic с TROPOMI-specific U_eff calibration

**Что отличается от Schuit 2023:**
- **Background construction.** Schuit использует per-scene 32×32 normalization для CNN input. Наш подход: **dual baseline** — reference baseline (positive space, anchored в заповедниках) + regional climatology с industrial buffer (negative space, broader coverage). Обоснование: для Западной Сибири с её heterogeneous biomes (болота, тайга, мерзлота, степи) per-scene normalization теряет regional context, а single-source negative-space exclusion имеет unknown unknowns.
- **Reference-anchored baseline (НОВОЕ в v2.3, novel methodological contribution).** Используем federal protected nature reserves (Юганский + Верхнетазовский + Кузнецкий Алатау + optionally Алтайский) как enforced clean reference zones. Zone-stratified baseline по latitude bands.
- **Detection logic.** Threshold-based detection поверх Z-score карт. CNN/SVC stages Schuit (Sections 2.3.2, 2.4) **не воспроизводим**.
- **Source attribution.** Industrial mask + nearest source distance.

**Корректное цитирование в публикации:**

> «Detection follows a regional threshold-based approach informed by the pre-ML processing logic of Schuit et al. (2023, Sect. 2.2): QA filtering, background-subtracted anomaly, and connected component object extraction. Background construction departs from Schuit's per-scene CNN-input normalization and uses a dual baseline approach: (1) a positive-space reference baseline anchored in Russian Federation strict nature reserves (zapovedniks) where industrial activity is prohibited by law (Yugansky, Verkhnetazovsky, Kuznetsky Alatau, optionally Altaisky); (2) a regional climatology with industrial buffer exclusion as complementary broader-coverage baseline. Cross-checking between the two baselines flags pixels with possible background contamination. The CNN+SVC machine learning stages of Schuit are not reproduced; v2.0 will introduce ML classification trained on accumulated cross-source agreement labels.»

### 3.2. Входные данные

```javascript
const collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4');
const band = 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected';
```

Дополнительные коллекции:
- ERA5 для ветра: `ECMWF/ERA5/HOURLY` (full reanalysis)
- Snow mask: `MODIS/061/MOD10A1` (NDSI)
- Industrial proxy: `RuPlumeScan/industrial/proxy_mask`
- **Protected areas reference: `RuPlumeScan/reference/protected_areas_mask`** (НОВОЕ в v2.3)
- Reference zones FeatureCollection: `RuPlumeScan/reference/protected_areas` (per-zone polygons + metadata)

### 3.3. QA filtering (Lorente 2021)

Без изменений с v2.2:

```javascript
function applyCH4_QA(img, qa_config) {
  let masked = img;
  
  if (img.bandNames().contains('qa_value')) {
    masked = masked.updateMask(masked.select('qa_value').gte(qa_config.qa_value_min));
  }
  if (img.bandNames().contains('aerosol_optical_depth')) {
    masked = masked.updateMask(masked.select('aerosol_optical_depth').lte(qa_config.aod_max));
  }
  if (img.bandNames().contains('solar_zenith_angle')) {
    masked = masked.updateMask(masked.select('solar_zenith_angle').lt(qa_config.solar_zenith_max_deg));
  }
  
  // Physical range
  masked = masked.updateMask(
    masked.select(band).gte(qa_config.physical_range_min_ppb)
        .and(masked.select(band).lte(qa_config.physical_range_max_ppb))
  );
  
  // Snow mask
  const snow = ee.ImageCollection('MODIS/061/MOD10A1')
    .filterDate(img.date(), img.date().advance(1, 'day'))
    .select('NDSI_Snow_Cover')
    .first();
  if (snow) {
    masked = masked.updateMask(snow.unmask(0).lt(qa_config.snow_mask_threshold));
  }
  
  return masked;
}
```

### 3.4. Background construction — DUAL BASELINE APPROACH (полностью переписан в v2.3)

#### 3.4.0. Reference Baseline construction (positive space, primary) — НОВОЕ в v2.3

Reference baseline computed **только** из pixels внутри protected areas (после internal buffer apply). Это **primary clean baseline** — anchored в federal-protected zones.

**Step 1: Load Reference Clean Zones**

```javascript
// src/js/modules/reference_baseline.js

exports.loadReferenceZones = function(config) {
  const zones_fc = ee.FeatureCollection(
    'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
  );
  
  // Filter по quality status
  const active_zones = zones_fc.filter(
    ee.Filter.inList('quality_status', ['active'])
  );
  
  // Optionally include Алтайский if quality passed
  if (config.reference_baseline.use_altaisky_if_quality_passed) {
    const altaisky_passed = ee.FeatureCollection(
      'projects/nodal-thunder-481307-u1/assets/RuPlumeScan/reference/protected_areas'
    ).filter(ee.Filter.and(
      ee.Filter.eq('zone_id', 'altaisky'),
      ee.Filter.eq('quality_status', 'active')  // updated после QA test
    ));
    return active_zones.merge(altaisky_passed);
  }
  
  return active_zones;
};
```

**Step 2: Apply internal buffer per zone**

Каждый зон имеет свой `internal_buffer_km` (Юганский 10 km close to oil&gas, Верхнетазовский 5 km, Кузнецкий Алатау 5 km, Алтайский 5 km). Это исключает edge effects от внешней активности.

```javascript
exports.applyInternalBuffers = function(zones_fc) {
  return zones_fc.map(function(zone) {
    const buffer_km = ee.Number(zone.get('internal_buffer_km'));
    const buffered = zone.geometry().buffer(buffer_km.multiply(-1000));
    return zone.setGeometry(buffered);
  });
};
```

Negative buffer (`buffer(-1000m)`) shrinks polygon inward.

**Step 3: Build per-zone climatology**

Per-zone, per-month, per-pixel:

```
For each zone z:
  For each month m in [1..12]:
    For each pixel (x,y) inside zone (after internal buffer):
      C_z(x,y,m) = median{X(x,y,t) : year(t) ∈ [2019, target_year-1], 
                                      |DOY(t) - DOY_target| ≤ doy_window_half_days,
                                      pixel inside zone z}
      σ_z(x,y,m) = 1.4826 · MAD{X(x,y,t)}
      count_z(x,y,m) = N valid observations
```

```javascript
exports.buildZoneBaselines = function(zones_fc, target_year, target_month, config) {
  const zone_baselines = zones_fc.map(function(zone) {
    const zone_geom = zone.geometry();
    
    const filtered = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4')
      .select('CH4_column_volume_mixing_ratio_dry_air_bias_corrected')
      .filter(ee.Filter.calendarRange(2019, target_year - 1, 'year'))
      .filter(ee.Filter.calendarRange(target_month - 1, target_month + 1, 'month'))
      .map(function(img) { return img.clip(zone_geom); });
    
    const median = filtered.reduce(ee.Reducer.median()).rename('zone_baseline');
    const mad = filtered
      .map(function(img) { return img.subtract(median).abs(); })
      .reduce(ee.Reducer.median())
      .multiply(1.4826)
      .rename('zone_sigma');
    const count = filtered.count().rename('zone_count');
    
    // Aggregate to single value per zone (mean of valid pixels)
    const zone_baseline_value = median.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: zone_geom,
      scale: 7000
    }).get('zone_baseline');
    
    const zone_sigma_value = mad.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: zone_geom,
      scale: 7000
    }).get('zone_sigma');
    
    return zone.set({
      'baseline_ppb': zone_baseline_value,
      'sigma_ppb': zone_sigma_value,
      'target_year': target_year,
      'target_month': target_month
    });
  });
  
  return zone_baselines;
};
```

**Step 4: Latitude-stratified baseline для AOI**

Каждый pixel в AOI берёт baseline от ближайшего по широте reference zone:

```javascript
exports.buildLatitudeStratifiedBaseline = function(aoi, zone_baselines, target_year, target_month, scale_m) {
  // Extract zone centroids and baselines
  const zones_list = zone_baselines.toList(zone_baselines.size());
  
  // For each pixel in AOI, find nearest zone by latitude
  const lat_image = ee.Image.pixelLonLat().select('latitude');
  
  // Build distance-weighted baseline (closest zone wins)
  let baseline_image = ee.Image.constant(0);
  let distance_image = ee.Image.constant(99999);
  
  zones_list.evaluate(function(zones_array) {
    zones_array.forEach(function(zone_feature) {
      const props = zone_feature.properties;
      const zone_lat = props.centroid_lat;
      const baseline_val = props.baseline_ppb;
      
      const lat_diff = lat_image.subtract(zone_lat).abs();
      const closer_mask = lat_diff.lt(distance_image);
      
      baseline_image = baseline_image.where(closer_mask, ee.Image.constant(baseline_val));
      distance_image = distance_image.min(lat_diff);
    });
  });
  
  return baseline_image.rename('reference_baseline').reproject({
    crs: 'EPSG:4326', scale: scale_m
  });
};
```

**Note:** Это упрощённая реализация — production version в RNA §11 использует server-side approach без `evaluate()` callback.

**Sanity checks для Reference Baseline (revised 2026-04-28 against empirical data):**

Original ranges (1900-1950 ppb July peak, 30-80 ppb amplitude) were
projections from in-situ surface CH4 flux to TROPOMI column observations
and turned out to be **overestimates**. Column XCH4 (vertically integrated)
is much flatter than near-surface CH4 because boundary layer accumulation
and atmospheric mixing dilute wetland emission signal in the column total.

Revised expectations validated against Sizov et al. (in prep, Western
Siberia methane wetland monitoring project, 7-year empirical TROPOMI L3
climatology 2019-2025):

| Metric | Empirical (article zone-mean wetland) | Yugansky concentrated wetland (>70%) |
|---|---|---|
| Peak month | August-September | August-October |
| Peak XCH4 | ~1860-1880 ppb | ~1880-1900 ppb (+20-30 ppb vs zone-mean) |
| Trough month | April-May (post-snowmelt) | April-May |
| Trough XCH4 | ~1840-1860 ppb | ~1870-1880 ppb |
| Seasonal amplitude | ~15-25 ppb | ~15-30 ppb |
| Annual trend | +9 ppb/year (2019: 1821 → 2025: 1884), matches global | matches |

Yugansky values are 20-30 ppb higher than article zone-mean because Yugansky
useable area has >70% wetland fraction (Vasyugan bog interior после 10 km
buffer cuts off taiga edges), while article zone-4 (Middle taiga) is only
28.5% wetland (rest forest at ~1849 ppb dilutes zone-mean).

**This validates dual baseline architecture** — reference-anchored approach
delivers cleaner wetland signature than industrial-buffer-exclusion (negative
space) methodology. Concentrated wetland reference is exactly what we
engineered.

**Updated red flags (baseline build flawed if):**
- Yugansky baseline зимой > 1920 ppb (was: > 1900) — local CH4 contamination suspect
- Yugansky baseline летом > 1950 ppb (was: > 1970) — boundary layer / retrieval bias
- Seasonal amplitude > 50 ppb — likely retrieval noise, not real signal
- Verkhne-Tazovsky systematically warmer than Yugansky in summer — northern permafrost should be 5-15 ppb cooler in column

**Validation source:** Sizov et al. in prep, table 3 (7-year mean monthly
XCH4 by wetland zone) and table 4 (annual trend, +9 ppb/year). См.
`docs/p-01.0a_validation_report.md` для side-by-side comparison.

#### 3.4.1.1. Per-source-type buffer (NEW в v2.3.1 / P-01.0d, TD-0027)

Industrial mask construction extended к use **per-source-type buffer** instead of uniform 30 km. Per-feature classification (`src/py/rca/classify_source_types.py`):

| source_type / subtype | category | buffer_km |
|-----------------------|----------|----------:|
| oil_gas / production_field | gas_field | **50** |
| oil_gas / viirs_flare_proxy + radiance ≥100 nW/cm²/sr | viirs_flare_high | 30 |
| oil_gas / viirs_flare_proxy + radiance <100 | viirs_flare_low | 15 |
| power_plant / coal\|gas\|tpp_gas | tpp_gres | 30 |
| power_plant / hydro\|nuclear | (DROPPED) | — |
| coal_mine | coal_mine | 30 |
| metallurgy | smelter | 30 |

**Rationale:** P-01.2 dual baseline cross-check identified Tambeyskoye gas field as suspect cluster #4 (mean Δ=59.6 ppb после 30 km uniform buffer). Major gas extraction infrastructure spans 50+ km — uniform 30 km buffer insufficient. Hydro/nuclear emit no detection-relevant gases — exclude entirely (cleaner semantics than 0 km).

VIIRS radiance-differentiated buffer: high-radiance flares (≥100 nW/cm²/sr) likely persistent gas-processing facilities → 30 km; localized low-radiance flares → 15 km.

Asset: `RuPlumeScan/industrial/proxy_mask_buffered_per_type` (replaces uniform `proxy_mask_buffered_30km` for new builds; old kept для backward-compat).

#### 3.4.1.2. Urban masking (NEW в v2.3.1 / P-01.0d, TD-0023)

NO₂/SO₂ regional baselines additionally mask **urban areas** identified via JRC Global Human Settlement Layer (GHS-SMOD 2030, 1 km native). Threshold ≥22 = semi-dense urban cluster + urban centre.

**Rationale:** anthropogenic NO₂/SO₂ emissions от urban transport / heating systems / construction confound regional baseline. P-01.0b finding: cities like Tyumen / Surgut / Novokuznetsk previously masked only via collocated TPP buffer, не by urban definition itself. Now both masks combined: `clean ↔ industrial-non-buffered AND non-urban`.

Reprojection convention: GHS-SMOD 1 km → analysis 7 km via `reduceResolution(MAX)` — any 1 km urban pixel → 7 km cell urban (conservative; avoids dilution at city boundaries).

Asset: `RuPlumeScan/urban/urban_mask_smod22`. Urban masking applied при `--use-urban-mask` flag в `build_regional_climatology.py`.

CH₄ regional baseline does NOT apply urban masking — methane sources include wetlands (rural) и urban gas leakage; urban exclusion would lose signal. NO₂/SO₂ urban-source confounding far stronger.

#### 3.4.1. Regional climatology с industrial buffer (secondary, broader coverage)

**Это existing approach из v2.2, теперь secondary.**

Per pixel (x,y), для месяца m, по архиву [2019, target_year-1]:

```
C_regional(x,y,m) = median{X(x,y,t) : year(t) ∈ [2019, target_year-1], 
                                       |DOY(t) - DOY_target| ≤ doy_window_half_days,
                                       x not in industrial_buffer}
```

Industrial buffer exclusion (30 km от known sources) применяется как secondary mechanism. Но мы знаем что this approach имеет unknown unknowns (DNA §1.5: positive baseline ≠ negative buffer exclusion).

```javascript
function buildRegionalClimatology(target_year, target_month, bg_config) {
  const collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4')
    .select('CH4_column_volume_mixing_ratio_dry_air_bias_corrected');
  
  const ind_mask = ee.Image('RuPlumeScan/industrial/proxy_mask')
    .focal_max({radius: bg_config.regional.industrial_buffer_exclude_km * 1000, 
                units: 'meters'})
    .not();
  
  const filtered = collection
    .filter(ee.Filter.calendarRange(
      bg_config.regional.history_years_min, 
      target_year + bg_config.regional.history_years_max_offset, 
      'year'
    ))
    .filter(ee.Filter.calendarRange(target_month - 1, target_month + 1, 'month'))
    .map(function(img) { return img.updateMask(ind_mask); });
  
  const median = filtered.reduce(ee.Reducer.median()).rename('regional_baseline');
  const mad = filtered
    .map(function(img) { return img.subtract(median).abs(); })
    .reduce(ee.Reducer.median())
    .multiply(1.4826)
    .rename('regional_sigma');
  const count = filtered.count().rename('regional_count');
  
  return median.addBands(mad).addBands(count);
}
```

#### 3.4.2. Local annulus correction

Для конкретного дня t — без изменений с v2.2:

```
R(x,y,t) = X(x,y,t) - C_regional(x,y,m)
S(x,y,t) = focal_median(R, annulus(r_in, r_out))
```

Annulus реализуется через `ee.Kernel.fixed()` с явной матрицей (см. §13.1).

#### 3.4.3. Hybrid background и dual baseline cross-check (НОВОЕ в v2.3)

```javascript
exports.buildHybridBackground = function(observation, target_year, target_month, aoi, config) {
  // Build BOTH baselines in parallel
  const reference_baseline = buildReferenceBaseline(target_year, target_month, aoi, config);
  const regional_climatology = buildRegionalClimatology(target_year, target_month, config.background);
  
  // Apply annulus correction to regional
  const annulus_kernel = makeAnnulusKernel(
    config.background.annulus.inner_km * 1000,
    config.background.annulus.outer_km * 1000,
    config.analysis_scale_m
  );
  
  const residual = observation.subtract(regional_climatology.select('regional_baseline'));
  const annulus_correction = residual.focal_median({kernel: annulus_kernel});
  
  // Hybrid regional background
  const lambda = config.background.lambda_climatology;
  const regional_hybrid = regional_climatology.select('regional_baseline')
    .add(annulus_correction.multiply(1 - lambda))
    .rename('regional_hybrid');
  
  // Compute anomalies vs both baselines
  const delta_vs_regional = observation.subtract(regional_hybrid).rename('delta_regional');
  const delta_vs_reference = observation.subtract(reference_baseline).rename('delta_reference');
  
  // Consistency flag
  const tolerance = config.background.consistency_tolerance_ppb;
  const baseline_diff = regional_hybrid.subtract(reference_baseline).abs();
  const consistency_flag = baseline_diff.lt(tolerance).rename('baseline_consistency');
  
  return ee.Image.cat([
    regional_hybrid,
    reference_baseline,
    delta_vs_regional,
    delta_vs_reference,
    consistency_flag,
    regional_climatology.select('regional_sigma'),
    regional_climatology.select('regional_count')
  ]);
};
```

**Что cross-check показывает:**

- `consistency_flag = true`: оба baselines дают similar value (разница < 30 ppb). Trustable.
- `consistency_flag = false`: baselines diverge (разница > 30 ppb). Возможные причины:
  - Regional climatology contaminated by undocumented industrial sources в данном регионе → Z-score над пикселем underestimated
  - Reference baseline biased для этой широты (например, Кузнецкий Алатау reference применяется в Алтайский край но с изменённой вертикальной структурой)
  - Real persistent enhancement в области (но без known industrial source в нашем inventory)
  
**Decision logic в pipeline:**

При `consistency_flag = false`, **primary anomaly metric** для detection — `delta_vs_reference` (более defensible, anchored в protected zone). `delta_vs_regional` записывается в feature properties как secondary check, но не используется для threshold mask.

При `consistency_flag = true`, оба metrics используются (`mean(delta_vs_regional, delta_vs_reference)`).

### 3.5. Anomaly metrics (extended in v2.3)

```javascript
function computeAnomalyMetrics(hybrid_bg, observation, config) {
  // Primary: choose based on consistency
  const consistency = hybrid_bg.select('baseline_consistency');
  
  // Use reference baseline когда consistent OR mode = "reference_only"
  // Use mean когда consistent AND mode = "dual_baseline"
  const use_reference_primary = config.background.mode === 'reference_only' || 
                                  consistency.eq(1).and(config.background.primary === 'reference');
  
  const delta_primary = ee.Image.constant(0)
    .where(use_reference_primary, hybrid_bg.select('delta_reference'))
    .where(use_reference_primary.not(), hybrid_bg.select('delta_regional'))
    .rename('delta_primary');
  
  const sigma = hybrid_bg.select('regional_sigma');
  const sigma_floor = ee.Image.constant(config.background.sigma_floor_units);
  const sigma_eff = sigma.max(sigma_floor).rename('sigma_eff');
  
  const z_score = delta_primary.divide(sigma_eff).rename('z');
  
  return ee.Image.cat([
    delta_primary,
    hybrid_bg.select('delta_regional'),
    hybrid_bg.select('delta_reference'),
    consistency,
    sigma_eff,
    z_score
  ]);
}
```

### 3.6. Pixel-level mask

```javascript
function ch4PixelMask(anomaly, config) {
  const z_test = anomaly.select('z').gte(config.anomaly.z_min);
  const delta_test = anomaly.select('delta_primary').gte(config.anomaly.delta_min_units);
  
  const local_med = anomaly.select('delta_primary').focal_median({
    kernel: makeAnnulusKernel(50000, 150000, 7000)
  });
  const relative = anomaly.select('delta_primary').subtract(local_med);
  const rel_test = relative.gte(config.anomaly.relative_threshold_min_units);
  
  return z_test.and(delta_test).and(rel_test).selfMask();
}
```

### 3.7. Object construction

Без изменений с v2.2:

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

### 3.8. Object metrics (extended in v2.3)

Каждое Feature вычисляет:
- area_km2, centroid, max/mean Z, max/mean delta_primary, n_pixels, plume_axis_deg
- **`delta_vs_regional_climatology`** (mean over object)
- **`delta_vs_reference_baseline`** (mean over object)
- **`baseline_consistency_flag`** (mean over object > 0.5)
- **`matched_inside_reference_zone`** (centroid intersects any reference zone)
- **`nearest_reference_zone`** (closest по latitude)

### 3.9. Wind attribution

Без изменений с v2.2 — single ERA5 source.

### 3.10. Source attribution

Без изменений с v2.2.

### 3.11. Confidence scoring (extended in v2.3)

Многокомпонентный confidence score:

```
C_stat = clip((Z_max - z_min) / (Z_high - z_min), 0, 1)
C_geom = clip((n_pixels - n_min) / (n_high - n_min), 0, 1)
C_wind = max(0, cos(D_θ))   if wind > min, else 0
C_coverage = clip(valid_pixel_fraction / required, 0, 1)
C_consistency = 1 if baseline_consistency_flag else 0.5  (НОВОЕ в v2.3)
C_multi = 1 + α · (N_gases_matched - 1)

C_total = w_stat · C_stat + w_geom · C_geom + w_wind · C_wind + 
          w_coverage · C_coverage + w_consistency · C_consistency
       (multiplied by C_multi cap [1, 1+2α])
```

**Critical adjustment:** Если `matched_inside_reference_zone == true` → `C_total *= 0.3` (downgrade by factor of 0.3, automatic flag for review).

Discretization без изменений: very_high ≥ 0.85, high ≥ 0.65, medium ≥ 0.35, low < 0.35.

### 3.12. Class assignment

Без изменений с v2.2.

---

## 4. Алгоритм NO₂: flux divergence following Beirle 2019/2021

Без изменений с v2.2. См. v2.2 §4 для полной спецификации.

Ключевые формулы:
- `E = D + N/τ` (Beirle 2019)
- `τ = 4h`, `L = NOx/NO2 = 1.32`
- Reproject в EPSG:32642 для divergence

---

## 5. Алгоритм SO₂: wind-rotated oversampling following Fioletov 2020

Без изменений с v2.2. См. v2.2 §5.

Primary: full nonlinear fit (4 params: A, σ_y, L, B) через scipy.optimize.curve_fit.
Fallback: Fioletov simplified (`α/τ` с fixed σ=15km, τ=6h).

---

## 6. IME mass quantification (experimental, CH₄ only)

Без изменений с v2.2.

Default: Schuit 2023 TROPOMI calibration `U_eff = 0.59·U10 + 0.00`.

---

## 7. Multi-gas evidence и классификация (novel component)

Без изменений с v2.2. Это первый novelty argument для tool-paper.

---

## 8. Configuration Presets (extended in v2.3)

Все presets из v2.2 плюс новая секция `reference_baseline` и `background.mode`.

#### `default` (extended)

```json
{
  "config_id": "default",
  "background": {
    "mode": "dual_baseline",
    "primary": "reference",
    "consistency_tolerance_ppb": 30
  },
  "reference_baseline": {
    "enabled": true,
    "use_zones": ["yugansky", "verkhnetazovsky", "kuznetsky_alatau"],
    "use_altaisky_if_quality_passed": true,
    "altaisky_quality_threshold_ppb": 30,
    "stratification": "by_latitude"
  }
  // ... остальное из v2.2 default
}
```

#### `regional_only` (NEW в v2.3) — diagnostic preset

Использует только regional climatology (как было в v2.2). Для диагностики: что если бы reference baseline не существовал.

```json
{
  "config_id": "regional_only",
  "background": {"mode": "regional_only"},
  "reference_baseline": {"enabled": false}
}
```

#### `reference_only` (NEW в v2.3) — diagnostic preset

Использует только reference baseline. Для диагностики чистоты reference approach.

```json
{
  "config_id": "reference_only",
  "background": {"mode": "reference_only"},
  "reference_baseline": {"enabled": true}
}
```

#### Existing presets (`schuit_eq`, `imeo_eq`, `sensitive`, `conservative`)

Все наследуют `default` background settings (dual_baseline mode), но с разными detection thresholds. См. v2.2 §8 для thresholds.

---

## 9. Reference Catalog Adapter (RCA) — supported sources

Без изменений с v2.2. Primary: Schuit 2023, IMEO MARS, CAMS Hotspot.

---

## 10. Comparison Engine

Без изменений с v2.2.

---

## 11. Reference Baseline Builder (NEW в v2.3)

### 11.1. Module purpose

Reference Baseline Builder — отдельный module, который:
1. Загружает Reference Clean Zone polygons (P-00.1 deliverable)
2. Применяет internal buffers per-zone
3. Опционально выполняет QA test для Алтайского
4. Строит per-zone, per-month, per-pixel climatology
5. Aggregates в latitude-stratified baseline для AOI
6. Exports как Asset `RuPlumeScan/baselines/reference_<gas>_<period>`
7. Используется Detection Engine как primary baseline cross-check

### 11.2. Asset structure

```
RuPlumeScan/
├── reference/
│   ├── protected_areas               # FeatureCollection (polygons + metadata)
│   └── protected_areas_mask          # Image (1 inside zone, 0 outside)
│
└── baselines/
    ├── reference_CH4_2019_2025       # Image (per-month bands × 12)
    │                                  # bands: ref_M01, ref_M02, ..., ref_M12,
    │                                  #        sigma_M01, ..., count_M01, ...,
    │                                  #        latitude_band assignment
    ├── reference_NO2_2019_2025
    └── reference_SO2_2019_2025
```

### 11.3. Algorithm steps (formal)

```
INPUT: 
  zones = FeatureCollection of Reference Clean Zones
  target_year, target_month
  config

OUTPUT: 
  Image with per-pixel baseline value, sigma, zone assignment

STEP 1: Load and filter zones
  active_zones = zones.filter(quality_status == "active")
  if config.use_altaisky_if_quality_passed:
    altaisky = zones.filter(zone_id == "altaisky" AND quality_status == "active")
    active_zones = active_zones.merge(altaisky)

STEP 2: Apply internal buffers
  buffered_zones = active_zones.map(
    zone => zone.setGeometry(zone.geometry.buffer(-zone.internal_buffer_km * 1000))
  )

STEP 3: For each zone, build per-pixel climatology
  for each zone z in buffered_zones:
    filtered = TROPOMI_L3_CH4
      .filter(year ∈ [history_min, target_year-1])
      .filter(month ∈ [target_month-1, target_month+1])
      .clip(z.geometry)
    
    z.median_image = filtered.reduce(median)
    z.mad_image = (filtered - median).abs().reduce(median) * 1.4826
    z.count_image = filtered.count()
    
    # Aggregate to single value per zone (mean over zone pixels)
    z.baseline_value = z.median_image.reduceRegion(mean, z.geometry).get('CH4')
    z.sigma_value = z.mad_image.reduceRegion(mean, z.geometry).get('CH4')

STEP 4: Latitude stratification
  For each pixel (lon, lat) in AOI:
    nearest_zone = argmin_{z in active_zones} |z.centroid_lat - lat|
    baseline_image[lon, lat] = nearest_zone.baseline_value
    sigma_image[lon, lat] = nearest_zone.sigma_value
    zone_id_image[lon, lat] = nearest_zone.zone_id

STEP 5: Export
  Asset: RuPlumeScan/baselines/reference_<gas>_<year>
  Bands: baseline_M01..M12, sigma_M01..M12, zone_id_M01..M12
```

### 11.4. Алтайский QA test

Перед использованием Алтайского в production baseline — обязательный test:

```
TEST: Compare Алтайский XCH4 vs Кузнецкий Алатау после seasonal correction.

mean_alt_summer = mean(XCH4 inside Алтайский, June-August, all years 2019-2025)
mean_kuz_summer = mean(XCH4 inside Кузнецкий Алатау, June-August, all years 2019-2025)
mean_alt_winter = mean(XCH4 inside Алтайский, December-February, all years 2019-2025)
mean_kuz_winter = mean(XCH4 inside Кузнецкий Алатау, December-February, all years 2019-2025)

# Both at similar latitudes (51°N vs 54°N), similar seasonal forcing expected
seasonal_diff_alt = mean_alt_summer - mean_alt_winter
seasonal_diff_kuz = mean_kuz_summer - mean_kuz_winter

# Test 1: Absolute level mismatch
abs_diff_summer = |mean_alt_summer - mean_kuz_summer|
abs_diff_winter = |mean_alt_winter - mean_kuz_winter|

# Test 2: Seasonal cycle mismatch  
cycle_diff = |seasonal_diff_alt - seasonal_diff_kuz|

PASS criteria:
  abs_diff_summer < 30 ppb
  abs_diff_winter < 30 ppb  
  cycle_diff < 20 ppb

if all pass:
  Алтайский.quality_status = "active"
else:
  Алтайский.quality_status = "unreliable_for_xch4_baseline"
  log reason: which tests failed, magnitudes
```

#### 11.4.1. Worked example — P-01.0a Altaisky FAIL (2026-04-28)

Первый production run этого QA test (history 2019-2025) **failed**:

| Metric | Value | Tolerance | Status |
|---|---|---|---|
| `alt_summer` (Jun-Aug) | 1842.0190 ppb | — | — |
| `kuz_summer` (Jun-Aug) | 1842.6326 ppb | — | — |
| `abs_diff_summer` | **0.6136 ppb** | < 30 | ✅ PASS |
| `alt_winter` (Dec-Feb) | 1848.1722 ppb | — | — |
| `kuz_winter` (Dec-Feb) | 1883.0369 ppb | — | — |
| `abs_diff_winter` | **34.8647 ppb** | < 30 | ❌ FAIL (+4.86) |
| `seasonal_diff_alt` (sum-win) | -6.1532 ppb | — | nearly flat |
| `seasonal_diff_kuz` (sum-win) | -40.4043 ppb | — | strong winter accumulation |
| `cycle_diff` | **34.2511 ppb** | < 20 | ❌ FAIL (+14.25) |
| **Verdict** | — | — | **`unreliable_for_xch4_baseline`** |

**Physical interpretation (defensible перед reviewers):**

Summer match excellent (0.61 ppb diff) — **both zones показывают similar
free-tropospheric column XCH₄ values around 1842 ppb** в summer. В этом
сезоне planetary boundary layer (PBL) deep enough, чтобы distinguishing
high-altitude vs lowland atmospheric column отсутствует.

Winter divergence (35 ppb) — **Алтайский (centroid 1500-2000 m elevation,
peaks > 3000 m)** is **above typical winter PBL inversion height** (~500-
1500 m в континентальной Сибири). Зимой над high-mountain biome:

- Surface CH₄ accumulation в stable winter PBL **не достигает** column
  retrieval altitude — Алтайский measures predominantly free-tropospheric
  air (relatively constant ~1850 ppb).
- Кузнецкий Алатау (peaks ~1800 m, but most useable area 500-1200 m)
  **внутри** winter PBL inversion → measures surface-trapped CH₄
  accumulation (1883 ppb winter mean, +40 ppb seasonal).

**Это physically meaningful divergence**, не retrieval bug. Алтайский как
reference zone для AOI (latitude band 55-75°N flatlands) **не репрезентативен**
для winter atmospheric column conditions.

**Decision (per DNA §2.1 запрет 16):** Алтайский excluded из production
reference baseline. `quality_status="unreliable_for_xch4_baseline"`.
Production CH₄ baseline = v1 (3 zones: Юганский + Верхне-Тазовский +
Кузнецкий Алатау).

**Defensibility statement для tool-paper Phase 7:**
> "QA test designed to flag reference zones whose atmospheric column
> XCH₄ behaviour diverges from the AOI flatland regime. Altaisky's
> high-altitude location (centroid 1500+ m, peaks > 3000 m) places its
> column above typical winter PBL inversion heights, decoupling its
> winter signature from lowland atmospheric accumulation regime
> (35 ppb winter divergence vs lowland Kuznetsky Alatau, despite 0.6
> ppb summer match). Exclusion from production baseline preserves
> AOI-representative climatology for the 55-75°N detection envelope."

См. полный QA result Asset `RuPlumeScan/validation/altaisky_qa/test_20260428`,
plus `docs/p-01.0a_altaisky_qa_result.json`.

### 11.5. Reference Baseline as standalone Asset

Reference Baseline Asset публикуется отдельно от Detection runs:

- **Asset path:** `RuPlumeScan/baselines/reference_CH4_2019_2025`
- **License:** CC-BY 4.0
- **Zenodo DOI:** assigned at v1.0 release
- **Usage by other researchers:** доступен через GEE для Western Siberia atmospheric studies, не только plume detection
- **Citation:** «Reference Baseline для атмосферного метана над Западной Сибирью на основе российских заповедников: Юганский, Верхнетазовский, Кузнецкий Алатау, Алтайский (when applicable). Period 2019-2025. Generated by RU-PlumeScan v1.0.»

Это **dedicated scientific contribution** независимо от detection toolkit.

### 11.5.1. Validator-side expected ranges (per zone, per month)

Эти ranges — **canonical reference** для verification correctness Reference
Baseline build. Применяются validator (researcher / external reviewer / future
Claude session) для решения PASS/FAIL без обращения к raw TROPOMI data.

**Note:** §3.4.0 «Sanity checks для Reference Baseline» содержит implementer
sanity checks (HOW to build correctly). Эта секция содержит validator
expected ranges (WHAT to expect от correctly-built baseline). Both должны
agree — если diverge, см. OpenSpec MC entries для resolution history.

Empirical values from P-01.0a build (target_year=2025, history 2019-2024,
3 active zones; updated 2026-04-28 against Sizov et al. in prep article t3
seven-year wetland zone climatology).

**Yugansky (60.5°N, useable 2946 km², ~70% wetland fraction):**

| Month | Expected baseline range (ppb) | Empirical M-2025 | Notes |
|-------|-------------------------------|------------------|-------|
| Jan-Feb | 1875-1885 | 1877.91 (M01) | winter accumulation в stable BL |
| Mar | 1875-1885 | 1878.59 | snowmelt onset |
| Apr | 1870-1880 | **1874.61 (trough)** | post-snowmelt clean air |
| May | 1870-1880 | (Q-mid fail M05) | minimum expected |
| Jun-Jul | 1875-1885 | 1874.81 / 1880.38 | summer wetland onset |
| Aug | 1880-1895 | (Q-mid fail M08) | peak wetland emission |
| Sep | 1880-1895 | 1886.82 | continued wetland |
| Oct | 1885-1900 | **1892.05 (peak)** | peak: synoptic BL collapse + late wetland |
| Nov | 1880-1895 | (Q-mid fail M11) | autumn |
| Dec | NaN | NaN | polar night |

- Annual amplitude: ~15-30 ppb (column XCH₄ flatness — boundary layer dilution)
- +20-30 ppb shift vs article zone-mean wetland (concentrated wetland design feature)

**Verkhne-Tazovsky (63.5°N, useable 4066 km², permafrost taiga):**

| Month | Expected baseline range (ppb) | Empirical M-2025 | Notes |
|-------|-------------------------------|------------------|-------|
| Jan-Feb | NaN polar night | NaN (count 0) | no sun at 63.5°N |
| Mar | 1865-1880 | 1871.59 | sun returns |
| Apr | 1860-1875 | 1866.95 | trough |
| May | 1855-1870 | (Q-mid fail) | minimum |
| Jun-Jul | 1855-1870 | 1860.87 / 1863.35 | summer minimum (no wetland here) |
| Aug | 1865-1880 | (Q-mid fail) | rising |
| Sep | 1875-1885 | 1878.33 | rising |
| Oct | 1885-1900 | **1893.96 (peak)** | synoptic peak |
| Nov | 1880-1895 | (Q-mid fail) | autumn |
| Dec | NaN polar night | NaN | |

- Annual amplitude: ~30-35 ppb (larger than Yugansky — less wetland buffering)
- 5-15 ppb cooler than Yugansky in summer (no wetland enhancement)

**Kuznetsky Alatau (54.5°N, useable 2220 km², mountain taiga, no wetlands):**

| Month | Expected baseline range (ppb) | Empirical M-2025 | Notes |
|-------|-------------------------------|------------------|-------|
| Jan | 1875-1890 | 1882.52 | winter (low count ~18, retrieval challenge) |
| Mar | 1870-1885 | 1875.22 | |
| Apr | 1860-1875 | 1863.54 | trough |
| May | 1845-1860 | (Q-mid fail) | summer minimum onset |
| Jun-Jul | 1840-1860 | **1844.64 / 1845.53 (lowest)** | mountain forest, no source |
| Aug | 1855-1875 | (Q-mid fail) | rising |
| Sep | 1860-1875 | 1864.43 | |
| Oct | 1865-1880 | **1872.22 (peak)** | smallest peak (no wetland) |
| Nov | 1860-1875 | (Q-mid fail) | |
| Dec | NaN polar night | NaN | |

- Annual amplitude: ~25-30 ppb
- Lowest summer values among all 3 zones (mountain forest baseline)

**Cross-zone agreement check (validation gate):**

Все 3 zones должны share October peak — это shared synoptic / freeze-up signal,
не zone-specific. Если October НЕ peak в Yugansky или Verkhne-Tazovsky:
investigate (year-to-year variability, wetland phenology shift).

**Altaisky (51.5°N, status: `unreliable_for_xch4_baseline`, NOT in production):**

QA test 2026-04-28 result: alt_summer 1842.02 vs kuz_summer 1842.63 (PASS),
alt_winter 1848.17 vs kuz_winter 1883.04 (FAIL +34.86), cycle_diff 34.25 (FAIL).
Excluded per DNA §2.1 запрет 16. См. `docs/p-01.0a_altaisky_qa_result.json` +
Asset `RuPlumeScan/validation/altaisky_qa/test_20260428`.

**Validation provenance:** `docs/p-01.0a_validation_report.md`,
`docs/p-01.0a_diagnostics_v1_full.json`, OpenSpec MC-2026-04-28-A
(против Sizov et al. in prep article t3 + t4).

---

## 12. Sensitivity analysis и synthetic injection

Без изменений с v2.2. Pass criterion: recovered/injected ≥ 0.7 для amplitude ≥ 30 ppb.

Дополнительно в v2.3:
- **Dual baseline sensitivity sweep** — варьируем `consistency_tolerance_ppb` [10, 20, 30, 50, 100] и смотрим как меняется fraction events с consistency_flag=true
- **Reference vs Regional comparison** — для каждого Plume Event compare `delta_vs_regional` vs `delta_vs_reference`. Histogram divergence показывает где regional climatology contaminated.

---

## 13. GEE implementation gotchas

Без изменений с v2.2. Девять реализационных ловушек:

1. Annulus kernel arithmetic — только через `ee.Kernel.fixed()`
2. Analysis scale ≥ 7000 m
3. `unmask(0)` для XCH4 запрещён
4. `ee.Image.translate()` projection trap для NO₂
5. `bestEffort: true` запрещён для detection statistics
6. `map(closure)` parameter passing — factory pattern
7. Memory limits на export — chunked per gas-month
8. Edge of ROI handling — buffer + clip
9. Snow mask source — MODIS NDSI

**Дополнительная gotcha в v2.3 (10):**

10. **Negative buffer `buffer(-1000m)` requires geometry simplification.** При apply internal buffer к polygon с complex coastlines/borders, negative buffer может create invalid geometries (self-intersecting). Pre-simplify polygon с tolerance 100m перед negative buffer:

```javascript
const simplified = zone.geometry().simplify(100);  // tolerance в metres
const buffered = simplified.buffer(-internal_buffer_km * 1000);
```

---

## 14. Open questions и known limitations

### 14.1. Known limitations (declared в публикациях)

**Single wind source (ERA5)** — ensemble approach unfeasible в pure GEE.

**TROPOMI L3 vs L2** — operational v02.04 vs reprocessed v18_17.

**TROPOMI XCH₄ bias_corrected — необходим но недостаточен.** Snow + low-albedo + high-albedo scenes остаются challenging.

**~~Wetland CH₄ background~~ — REMOVED в v2.3.** Эта проблема **решена** через positive-space approach. Reference baseline от Юганского заповедника (где Васюганские болота составляют значительную часть) является enforced wetland baseline. Industrial buffer exclusion больше не единственная защита от wetland contamination.

**Snow/ice for CH₄ in Arctic winter** — exclude winter scenes → no detection для cold-season events.

**Single-day NO₂ detection недоступна** — Beirle 2019 multi-month average required.

**SO₂ outside known sources** — Fioletov 2020 per-source approach.

**SO₂ detection limits** — Norilsk reliable, mid-size sources marginal.

**Quantification accuracy** — ±50% best case.

**GEE compute quotas** — chunked exports + off-peak.

**No L2 access via GEE JS** — Python-only path.

**Reference zones quality limitations (НОВОЕ в v2.3):**
- Алтайский — pending QA test before production use. Mountain biome может give XCH4 column values несопоставимые с равнинными zones.
- Юганский — окружён active oil&gas industry, edge effects от внешней advection возможны. Mitigation: 10 km internal buffer.
- Reference zones cover only ~3% AOI total (16,832 км² vs ~600,000 км² total Western Siberia AOI). Latitude stratification extrapolates reference baseline за пределы protected zones. Это extrapolation имеет uncertainty, особенно вдали от reference zone centroid.
- Reference zones для NO₂ и SO₂ применимы limited — для NO₂ multi-month averaging integrates over wide geographic range; для SO₂ per-source approach не requires baseline.

### 14.2. Open questions

**Q1: Reference baseline для NO₂ и SO₂.**  
Currently reference baseline применяется только для CH₄. Для NO₂ можно использовать reference zones как clean reference для tropospheric NO₂ column (зимой ожидается background level ~0.5-1.0 µmol/m²). Future enhancement.

**Q2: Reference baseline для historical periods до 2019.**  
TROPOMI начинает 2018-04. Для periods before 2019 — reference baseline недоступен, fall back на regional climatology only.

**Q3: Optional Beirle 2021 ESSD divergence-only mode.**

**Q4: Pixel-wise L (NOx/NO2 ratio) per Beirle 2021 ESSD.**

**Q5: Regional U_eff calibration для Западной Сибири.**

**Q6 (НОВОЕ в v2.3): Latitude stratification vs Spatial interpolation.**  
Currently nearest reference zone by latitude. Альтернатива: spatial interpolation (e.g., distance-weighted между zones). Может better для pixels на границе latitude bands. Future enhancement, requires sensitivity test.

**Q7 (НОВОЕ в v2.3): Reference zones beyond Western Siberia.**  
При extension инструмента на другие регионы РФ (Сибирь, Дальний Восток, Европейская часть) — нужны new reference zones. Российская система заповедников широка (~100+ заповедников по РФ), есть кандидаты для каждого региона.

### 14.3. Что в Roadmap но не в Algorithm v2.3

- v2 ML classifier поверх v1 candidates
- L2 re-processed input через external Python pipeline
- Variable τ для NO₂ через ERA5 boundary_layer_height
- High-resolution Sentinel-2 follow-up для confirmed CH₄ events
- Pixel-wise L для NO₂
- Regional U_eff calibration
- **Reference baseline для NO₂ и SO₂** (новое)
- **Reference zones extension за пределы Западной Сибири** (новое)

См. `Roadmap.md`.

---

## 15. Версионирование Algorithm

| Версия | Дата | Изменение |
|---|---|---|
| 1.x | до 2026-04-13 | v1 deprecated (monthly composites concept error) |
| 2.0 | 2026-04-25 | Per-gas approach, Schuit/Beirle/Fioletov |
| 2.1 | 2026-04-25 | Configurable Detection Surface, Common Plume Schema, поправки v2.0 |
| 2.2 | 2026-04-25 | Verification через GPT-5.5 на peer-reviewed sources. 9 точечных уточнений (CH₄ framing, SO₂ fit, IME U_eff, Lauvaux→IMEO, ERA5, multi-gas matching framing, Beirle bibliographic). |
| 2.3 | 2026-04-26 | Reference-anchored baseline approach (CHANGE-0017). §3.4 полностью переписан под dual baseline. Reference Baseline Builder как §11. Common Plume Schema extended (delta_vs_reference, baseline_consistency_flag, matched_inside_reference_zone). Wetland_CH4 limitation removed (решена через positive space). Reference zones quality limitations added. Tool-paper второй novelty argument. |

Algorithm обновляется при добавлении новых методов детекции или критических исправлений.
