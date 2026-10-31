# Post-upgrade Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Checkboxes track execution.

**Goal:** Implement and verify all seven recommended post-upgrade repairs.
**Architecture:** Repair the existing Svelte/Vite readers and verification contracts, qualify successors to frozen Python pipeline releases, and adapt the existing analytics collector to the current qualified provider. Preserve histories and authorities.
**Tech Stack:** Svelte, Vite, Vitest, Playwright, pinned Node22/Python3.12, PostgreSQL18, OpenHAB, systemd.
**Spec:** docs/superpowers/specs/2026-10-24-post-upgrade-repairs-design.md

## Global Constraints

- Main checkout /home/sat/earthship-ui is dirty. This worktree baseline is2e7cbd9c1672e7d8a2128c9b093867dfc3c7c0c7 and includes its existing state; preserve unrelated edits.
- Active UI baseline /home/sat/earthship-ui/artifacts/bedroom-relocation-20261024.local/ui-release; retain strict v2 sensor epoch and120-second freshness and Bedroom boundary2026-10-24T23:14:52Z.
- No new physical/financial actions, control authority, external provider or billing. Preserve qualified model families and original observations, issue times, pins and immutable packages.
- Heavy jobs use existing household_job_run.py with PYTHONDONTWRITEBYTECODE=1, /usr/bin/python3 -B, absolute commands and taskset; preserve original pool6GiB/8CPU/256tasks/no-swap and launcher per-job<=128tasks. Node=/home/sat/earthship-ui/artifacts/weathernext3-capabilities.local/node-runtime-1bec56ef7cfa9a76/node.
- Thermal stage deployment SHA7d82037e6ba4fbe3427bf8aef634056651346b5bd55e44078c11d8f5576e2c2d is immutable. Replace changed code via qualified successor; do not mutate manifests or models to bypass verification.
- Existing score120s bound, activation240s/150s safe-window gates and all freshness/permission rules remain unchanged.
- User authorized execution of the audited recommendations. No new design/permission round is needed for reversible scoped repairs and necessary qualified deployments. No pushes requested.
- No implementation subagents in parallel. Read-only diagnosis may overlap. Commit only each task's changes and provide a diff/report file for review. No subagents from workers.

## Review Focus

- New human-advice profile must not admit proposals or promote malformed legacy qualification reports (Task3).
- Retired-file assertions must be replaced by meaningful current behavior, not blindly deleted or weakened (Task2).
- Freshness expiration must remove stale analytics values even when the transport remains HTTP200 (Task4).
- Failures during timer reservation/activation must restore scheduling and leave prior model safe; no new overlapping windows (Task6).
- Timeout/cancel paths must preserve immutable scoring identity, original results, bounded work and diagnostic causes (Task5).

### Task 1: Repair test project entrypoints and owned discovery (findings05,07)
**Files:** Modify playwright.config.js,vite.config.js and necessary tests/fixtures safety infrastructure; mirror applicable configuration to the future active successor.
**Interfaces:** consumes actual package.json test scripts and current tests/e2e inventory; produces working fixtures/sensors selections and test discovery limited to maintained tests.
- [ ] Reproduce missing fixtures project with pinned Playwright --list and unwanted artifact discovery using a disposable sentinel test outside maintained tests.
- [ ] Define supported fixtures/sensors projects and service-worker isolation matching actual source; restore missing maintained project tests where required by a real supported surface, never silently select zero tests.
- [ ] Restrict Vitest include/exclude to maintained tests, retaining e2e/worktree/node_modules separation. Ensure tests never contact real household backends: shared fixture transport or audited ephemeral-loopback isolation.
- [ ] Verify project discovery and maintained-test enumeration, plus representative disposable browser fixture under unchanged resource limits. Diagnose thread/startup constraints rather than raising caps.
- [ ] Commit scoped changes, write report with red/green evidence and source diff.

