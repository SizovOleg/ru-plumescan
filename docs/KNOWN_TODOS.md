# Known TODOs / Deferred Quality Refinements

Список задач, отложенных до явного triggering condition. Каждая запись имеет:
- **Trigger** — условие, при котором задачу нужно вернуть в active backlog
- **Origin** — где обнаружено (DevPrompt / phase / commit)
- **Owner** — кто отвечает (researcher / Claude / community)
- **Effort estimate** — порядок необходимой работы

Формат вдохновлён OpenSpec.md, но это отдельный документ для **operational
deferrals**, не для architectural changes.

---

## TD-0032 NEW — Consistency-driven primary switch (Algorithm §3.5) **[LOW priority — Phase 2A v1.1 backlog]**

- **Origin:** P-02.0a Шаг 4 GPT review #2 (2026-05-05) — accepted simplification.
- **Status:** documented gap — explicitly tracked для honest scope.
- **Issue:** `build_hybrid_background()` currently implements `mode='reference_only'`
  per Algorithm §3.5 — primary baseline always uses reference where defined,
  regardless of `consistency_flag` value. The full consistency-driven primary
  switch (Algorithm §3.5 lines 818-826):
  ```javascript
  const use_reference_primary = config.background.mode === 'reference_only' ||
                                  consistency.eq(1).and(config.background.primary === 'reference');
  ```
  is deferred. `consistency_flag` is metadata only в v1; the metadata is
  available к downstream classification cascade (Шаг 6 wetland heuristic), но
  primary selection itself does not consult it.
- **Implications:** When consistency_flag=false (baselines diverge by >30 ppb),
  pixel uses reference value anyway. Researcher decision Шаг 4 GPT review:
  reference is methodology anchor (clean-zone baseline), regional fallback only
  for masked pixels. This is more conservative than `mode='hybrid'` would be.
- **Trigger для активации:** if Phase 2A validation reveals systematic divergence
  between baselines в areas where regional is more accurate (e.g., wide gas
  fields where reference baseline biased), revisit к add full mode='hybrid'
  path.
- **Effort:** ~30 LoC orchestrator-side mode parameter + Algorithm.md §3.5 update
  + 4-6 new tests (consistent → ref, divergent + mode=hybrid → reg, divergent
  + mode=reference_only → ref). ~3-4 hours.
- **Dependency:** Phase 2A v1.0 closure + sensitivity test results.
- **Reference:** Algorithm.md §3.5 lines 901-906 inline note.

---

## TD-0035 NEW — apply_event_overrides graph depth scaling **[LOW priority — track first catalog launch]**

- **Origin:** P-02.0a Шаг 5+6+7 GPT review #3 finding 2026-05-05.
- **Status:** acceptable Phase 2A v1; track if catalog grows beyond manual review threshold.
- **Issue:** `rca/detection_helpers.py::apply_event_overrides` iterates client-side
  over override entries and applies `events_fc.map(...)` per entry. For typical
  Phase 2A v1 scope (<20 manual overrides total), graph depth stays well within
  EE serialization limits (~256 nodes per task). At >50 overrides, graph
  serialization risk increases.
- **Detection:** monitor catalog growth. Trigger refactor если:
  - Override count >50 в `config/event_overrides.json`
  - "User memory limit exceeded" or "FeatureCollection.map: Computation timed
    out" errors appear на launch
- **Fix path (если triggered):** refactor к single `.map()` call с composite
  filter built from override list:
  ```python
  composite_filter = ee.Filter.Or(*[
      ee.Filter.And(
          ee.Filter.lt("centroid_lat_diff", tol_lat),
          ee.Filter.lt("centroid_lon_diff", tol_lon),
          ee.Filter.dateRangeContains("orbit_date_millis", date_min, date_max),
      ) for entry in overrides
  ])
  ```
  And for each-feature: derive matched override server-side via .filter() chain.
- **Effort:** 2-3 hours (refactor + tests + verification на real catalog).
- **Trigger:** override count >50 OR launch failure.

---

## TD-0034 — Reference baseline P-01.0a v1 has 7 of 12 months only **[RESOLVED 2026-05-05 — physical TROPOMI coverage, not methodology gap]**

**Resolution (2026-05-05 post Шаг 5 verification):** Researcher determined this is the
**correct physical coverage** of TROPOMI CH₄ retrievals over Western Siberia, not a
methodology gap. Winter months (M02/M05/M08/M11/M12) lack usable retrievals due к
sensor physical limitations:
- Low sun zenith angle (high latitudes, winter season)
- Snow albedo (saturates SWIR retrieval)
- Cloud cover persistence

The 7-month coverage (M01, M03, M04, M06, M07, M09, M10) corresponds к все months с
usable TROPOMI CH4 retrievals over Western Siberia AOI. Tool-paper scope is honest:
"Detection covers all months с usable TROPOMI retrievals". Algorithm.md / RNA.md
updated с physical-coverage note.

No reference rebuild needed. `REFERENCE_AVAILABLE_MONTHS = [1,3,4,6,7,9,10]` is
canonical, not provisional. CLOSED.

### Original TD-0034 issue (preserved для historical record):

- **Origin:** P-02.0a Шаг 5 pre-launch asset verification 2026-05-05.
- **Status:** documented limitation — Phase 2A v1 detection restricted к 7 months.
- **Issue:** `RuPlumeScan/baselines/reference_CH4_2019_2025_v1` (P-01.0a) only
  contains bands `ref_M{NN}, sigma_M{NN}, lat_dist_M{NN}` для months
  M01, M03, M04, M06, M07, M09, M10. Months M02, M05, M08, M11, M12 absent —
  Q-mid pattern (TD-0008 user memory limit) + winter retrievals (snow/cloud).
