/**
 * @fileoverview CH₄ detection algorithm primitives для GEE Code Editor (Phase 2A).
 *
 * Canonical reference mirrors `src/py/rca/detection_ch4.py` (Python orchestrator
 * uses Python equivalents directly via ee Python API). This module exists для
 * GEE Code Editor users who need server-side primitives via ee.require().
 *
 * Six primitives per Algorithm v2.3.2:
 *   1. computeZScore             — §3.5 dual baseline z-score
 *   2. applyThreeConditionMask   — §3.6 z + Δ + relative-to-annulus
 *   3. extractClusters           — §3.7 connectedComponents
 *   4. computeClusterAttributes  — §3.8 per-cluster metrics (axis client-side)
 *   5. validateWind              — §3.9 (v2.3.1) ERA5 850hPa
 *   6. attributeSource           — §3.10 50 km + type ranking
 *
 * DNA §2.1 critical:
 *   * Запрет 4: no `unmask(0)` для XCH4 — regional fallback values used
 *   * Запрет 5: no ee.Kernel arithmetic — annulus = outer-disk-only (TWO-PASS)
 *   * Запрет 6: per-region adaptive z_min applied at orchestrator level
 *
 * @module detection_ch4
 */

/* eslint-disable no-undef */

'use strict';

// ---------------------------------------------------------------------------
// Constants (Algorithm v2.3.2)
// ---------------------------------------------------------------------------

exports.ANALYSIS_SCALE_M = 7000;
exports.SIGMA_FLOOR_PPB = 15.0;
exports.ANNULUS_OUTER_KM_DEFAULT = 150;
exports.SOURCE_TYPE_PRIORITIES_CH4 = {
    gas_field: 1,
    viirs_flare_high: 2,
    coal_mine: 3,
    tpp_gres: 4,
    viirs_flare_low: 5,
    smelter: 6,
};

// ---------------------------------------------------------------------------
// Primitive 1: z-score с dual baseline fallback (Algorithm §3.5)
// ---------------------------------------------------------------------------

/**
 * Compute z-score image. Primary baseline = reference where defined, regional
 * fallback (DNA §2.1.4 — no unmask(0)).
 *
 * Returns ee.Image с bands ['z', 'delta_primary', 'primary_value'].
 */
exports.computeZScore = function (orbit_image, reference_baseline, regional_baseline, month, params) {
    var p = params || {};
    var target_band = p.target_band || 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected';
    var sigma_floor = p.sigma_floor_ppb || exports.SIGMA_FLOOR_PPB;
    var suffix = 'M' + (month < 10 ? '0' : '') + month;

    var ref_value = reference_baseline.select('ref_' + suffix);
    var ref_sigma = reference_baseline.select('sigma_' + suffix);
    var reg_value = regional_baseline.select('median_' + suffix);
    var reg_sigma = regional_baseline.select('sigma_' + suffix);

    var primary_value = ref_value.unmask(reg_value).rename('primary_value');
    var primary_sigma = ref_sigma.unmask(reg_sigma);
    var sigma_eff = primary_sigma.max(ee.Image.constant(sigma_floor));

    var obs = orbit_image.select(target_band);
    var delta_primary = obs.subtract(primary_value).rename('delta_primary');
    var z = delta_primary.divide(sigma_eff).rename('z');

    return ee.Image.cat([z, delta_primary, primary_value]);
};

// ---------------------------------------------------------------------------
// Primitive 2: 3-condition mask (Algorithm §3.6)
//
// Implementation note (DNA §2.1.5 — no ee.Kernel arithmetic):
// TWO-PASS approach for annulus median. Use outer disk (150 km) only;
// inner disk (50 km) included contributes ~12.5% area weight. Bias на
// median estimate ≤ ~12% (conservative — under-detection).
// ---------------------------------------------------------------------------

