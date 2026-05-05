"""
P-02.0a: CH₄ event catalog orchestrator (Phase 2A).

Status: SCAFFOLD (Шаг 0). Implementation в Шаг 5.

Per RFC v2 frozen architecture + DevPrompt P-02.0a §5.

Workflow (when implemented):
  1. Per-orbit detection с 3-condition mask (Algorithm §3.6)
  2. connectedComponents clustering (Algorithm §3.7)
  3. Wind validation 850hPa (Algorithm §3.9, TD-0031)
  4. Source attribution 50 km (Algorithm §3.10)
  5. TD-0017 transboundary check (selective)
  6. TD-0021 zone-boundary adjustment
  7. Manual override (Algorithm §6, event_overrides.json)
  8. Per-year sharded export (7 annual + master index)
  9. Cross-year repeatability analysis

Per-region adaptive z_min: Kuzbass (lat∈[53,55], lon∈[86,88]) → z_min=4.0,
default → 3.0 (TD-0018 Phase 1c handoff).

Canonical Provenance pattern (TD-0024/0025): compute once at process start,
flow через all touchpoints без recompute.

Run: python src/py/setup/build_ch4_event_catalog.py [--year-start 2019] [--year-end 2025] [--launch-only]
"""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Orchestrator entry. SCAFFOLD — implementation в Шаг 5."""
    raise NotImplementedError("Шаг 5 implementation pending after Шаги 1-4 docs/schema/JS")


if __name__ == "__main__":
    sys.exit(main())
