"""
SO₂ Python plume fit — реализуется в DevPrompt P-04.1.

GEE JavaScript не поддерживает nonlinear fit, поэтому SO₂ Fioletov 2020
методология (full nonlinear fit с 4 параметрами A, σ_y, L, B) выполняется
в Python через `scipy.optimize.curve_fit`.

Запланированные модули (RNA §11.3):
  * `plume_models.py` — `gaussian_exp_plume()`, simplified Fioletov.
  * `fit_engine.py` — wrappers вокруг scipy.optimize.
  * `gee_integration.py` — fetch sampled points → fit → upload back.
"""
