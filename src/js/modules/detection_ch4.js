/**
 * detection_ch4 — JS algorithm primitives для CH₄ plume detection (Phase 2A).
 *
 * Status: SCAFFOLD (Шаг 0). Implementation в Шаг 4.
 *
 * Module exports (6 primitives per Algorithm §3.5-3.10):
 *
 *   computeZScore(orbit_image, reference_baseline, regional_baseline)
 *     — z-score image per Algorithm §3.5; uses reference primary,
 *       regional fallback (DNA §2.1.4 — no unmask(0); fallback through
 *       regional baseline value, не constant 0)
 *
 *   applyThreeConditionMask(orbit_image, z_image, baseline_value, params)
 *     — Algorithm §3.6 conjunction:
 *       (z ≥ z_min) AND (Δ ≥ delta_min) AND (Δ - annulus_median ≥ relative_min)
 *     — annulus median via TWO-PASS (DNA §2.1.5 forbids ee.Kernel arithmetic)
 *
 *   extractClusters(mask_image, min_cluster_px)
 *     — Algorithm §3.7 connectedComponents 8-conn, min size filter
 *
 *   computeClusterAttributes(cluster_image, orbit_image, baseline_value, z_image)
 *     — Algorithm §3.8 per-cluster: centroid, area_km2, n_pixels,
 *       max_z, mean_z, max_delta, mean_delta, plume_axis_deg
 *
 *   validateWind(cluster_fc, era5_collection, params)
 *     — Algorithm §3.9 (v2.3.1 TD-0031): 850hPa primary, ±30° threshold,
 *       min wind speed 2 m/s, ±3h temporal window
 *
 *   attributeSource(cluster_fc, source_points, params)
 *     — Algorithm §3.10: 50 km radius search + type ranking
 *       (gas_field > viirs_flare_high > coal_mine > tpp_gres > ...)
 *
 * Loaded by Python orchestrator via ee.require() in build_ch4_event_catalog.py.
 */

'use strict';

// SCAFFOLD — populated в Шаг 4.

exports.computeZScore = function () {
    throw new Error('Шаг 4: implement computeZScore');
};

exports.applyThreeConditionMask = function () {
    throw new Error('Шаг 4: implement applyThreeConditionMask');
};

exports.extractClusters = function () {
    throw new Error('Шаг 4: implement extractClusters');
};

exports.computeClusterAttributes = function () {
    throw new Error('Шаг 4: implement computeClusterAttributes');
};

exports.validateWind = function () {
    throw new Error('Шаг 4: implement validateWind');
};

exports.attributeSource = function () {
    throw new Error('Шаг 4: implement attributeSource');
};
