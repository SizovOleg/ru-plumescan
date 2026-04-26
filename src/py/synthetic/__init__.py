"""
Synthetic plume injection — реализуется в DevPrompt P-08.0.

Генерация синтетических CH₄ плюмов на чистых регионах для recovery test
(CLAUDE.md §5.2): pass criterion — recovered/injected ≥ 0.7 для
amplitude ≥ 30 ppb.

Запланированные модули:
  * `plume_injection.py` — генератор синтетических плюмов.
  * `recovery_test.py` — pipeline: inject → run detection → measure recovery.
"""
