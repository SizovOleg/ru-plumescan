# Known TODOs / Deferred Quality Refinements

Список задач, отложенных до явного triggering condition. Каждая запись имеет:
- **Trigger** — условие, при котором задачу нужно вернуть в active backlog
- **Origin** — где обнаружено (DevPrompt / phase / commit)
- **Owner** — кто отвечает (researcher / Claude / community)
- **Effort estimate** — порядок необходимой работы

Формат вдохновлён OpenSpec.md, но это отдельный документ для **operational
deferrals**, не для architectural changes.

---

## TD-0001 — VIIRS proxy comprehensive analysis

- **Origin:** P-00.1 v2 ingestion (commit `<merge SHA>`, branch `p-00.1-industrial-and-reference`)
- **Owner:** Claude (исполняющий) при triggering
- **Status:** deferred — visual sanity passed, quantitative refinement pending
- **Trigger:** revisit if false positive rate в clean regions (далеко от known
  industrial sources) > 5% по итогам Phase 2A detection runs.
- **What's deferred:**
  1. Full radiance histogram per spatial bin (5°×5° или finer) для
     identification clusters concentration vs scatter.
  2. Distance-to-nearest-manual-point metric — VIIRS points в > 50 km от любого
     manual industrial source (потенциальные unverified flares).
  3. False positive analysis — overlay VIIRS points c MODIS land cover
     `Cropland` / `Grasslands` (LC=12, 10) для detection agricultural lights
     которые могли пройти urban filter.
  4. Threshold sensitivity sweep — re-run `build_viirs_proxy --threshold {30,
     50, 70, 100}` с calibration_status comparison; document optimal threshold
     per region (north Yamal vs south Khanty).
  5. Spatial clustering metrics (Ripley's K, DBSCAN) — distinguish flares
     (clustered around facilities) от noise (scattered).
- **Effort:** 1-2 days (Python pandas/scipy analysis + visualization).
- **Output:** addendum в `data/industrial_sources/README.md` + figure для
  tool-paper Discussion section.

---

## TD-0002 — Lauvaux 2022 ingester (если получим CSV)

См. OpenSpec.md `CHANGE-B003`. Активируется при response от Lauvaux/Kayrros.

---

## TD-0003 — Pixel-wise L (NOx/NO2 ratio) per Beirle 2021 ESSD

См. OpenSpec.md `CHANGE-B004`. Активируется после v1.0 release при наличии
validation evidence что constant L=1.32 занижает accuracy.

---

## TD-0004 — Алтайский full-resolution polygon download

- **Origin:** P-00.1 v2 sub-agent ingestion
- **Owner:** Claude при triggering
- **Status:** deferred — current Nominatim-simplified polygon (4.5% area diff)
  прошёл R2 tolerance.
- **Trigger:** если P-01.0a Алтайский QA test fail и одна из root causes —
  inadequate polygon coverage (e.g., акватория Телецкого озера mishandled).
- **What's deferred:** download full-resolution Алтайский polygon через
  `polygons.openstreetmap.fr` (без WebFetch token limit) или WDPA API directly
  (требует registration / accept terms). Re-clip с MODIS Land Cover чтобы
  excluded water bodies если QA указывает.
- **Effort:** 0.5 day.

---

## TD-0005 — WDPA cross-verification of zapovednik polygons

- **Origin:** R1 from researcher (P-00.1 v2 polygon source priority)
- **Owner:** Claude при triggering
- **Status:** deferred — OSM polygons accepted as primary, WDPA as future
  cross-check. Sub-agent attempted WDPA bulk download, requires accept-terms
  через web UI which is not feasible without browser session.
- **Trigger:**
  1. Researcher provides WDPA bulk download manually (one-time UI accept), OR
  2. WDPA-OSM intersection diff > 10% обнаружен during P-01.0a QA, OR
  3. External reviewer requires WDPA-canonical boundaries для publication.
- **What's deferred:** WDPA dataset ingest, IoU vs OSM polygons, document any
  divergence > 5% intersection area.
- **Effort:** 1 day (assuming WDPA accessible).

---

## TD-0006 — Юганский useable area dropdown (если P-01.0a покажет low count)

- **Origin:** P-00.1 v2 closure (researcher revised escalation gate 2026-04-27)
- **Owner:** Researcher (decision), Claude (implementation)
- **Status:** deferred — current useable area 2946 km² (~60 pixels) проходит
  revised threshold (zone-aggregate ≥ 1000 obs/month).
- **Trigger:** P-01.0a показывает zone-aggregate count < 1000 obs/month для
  Юганского. **Researcher decision required** before any reduction (per R5
  hard constraint: 10 km buffer защита от Самотлор/Salym advection критична).
- **What's deferred:** trade-off analysis reduce buffer 10→8 km vs accept low
  count vs use composite (Юганский + Верхне-Тазовский) baseline.
- **Effort:** 0.5 day analysis + escalation discussion.

---

## Process notes

- Перед закрытием fase / phase: scan этот файл, mark resolved entries как
  ARCHIVED (с датой и commit SHA где fix применён). Удалять не нужно —
  archived entries полезны как historical record.
- Если задача активирована — переместить в backlog (создать DevPrompt) и
  пометить status `ACTIVE` здесь.
- Этот документ обновляется при обнаружении новых deferrals; не требует
  formal CHANGE entry в OpenSpec (operational, не architectural).
