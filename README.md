# RU-PlumeScan

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GEE](https://img.shields.io/badge/Earth_Engine-Required-green.svg)](https://earthengine.google.com/)
[![Status](https://img.shields.io/badge/status-v0.5--dev-orange.svg)](#status)

**Configurable Detection Surface for TROPOMI/Sentinel-5P methane, NO₂, and SO₂ anomalies over Western Siberia.**

## Overview

RU-PlumeScan is a regional, configurable workbench for detecting gas anomalies over Western Siberia using TROPOMI/Sentinel-5P satellite data in Google Earth Engine. Built around peer-reviewed methodologies (Schuit et al. 2023, Beirle et al. 2019, Fioletov et al. 2020), it provides:

- **Per-gas detection** for CH₄ (threshold-based, regional climatology), NO₂ (flux divergence), SO₂ (wind-rotated plume fitting)
- **Configurable parameters** with named Presets (`default`, `schuit_eq`, `imeo_eq`, `sensitive`, `conservative`, `custom_<sha8>`)
- **Reference Catalog Adapter (RCA)** for cross-source comparison with Schuit 2023, UNEP IMEO MARS, CAMS Methane Hotspot Explorer
- **Multi-gas evidence aggregation** — novel event-level matching for industrial source attribution
- **Full provenance** — every Plume Event includes a config snapshot (`params_hash`, `algorithm_version`, `run_id`)
- **Forward-compatibility** to ML-augmented detection (v2)

Detection methodology is *not* compositing-based: per-orbit / multi-month aggregation matches the gas physics (transient CH₄ plumes, multi-month NO₂ averaging, per-source SO₂ rotation).

## Status

🚧 **Under development** — v0.5 implementation phase. Architectural documentation finalized 2026-04-25. Target v1.0 release: end of 2026.

See [Roadmap.md](./Roadmap.md) for development phases and [OpenSpec.md](./OpenSpec.md) for the change log.

## Quick start

> Implementation-side quick start будет добавлен по мере прохождения Phase 0 → Phase 5.

For now:
- Read [DNA.md](./DNA.md) → [Algorithm.md](./Algorithm.md) → [RNA.md](./RNA.md) for the full design.
- Python helpers (RCA, validation, SO₂ fit) live under [`src/py/`](./src/py/). Install dev deps:
  ```bash
  pip install -r src/py/requirements-dev.txt
  ```
- GEE JavaScript modules live under [`src/js/`](./src/js/). They are intended to be `require()`-d from a published GEE App.

## Documentation

| Document | Purpose |
|---|---|
| [DNA.md](./DNA.md) | Project invariants — onto­logy, prohibitions, priorities. Mutates only with explicit approval. |
| [CLAUDE.md](./CLAUDE.md) | Agent contract for Claude Code Desktop (implementation agent). |
| [Algorithm.md](./Algorithm.md) | Methodology — per-gas detection, Common Plume Schema, IME, multi-gas matching. |
| [RNA.md](./RNA.md) | Implementation stack — GEE JS + Python, Asset structure, naming conventions, defaults. |
| [Roadmap.md](./Roadmap.md) | Phased development plan, milestones, validation criteria. |
| [OpenSpec.md](./OpenSpec.md) | Change log — proposed / applied / blocked changes with rationale. |
| [DevPrompts/](./DevPrompts/) | Numbered implementation tasks for Claude Code Desktop. |

## Project layout

```
ru-plumescan/
├── DNA.md  CLAUDE.md  Algorithm.md  RNA.md  Roadmap.md  OpenSpec.md
├── DevPrompts/                  # Numbered tasks (P-00.0, P-00.1, …)
├── src/
│   ├── js/                      # GEE JavaScript: detection, comparison, UI
│   └── py/                      # Python: RCA ingesters, SO₂ fit, synthetic, analysis
├── docs/                        # User-facing guides
├── data/industrial_sources/     # GeoJSON inputs for industrial proxy mask
└── .github/workflows/           # CI (lint, test)
```

## Citation

Placeholder — will be updated at v1.0 release with Zenodo DOI. See [`CITATION.cff`](./CITATION.cff).

## License

- **Code:** MIT (see [`LICENSE`](./LICENSE))
- **Catalog products** (when published as Zenodo Assets): CC-BY 4.0
- **UNEP IMEO MARS** ingested data is redistributed under CC-BY-NC-SA 4.0 — non-commercial use, attribution required.

## Acknowledgments

Built on peer-reviewed methodologies:
- Schuit et al. 2023, *ACP*, [doi:10.5194/acp-23-9071-2023](https://doi.org/10.5194/acp-23-9071-2023)
- Varon et al. 2018, *AMT*, [doi:10.5194/amt-11-5673-2018](https://doi.org/10.5194/amt-11-5673-2018)
- Beirle et al. 2019, *Sci. Adv.*, [doi:10.1126/sciadv.aax9800](https://doi.org/10.1126/sciadv.aax9800)
- Beirle et al. 2021, *ESSD*, [doi:10.5194/essd-13-2995-2021](https://doi.org/10.5194/essd-13-2995-2021)
- Fioletov et al. 2020, *ACP*, [doi:10.5194/acp-20-5591-2020](https://doi.org/10.5194/acp-20-5591-2020)
- Lorente et al. 2021, *AMT*, [doi:10.5194/amt-14-665-2021](https://doi.org/10.5194/amt-14-665-2021)

Reference catalogs:
- UNEP International Methane Emissions Observatory (IMEO MARS) / Eye on Methane
- Copernicus Atmosphere Monitoring Service (CAMS) Methane Hotspot Explorer
- Schuit et al. 2023 plume catalog ([Zenodo 8087134](https://zenodo.org/records/8087134))

## Contact

- **Author:** Сизов Олег / Oleg Sizov, ИПНГ РАН (Oil and Gas Research Institute RAS)
- **Issues:** https://github.com/SizovOleg/ru-plumescan/issues