exports.applyThreeConditionMask = function (z_image, delta_primary, params) {
    var p = params || {};
    var z_min = p.z_min !== undefined ? p.z_min : 3.0;
    var delta_min_ppb = p.delta_min_ppb !== undefined ? p.delta_min_ppb : 30.0;
    var relative_min_ppb = p.relative_min_ppb !== undefined ? p.relative_min_ppb : 15.0;
    var annulus_outer_km = p.annulus_outer_km || exports.ANNULUS_OUTER_KM_DEFAULT;

    var z_test = z_image.gte(z_min);
    var delta_test = delta_primary.gte(delta_min_ppb);

    var outer_kernel = ee.Kernel.circle({
        radius: annulus_outer_km * 1000,
        units: 'meters',
    });
    var annulus_median = delta_primary.reduceNeighborhood({
        reducer: ee.Reducer.median(),
        kernel: outer_kernel,
        skipMasked: true,
    });
    var rel_test = delta_primary.subtract(annulus_median).gte(relative_min_ppb);

    return z_test.And(delta_test).And(rel_test).rename('anomaly_mask').selfMask();
};

// ---------------------------------------------------------------------------
// Primitive 3: connectedComponents (Algorithm §3.7)
// ---------------------------------------------------------------------------

exports.extractClusters = function (mask_image, params) {
    var p = params || {};
    var min_cluster_px = p.min_cluster_px || 5;
    var max_size = p.max_size || 256;
    var connectedness = p.connectedness || 8;

    var kernel = connectedness === 8 ? ee.Kernel.square(1) : ee.Kernel.plus(1);
    var labeled = mask_image.connectedComponents({ connectedness: kernel, maxSize: max_size });

    var pixel_counts = mask_image.connectedPixelCount({
        maxSize: max_size,
        eightConnected: connectedness === 8,
    });
    var significant = pixel_counts.gte(min_cluster_px);

    return labeled.updateMask(significant);
};

// ---------------------------------------------------------------------------
// Primitive 4: cluster attributes (Algorithm §3.8)
// plume_axis_deg requires client-side eigendecomposition — set по orchestrator
// post-reduceRegions(pixel_coords) via numpy.linalg.eig.
// ---------------------------------------------------------------------------

exports.computeClusterAttributes = function (
    cluster_image,
    orbit_image,
    baseline_value,
    z_image,
    aoi,
    params,
) {
    var p = params || {};
    var target_band = p.target_band || 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected';
    var scale_m = p.scale_m || exports.ANALYSIS_SCALE_M;

    var vectors = cluster_image.reduceToVectors({
        geometry: aoi,
        scale: scale_m,
        geometryType: 'polygon',
        eightConnected: true,
        bestEffort: false,
        maxPixels: 1e9,
        labelProperty: 'cluster_id',
    });

    var delta = orbit_image.select(target_band).subtract(baseline_value);

    var with_z = z_image.reduceRegions({
        collection: vectors,
        reducer: ee.Reducer.max().combine(ee.Reducer.mean(), '', true).combine(ee.Reducer.count(), '', true),
        scale: scale_m,
    });

    with_z = with_z.map(function (feat) {
        return feat.set({ max_z: feat.get('max'), mean_z: feat.get('mean'), n_pixels: feat.get('count') });
    });

    var with_delta = delta.reduceRegions({
        collection: with_z,
        reducer: ee.Reducer.max().combine(ee.Reducer.mean(), '', true),
        scale: scale_m,
    });

    return with_delta.map(function (feat) {
        var centroid = feat.geometry().centroid({ maxError: 1 });
        var coords = ee.List(centroid.coordinates());
        return feat.set({
            centroid_lon: coords.get(0),
            centroid_lat: coords.get(1),
            area_km2: feat.geometry().area({ maxError: 1 }).divide(1e6),
            max_delta: feat.get('max'),
            mean_delta: feat.get('mean'),
        });
    });
};

// ---------------------------------------------------------------------------
// Primitive 5: wind validation (Algorithm §3.9 v2.3.1, TD-0031)
// 850hPa primary, ±30°, vector averaging
// ---------------------------------------------------------------------------

