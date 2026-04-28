/**
 * @fileoverview Unit tests for reference_baseline.js module.
 *
 * Запуск: вставить в GEE Code Editor, нажать Run, проверить выводы Console.
 * Это smoke-tests без assertion framework — нет JS test runner в GEE.
 *
 * Test cases (Algorithm v2.3 §11, RNA v1.2 §11.2):
 *   T1. loadReferenceZones returns 3 active zones (Алтайский excluded).
 *   T2. loadReferenceZones с use_altaisky_if_quality_passed=true:
 *       пока Алтайский имеет optional_pending_quality — всё ещё 3 zones.
 *   T3. applyInternalBuffers: Юганский area сократилась после buffer(-10 km).
 *   T4. buildZoneBaselines возвращает per-zone baseline_ppb для CH4 / July 2025.
 *   T5. buildStratifiedBaseline: pixel в (62°N, 75°E) получает baseline от
 *       Verkhne-Tazovsky (latitude 63.5 closer than Yugansky 60.5).
 *   T6. checkInsideZone(point in Yugansky) returns 'yugansky'.
 *   T7. checkInsideZone(point outside any zone) returns 'none'.
 */

/* eslint-disable no-undef */

var ref = require('users/SizovOleg/RuPlumeScan:modules/reference_baseline');

print('=== reference_baseline.js — smoke tests ===');

// ---------- T1 ----------
print('--- T1: loadReferenceZones — 3 active zones ---');
var zones_default = ref.loadReferenceZones({
  use_zones: ['yugansky', 'verkhnetazovsky', 'kuznetsky_alatau'],
  use_altaisky_if_quality_passed: false,
});
print('T1 expected size = 3, actual =', zones_default.size());
print('T1 zone_ids:', zones_default.aggregate_array('zone_id'));

// ---------- T2 ----------
print('--- T2: use_altaisky_if_quality_passed=true (Алтайский pending) ---');
var zones_with_alt_request = ref.loadReferenceZones({
  use_zones: ['yugansky', 'verkhnetazovsky', 'kuznetsky_alatau'],
  use_altaisky_if_quality_passed: true,
});
print('T2 expected size = 3 (Алтайский still pending), actual =', zones_with_alt_request.size());

// ---------- T3 ----------
print('--- T3: applyInternalBuffers shrinks Yugansky ---');
var yugansky_only = zones_default.filter(ee.Filter.eq('zone_id', 'yugansky'));
var yugansky_orig_area = yugansky_only.first().geometry().area().divide(1e6);
var yugansky_buffered = ref.applyInternalBuffers(yugansky_only);
var yugansky_buf_area = yugansky_buffered.first().geometry().area().divide(1e6);
print('T3 Yugansky orig area km²:', yugansky_orig_area);
print('T3 Yugansky buffered area km² (expect ~3000 после 10 km buffer):', yugansky_buf_area);

// ---------- T4 ----------
print('--- T4: buildZoneBaselines (CH4, July 2025) ---');
var buffered = ref.applyInternalBuffers(zones_default);
var zone_baselines = ref.buildZoneBaselines(buffered, 'CH4', 2025, 7, {
  analysis_scale_m: 7000,
});
var jul_results = zone_baselines.aggregate_array('baseline_ppb');
print('T4 Per-zone baseline_ppb для CH4 July (expect ~1900-1950 ppb):', jul_results);
print('T4 Per-zone count_avg:', zone_baselines.aggregate_array('count_avg'));

// ---------- T5 ----------
print('--- T5: stratified baseline assignment по latitude ---');
var aoi = ee.Geometry.Rectangle([60, 50, 95, 75]);
var stratified = ref.buildStratifiedBaseline(aoi, zone_baselines, 7000);
var test_pt_north = ee.Geometry.Point([75, 62]); // closer to Verkhne-Tazovsky (63.5°N)
var test_pt_south = ee.Geometry.Point([88, 54]); // closer to Kuznetsky Alatau (54.5°N)
var north_baseline = stratified.select('reference_baseline').reduceRegion({
  reducer: ee.Reducer.first(),
  geometry: test_pt_north,
  scale: 7000,
});
var south_baseline = stratified.select('reference_baseline').reduceRegion({
  reducer: ee.Reducer.first(),
  geometry: test_pt_south,
  scale: 7000,
});
print('T5 (62°N, 75°E) baseline (expect Verkhne-Tazovsky value):', north_baseline);
print('T5 (54°N, 88°E) baseline (expect Kuznetsky Alatau value):', south_baseline);

// ---------- T6/T7 ----------
print('--- T6/T7: checkInsideZone ---');
var pt_inside_yugansky = ee.Geometry.Point([74.5, 60.5]);
var pt_outside = ee.Geometry.Point([85.0, 67.0]); // в зону между заповедниками
print('T6 point inside Yugansky:', ref.checkInsideZone(pt_inside_yugansky));
print('T7 point outside any zone:', ref.checkInsideZone(pt_outside));

print('=== End ===');