### Task 2: Reconcile maintained checkout test contracts (finding06)
**Files:** tests/current-aqi-receipt.test.js,tests/openhab/aqi-migration.test.js,tests/deployment-service.test.js,tests/ui/ForecastComparison.test.js,tests/store.test.js,tests/sse.test.js and remaining failed current tests; production modules only when a supported behavior is actually missing.
**Interfaces:** consumes Task1 discovery and audit contracts/current-unit-results.json; produces a fully meaningful current maintained suite.
- [ ] Reproduce actual current failure set; classify every assertion against current provider-retirement and UI requirements, keeping a per-failure disposition.
- [ ] Retire tests for intentionally removed providers/units and replace them with current acquisition/unsupported-state behavior checks. Fix obsolete expected labels/snapshot/SSE behavior based on actual current contracts. Restore required missing behavior if found; do not restore retired providers or weaken correctness for a green run.
- [ ] Prove relevant replacements catch wrong behavior; run complete maintained suite and build within existing job admission. Record every remaining failure by name; task is not complete while required checks remain red.
- [ ] Commit scoped changes and report tests/dispositions.

### Task 3: Repair human-advice-separated observation reading (finding01)
**Files:** src/lib/household/observation.js,src/lib/household/qualification.js,src/lib/ui/HouseholdObservation.svelte and maintained observation/qualification/server/UI tests.
**Interfaces:** consumes exact installed pipeline.py human_advice_separate profile and household_observation.py qualification/v3 emitter; produces a strict read-only compatible reader and meaningful diagnostic UI, never command authorization.
- [ ] Capture a private runtime reproduction and author non-private complete fixtures for the current separate-advice profile, including unavailable bounded_exhaustive_v1/empty v3 qualification families; prove current reader/server rejects it.
- [ ] Implement an explicit closed current-profile path retaining hash/identity/clock/authority/automatic_actuation checks. Preserve original command-report validation. New profile must have no command proposals and no release authorization; malformed or authority-bearing variants fail closed.
- [ ] Test both independent enum and qualification mismatches, expiry, identity mismatch, extra/missing fields, nonempty proposals and claimed release. Render the separate-advice state honestly.
- [ ] Run related tests plus complete suite, commit, report. Parent qualifies a successor UI and verifies live HTTP200/read-only rendering.

### Task 4: Repair analytics current forecast integration and stale display (finding03)
**Files:** /home/sat/Solar_PV/analytics/src/earthship_energy/{forecasts,scheduled,ui_reader}.py and its maintained tests/units; src/lib/ui/EnergyAnalyticsDetail.svelte,src/lib/energy/analyticsResult.js and corresponding tests.
**Interfaces:** consumes current qualified WeatherNext/PV source with original issue/provenance, existing analytics forecast_snapshots schema and publisher health; produces current snapshots and no stale values presented as current. Use a separate isolated analytics patch; parent integrates source/deploys approved adapter.
- [ ] Reproduce legacy absent snapshot unit and old parser/source mismatch; reproduce stale issuedAt forecast numeric field in current-facing analytics details.
- [ ] Adapt the existing acquisition to qualified current provider and restore an appropriately bounded scheduled snapshot path, retaining schema/revision/cohort and history semantics. No retired provider fallback or billing.
- [ ] Suppress or explicitly historical-label stale forecast numbers; test stale, future issue, malformed provenance, unsupported fields and good current source behavior.
- [ ] Run analytics tests and UI tests, qualify/deploy adapter and schedule, observe a genuine new snapshot and publisher health. Commit/report with rollback and before/after provenance.

### Task 5: Repair bounded thermal serving/scoring (finding02)
**Files:** pinned-source successors of openhab/scripts/{household_cycle.py,household_forecast_score.py,household_native_geometry_prepare.py,household_cycle_deploy.py} and related maintained tests; exact files depend on verified diagnosis.
**Interfaces:** consumes thermal-diagnosis artifacts and current retained scoring/serving receipts; produces verified causes, bounded correct scoring/serving and a qualified successor.
- [ ] Restore incidental unmanifested caches only by quarantine (completed operationally; exact stage verified unchanged). Ensure all probes/entrypoints prevent future bytecode writes in immutable packages.
- [ ] Preserve actionable refusal cause and reproduce CPU-hotspot/deadline and lock/window contention using private retained inputs or hand-built independent test fixtures. Read-only profiling may not invoke production score_jobs or rewrite existing reports.
- [ ] Implement root-cause optimization/lifecycle correction that preserves original scoring identity and results,120s bound, freshness/permission gates and existing resource caps. Refine task from diagnosis before coding; no guessed workaround.
- [ ] Qualify successor using established cold/pin/runtime compatibility gates, run meaningful regression/performance tests, verify natural scheduled publication/scoring outcomes and source integrity. Commit/report.