exports.validateWind = function (cluster_fc, era5_collection, orbit_time_millis, params) {
    var p = params || {};
    var wind_level_hpa = p.wind_level_hpa || 850;
    var alignment_threshold_deg = p.alignment_threshold_deg !== undefined ? p.alignment_threshold_deg : 30.0;
    var min_wind_speed_ms = p.min_wind_speed_ms !== undefined ? p.min_wind_speed_ms : 2.0;
    var window_hours = p.temporal_window_hours || 3;

    var band_u = 'u_component_of_wind_' + wind_level_hpa + 'hPa';
    var band_v = 'v_component_of_wind_' + wind_level_hpa + 'hPa';

    var orbit_date = ee.Date(orbit_time_millis);
    var window = era5_collection
        .filterDate(orbit_date.advance(-window_hours, 'hour'), orbit_date.advance(window_hours, 'hour'))
        .select([band_u, band_v]);
    var mean_wind = window.mean();

    return cluster_fc.map(function (feat) {
        var centroid = feat.geometry().centroid({ maxError: 1 });
        var sample = mean_wind.reduceRegion({
            reducer: ee.Reducer.first(),
            geometry: centroid,
            scale: 9000,
        });
        var u = ee.Number(sample.get(band_u));
        var v = ee.Number(sample.get(band_v));
        var wind_speed = u.hypot(v);
        // Atmospheric convention — direction wind is FROM (0=N, 90=E)
        var wind_dir = u.atan2(v).multiply(180.0).divide(Math.PI).add(180).mod(360);

        var plume_axis = ee.Number(feat.get('plume_axis_deg'));
        var raw_diff = wind_dir.subtract(plume_axis).abs();
        var angle_diff = raw_diff.min(ee.Number(180).subtract(raw_diff));

        var sufficient = wind_speed.gte(min_wind_speed_ms);
        var wind_consistent = ee.Algorithms.If(
            sufficient,
            angle_diff.lte(alignment_threshold_deg),
            null,
        );
        var alignment_score = ee.Number(1).subtract(angle_diff.divide(90).min(1));

        var props = {
            wind_u: u,
            wind_v: v,
            wind_speed: wind_speed,
            wind_dir_deg: wind_dir,
            wind_alignment_score: alignment_score,
            wind_consistent: wind_consistent,
            wind_level_hPa: wind_level_hpa,
            wind_source: 'ERA5_HOURLY_' + wind_level_hpa + 'hPa',
        };
        props['wind_u_' + wind_level_hpa + 'hPa'] = u;
        props['wind_v_' + wind_level_hpa + 'hPa'] = v;
        return feat.set(props);
    });
};

// ---------------------------------------------------------------------------
// Primitive 6: source attribution (Algorithm §3.10)
// 50 km radius + type ranking + distance tiebreak
// ---------------------------------------------------------------------------

exports.attributeSource = function (cluster_fc, source_points, params) {
    var p = params || {};
    var search_radius_km = p.search_radius_km || 50;
    var priorities = ee.Dictionary(p.type_priorities || exports.SOURCE_TYPE_PRIORITIES_CH4);
    var default_priority = 999;

    return cluster_fc.map(function (cluster) {
        var centroid = cluster.geometry().centroid({ maxError: 1 });
        var nearby = source_points.filterBounds(centroid.buffer(search_radius_km * 1000));

        var ranked = nearby.map(function (source) {
            var distance = centroid.distance(source.geometry()).divide(1000);
            var stype = source.get('source_type_category');
            var priority = ee.Number(priorities.get(stype, default_priority));
            return source.set({ distance_km: distance, priority: priority });
        }).sort('distance_km').sort('priority');

        var size = ranked.size();
        return ee.Feature(
            ee.Algorithms.If(
                size.gt(0),
                cluster.set({
                    nearest_source_id: ee.Feature(ranked.first()).get('source_id'),
                    nearest_source_distance_km: ee.Feature(ranked.first()).get('distance_km'),
                    nearest_source_type: ee.Feature(ranked.first()).get('source_type_category'),
                }),
                cluster.set({
                    nearest_source_id: null,
                    nearest_source_distance_km: null,
                    nearest_source_type: null,
                }),
            ),
        );
    });
};
