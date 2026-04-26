# DevPrompts

Нумерованные задачи для исполняющего агента (Claude Code Desktop). См. [CLAUDE.md](../CLAUDE.md) — каждый DevPrompt пишется внешним архитектором, исполняется агентом, реализация проверяется sanity checks из [CLAUDE.md §5](../CLAUDE.md).

## Конвенция именования

`P-<phase>.<sequence>_<short_name>.md` — например, `P-00.0_repo_init.md`, `P-02.1_detection_ch4_ime.md`.

Phase numbering — см. [Roadmap.md §1](../Roadmap.md):

| Phase | DevPrompts | Содержание |
|---|---|---|
| 0 | P-00.x | Foundation: repo init, industrial proxy, schema validation, presets storage |
| 1 | P-01.x | Backgrounds: climatologies CH4/NO2/SO2, annulus kernels |
| 2 | P-02.x / P-03.x / P-04.x | Detection: CH4 / NO2 / SO2 |
| 3 | P-05.x | RCA ingesters (Schuit, IMEO MARS, CAMS) |
| 4 | P-06.x | Comparison Engine, cross-source agreement |
| 5 | P-07.x | UI App |
| 6 | P-08.x | Validation campaign (synthetic, regression, sensitivity, false positive, cross-source) |
| 7 | P-09.x | Tool-paper preparation (figures, release) |

## Текущие промты

- [P-00.0_repo_init.md](./P-00.0_repo_init.md) — repository + Common Plume Schema + foundation. **Active.**