### Task 6: Repair native activation starvation (finding04)
**Files:** qualified successor openhab/scripts/household_native_training.py and existing activation/handoff scheduling helpers/tests/units.
**Interfaces:** consumes verified starvation reproduction and Task5 scheduling interfaces; produces one bounded safe activation opportunity while restoring owned scheduling on every exit.
- [ ] Reproduce active scorer spanning the safe half-cycle and240s timeout with fake clock/actual wait implementation; include failure/interrupt cleanup and concurrent serving reservations.
- [ ] Reserve a handoff opportunity before packaging or cooperate with owned score scheduling; preserve150s safe window and240s bound, leave forecast/geometry safety intact, restore exact prior timer state on success/failure/cancellation. Do not simply stop arbitrary jobs or expand deadlines.
- [ ] Run original native-family compatibility/qualification checks, execute or observe an authorized real refresh/activation through the existing resource controls and verify resulting selected model/pins and new serving output. Preserve incumbent/history until gates pass.
- [ ] Commit/report with exact activation and rollback evidence. Task stays incomplete until a genuine cycle verifies it.

### Task 7: Integrate, deploy and close all findings
**Files:** successor UI artifact, existing service drop-ins and canonical repair verification tracker; exact targeted main paths only.
**Interfaces:** consumes reviewed scoped commits/successor packages; produces a live repaired deployment and coherent maintained checkout with proof for all seven findings.
- [ ] Review whole change range against spec and all task reports; resolve substantive findings.
- [ ] Build/test successor from actual active UI baseline, apply reviewed compatible changes, retain package/control/model policies. Apply only own exact guarded patches to dirty main and analytics sources; preserve unrelated hashes.
- [ ] Verify default unit command, builds, intended e2e selections and actual isolated fixtures, live six-route/two-size read-only browser charts/details, Household HTTP200, fresh analytics, normal thermal serving/scoring and successful native activation.
- [ ] Update each seven-finding tracker row only with authoritative tests/runtime outputs; include remaining expected-unavailable states and no new actuator authority.
- [ ] Complete the goal only after requirement-by-requirement audit proves all required repairs deployed and verified. Do not replace completion with a narrower success or a stopped budget.


