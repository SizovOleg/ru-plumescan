# DevPrompts

Нумерованные задачи для исполняющего агента (Claude Code Desktop). См. [CLAUDE.md](../CLAUDE.md) — каждый DevPrompt пишется внешним архитектором, исполняется агентом, реализация проверяется sanity checks из [CLAUDE.md §5](../CLAUDE.md).

## Конвенция именования

`P-<phase>.<sequence>_<short_name>.md` — например, `P-00.0_repo_init.md`, `P-02.1_detection_ch4_ime.md`. Архивные версии переименовываются в `P-XX.Y_<name>_v<N>_archived.md`.

Phase numbering — см. [Roadmap.md §1](../Roadmap.md) (v1.1):

| Phase | DevPrompts | Содержание |
|---|---|---|
| 0 | P-00.x | Foundation: repo init, **industrial + protected areas reference (P-00.1, dual scope)**, schema tests, presets storage |
| 1 | P-01.0a / P-01.0b / P-01.2 | **Reference baseline (1a)** + Regional climatology (1b) + Dual baseline cross-check validation (1c) |
| 2 | P-02.x / P-03.x / P-04.x | Detection: CH4 / NO2 / SO2 |
| 3 | P-05.x | RCA ingesters (Schuit, IMEO MARS, CAMS) |
| 4 | P-06.x | Comparison Engine, cross-source agreement |
| 5 | P-07.x | UI App |
| 6 | P-08.x | Validation campaign (synthetic, regression, sensitivity, false positive, cross-source) |
| 7 | P-09.x | Tool-paper preparation (figures, release) |

## Текущие промты

- [P-00.0_repo_init.md](./P-00.0_repo_init.md) — repository + Common Plume Schema + foundation. **Completed** (commit `0cf69ab`, archive cleanup `58f0a56`).
- [P-00.1_industrial_and_reference_proxy.md](./P-00.1_industrial_and_reference_proxy.md) — industrial proxy + protected areas reference mask (dual scope per CHANGE-0017). **Active.**

## Архивные

- [P-00.1_industrial_proxy_v1_archived.md](./P-00.1_industrial_proxy_v1_archived.md) — оригинальная версия P-00.1 (только industrial scope), заменена на dual-scope версию по CHANGE-0017 (2026-04-26). Сохранена только для traceability — НЕ использовать для implementation.
