"""
P-02.0a unit tests для detection_ch4 JS primitives — Python-side wrappers.

Status: SCAFFOLD (Шаг 0). Tests в Шаг 4.

Each test invokes JS primitive via ee.require() с known synthetic input,
verifies expected output. Standalone unit testing of GEE-server-side
primitives requires either:
  (a) Synthetic test images constructed via ee.Image.constant() / .where()
  (b) Real TROPOMI sample orbits для integration-style tests

Approach: (a) for primitive correctness, (b) для integration test (Шаг 7).
"""

from __future__ import annotations


def test_compute_z_score_scaffold():
    """SCAFFOLD — populate в Шаг 4."""
    pass


def test_apply_three_condition_mask_scaffold():
    """SCAFFOLD — populate в Шаг 4. Verify all 3 conditions enforced."""
    pass


def test_annulus_two_pass_approach():
    """
    SCAFFOLD — verify annulus median computation uses two-pass approach
    (NOT ee.Kernel arithmetic per DNA §2.1.5). Шаг 4.
    """
    pass


def test_extract_clusters_scaffold():
    """SCAFFOLD — Шаг 4. Verify min_cluster_px filtering."""
    pass


def test_validate_wind_850hpa_default():
    """SCAFFOLD — verify wind level = 850hPa default (TD-0031). Шаг 4."""
    pass


def test_attribute_source_type_priority():
    """
    SCAFFOLD — verify type ranking gas_field > viirs_flare_high >
    coal_mine > tpp_gres. Шаг 4.
    """
    pass