### Task 8: Complete isolated sensor resource qualification and inherited final gates
**Dependent plan amendment after Task7 five-round breaker:** Actual Q02 exposed CompletableFuture per-task thread fallback under the provisional APC1 test profile; all Task7 source defects are reviewed fixed, but actual11+2 remains mandatory.
- [ ] Apply the narrow test-only common.parallelism=2 choice, preserving APC1 and original global limits. Q04 proved the provisional64-task OpenHAB member still exhausts normal Felix startup; fix round1 tested controller80/OpenHAB80 but Q05 still had native-thread startup OOMEs; fix round2 tested64/96 but Q06 recorded startup task exhaustion. The independently reviewed fixed round3 candidate keeps controller64, sets full OpenHAB112/guardian8/ingest8/ChirpStack8, retains MQTT8/PostgreSQL24/Redis8/simulator8, and preserves lifecycle-proof controller96/guardian16/MQTT-only. Total remains248; guardian8 requires actual recovery qualification plus all original end-to-end gates. The round3 full sum was3008MiB/8CPU/248tasks. Q07 refused before create with residual~3128MiB above its2880 ceiling. Independently designed round4 lowers only provisional test OpenHAB memory1536->1152MiB (heap768 unchanged), external2496->2112 and total3008->2624; unchanged256MiB reserve permits residual<=3264. CPU8/tasks248/no swap/global6144 unchanged. Working caps still require actual guardian8 recovery and11+2/zero-events proof, not arithmetic. Round4 source306EACH approved but actualQ08 failed11setup withOH112peak118/pids.max244. Final round5 follows B/sensor-final-budget-design.md: launcher still admits64, controller narrows48 before external effects; OH128 stays constant; after all11Python PASS, irreversible exact ChirpStack then Redis retirement and zero-cgroup proof precede restoration to original64 for both unchanged browser cases. Each phase248tasks/memory2624/CPU<=8, lifecycleproofunchanged. Immutable manifest, original OFD custody, bounded fixed operations and cleanup-only phase recovery remain mandatory. No further fixed cap search, global policy increase or additional readiness allowance.
- [ ] Establish executor selection with a bounded JVM diagnostic and capture exact owned startup properties/thread observations during full qualification.
- [ ] Require unchanged actual11Python+2REST/SSEbrowser cases, original timeouts/viewports/assertions, zero new resource-limit events, all7 actual kernel caps, source/credential/volume/production preservation and terminal cleanup.
- [ ] Then perform inherited guarded main integration, fresh successor build/deployment, six routes/two sizes and final all-finding/whole-branch review gates. Task7 source completion alone does not close findings05/06/07.


### Task 9: Record the measured weather polling repair and qualified source authority
**Independent, user-priority defect after decoder compatibility recovery:** a 120.057546s one-packet miss plus changed 30s poll phase implied a 22.807259s Home unavailable window; pre-upgrade comparable October23 windows were about3.2s. Home uses stationQuality, while Bedroom/other receipt consumers use temperatureEvidence. This is a latency repair, preserving strict120-second freshness and all epochs/identity/permission gates.
**Source ownership:** `openhab/weather-station-v2-resources.json` exists ONLY in successor: change configuration.refresh30->2 for `http:url:weatherStationV2` there; do not recreate its historical disabled/createOnly preparation recipe in primary/Main. In BOTH primary and successor change `openhab/file-config/things/weather-temperature-evidence.things` ONLY refresh30->2. Add `docs/operations/2026-10-25-weather-polling-recovery.md`; update only qualified native source/release references in `docs/operations/thermal-model-graduation.md` from7b31/r3 to reviewed e5828bd4c5e4059032713f5d628fa097e0264d34/r5, retaining the explicitly dated10:13Z original selection/history rather than relabelling it.
- [ ] Read B/radio-residual-handoff-diagnosis.md and actual polling deployment receipt; preserve all other resource-manifest fields including createOnly:true and preparation enabled:false. Never reapply this whole create-only manifest to the ONLINE managed Thing; parent uses supported PUT config with captured complete map. Preserve READONLY sibling channels and temperature source URL.
- [ ] Make only the exact two polling source changes and concise operational docs; explain real RF expiry versus avoidable poll tail, both owner/config paths, strict120 unchanged, decoder/current-library isolation and guarded rollback. Record approximately403MiB/day station-quality serialized JSON input projection at2s, not claimed physicalPG/WAL/load-test result; leave persistence strategy unchanged. Preserve Bedroom relocation/history boundaries. No UI feature, held-value cache, actuator authority, TTL or numerical change.
- [ ] No new tests for these reversible low-impact settings/docs. Verify JSON parsing, exact semantic diff (onlyrefresh), exact Thing text diff, same shared Thing/docs payload in both trees; successor-only station manifest change and relevant existing configuration-contract check only if it covers these values. No full unchanged suites/build/heavy job. Source-only implementation does not qualify actual latency/browser behavior.
- [ ] Signed clean scoped commits in both trees, include primary parent Task9 plan amendment as-is, same-task report with all checks and exact hashes. Parent independently reviews, refreshes guarded integration/release pins and performs actual receiver+bothOpenHABsources+Home observation and inherited build/final gates. No Main/index/unit/private-data/live actions by worker.