- **Impact:** Phase 2A CH4 detection cannot run for missing months because:
  - `compute_z_score` selects `ref_M{NN}` band per orbit; missing band → error
  - Build_hybrid_background requires ref bands per month
  - Affected: ~5 of 12 months (~42%) of detection coverage lost
  - Most significantly missing: **M08 (August)** — peak summer methane emissions
    season; **M11/M12** — late autumn anomalies before snow cover stable
- **Phase 2A v1 mitigation:** orchestrator iterates ONLY available months
  (REFERENCE_AVAILABLE_MONTHS = [1,3,4,6,7,9,10] в `detection_helpers.py`).
  Detection в other months simply not produced; no false-negative claims made.
  Annual catalog has explicit `available_months` property documenting the gap.
- **Resolution path:**
  1. Investigate Q-mid pattern в P-01.0a build (TD-0008 sister issue — may need
     12 separate batch tasks per Option C pattern)
  2. Build extension asset `reference_CH4_2019_2025_v2` с все 12 months
  3. Migrate orchestrator к v2 reference, drop available_months parameter
- **Trigger:** when Phase 2A v1 catalog complete + summer/winter coverage gaps
  documented в validation report. OR if reviewer flags missing-months gap.
- **Effort:** 2-3 days (P-01.0a-style monthly batch rebuild + asset migration).
- **Related:** TD-0008 (Q-mid memory limit, regional fix), TD-0010 (Kuznetsky
  Alatau low retrieval count — may compound Q-mid issue для southern band).

---

## TD-0033 NEW — Шаг 7 Kuzbass regression integration test should exercise wind_state='insufficient_wind' branch **[LOW priority]**

- **Origin:** P-02.0a Шаг 4 GPT review #2 (2026-05-05) — non-blocking observation.
- **Status:** TBD when Шаг 7 implemented.
- **Issue:** Current `test_detection_ch4_integration.py` covers `wind_state='axis_unknown'`
  branch (cluster без `plume_axis_deg`). Other 3 wind_state branches (`aligned`,
  `misaligned`, `insufficient_wind`) NOT exercised by integration suite — only
  by unit-level math tests against the reference formula.
- **Trigger:** Phase 2A Шаг 7 implementation (Kuzbass 2022-09-20 regression test).
- **What's deferred:** Add synthetic low-wind case (e.g., u=0.5, v=0.5 m/s,
  wind_speed = 0.71 m/s < 2.0 threshold) to integration suite. Verify
  `wind_state='insufficient_wind'` and `wind_consistent=null`. Likely 1-2
  additional integration tests + 1 setup helper.
- **Effort:** ~30 minutes during Шаг 7 implementation.
- **Reference:** GPT review #2 final recommendation (non-blocking).

---

## TD-0025 NEW — Integrate compute_provenance directly в build scripts **[HIGH PRIORITY]**

- **Origin:** P-01.0c closure observation 2026-05-04 (researcher review of TD-0024 backfill outcomes).
- **Status:** OPEN HIGH — Phase 2A pre-implementation blocker.
- **Issue:** TD-0024 root cause was multiple code paths assembling configs independently:
  - `build_regional_climatology.py` (runtime build) sets asset metadata via `combined.set({...})` без provenance fields
  - `closeout_phase_1b.py` (closure script) computes hash from independently re-assembled config dict, calls `setAssetProperties` post-hoc
  - Even when both produce «consistent» hash (e.g., NO₂ `7c2f8b2b` STARTED=SUCCEEDED=asset), the underlying config dict was non-canonical relative к build script source
- **Fix design (Phase 2A pre-implementation):**
  - **`build_regional_climatology.py`** must call `compute_provenance(config) → Provenance` at process start
  - Pass `Provenance` object к все downstream operations:
    - STARTED log entry via `write_provenance_log(prov, status="STARTED", ...)`
    - Asset metadata via `combined.set(prov.to_asset_properties())` at `Export.image.toAsset` time (NOT post-hoc setAssetProperties)
    - SUCCEEDED log entry via `write_provenance_log(prov, status="SUCCEEDED", ...)`
  - **`build_reference_baseline_ch4.py`** same integration
  - **Detection scripts** (Phase 2A): same pattern — compute_provenance once at start, propagate
  - Closure / monitoring scripts MUST receive Provenance from upstream (file or function arg), never recompute
- **Scope:**
  - Update build_regional_climatology.py + build_reference_baseline_ch4.py to integrate compute_provenance natively
  - Update orchestrator state file (`p-01.0b_state_*.json`) to persist Provenance object для resumability
  - Add unit test verifying build script + closure script produce same hash when given same config preset
  - Update Algorithm.md §2.4 + RNA.md §11.5 со updated workflow
- **Trigger:** Phase 2A design DevPrompt — fix MUST be in place before any detection event Run records generated.
- **Effort:** 4-6 hours (integration + tests).
- **Dependency:** TD-0024 closure (DONE), Provenance dataclass available (DONE).

---

## TD-0027 — Industrial buffer per source type **[RESOLVED 2026-05-05 (P-01.0d)]**

**Resolution (P-01.0d):** Heterogeneous per-feature buffer applied via classification table (`src/py/rca/classify_source_types.py`):
- `gas_field` 50 km (13 features, including 6 newly-added missing gas fields)
- `viirs_flare_high` 30 km (168 features, radiance ≥100 nW/cm²/sr)
- `viirs_flare_low` 15 km (306 features)
- `tpp_gres` 30 km (33 features, hydro/nuclear dropped)
- `coal_mine` 30 km (7 features)
- `smelter` 30 km (5 features)

