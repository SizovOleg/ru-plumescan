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

## TD-0008 — Refactor build_zone_baseline_single_month memory footprint (Q-mid months) **[PRIORITY HIGH]**

- **Origin:** P-01.0a Phase A diagnostics (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Claude (исполняющий) при triggering
- **Status:** **PRIORITY HIGH (escalated from `deferred`)** — после P-01.0a confirmed
  pattern не fix-able by simple sleep, и Phase 2A pipeline зависит от valid
  baselines для biologically active transition months (M05 Май, M08 Август,
  M11 Ноябрь — wetland onset, peak emission, freeze-up).
- **Trigger:** **BLOCKS Phase 2A** (CH4 detection) — must mitigate перед production
  detection runs. Любой из:
  - Refactor compute (preferred, 1 day work)
  - Temporal interpolation as Phase 2A Option A
  - Skip Q-mid detection runs as Phase 2A Option B
- **Root cause:** `filtered.reduce(median)` followed by `reduceRegion(mean)`
  on stack of ~540 daily images (6 years × 3 months × ~30 daily L3 mosaics)
  exceeds GEE user-side memory limit для interactive `getInfo()` calls.
  Working months (M01, M03, M04, M06, M07, M09, M10, M12) имеют edge effects
  (months 0, 13 partial filter → smaller stack).
- **Fix sketch:** refactor `compute_seasonal_mean` / `build_zone_baseline_single_month`
  на per-month-per-year compute (chunked) с aggregation в Python instead of
  single big server-side reduce. Reduces peak memory ~30×.
  ```python
  monthly_means = []
  for year in range(YEAR_MIN, YEAR_MAX):
      for m_offset in (-1, 0, 1):
          target_m = target_month + m_offset
          monthly_mean = (
              filter_year_month(year, target_m)
              .median()
              .reduceRegion(...).getInfo()
          )
          monthly_means.append(monthly_mean)
  zone_aggregate = python_median(monthly_means)
  ```
- **Effort:** 1 day refactor + re-test all 12 months.

---

## TD-0009 — Cross-biome shared October peak — regional synoptic signal (potential publication)

- **Origin:** P-01.0a validation (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Researcher (decision), Claude (analysis при triggering)
- **Status:** **deferred — not blocker** для current detection pipeline.
  Reference baseline functional с this peak (it's measured signal, не bug).
- **Observation:** All 3 reference zones share October peak — Yugansky 1892,
  Verkhne-Tazovsky 1894, Kuznetsky Alatau 1872. Three biomes (wetland /
  permafrost / mountain), three latitudes (60.5° / 63.5° / 54.5°N) — все
  показывают **synchronous** October peak. Suggests common atmospheric-
  column-level driver, не biotic emission cycle.
- **Trigger:** **HIGH-VALUE investigation** if researcher has cycles для:
  1. Confirm signal not artefact (e.g., MODIS snow filter edge case при
     NDSI 20-40 partial coverage в October)
  2. Cross-validate against in-situ tall-tower measurements (Karasevsky,
     Demyansky, ZOTTO towers)
  3. ERA5 boundary layer height time-series correlation
- **Hypotheses to test:**
  1. Autumn PBL collapse + surface accumulation (lowland-only — but Kuz-Alatau
     mountain forest also peaks → counter-evidence)
  2. MODIS snow filter edge case (NDSI 20-40 partial coverage bias)
  3. Soil-atmosphere shoulder season exchange (literature: Walter Anthony 2010,
     Sasakawa 2012 для Yamal lakes ebullition)
  4. Continental transport pattern shift (autumn jet stream rearrangement)
- **Potential publication:** «First systematic empirical observation of
  cross-biome synchronous October XCH₄ peak in Western Siberia from TROPOMI
  L3 reference baseline» — could be standalone short paper или figure
  для tool-paper Phase 7 Discussion section.
- **Effort:** 5-7 days analysis + literature comparison + figure preparation
  (если pursued seriously).

---

## TD-0010 — Kuznetsky Alatau retrieval count limitation

- **Origin:** P-01.0a validation (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Claude / Researcher
- **Status:** documented caveat, не actionable refactor.
- **Observation:** Kuznetsky Alatau monthly counts 60-140 (vs Yugansky
  ~5000-8000, Verkhne-Tazovsky ~10000-20000). Two orders of magnitude
  fewer valid TROPOMI observations. Cause: mountain cloud cover + SWIR
  retrieval challenges over snow / aspect-variable surfaces.
- **Implications для Phase 2A:**
  - Zone-aggregate baseline still computable (~80-140 valid pixels/month
    adequate для zone-mean median).
  - Sigma estimates noisier for low-N months (e.g., M01 sigma=2.78 ppb
    с count=18 likely artefact).
  - Reduced sensitivity для CH4 detection в latitude band 53-57°N
    (where Kuznetsky Alatau is primary reference per Algorithm §11.3
    Step 4 latitude stratification).
- **Trigger:** if Phase 2A detection в Кузбасс / Мариинск /
  Новокузнецк latitude band shows higher false-negative rate vs
  northern bands, revisit baseline coverage.
- **Mitigations:**
  1. Accept reduced sensitivity, document in tool-paper limitations.
  2. Consider alternative reference zones для southern band (Saian
     Mountains? Tomsk forest reserves? — would require DNA mutation
     per §2.3 для added zones).
  3. Composite baseline (Yugansky weighted partially для южной AOI)
     — alters latitude stratification methodology.
- **Effort:** 0.5 day documentation, или 3-5 days если adding new
  reference zone.

---

## TD-0007 — Yugansky October peak vs article September peak (1-month timing offset)

- **Origin:** P-01.0a Yugansky validation (commit `<merge SHA>`, 2026-04-28)
- **Owner:** Claude (исполняющий) при triggering
- **Status:** deferred — discrepancy между Yugansky measured peak month (October)
  и Sizov et al. in prep article zone-mean peak month (September). Both
  observations valid against revised Algorithm §3.4.0 expectations
  (peak month range August-October).
- **Trigger:** revisit if Phase 2A detection sensitivity shows artifacts
  associated with the October-vs-September timing (e.g., reference baseline
  systematically overestimates October XCH₄ → masks real Plume Events
  в October).
- **Hypotheses:**
  1. Internal buffer 10 km cuts off edge wetlands (which peak earlier in
     August-September) — concentrated bog interior peaks 1-2 weeks later
     due to thermal lag of permafrost-underlain peat.
  2. Year-to-year variability в 6-year (ours 2019-2024) vs 7-year
     (article 2019-2025) averaging windows — 2025 may have peaked earlier.
  3. Real spatial heterogeneity within zone — Yugansky zone is larger
     and more northerly than article zone-mean, possibly later snow-melt
     and freeze-up timing.
- **What's deferred:**
  1. Per-pixel monthly histogram inside Yugansky useable area (identify
     spatial gradient of peak timing).
  2. Year-by-year decomposition (separate 2019/2020/2021/2022/2023/2024
     monthly cycles — has any single year dragged the average).
  3. Consult article authors про zone-4 specific composition.
- **Effort:** 1 day analysis.

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