### Task 10: Restore dense-history thermal source replay
Dependent subplan: /home/sat/earthship-ui/.worktrees/post-upgrade-runtime-20261024/docs/superpowers/plans/2026-10-26-native-temperature-source-density.md. Actual current rolling-day count8345/13,800,123rawbytes provesold8MiBsourcecontractexceeded whilenewshared24,000,000issueaggregate and10000rows fit. Oldreaders/basefit sources remainunchanged, newlosslesssharedsegmentedprofileexplicitlyqualified; independentcontinuousall-role replay andprivate/full/natural deploymentgates are mandatory. No parallel sourceimplementers.

### Task 11: Propagate the qualification phase request deadline
Dependent final-qualification repair after Task8's five-round breaker, not another Task8 cap-search round. Sourcefinding SDD/task-8-rereview-5.md is real/load-bearing: backend validation can submit the new stop at fake36s after30/35s bounds.
- [ ] Carry the request's absolute original budget from before phase context/lease/retired checks through all nested validation/read operations and the stop submission. No fresh budget after validation, arbitrary timeout wire field, new effect, cap change, operation authority or deadline increase.
- [ ] Bound each actual IO/manager operation by remaining time, recheck before effects, and preserve cleanup after expiry. Expired request context must not poison the independent original quiesce/seven-ID/v0/positive-absence/FDStore/barrier/count0 cleanup path; unknown states hold custody.
- [ ] Add the exact demonstrated fake-clock regression and slow/nested/prevalidation/IO/expiry-cleanup cases; retain all426 prior cases in both trees. Mirror source, signedclean commits, fresh6helperbundle, independently review this narrow delta.
- [ ] Only then perform applicable installedproof16/MQTT-only compatibility and post-retirement qualification guardian8SIGKILL/OFD/restart/terminal witness, followed by fresh uninterrupted original11Python+2actualbrowser/allcaps/zeroevents/source/private/production/volume/positivecleanup gates. Task8's resource-capacity evidence remains OPEN until these pass.
- [ ] Resume guarded Main/newUI/reader deployment, final6routes×2sizes/currentdata/systemstate and combined finalgoalreview. Source-only helper passes or a healthy fast run cannot close the structural deadline finding.


### Task 12: Move and enlarge the Home clock and date

User request2026-10-26: move the clock/date one row down, into the beginning of the load-and-energy display below it, and enlarge both for human visibility. Complete this UI tweak before resuming remaining repair implementation. The target is the Home Power Flow tile immediately below the fixed alert header. Keep a single live clock on Home, at the left of its existing power/daily-energy figures, with substantially larger time and date and readable contrast. Preserve existing local timezone, locale date and 12-hour minute display, live tick and teardown. Preserve header alerts, recommendation UI, connection lamp, all sensor/energy data and control behavior. Prefer retaining the current compact clock on other routes, where no Home power-flow row exists; Home alone moves it. Fit both1280x720 and1340x800 without clipping time/date or hiding energy figures; use responsive layout for narrow screens. No unrelated redesign.

Worktrees: primary /home/sat/earthship-ui/.worktrees/post-upgrade-repairs-20261024 BASE4f6ae0a2f5824493407a2ddd02363595e9159647 and successor /home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/ui-successor BASEfe9d7cfcb6af449ff508ef9a17ef47b7212cdb79. Existing Header.svelte includes successor-only recommendation UI; preserve it. Own smallest UI source set (Header, Home, optionally a reusable Clock component) in both and a short doc if useful. Preserve all unrelated files/indexes/private configuration. No Main edits or live changes by implementer. Signed scoped commits; no amend/push/reset. Full report in task-12-report.md, short return with commits/tests/concerns. No subagents.

This is a reversible presentation-only change: no new tests that merely mirror CSS or markup; use appropriate existing focused tests and actual browser/build checks. Heavy tests/builds ONLY with parent-granted window and original shared launcher/resource gates; ask parent for that window before running. Source implementation and static reads permitted now. Parent owns fresh release materialization, original split build and approved deployment/read-only visual checks. Do not invoke defensive-security scans or stress experiments; functional source review remains.