New Asset: `RuPlumeScan/industrial/proxy_mask_buffered_per_type` — sanity 7/7 PASS включая Tambeyskoye centroid (50 km buffer applied, masked).

Final RESOLVED status pending Шаг 6 verification (Tambeyskoye + similar gas fields no longer appear как suspect clusters в regenerated dual baseline cross-check).

См. Algorithm §3.4.1.1 + OpenSpec MC-O.

### Original TD-0027 issue (preserved):

- **Origin:** P-01.2 closure 2026-05-04 — Tambeyskoye cluster #4 (74.08°N, 83.70°E, area 161 km², mean Δ=59.6 ppb) revealed default 30 km buffer insufficient для major gas fields.
- **Status:** OPEN — Phase 2A pre-implementation investigation.
- **Issue:** Current `proxy_mask_buffered_30km` applies uniform 30 km buffer для всех industrial proxy points. P-01.2 dual baseline cross-check showed:
  - **Tambeyskoye gas field** (cluster #4 M07): mean Δ=59.6 ppb residual после 30 km masking — gas field area extends beyond mask.
  - Likely affects other major fields: Bovanenkovo (68.4°N, 70.4°E), Yamburg (67.5°N, 75.0°E), Yuzhno-Russkoye, Urengoy.
- **Hypothesis:** Large gas fields (extraction infrastructure spans 50-100 km, не point sources) need wider buffer ~50 km vs 30 km default. Small TPP / refineries may stay at 30 km.
- **Investigation deliverables (Phase 2A pre-implementation):**
  - Per-source-type buffer mapping (e.g., `gas_field` → 50 km, `tpp_gres` → 30 km, `refinery` → 25 km, `compressor_station` → 15 km)
  - Asset attribute `source_type` в `RuPlumeScan/industrial/source_points` (currently не differentiated)
  - Build new Asset `proxy_mask_buffered_per_source_type` с heterogeneous buffer
  - Cross-check: re-run dual baseline analysis с new buffer, verify Tambeyskoye + similar gas fields no longer appear как suspect clusters
- **Trigger:** Phase 2A design DevPrompt — discuss с TD-0023 (urban masking) architectural revision since both involve mask refinement.
- **Effort:** ~1-2 days (source classification + new mask Asset build via Option C orchestrator if needed).
- **Related:** TD-0023 (urban masking), TD-0011 (prebuilt mask infrastructure).

---

## TD-0026 — Setup GEE service account для CI full audit **[RESOLVED 2026-05-05]**

**Resolution (2026-05-05):** Service account `ru-plumescan-ci-audit@nodal-thunder-481307-u1.iam.gserviceaccount.com` created с two IAM roles (`Service Usage Consumer` + `Earth Engine Resource Viewer (Beta)`). Secret `GEE_SERVICE_ACCOUNT_KEY` configured в GitHub repo secrets. Workflow `.github/workflows/audit.yml` runs full GEE audit successfully на workflow_dispatch trigger.

Verification: workflow_dispatch run [25370718735](https://github.com/SizovOleg/ru-plumescan/actions/runs/25370718735) PASSED 9/9 assets с canonical provenance (3 regional CH₄/NO₂/SO₂ + 3 v1_pre_urban_mask archive copies + 2 dual_baseline_delta_CH4 + 1 reference_CH4_v1).

Diagnostic chain (7 PRs/runs до full PASS):
1. PR #7: `ee.Initialize` ignored `GOOGLE_APPLICATION_CREDENTIALS` env var → fix via explicit `ServiceAccountCredentials`
2. PR #8: bash `echo` mangled JSON `\n` escape sequences → fix via `printf '%s'`
3. PR #9: secret missing outer `{...}` (paste artifact) → fix via Python write + auto-wrap
4. IAM: missing `Service Usage Consumer` → granted
5. IAM: missing `Earth Engine Resource Viewer` → granted
6. IAM propagation lag → wait 2 min
7. Final PASS

См. TD-0029 для full diagnostic procedure documentation.

Going forward: full GEE audit available via workflow_dispatch (manual). Can be enabled на every PR push by changing `if:` condition в workflow.

---

## TD-0026 (original issue — preserved for historical record)

- **Origin:** P-01.0c CI workflow setup 2026-05-03 (escalation per researcher directive «If auth setup needs manual configuration — escalate, не assume»).
- **Status:** RESOLVED 2026-05-05.
- **Issue:** `tools/audit_provenance_consistency.py` без `--no-gee` flag requires GEE authentication. CI workflow `.github/workflows/audit.yml` `gee-audit` job currently gated на `workflow_dispatch + full_gee_audit=true` because `GEE_SERVICE_ACCOUNT_KEY` secret не configured. Local audit remains primary gate.
- **Required action (researcher / project owner):**
  1. Create GEE service account с **read-only** access on:
     - `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/baselines/*`
     - `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/catalog/*`
     - (optional) `projects/nodal-thunder-481307-u1/assets/RuPlumeScan/refs/*` для Phase 1c+
  2. Generate JSON key file
  3. Upload as GitHub secret named `GEE_SERVICE_ACCOUNT_KEY` (full JSON content, not file path)
  4. Modify `.github/workflows/audit.yml`:
     - Remove `if: ${{ github.event_name == 'workflow_dispatch' && ... }}` condition on `gee-audit` job, OR
     - Change to `if: ${{ secrets.GEE_SERVICE_ACCOUNT_KEY != '' }}` so it auto-runs when secret present
  5. Verify next PR triggers full GEE audit successfully
- **Why HIGH priority:** Phase 2A detection events automated on schedule. Full audit gate critical для catching provenance violations from new code (TD-0024-style drift). `--no-gee` schema validation alone insufficient — миссит asset hash mismatches.
- **Trigger:** before Phase 2A production detection runs go live.
- **Effort:** ~30 minutes researcher action + 10 min YAML edit.

---

## TD-0029 — GEE implementation gotchas appendix **[LOW priority — expanded 2026-05-05]**

Lessons captured during P-01.0d (2026-05-04) + TD-0026 CI auth setup (2026-05-05). 8 distinct issues encountered, all с empirical fixes. Documented здесь для future LLM-generated и human code; eventual append к Algorithm.md §15 GEE gotchas.

### Code-level (P-01.0d implementation, 4 issues)

1. **Lazy-evaluation hazard:** `fc.filter(...)` returns deferred reference; deleting source asset before downstream Export → "Collection asset not found". **Fix:** materialize `fc_new` from archive after Export sequence guaranteed start.
2. **Reprojection reducer:** binary masks reprojected с default mean reducer dilute signal at low-resolution boundaries. **Fix:** `reduceResolution(MAX)` для conservative ANY-pixel-positive semantics.
3. **Sanity coordinate sensitivity:** when buffer changes (30→50 km), previously-clean sanity points may fall within new buffer. **Fix:** move coord или document expected change.
4. **Number/Boolean coercion:** `ee.String.equals()` returns ComputedObject; `.And()` chaining fails. `ee.List.contains()` returns Boolean. **Fix:** use `.compareTo("X").eq(0)` (returns Number), или nested `ee.Algorithms.If(...)` chain.

### CI/auth-level (TD-0026 setup, 4 issues)

5. **`ee.Initialize(project=...)` ignores `GOOGLE_APPLICATION_CREDENTIALS`:** unlike most google-cloud SDKs, GEE Python API doesn't auto-pick up env var. **Fix:** read JSON, extract `client_email`, construct `ee.ServiceAccountCredentials(email, key_path)`, pass explicitly.
6. **Bash `echo "$VAR"` mangles JSON private_key:** strict bash interprets `\n` escape sequences inside string variable, corrupting service account JSON. **Fix:** `printf '%s' "$VAR"` для literal write, или write via Python (`open(path, 'w').write(os.environ['VAR'])`).
7. **GitHub Actions secrets с multi-line JSON paste artifact:** users pasting JSON sometimes drop outer `{...}` braces. **Fix:** defensive auto-wrap inside CI script before parse.
8. **Two-layer GEE IAM:** beyond GCP project IAM (`Service Usage Consumer`), Earth Engine has separate `roles/earthengine.viewer` permission. Missing it gives confusing error `'earthengine.computations.create' denied`. **Fix:** grant BOTH roles. Earth Engine Resource Viewer is Beta as of 2026-05.

### Procedural lessons

- IAM propagation can take 1-2 min — failures immediately после grant may resolve themselves
- Granting role via "Edit principal" doesn't always preserve existing roles — verify both present after edit
- Symptom regression (later run shows earlier-fixed error) is usually IAM propagation lag, не actual revert

- **Origin:** P-01.0d implementation 2026-05-04/05 — encountered 4 distinct GEE
  Python API gotchas worth documenting for future LLM-generated и human code.
- **Status:** OPEN, low priority. Effort ~15 min — append к Algorithm.md §15.
- **Lessons captured:**
  1. **Lazy-evaluation hazard:** `fc.filter(...)` returns deferred reference;
     deleting source asset before downstream Export → "Collection asset not
     found". **Fix:** materialize `fc_new` from archive after Export sequence
     guaranteed start, или use `Export.table.toAsset` immediately on filtered
     deferred ref before mutating source.
  2. **Reprojection reducer:** binary masks reprojected с default mean reducer
     dilute signal at low-resolution boundaries (1km→7km halved Surgut urban
     signal). **Fix:** use `reduceResolution(MAX)` для conservative
     ANY-pixel-positive semantics.
  3. **Sanity coordinate sensitivity:** when buffer changes (e.g., 30→50 km для
     gas_field), previously-clean sanity points may fall within new buffer
     (Yamal vacuum (71, 73) ↔ Kruzenshternskoye 40 km). **Fix:** either move
     coord или document expected change.
  4. **Number/Boolean coercion:** `ee.String.equals()` returns ComputedObject не
     Number; `.And()` chaining fails. `ee.List.contains()` returns Boolean,
     also fails `.And()`. **Fix:** use `.compareTo("X").eq(0)` returning Number,
     или nested `ee.Algorithms.If(...)` chain instead of algebraic chains.
- **Trigger:** when Algorithm.md §15 (GEE gotchas) revised next; либо когда
  similar issue encountered.

---

## TD-0023 — Cities-vs-industrial scope inflation **[RESOLVED 2026-05-05 (P-01.0d)]**

**Resolution (P-01.0d):** New `RuPlumeScan/urban/urban_mask_smod22` Asset created via JRC GHS-SMOD ≥22 threshold. Combined с industrial mask via AND-merge в `build_regional_climatology.py --use-urban-mask`. Sanity 4/4 PASS (Tyumen/Surgut/Novokuznetsk masked as urban, Yamal vacuum non-urban). Reprojection 1km→7km uses MAX reducer (conservative — any 1km urban → 7km cell urban). См. Algorithm §3.4.1.2 + OpenSpec MC-O.

NO₂/SO₂ regional baselines rebuilding с urban + per-type combined masking (24-30h ETA). Final RESOLVED status pending Шаг 6 sanity verification.

### Original TD-0023 issue (preserved):

- **Origin:** P-01.0b Phase 1b closure sanity validation 2026-04-30 — Tyumen,
  Surgut, Novokuznetsk all masked в NO₂/SO₂ regional baselines via 30 km
  buffer of collocated TPP/GRES industrial proxy points.
- **Status:** OPEN HIGH — Phase 2A NO₂/SO₂ detection blocker; Phase 1c
  (CH₄-only) NOT blocked.
- **Issue:** Major cities have anthropogenic NO₂ contamination от:
  - Transport (автомобили, public transit)
  - Heating systems
  - Construction, urban activity
  - **Not just collocated TPPs**

  Current 30 km industrial buffer effectively masks entire urban regions when
  a TPP is collocated. Consequences:
  - Lose detection capability в these regions для Phase 2A (~1.5M residents
    в excluded urban areas)
  - Cannot validate против CAMS / IMEO catalogs (which may include urban events)
  - Tool-paper claim "exclude industrial sources" inaccurate — actually
    excludes urban regions
- **Architectural decision needed (Phase 2A NO₂ design):**
  - **(a)** reduce buffer to 15-20 km для collocated TPPs (less aggressive)
  - **(b)** add urban polygons explicitly excluded from baseline (separate
    `urban_mask` layer)
  - **(c)** build separate urban baseline (most architecturally clean)
- **Trigger:** Phase 2A NO₂/SO₂ design DevPrompt. Requires architectural
  discussion с researcher.
- **Effort:** 2-3 days (option b: city polygon ingestion + 15 km baseline
  rebuild) до 1-2 weeks (option c: separate baseline architecture).
- **Phase 1c safety:** не блокирует (CH₄-only baseline cross-check).

---

## TD-0024 — Provenance hash consistency bug **[RESOLVED 2026-05-03 (P-01.0c)]**

- **Origin:** P-01.0b Phase 1b closure 2026-04-30 — SO₂ STARTED log used
  different params_hash than SUCCEEDED log + asset metadata.
- **Status:** **RESOLVED 2026-05-03** — backfill executed, prevention pattern
  enforced via frozen `Provenance` dataclass + CI audit gate. См. OpenSpec
  MC-2026-05-03-M + `docs/p-01.0c_backfill_report.json`.
- **Resolution summary:**
  - All 4 baseline assets backfilled с canonical params_hash (reference CH₄ v1
    + regional CH₄ + regional NO₂ + regional SO₂)
  - Honest backfill caveat fields document reconstruction limitations
  - Original runtime hashes preserved as `pre_backfill_params_hash` для forensic audit
  - Centralized `compute_provenance(config) → Provenance` (frozen dataclass)
    prevents future hash drift by construction
  - Audit tool `tools/audit_provenance_consistency.py` + allowlist mechanism +
    CI integration via `.github/workflows/audit.yml` (`--no-gee` schema validation
    on every PR; full GEE audit gated on workflow_dispatch + secret)
  - Algorithm.md §2.4.1 + RNA.md §9.1 documentation о canonical pattern
- **Escalation outstanding:** full GEE audit в CI requires
  `GEE_SERVICE_ACCOUNT_KEY` GitHub secret. Per researcher directive — не
  assumed, deferred к user. Local audit (`python tools/audit_provenance_consistency.py`)
  остаётся primary gate until secret configured.

### Original audit findings (kept для historical record)
- **Audit results (2026-04-30, all 4 P-01.0a/0b runs):**

  | Run | log STARTED | log SUCCEEDED | asset.params_hash | Verdict |
  |-----|-------------|---------------|-------------------|---------|
  | CH₄ reference v1 (P-01.0a) | (none — retroactive) | `1a89d4f6` | **MISSING** | INCOMPLETE — asset has no params_hash property at all |
  | CH₄ regional (P-01.0b) | (none — retroactive) | `d2e6362c` | `c8b6e97f` | MISMATCH — log vs asset |
  | NO₂ regional (P-01.0b) | `7c2f8b2b` | `7c2f8b2b` | `7c2f8b2b` | OK consistent |
  | SO₂ regional (P-01.0b) | `40f04025` | `f669e1c8` | `f669e1c8` | MISMATCH — STARTED vs SUCCEEDED+asset |

- **Diagnosis:** issue is **partially systemic**. 3 distinct failure modes:
  1. **CH₄ reference v1**: asset built before provenance helpers existed
     (P-01.0a pre-CR review); has algorithm_version but не params_hash/run_id
  2. **CH₄ regional**: retroactive log entry used config dict different
     from build-time config that landed на asset properties
  3. **SO₂ regional**: STARTED log computed provenance from config dict
     that differed slightly from SUCCEEDED log canonical config

- **Root cause:** params_hash computed multiple times in different code paths
  с config dicts assembled inconsistently. Не enforced как single
  immutable reference.

- **Fix design (Phase 2A pre-implementation):**
  - Compute `prov = compute_provenance(config)` ONCE at process start
  - Pass `prov` immutably к all logging + asset metadata setters
  - Add unit test: assert STARTED.params_hash == SUCCEEDED.params_hash for
    all entries with matching run_id base
  - For asset metadata: setAssetProperties immediately after Export task
    submit (not after combine, where config could drift)
  - Audit script `tools/audit_provenance_consistency.py` — runs across
    `logs/runs.jsonl` + asset properties, flags mismatches

- **Retroactive remediation (NOT done — would rewrite history):**
  - Could update CH₄ reference v1 asset to add canonical params_hash
    (1a89d4f6 from log)
  - Could update CH₄ regional asset to use d2e6362c from log
  - Could update SO₂ STARTED log entry (rewrite jsonl) to use f669e1c8
  - **Decision:** documented as audit finding в TD-0024. Не silently change
    historical artefacts. Phase 2A pre-implementation fix prevents recurrence
    going forward.

- **Trigger:** Phase 2A design DevPrompt — fix MUST be implemented before
  detection events generate run records. Audit existing entries pre-launch.

- **Effort:** 4-6 hours (fix in `provenance.py` + orchestrator integration +
  audit script + unit tests).

- **DNA §2.1 запрет 12 status:** formally satisfied для NO₂ (всё matches).
  Formally satisfied для SO₂/CH₄ regional asset metadata. **Not satisfied
  для CH₄ reference v1 asset** (no params_hash) — must fix during Phase 2A
  preparation.

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

## TD-0017 NEW — Transboundary transport contamination (Krasnoyarsk → western AOI)

- **Origin:** P-01.0b CR review CLAIM 3 fix 2026-04-29
- **Status:** documented caveat — **partial empirical support от P-01.2** (suspect clusters #3 + #5 located eastern edge AOI 94°E in Krasnoyarsk Krai)
- **Phase 1c finding (P-01.2):** Top-5 suspect clusters M07 include 2 sites at lon ≈ 94°E (54.45°N + 53.73°N), mean Δ = 54-60 ppb. Could be undocumented sources OR transboundary transport from Krasnoyarsk industrial cluster eastward. **Phase 2A action filed:** HYSPLIT back-trajectory check для events с centroid at lat∈[53,56], lon ≥ 92.
- **Observation:** Krasnoyarsk industrial cluster (Krasnoyarskaya GRES-2 1250 MW
  + 3 более) в 90-95°E band added to `industrial/source_points` v2 (CLAIM 3
  fix). Industrial mask now excludes these points. Но при favorable easterly
  winds — CH₄/SO₂/NO₂ от этих sources может transport westward в KhMAO/Yamal
  и appear как increased baseline на pixels NOT covered industrial buffer.
- **Trigger:** Phase 2A detection sensitivity test — investigate
  false-positive rate в western AOI parts при detection runs covering periods
  с predominantly easterly transport.
- **Effort:** 2-3 days (HYSPLIT back-trajectory analysis или ERA5 wind
  climatology correlation).

---

## TD-0018 NEW — Kuzbass detection caveat (mask gap pre-fix + low Kuz-Alatau counts) **[suspect clusters mapped]**

- **Origin:** P-01.0b CR review CLAIM 3 + MC-2026-04-29-I 2026-04-29
- **Status:** **HIGH severity для Phase 2A в Kuzbass region** — **suspect clusters mapped P-01.2 2026-05-04**
- **Phase 1c finding (P-01.2):** 195 suspect clusters M07, 221 M10 across full AOI. Kuzbass-specific (lat 53-55°N, lon 86-88°E) clusters identified в `docs/p-01.2_suspect_regions_M07.geojson` + `_M10.geojson`. Phase 2A handoff specifies z_min=4.0 для этой region + manual review trigger для events с `nearest_source_id=null` near top-5 clusters.
- **Observation:** Primary CH₄ detection target region (regression baseline
  Кузбасс 2022-09-20 per CLAUDE §5.1) has compounded uncertainty:
  - **Industrial mask gap pre-fix:** 4 major Kuzbass plants (Tom-Usinsk,
    Kuznetsk TES, Novo-Kemerovo, Kemerovo) missed в P-01.0b CH₄ regional
    baseline. Pixels near these plants могут содержать residual industrial
    signal в regional baseline. Mask fixed в same PR, но CH₄ regional Asset
    built на pre-fix mask (preserved per Option E).
  - **Reference baseline reliability:** Kuznetsky Alatau (lat 53-57°N,
    Kuzbass primary reference) imeет low TROPOMI counts 60-140/month vs
    5000+ для lowland zones (P-01.0a TD-0010). Mountain cloud cover + SWIR
    challenges.
  - **Cross-check unreliable:** Both baselines have elevated uncertainty
    в этой region. Dual baseline architecture's «one robust baseline»
    assumption not satisfied.
- **Phase 2A mitigation requirements:**
  - **Stricter z_min threshold** для Kuzbass-region plumes: z_min=4.0
    (vs default 3.0). Reduces false positive rate but also reduces sensitivity.
  - **Manual review trigger:** events с `nearest_source_id=null` near
    coordinate (86-88°E, 53-55°N) — likely missed Kuzbass industrial
    source. Compare с updated `industrial/source_points` v2 (post-fix).
  - **Document Phase 2A detection limit:** Kuzbass ~14 ppb sensitivity vs
    Yamal/Khanty ~30+ ppb sensitivity (proxy estimate).
- **Trigger:** Phase 2A CH₄ detection run on regression baseline Кузбасс
  2022-09-20.
- **Effort:** apply mitigation в Phase 2A DevPrompt (15 min config), then
  validate с regression test.

---

## TD-0019 — Reference baseline latitude-stratification: extrapolation quantitative impact **[RESOLVED 2026-04-29]**

- **Origin:** P-01.0b 6-point Ref vs Regional cross-check + researcher
  investigation request 2026-04-29.
- **Status (2026-04-29): RESOLVED — methodology bounded, distance not the
  driver.**
- **Trigger observation:** P-01.0b cross-check spread 38 ppb (-17.91 to
  +21.56) для non-industrial points — beyond `consistency_tolerance_ppb=30`.
  Hypothesis: latitude-only zone stratification (centroids 54.5/60.5/63.5°N,
  no longitude weight) extrapolates baselines unreliably на distant points.
- **Investigation deliverables:** `docs/p-01.0b_extrapolation_investigation/`
  - `01_zone_map.png` — zone assignment + lat-distance heatmap
  - `02_delta_vs_distance.png` — Δ scatter с linear fit (n=104 random clean
    points, M07)
  - `03_latitude_transect.png` — ref vs reg at lon=75°E
  - `REPORT.md` — full analysis
  - `stats.json` — raw numerical
- **Findings:**
  - **R² = 0.0023** (|Δ| vs lat_dist_km, n=104, p=0.629). NOT significant.
  - Slope -0.003 ppb/km — distance к centroid не predicts \|Δ\|.
  - \|Δ\|: max 54, mean 19.8, median 15.8 ppb. Substantial \|Δ\| exists
    но distance не explains it.
  - Visible step-change discretization artifact at zone boundaries
    (57°N, 62°N) — produces local Δ even for points close to centroid.
  - Zone 4 article t1 comparison: ref_mean=1873 vs article=1854 (Δ=+19).
    Plausible — period + biome (whole zapoved vs wetland-only) mismatch.
- **Verdict per researcher's pre-stated criterion (R² < 0.2):** PROCEED
  normally. \|Δ\| reflects biome/period differences, NOT extrapolation
  artifact.
- **Phase 2A guidance produced:**
  - Phase 2A `consistency_flag=false` triggers should record `lat_dist_km`
    per candidate as confidence-modifier — NOT a hard fallback rule.
  - Step-change boundaries (~57°N, ~62°N at lon=75°E) могут produce
    spurious cross-check disagreements; document для Phase 1c.
- **Future improvement (deferred, NOT blocker):** distance-weighted blend
  между nearest-2 zones смягчил бы step changes. Candidate для potential
  CHANGE-0018 после Phase 1c full cross-check map.

---

## TD-0021 NEW — Zone-boundary detection sensitivity (CH₄ Phase 2A) **[steps quantified, handoff complete]**

**P-01.2 update (2026-05-04):** Step sizes quantified at 75°E transect (0.1° resolution):
- Boundary 57.5°N (Kuznetsky → Yugansky): step_M07 = +34.85 ppb, step_M10 = +19.83 ppb
- Boundary 62.0°N (Yugansky → Verkhne-Taz): step_M07 = −16.18 ppb, step_M10 = +1.82 ppb

Phase 2A mitigation parameters specified в `docs/p-01.2_phase_2a_handoff.md`: smoothing window 2°, trigger ≤ 100 km from boundary, optional CHANGE-0018 (distance-weighted blend nearest-2 zones) deferred.

### Original TD-0021 issue (preserved):

- **Origin:** P-01.0b extrapolation investigation 2026-04-29 (TD-0019
  resolution + latitude transect at 75°E findings).
- **Status:** documented, deferred к Phase 2A CH₄ detection design.
- **Observation:** reference baseline shows discrete plateaus at latitude
  band boundaries: Kuznetsky↔Yugansky transition ~57°N (Δ ≈ 14 ppb step,
  1846→1880), Yugansky↔Verkhne-Tazovsky transition ~62°N (Δ ≈ 17 ppb step,
  1880→1863). Regional baseline continuous. Phase 2A CH₄ detection within
  ~50 km from these boundaries может trigger spurious
  `consistency_flag=false` (dual-baseline disagreement caused by reference
  discretization, не real anomaly).
- **NOT blocker для NO₂/SO₂ — they don't use reference baseline в v1**
  (single regional climatology only per RNA §11.1). Critical для Phase 2A
  CH₄ design.
- **Mitigation options (для Phase 2A DevPrompt or CHANGE-0018):**
  - **(a)** moving-average smoothing reference over neighbouring 100 km
    latitude — preserves architecture, smooths step changes
  - **(b)** distance-weighted blend nearest-2 zones — full
    methodology revision (CHANGE-0018 candidate)
  - **(c)** record `lat_dist_km_to_band_boundary` per CH₄ candidate and
    treat `consistency_flag=false` near boundaries как "ambiguous"
    requiring additional evidence (cluster + wind alignment)
- **Effort:** option (c) ≈ 1 hour (config flag в Phase 2A); options (a)/(b)
  ≈ 1-3 days each.

---

## TD-0022 NEW — Article t1 full zonal-stats comparison (Phase 1c validation) **[Zone 4 confirmed; Zones 1+8 deferred]**

**P-01.2 partial closure (2026-05-04):** Zone 4 (Middle taiga 60-63°N) confirmed: article 1854 ppb vs наш ref_mean 1870.5 ppb, Δ +16.5 ppb plausibly explained by wetland-only article extent vs full-band our reference. Zones 1+8 article numbers недоступны → **deferred** к follow-up или Phase 6 validation campaign.

### Original TD-0022 issue (preserved):

- **Origin:** P-01.0b extrapolation investigation 2026-04-29 — partial
  comparison only (Zone 4 confirmed +19 ppb plausible per period+biome
  mismatch).
- **Status:** deferred к Phase 1c.
- **Need:** full t1 zonal stats for all 8 article zones (currently only
  Zone 4 = 1854 ppb provided). Specifically Zone 1 (Tundra 67-72°N) and
  Zone 8 (Steppe 52-55°N) needed to evaluate latitude-stratified
  reference assignments на extrapolated bands.
- **Phase 1c plan:** request adjacent project authors → extract all 8 zones
  → compare с our reference per latitude band → independent third-party
  validation для tool-paper.
- **Action:** capture in Phase 1c DevPrompt (P-01.2_dual_baseline_validation.md
  предположительно). Если authors недоступны — note as limitation, не
  blocker.
- **Effort:** depends on author response time + manual data extraction
  (~30 min once received).

---

## TD-0020 — Bovanenkovo test point coordinate error **[RESOLVED 2026-05-05 (P-01.0d)]**

**Resolution:** Sanity test points в P-01.0d closeout use accurate Bovanenkovskoye centroid (68.4°E, 70.4°N). Verified masked 50 km buffer applied correctly across all 3 regional baselines (CH4/NO2/SO2). Coordinate convention now consistent across codebase.

### Original TD-0020 issue (preserved):

- **Origin:** P-01.0b validation report point 6 misnomer 2026-04-29
- **Status:** documented, low priority
- **Observation:** validation report labels point 6 «Bovanenkovo proxy»
  (70.5°E, 70.5°N), но actual Bovanenkovo NGKM centroid находится
  ≈(68.4°E, 70.4°N) — ~80 km west. Sampled coord falls в less-instrumented
  Yamal zone, NOT в proper Bovanenkovo gas field.
- **Impact:** misleading mask-coverage claim в PR #3 description and
  earlier P-01.0b summary. Real Bovanenkovo would be in 30 km industrial
  buffer (after CLAIM 3 fix), но sampled point may not be.
- **Action item:** при next sanity validation, replace point 6 с actual
  Bovanenkovo (68.4, 70.4) AND add fresh point at (70.5, 70.5) под
  honest label "Mid-Yamal east clean".
- **Effort:** 5 min config update + script re-run.

---

## TD-0008 — Refactor build_zone_baseline_single_month memory footprint (Q-mid months) **[RESOLVED 2026-04-30 — cross-gas verified]**

**Final outcome (2026-04-30):** Option C (12 separate batch tasks per gas) verified
across **all 3 gases**:
- CH₄ regional climatology 2026-04-29: 12/12 SUCCEEDED including Q-mid
- NO₂ regional climatology 2026-04-30: 12/12 SUCCEEDED including Q-mid
- SO₂ regional climatology 2026-04-30: 12/12 SUCCEEDED including Q-mid

Pattern documented в `build_regional_climatology.py` orchestrator. Hypothesis
empirically confirmed across 3 different gas pipelines + 3 different runs +
36 separate batch tasks total. TD-0008 closed с high confidence. См.
OpenSpec MC-2026-04-30-L.

---

## TD-0011 — Pre-computed mask Asset для NO₂/SO₂ optimization **[RESOLVED 2026-04-30]**

**Outcome:** `RuPlumeScan/industrial/proxy_mask_buffered_30km` Asset successfully
used for NO₂ + SO₂ regional climatology builds 2026-04-30. Saved ~1.5 hours
compute per gas (3 hours total) via skip of inline `focal_max(15km)` operation.
Pattern: `--use-prebuilt-mask` flag в orchestrator. См. MC-2026-04-30-J/K.

---

## TD-0012 — Mask consistency cross-gas verification **[RESOLVED 2026-04-30]**

**Outcome:** Same `proxy_mask_buffered_30km` asset used uniformly across CH₄
(post-build verification commit 589efaf), NO₂ (2026-04-30 closure), и SO₂
(2026-04-30 closure). Industrial pixel masking verified consistent в 3-gas
sanity tests:
- Norilsk Nadezhdinsky: masked в всех 3 gases ✓
- Tom-Usinsk GRES (Kuzbass): masked в NO₂ + SO₂ (CH₄ used pre-fix mask per
  Option E rationale, см. TD-0018)
- Yugansky reference centroid: masked (collocated с oil infrastructure) ✓

---

## TD-0008 archive note (kept для historical record)

- **Origin:** P-01.0a Phase A diagnostics (commit `<P-01.0a merge SHA>`, 2026-04-28)
- **Owner:** Claude (исполняющий) при triggering
- **Status (2026-04-29): RESOLVED.** Option C verified в P-01.0b CH₄ run —
  все 12 monthly tasks COMPLETED including Q-mid M02/M05/M08/M11. 12 separate
  batch tasks (each own server-side memory allocation) bypass cumulative
  graph memory limit single-iteration approach. Hypothesis confirmed.
- **Outcome:** A (full success). См. OpenSpec MC-D + retroactive run log
  `default_2019_2025_d2e6362c` в `logs/runs.jsonl`.
- **Apply pattern для:** future regional baseline NO₂/SO₂ runs (built into
  build_regional_climatology.py orchestrator). И P-01.0a reference baseline
  if rebuild needed.

### Original concern (kept для historical record)
- **Trigger:** **BLOCKS Phase 2A** (CH4 detection) — must mitigate перед production
  detection runs. Любой из:
  - Refactor compute (preferred, 1 day work)
  - Temporal interpolation as Phase 2A Option A
  - Skip Q-mid detection runs as Phase 2A Option B

### TD-0008 fix hypothesis (researcher 2026-04-28)

Pattern **M02/M05/M08/M11 = months 2,5,8,11 = every 3rd modulo 12**.
Это suggests **GEE internal compute scheduling**, не data-related (data
same across all months — TROPOMI L3 daily mosaics evenly distributed).

**Option C (worth testing):** split full-year build на **12 separate
batch tasks** instead of single iteration в одном process. Each Export
task получает own server-side memory allocation, обходя cumulative
graph memory limit one process generates iterating over 12 months.

Implementation sketch:
```python
for month in range(1, 13):
    task = ee.batch.Export.image.toAsset(
        image=build_single_month_stratified(month),
        assetId=f"...reference_CH4_2019_2025_v1_M{month:02d}",
        ...
    )
    task.start()
# Затем merge 12 single-month assets в multi-band Image через
# ee.Image.cat() или одиночное reuploading combined.
```

**Trade-off:** 12 separate tasks vs 1 multi-band Image → finer error
isolation (one Q-mid month fail не блокирует others) + parallelizable.
**Risk:** orchestration complexity (waiting на 12 tasks, dealing с
partial failures, merging final asset).

**Effort estimate revised: 2-3 days** (hypothesis test + refactor +
re-run для CH4 + 4-band per-zone-id assets — also useful для other gases).
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
