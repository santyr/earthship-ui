# Verification evidence

Current final-candidate evidence is appended below. Earlier pending/failing statements are preserved chronological evidence and are superseded only by an explicit later result for the identified revision.
Audit base: `65ee7e95d58e6a6101700da3eccea67c9fea0ec7`. Initial remote CI [39434796248](https://github.com/santyr/earthship-ui/actions/runs/39434796248) failed OpenHAB shards 0/1; separate [thermal delivery](https://github.com/santyr/earthship-ui/actions/runs/39434796413) passed. Remote main and no open PRs verified at start. Local complete baseline not yet established.

Environments: host Node v24.13.0 / npm 11.17.0 (general CI requires Node 22); Python 3.12.3; Docker 29.8.0. Fresh `/tmp/earthship-audit-20261020-venv` uses requirements-test.txt. Companion source extracted at exact `24d2e8984810cb596fe9792768510a356786f709` into `.ci/solar-pv` (the live companion checkout differs and is untouched). `npm ci` ran only in isolated checkout. WeatherNext and sensor environments remain separate.

Normal bwrap command startup failed with `Failed RTM_NEWADDR: Operation not permitted`; approved escalated commands are used. Resource admission remains mandatory for substantial workloads. Logs stay outside public source; curated command/results will be recorded here. Counts from focused/repeated runs are not added as distinct tests.

## Geometry baseline isolation

The unlaunched synthetic-fixture reproduction finished exit 1: exactly the six handoff failures, 30 passed, 1.41s (`/tmp/earthship-audit-six-red.log`). Under the legitimate shared production-compatible launcher, 35 passed and a separate source-permission mismatch failed: native provenance correctly refused group-writable files from worktree creation. Tracked files in this disposable checkout alone were tightened with `mode & ~022`, matching CI provenance; no production permissions were changed.

The same three fixture files plus `openhab/scripts/test_household_cycle_resources.py` finished exit 0: **101 passed in 3.41s** (`/tmp/earthship-audit-geometry-green.log`). Only synthetic fixtures inject publication preflight; real cap/swap/IO/nice/headroom/thread rejection tests remain unchanged. Full shards remain pending.

## Night-load owners

`python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 96 --seconds 600 -- /usr/bin/env node_modules/.bin/vitest run tests/openhab/night-load-override-rule.test.js tests/openhab/night-load-recovery.test.js tests/openhab/request-ledger.test.js`

Original owner with new regressions: exit 1, 6 failed / 44 passed (`/tmp/earthship-audit-owner-red.log`). Repair plus byte-budget and conservative OFF regression: exit 0, **52 passed / 3 files** in 227ms (`/tmp/earthship-audit-owner-green.log`). Existing duplicate test changed its requestedAt; its expected reason is now the intentional explicit ID conflict, still zero commands. Normal matrices, independent goat camera, provider delay/restart-uncertain and feeder ledger suites remain covered. Final complete suite pending.

## Thermal interval regression

`python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 600 -- /usr/bin/env PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q openhab/scripts/test_thermal_interval_overlap.py openhab/scripts/test_thermal_weather_conditioning.py openhab/scripts/test_native_thermal_forecast.py openhab/scripts/test_household_native_weather.py`

The new interval file failed 5 and passed 6 cases against the original source (exit 1). The repaired four-file gate passed **68** (exit 0, 17.85s). Fixtures cover :00/:15 issues, rising/falling/unchanged radiation, zero/night transitions, whole-horizon conservation, raw/corrected native capture and frozen household replay. No site temperature-error claim follows from the constructed gradient.

## Current runtime readback

[runtime-start.json](runtime-start.json) contains authenticated GET-only source hashes/counts, not raw private records. At 14:44:44 UTC October 20: greywater and feeder source exactly match tracked source; night-load installed rule remains prior source; 84 Things / zero retired-provider matches; production sensor service online with **zero registered devices**. The apparent inactive daily training timer is superseded by active `thermal-native-six-hourly.timer` (natural next target 12:50 Denver), which runs `thermal-native-daily.service`. Current shared pool: 6 GiB maximum / 5 GiB high / no swap / 8 CPU equivalents / 256 tasks. These live limits were read, not imposed from historical notes.

## Frontend interim complete unit run

`python3 scripts/run-household-job.py --minimum-mib 768 --preferred-mib 1536 --tasks 96 --seconds 600 -- /usr/bin/env RAYON_NUM_THREADS=1 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 npm test -- --maxWorkers=1 --config /tmp/earthship-audit-frontend-vitest.config.mjs` finished exit0: **182files/2743tests passed**,50.97s. The temporary config permits source import only inside the .codex worktree during testing; production fs deny was unchanged. Standard-config Node22 final gate will run in `/tmp/earthship-audit-worker`. A build transformed853modules then the unchanged shared monitor deferred it; this is not a passing build.

## PV regression and retained reassessment

`python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 600 -- /usr/bin/env PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest openhab/scripts/test_pv_pair_baseline.py openhab/scripts/test_household_pv_model.py openhab/scripts/test_pv_legacy_history.py openhab/scripts/test_pv_local_days.py openhab/scripts/test_weather_pv_calibration.py openhab/scripts/test_weather_directional_pv.py openhab/scripts/test_pv_learning_refresh.py openhab/scripts/test_weather_pv_calibration_source.py openhab/scripts/test_pv_calibration_policy.py openhab/scripts/test_household_calibrated_energy.py -q` → exit0,**103passed**,5.49s.

Local-day red:7failed/3passed; shared-baseline red:7failed/2passed; subsequent old-dataset rejection and exact wind-unit regressions failed separately before repair. An all-PV glob run stopped after28cases with shared admission exit75; not counted as a completed suite.16complete served-projection dictionaries (1/24h,:00/:15,DST/terrain/night/missingwind/gradients) matched original serving implementation exactly.

The curated [original-data reassessment](pv-retained-reassessment.json) records verified hashes and aggregate counts only. Existing final training support29days and holdout5days remain unchanged. Rebuilt737pair baselines from55original Google snapshots and29native geometry series changed671pairs, meanabs5.836047893W/max59.088710966W. The original124pair/5day split yields raw/candidate MAE560.914930509/438.905995783W; corrected566.696925399/440.393837508W and still selected. This reuses the same development evidence/availability assumptions and does not qualify new prospective skill.

## Executable coverage inventory

The initial [test ownership map](test-ownership.json) assigns755candidate entry files to existing/main/specialist gates; this is source discovery, not an executed-test count. OpenHAB disjoint file partition at this point:145/137/152 (434files); operational100/completion26/Vitest182/general browser7 plus sensor and standalone families. Final inventory will include newly added coverage tests.

A09 initially failed six executable-gate checks. After repair, geometry discovers65cases/fivefiles; general browser71/sevenfiles; sensor2/onefile. The sensor command without `SENSOR_INTEGRATION=1` exits1 before server startup rather than skipping. QA two-test gate passes after reproducing an ineffective Set-membership assertion and stale HOME-SEASON ID.

Seven PostgreSQL modules were previously skipped at import because CI omitted pinned `analytics/tests` support. Supplying exact pinned fixture/migrations collects six cases and exposes a seventh module's reference to later companion APIs absent from the mandatory general pin. Its repair/explicit separate qualification profile remains in progress; the new executable collection guard is intentionally still failing, not weakened.

## Exact binary cryptographic qualification

Two admitted local commands ran `sudo -n unshare --net -- sh -c 'ip link set lo up; exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"' sh /tmp/earthship-audit-20261020-venv/bin/python scripts/qualify-thermal-{nak,delivery}.py --nak /home/sat/.local/bin/nak`, with512MiB/64tasks/300seconds bounds. Both exited0. Exact nak v0.20.7 SHA256 `ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e`. Authentication passed eight named checks; encrypted local-relay delivery passed eight named checks including NIP42, exact two-copy acceptance, authenticated reply and restart no-repost. No household keys, production journal writes or external network/message delivery. These are local cryptographic/software proofs, not household bunker/remote-relay/operator receipt qualification. Final-revision CI reruns remain pending.

## Dependency maintenance

Original `npm audit --json`:exit1,7package findings(3moderate/4high),27distinctadvisories. `npm audit fix --package-lock-only --ignore-scripts`:exit0; after lock audit exit0,zero vulnerabilities. Fifteen package entries update with no added/removed packages, range changes or package.json changes. New lock SHA25635c941310fa1036b091d40e2840db925233e36c0c9826ad39e26d436ef11774b. Fresh final npmci/unit/build/browser verification remains pending. This is dependency hygiene; static triage did not demonstrate an application exploit.

## Native PostgreSQL profiles

Six native modules passed against mandatory companion24d2e8984810cb596fe9792768510a356786f709 (18.86s). The actual JS→SQL→BMShealth/UI/sanity test needs later APIs absent from that pin; it passed separately against exact clean companion7b70117bcfb9599a12d0325771ed1103f083fa5c (5.33s). All7executed with0skips/failures and disposable containers removed. General dependency remains unchanged; profiles never mix imports in one interpreter. Full gate orchestration is being made explicit in CI.

Both used audit Python3.12.3/pytest9.1.1/psycopg2 2.9.13; BMS JS source ran Node24.13.0 in this focused run. Docker PostgreSQL16.14 imageID8a4b045886180c64f518ca6a4b0791b15fb997f3b3b619bd5ee141914668db55 / repository digest95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b. Test-driver shared admission was enforced; external Docker-daemon children do not inherit driver cgroup limits and the pinned disposable fixture has no container memory/CPU flags. Final hosted CI provides the matching wholly disposable worker. No production DSN/roles or data were used.

## Independent whole-branch review and repair

Fresh reviewer inspected65ee7e95..f03f6a9 and ran two bounded original-code reproductions. It found P1 accepted identity self-poisoning (A12) and P2 Astro statechanged-only ordering (A13), both repaired with normal-harness red→green tests. No further demonstrated blocker was found in the inspected numerical, ledger, policy, sensor, feeder-scope or browser-isolation changes. This is independent review, not proof that undiscovered defects cannot exist or deployment qualification.

A12 original regressions:2failed/31passed. Reject timestamp text over128characters before durable work and enforce the reader's512-character identity limit on admission. A13 original regression:1failed/10passed; snapshot evidence updates no longer mutate preserved Item state.

`python3 scripts/run-household-job.py --minimum-mib 768 --preferred-mib 1536 --tasks 96 --seconds 600 -- /usr/bin/env RAYON_NUM_THREADS=1 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 node_modules/.bin/vitest run --maxWorkers=1 tests/openhab/night-load-override-rule.test.js tests/openhab/night-load-recovery.test.js tests/openhab/request-ledger.test.js tests/openhab-reconciliation.test.js tests/store.test.js tests/alert-staleness.test.js tests/astro-presentation.test.js` → exit0,**119passed/7files**,1.18s. An earlier unbounded-worker attempt hit the unchanged task cap and exited1; it is not a passing result. The successful final command uses one test worker and bounded native thread fan-out.

## Clean standard Node22 frontend gate

Clean clone `/tmp/earthship-audit-worker` at **cb4f16bb10c9e397486dc7eef0f2e9ab9dc2b1bb**, Node22.22.0, lock refreshed by standard `npm ci` (exit0,zeroauditfindings). Under shared admission1024–2048MiB/128tasks/900seconds and RAYON_NUM_THREADS=1/GOMAXPROCS=2/UV_THREADPOOL_SIZE=2:

- `npm run test:unit -- --maxWorkers=1 --reporter=default --reporter=junit --outputFile=/tmp/earthship-audit-final-results/cb4f16bb10c9e397486dc7eef0f2e9ab9dc2b1bb/unit.xml` → exit0,**182files/2746tests passed**,52.14s. Standard repository config; no .codex adapter.
- `npm run build` → exit0,1.47s. Existing chunk-size warning retained; no build error.

These exact runtime/frontend bytes are committed. Subsequent CI-only orchestration/documentation changes still require final-revision hosted checks; no full-completion claim yet.

A09 profile runner checks pass11cases (2.86s), including execution of the actual maintained shard shell under success/general-failure/BMS-failure injection. Every discovered file executes exactly once under its declared profile. General24d2pin remains unchanged; only the current BMS consumer test uses7b70117 in a fresh process. Both statuses control the shard exit.

## Resumed workflow validation repair

The first draft-head CI run [39446247379](https://github.com/santyr/earthship-ui/actions/runs/39446247379) failed before creating jobs. Pinned actionlint1.7.7 reproduced `context "runner" is not allowed here` for job-level browser cache env. Moving the value to its two consuming steps preserves the exact temporary cache path and sudo propagation. All five workflows now compile with zero diagnostics. The normal completion regression also compiles a deliberately invalid job-context fixture and requires rejection.

Fresh resumed command at eb9d22d6 plus the two-file patch: shared launcher256–768MiB/64tasks/300seconds, PATH including `/tmp/earthship-actionlint/bin`, PYTHONPATH `openhab/scripts:.ci/solar-pv/analytics/src:.ci/solar-pv/analytics/tests`, audit Python `-m pytest -q tests/completion/test_verification_gates.py` → exit0, **11passed**,2.93s. This current count supersedes earlier verbal counts. Real production resource policy unchanged.

At resume, receipt-integrity, forecast-ML and thermal-delivery hosted runs at eb9d22d6 completed successfully; sensor contracts and eleven native integration cases passed, but two browser cases failed; main CI never started because of the validation defect. These are partial/interim results, not final integrated qualification.

## Browser execution and fixture corrections

Actual Chromium startup exhausted TasksMax128 because coordinator and worker each started about30Rolldown native workers. Keep existing caps and use `ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2` alongside RAYON1/GOMAX2/UV2. Default headless shell then executed real assertions; CPU affinity alone had not fixed startup.

At d549886d plus the exact8-file layout/fixture patch, standard Node22.22.0 and isolated loopback namespace: `npm run test:e2e -- --workers=1` → **71passed**,exit0,1.3min; `npm run test:geometry -- --workers=1` → **65passed**,exit0,1.2min. These overlap and are never summed. Both use launcher1024–2048MiB/128tasks/600seconds, private browser cache, `env -u NODE_OPTIONS` and the bounded thread settings. Full commands/logs are retained privately under `/tmp/earthship-audit-browser-{full,geometry}-repaired.log`.

Negative control: in-memory2000pxControls overflow made the maintained m9 case fail at controls-layout.spec.js172 (`scrollWidth2021 > clientWidth1280`),exit1. Injection was removed; both complete maintained suites passed afterward. Existing page-error/unexpected-mutation guards remain active. Fourteen initial browser failures split into actual A14–A16 layout defects and outdated exact fixture selectors/labels or absent optional-report/Thing responses; no safety/readiness or geometry assertion was weakened.

Sensor fixture rootcause: anonymous disposableOpenHAB5.2.1 /rest/items200 versus /rest/things401; reconciled store truthfully withheld readiness. New opt-in simulation-only auth bootstrap puts a private test token only in server-side Viteproxy. Native browser red2failed; green2passed6.9s, both viewports. Auth guards3passed; contracts69passed/11explicit opt-in integration skips in focused environment. Full11native integrations plus2browser must still pass on the final hosted source. Owned local containers/volumes/tokenstage were removed; preexisting test volumes and production18085 listener untouched.

Hosted actionlint at d549886d found two pre-existing ShellCheckSC2155 warnings masked locally by absentShellCheck. Separate UID/GID assignments from export; do not disable the compiler. PinnedShellCheck0.9.0 was extracted in /tmp (no host install). Actionlint1.7.7 with ShellCheck present plus auth/gate regressions → **14passed**,2.94s,exit0.

## Measured-target fitting/support repair (C04)

Native source regression showed directional24targets represented by24/48distinct forecast rows changed gain0.9→0.8666667 without a new measurement. Nine failing kernel cases additionally covered scalar/weather/ridge/typed bias weighting and conflicting target truth. New fitting gives each measured target unit mass spread across its original forecasts; ridge preprocessing/intercept/Gram/RHS and prior mass all use those weights. Support separately records pairs, unique measured targets, Denver dates and explicitly unestimated dependence. Temporal blocks remain null until empirical reassessment.

PV models/reports become v3; site/weather/typed models become v2. Original v1/v2 coefficient interpretation remains readable; unchanged old-schema candidates cannot silently no-op into new training. New weighting sources are required by selected-model runtime bindings. Parent-added actual temperature/wind selection regressions failed2cases when weights.py was omitted, then passed together with the kernel and actual historical predictor: **35passed**,0.35s,exit0. Agent final stable C04 subset passed112cases/0skips plus11subtests8.10s; broader earlier516/17skips was numerical dependency evidence only (missing optional native dependencies), not final release qualification. Typed equivalent-offset target support also had its own red→green case before kernel freeze. No installed model or original dataset/receipt was altered.


## Consolidated evaluation integration (source candidate)

C01/C02/C03 now use a private durable maturity queue, immutable versioned score records, matched/fallback populations and separately retained procedure/artifact provenance. Seven-day reporting is target-based; actual336-hour targets survive issue lookback. Queue discovery and unknown unindexed originals are explicit. Existing wind and native conditioned-proxy diagnostics run under the same monitor deadline/work budget. Optional paths cannot suppress valid temperature scores. A production adapter defect (budgeted database factory called without `remaining`) was repaired rather than weakening reader checks.

Maintained pinned WeatherNext environment: `python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 600 -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=openhab/scripts:openhab/scripts/weather_learning/tests /tmp/earthship-audit-weather-venv/bin/python -m unittest discover -s openhab/scripts/weather_learning/tests` → **290 tests passed, 32.490s, exit0**. This suite performs no cloud access. Focused integrated monitor/correction/wind/conditioning/serving/worker group → **56 passed, 8.80s, exit0**. Paired metrics/provenance/reassessment/worker group → **24 passed plus2subtests, 1.73s, exit0**. Queue coverage group → **28 passed, 14.997s, exit0**. These overlapping focused counts must not be summed as distinct tests.

New numerical source permissions were tightened only in the isolated checkout after the unchanged runtime guard refused a group-writable new weights module. Source closure now explicitly retains `weather_learning/weights.py`; no production admission or resource bypass was added. Complete integrated final-revision workflow results remain pending.


## Independent consolidated review and repair pass

Independent whole-branch review of `df742cd2f796a33b81824146f735feba2bd94c95` found two P2 correction-monitor failures: missing original model objects stalled unrelated work, and late-arriving outcomes escaped the seven-day allowance. Actual solar transport exceptions were also outside the handler. Native regressions reproduced all cases before repair. The repair adds durable per-original retry/dependency records, continued independent work, explicit transport handling and exact availability bounds; guards still propagate deadlines. Procedure/horizon/month/regime coverage was completed under correction evaluationv2 with unknown legacy policy provenance preserved. Additional native regressions cover durable score tampering, bounded detail and full64-label accounting. Final focused correction/wind/monitor/worker group: **55 passed,11.48s,exit0**.

Clean Node22.22.0 checkout at `df742cd`: `npm ci` →156packages installed,0audit vulnerabilities,exit0. Initial default-worker run terminated with exit241 before results under the disposable resource cap; it is not a passing suite. Bounded retry `npm run test:unit -- --maxWorkers=1` → **182files/2746tests passed,50.77s,exit0**; `npm run build` →exit0,1.49s, existing large-chunk warning. Shared launcher1024–2048MiB/128tasks/no-swap, native thread caps preserved. No frontend source changed in the subsequent correction-only review fixes. Hosted final revision results remain pending.


## Final boundary and geometry checks after review fixes

At `e6b4997`, pinned foundation suite completed **291tests,37.495s,exit0**. Standard Node22 Chromium `npm run test:geometry -- --workers=1` completed **65tests,1.2min,exit0** in a network namespace with loopback only, using1024–2048MiB/128tasks and native thread caps. General71-case browser and sensor11-container/2-browser suites completed successfully on hosted `df742cd`; final source reruns remain required. These browser families overlap; no sum is presented as distinct tests.

Real resource smoke under shared approved256–512MiB/64task/300second leaf, `EARTHSHIP_RESOURCE_SMOKE=1` and one numerical thread: `python -m pytest -q -ra openhab/scripts/test_native_resource_admission.py openhab/scripts/test_weather_receiver_characterization.py` →4passed/5skipped,0.48s,exit0. Five receiver skips name missing `flask_cors` in the general test venv. The existing host Python environment supplies Flask-Cors4.0.0: isolated `python -m pytest -q -ra openhab/scripts/test_weather_receiver_characterization.py` →**5passed,0.18s,exit0**. That characterization asserts known legacy source limitations with all network/state writes stubbed; it does not qualify legacy retained values as fresh measurements. General hosted receiver skips additionally name the absent host-only source; SDK skips are covered by the separate pinned foundation environment; native resource smoke is explicitly opt-in because it requires a real admitted scope. Final CI now emits full skip summaries through `PYTEST_ADDOPTS=-ra`.

Read-only final source/deployment projection: [runtime-final.json](runtime-final.json),16:45UTC; protected sensor counts read16:46UTC. No production mutation.


## Horizon/older-history PV completion

An additional source sweep reproduced a remaining next-hour arithmetic path in the horizon assessor. Native numeric regressions failed7cases/2passed before repair; final affected suite147passed/0skips/1.38s,exit0,Python3.12.3/pytest9.1.1. Exact admitted command:

```bash
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 600 -- /usr/bin/env OPENBLAS_NUM_THREADS=1 PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q openhab/scripts/test_pv_horizon_pair_baseline.py openhab/scripts/test_pv_pair_baseline.py openhab/scripts/test_pv_horizon_assessment.py openhab/scripts/test_pv_calibration_policy.py openhab/scripts/test_weather_pv_calibration.py openhab/scripts/test_weather_directional_pv.py openhab/scripts/test_target_weighting.py openhab/scripts/test_pv_learning_refresh.py openhab/scripts/test_pv_local_days.py openhab/scripts/test_pv_legacy_history.py openhab/scripts/test_household_pv_model.py openhab/scripts/test_weather_pv_calibration_source.py
```

The shared calibration/horizon datasets now require explicitv2 baseline identity; oldv1 originals stay original-only. Exact retained-source horizon/legacy reconstruction and discontinuity metrics are in qualification/model-reassessment. All131retained original files checked unchanged; no selected pointer or production source changed.


Future-original boundary: a source completed in the future initially blocked later indexed mature work (`states={}` versus expectedcompleted1). New native regression failed before the fix; durable not-yet-available intake retry/cursor progression preserves the future original and lets independent work complete. Full affected correction/wind/monitor/worker group **56passed,11.68s,exit0**. Test ownership now maps766entry files plus explicit standalone crypto gates, with per-test-file SHA256 and no orphan. Final integrated source gates still required.


At final source `96247d26494c553e7debba065a0263d6b9fcae97`, the advertised geometry gate completed65tests/1.2min/exit0. Existing isolated user-systemd retry fixture `EARTHSHIP_ISOLATED_SYSTEMD_TEST=1 python -m pytest -q -ra scripts/test_thermal_shadow_retry.py --junitxml=/tmp/earthship-audit-final-systemd.xml` completed **3passed,28.70s,exit0**, with only UUID-scoped transient counter workers and cleanup verified by the fixture; no household callback or credential was used. The general CI's three intentional systemd skips are covered by this separate native profile.


## Final skip-accounting repair — A18

All five required workflows finished successfully at96247d26494c553e7debba065a0263d6b9fcae97, including three OpenHAB shards. Final skip review nevertheless found the explicitly enabled ML qualification fit silently skipped. Source-order reconstruction from all1415 progress markers and matching collection identifies `test_thermal_fit_evidence.py::test_real_qualification_fit_is_exercised_only_on_the_hosted_runner`. Registered scorer CLI fixtures leaked the standalone scorer's intentional fit-disable environment. New normal completion regression runs all11 registered cases then an enabled-fit sentinel: before fix1failed/11passed internally and parent1failed; after fixture-only restoration the complete verification-gate/registered-scorer group passed23/12.44s/exit0. Production scorer policy unchanged.

Command: `python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 300 -- /usr/bin/env PATH=/tmp/earthship-actionlint/bin:/tmp/earthship-shellcheck/usr/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src:.ci/solar-pv/analytics/tests /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra tests/completion/test_verification_gates.py openhab/scripts/test_installed_registered_score_cli.py`. Final integrated workflows are rerun for this test-isolation repair;96247 is not the final source claim.


A18 follow-up:494213c's five workflows finished green, but its full ML progress still showed1414passed/one skipped; this is **not** a passing full-fit qualification result. Full caller inspection found additional queue, release-index and busy-lock CLI tests leaking the same standalone scorer environment. A source-derived subprocess regression now discovers every actual in-process scorer CLI caller: original1failed/22passed, complete affected fixture repair109passed/23.95s/exit0. The fixture-only fix preserves production policy.

The heavyweight synthetic fit now has a separate `qualification-fit` job in the maintained forecast workflow. The general1414-case ML partition explicitly deselects that one case; the dedicated job runs it once with the existing explicit opt-in and checks JUnit for exactly the expected executed case, zero skips/failures/errors. Its normal completion regression executes the actual shell with passed, skipped and absent receipts; only passed succeeds. Pinned actionlint1.7.7 with ShellCheck0.9.0 is included in109passing affected checks. No production deadline, resource limit or opt-in was weakened. Final source gates will identify both disjoint ML profiles.


6ecd37f dedicated full-fit job executed its actual case successfully (`1passed/7.16s`, zero skips). General test job exposed a strict legacy workflow-argument check treating the new `--deselect` argument as a file. Local existing regression reproduced1failure; repair requires that exact exclusion, validates every remaining file, and retains the whole thermal-fit module in the general partition. Focused1test passed/exit0; full operational and final source gates are being completed. This is a test contract update, not a production behavior change.


## Final integrated source verification

All required software gates completed successfully at **`8f6e9183b3cba1cdaa1310102f000e7a2db65bb2`**. This section supersedes earlier pending execution statements and the earlier simple PV development comparison; the full source-bound cohort/selection account is in qualification.md/model-reassessment.json. [Hosted index](ci-final.json) retains complete workflow commands and environments, job links, exit codes, exact counts, full named skip reasons and runtime versions. [Native index](native-final.json) binds JUnit/command-log hashes and disjoint completion partitions. [Test ownership](test-ownership.json) assigns766 entry files, with per-file SHA256 and zero orphans; file discovery is not counted as executed cases. No total is formed by adding overlapping specialist suites or subtests.

| Required workflow | Immutable run | Result |
|---|---|---|
| Household receipt integrity | [39468560541](https://github.com/santyr/earthship-ui/actions/runs/39468560541) | completed success; every job success/exit0 |
| Thermal delivery qualification | [39468560560](https://github.com/santyr/earthship-ui/actions/runs/39468560560) | completed success; every job success/exit0 |
| Distributed sensor qualification | [39468560594](https://github.com/santyr/earthship-ui/actions/runs/39468560594) | completed success; every job success/exit0 |
| Forecast ML hardening | [39468560589](https://github.com/santyr/earthship-ui/actions/runs/39468560589) | completed success; every job success/exit0 |
| CI | [39468560841](https://github.com/santyr/earthship-ui/actions/runs/39468560841) | completed success; every job success/exit0 |

| Gate/profile | Completed evidence |
|---|---|
| [receipt-integrity](https://github.com/santyr/earthship-ui/actions/runs/39468560541/job/118786282640) | 526 passed in 308.85s (0:05:08) |
| [encrypted-delivery](https://github.com/santyr/earthship-ui/actions/runs/39468560560/job/118786283237) | 8 named checks passed |
| [software-path](https://github.com/santyr/earthship-ui/actions/runs/39468560594/job/118786284285) | ============================= 11 passed in 55.47s ==============================; 2 passed (8.8s) |
| [contracts](https://github.com/santyr/earthship-ui/actions/runs/39468560594/job/118786284614) | ======================== 69 passed, 11 skipped in 0.90s ======================== |
| [forecast-ml](https://github.com/santyr/earthship-ui/actions/runs/39468560589/job/118786283469) | 1414 passed, 1 deselected in 973.13s (0:16:13) |
| [qualification-fit](https://github.com/santyr/earthship-ui/actions/runs/39468560589/job/118786284136) | 1 passed in 10.45s |
| [weathernext-foundation](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786284596) | Ran 291 tests in 38.562s |
| [nak-authentication](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786284844) | 8 named checks passed |
| [test](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786285033) | Test Files  182 passed (182); Tests  2746 passed (2746); 557 passed, 101 skipped in 17.80s; 1396 passed, 3 skipped in 150.13s (0:02:30) |
| [OpenHAB tests (1/3)](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786285035) | 2059 passed, 5 skipped, 103 subtests passed in 1048.92s (0:17:28); general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [browser-fixtures](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786285080) | 71 passed (1.5m) |
| [OpenHAB tests (0/3)](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786285111) | 2143 passed, 8 skipped, 68 subtests passed in 827.11s (0:13:47); general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [OpenHAB tests (2/3)](https://github.com/santyr/earthship-ui/actions/runs/39468560841/job/118786285262) | 2304 passed, 7 skipped, 69 subtests passed in 1145.45s (0:19:05); 1 passed in 1.90s; general_pytest_exit=0 bms_aux_pytest_exit=0 |

The real synthetic hosted qualification fit **executed**: all1415 ML cases passed across disjoint1414-case regression and one-case dedicated fit jobs, zero skips, including `test_real_qualification_fit_is_exercised_only_on_the_hosted_runner`. A green workflow alone was insufficient before A18. Dedicated current-source test/CI and independent review verify the fixture repair without changing standalone fit-disable or resource guards.

GitHub pull-request jobs use a synthetic merge checkout; ci-final.json records its actual commit/parents and verifies its entire tracked Git tree equals the named PR source revision. Local native checks execute the PR revision directly.

Hosted general environment: Ubuntu24.04, Python3.12.15/pytest9.1.1, Node22.23.3/npm10.9.9. Sensor profile: Python3.12.15/pytest8.3.5, Node24.21.0/npm11.19.0 and its separate pinned dependencies. General companion24d2e8984810cb596fe9792768510a356786f709; BMS consumer alone7b70117bcfb9599a12d0325771ed1103f083fa5c in a separate interpreter. Pinned WeatherNext dependencies remain separate and perform no cloud access. Local native Python3.12.3/pytest9.1.1; receiver-only existing system pytest9.0.2/Flask-Cors4.0.0. Chromium geometry uses Node22.22.0/npm11.8.0, Playwright1.61.1; source lock uses Vitest4.1.12/Vite8.1.5/Svelte5.56.6. Build's existing chunk-size warning and runner action deprecation notices do not indicate test failures.

Expected hosted skips:101 completion executions need exact stock/stdin binary pins and are executed in the658-case native completion partition; three operational skips require isolated user-systemd and are executed locally; the sensor contract job excludes its11 Docker integrations, all executed in its software-path job plus two browser cases. Generic OpenHAB skips cover the separate real resource leaf, host-only receiver source, pinned EE SDK and dedicated hosted fit. Imported receiver tests repeat across partitions; these are execution counts, not14 independent measurement contracts. Every named reason is in ci-final.json. None of these software skips is counted as radio, metrology, cloud connectivity or household operator qualification.

Final native commands use the approved launcher, unchanged no-swap/headroom guards and disposable state:

```bash
# Full exact-binary completion partition, loopback only. Three PostgreSQL cases below are explicitly deselected here.
python3 scripts/run-household-job.py --minimum-mib 512 --preferred-mib 1024 --tasks 96 --seconds 600 -- /usr/bin/sudo -n /usr/bin/unshare --net -- /bin/sh -c '/usr/sbin/ip link set lo up; exec /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups /usr/bin/env PATH=/tmp/earthship-actionlint/bin:/tmp/earthship-shellcheck/usr/bin:/usr/local/bin:/usr/bin:/bin EARTHSHIP_TEST_NAK=/home/sat/.local/libexec/earthship-thermal/nak-v0.20.7-earthship-nip04-stdin.1 EARTHSHIP_TEST_NAK_SHA256=2620c86f7a2b466a41977ae7e318d1810c727503deaf53ea1c76a5ac24e6f927 PYTHONPATH=/home/sat/.codex/worktrees/d4ee/earthship-ui/openhab/scripts:/home/sat/.codex/worktrees/d4ee/earthship-ui/.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra tests/completion/ --deselect=tests/completion/test_thermal_nip04_ledger.py::test_default_sink_preflight_then_reply_stores_real_v2_action --deselect=tests/completion/test_thermal_nip04_ledger.py::test_real_v2_journal_recovers_commit_before_ack_and_preserves_original_cipher --deselect=tests/completion/test_thermal_primal_backup.py::test_full_primal_bundle_restores_real_v2_journal_and_durable_delivery --junitxml=/tmp/earthship-audit-final-8f6e-completion-isolated.xml'

# Complementary original Docker fixtures; random host-loopback ports, synthetic keys, no relay delivery.
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 300 -- /usr/bin/env PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra tests/completion/test_thermal_nip04_ledger.py::test_default_sink_preflight_then_reply_stores_real_v2_action tests/completion/test_thermal_nip04_ledger.py::test_real_v2_journal_recovers_commit_before_ack_and_preserves_original_cipher tests/completion/test_thermal_primal_backup.py::test_full_primal_bundle_restores_real_v2_journal_and_durable_delivery --junitxml=/tmp/earthship-audit-final-8f6e-completion-pg.xml

python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 64 --seconds 300 -- /usr/bin/env EARTHSHIP_ISOLATED_SYSTEMD_TEST=1 EARTHSHIP_RESOURCE_SMOKE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra scripts/test_thermal_shadow_retry.py openhab/scripts/test_native_resource_admission.py openhab/scripts/test_score_production_cpu.py --junitxml=/tmp/earthship-audit-final-8f6e-host.xml

python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 64 --seconds 300 -- /usr/bin/env PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /usr/bin/python3 -m pytest -q -ra openhab/scripts/test_weather_receiver_characterization.py --junitxml=/tmp/earthship-audit-final-8f6e-receiver.xml

# CWD=/tmp/earthship-audit-final-worker, clean matching source; actual maintained sudo namespace identity.
python3 scripts/run-household-job.py --minimum-mib 1024 --preferred-mib 2048 --tasks 128 --seconds 600 -- /usr/bin/sudo -n /usr/bin/unshare --net -- /bin/sh -c '/usr/sbin/ip link set lo up; exec /usr/bin/env -u NODE_OPTIONS PATH=/tmp/earthship-audit-node22/package/bin:/usr/local/bin:/usr/bin:/bin PLAYWRIGHT_BROWSERS_PATH=/home/sat/.cache/ms-playwright RAYON_NUM_THREADS=1 ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 /tmp/earthship-audit-node22/package/bin/node /usr/local/bin/npm run test:geometry -- --workers=1 --output=/tmp/earthship-audit-8f6e-geometry-ci-user-results'
```

Native results are recorded exactly in native-final.json:655-case isolated completion partition plus complementary3cases (disjoint658 total, zero skipped);19resource/systemd cases; five isolated receiver cases; geometry65passed/1.2min. All exit0; exact summaries and hashes are in native-final.json. Docker-daemon children have the preexisting fixture isolation described above and do not inherit the driver's cgroup; no claim otherwise.

The final local operational suite also passed1396cases/three explicit systemd skips in117.85s at8f6e9183. Its first local attempt had15Docker fixture errors because PATH omitted the existing /snap/bin executable; adding that declared host path restored all disposable cases. No application/test guard was changed for that environment issue.

Initial native completion trial had1failure/652passes/three errors because actionlint was missing from namespace PATH and host-daemon PostgreSQL was unreachable from its distinct loopback. Correct pinned PATH plus explicit native partitions resolved the environment boundary without production/test validation bypass. Local geometry setup also initially used a nonexistent npm bundle path, then encountered root-owned generated cache/results from the prior run; only this disposable cache ownership/output path was corrected. Two exploratory unprivileged-user runs each passed64cases and timed out in different tests (reload or transient history). Their cause remains unproven; they were not reproduced in the maintained root/sudo namespace profile or hosted71-case run. No assertion/timeout was relaxed and no speculative product patch was made. An interrupted10-assertion diagnostic exited130 and is not a completed gate.

Genuine retained household replay: [curated original proof](retained-pipeline-proof.json), identity188cf1d4e6d8629b12835fed837ba5816d3a9cb6f6185cb59be536ece5852961. Actual snapshot/models/plan/public/admission match under their original3f5d8cb producer;353source files/68runtime entries unchanged. Shared development admission256MiB/swap0/24tasks/Nice15/CPUWeight25, parent8CPU quota; leaf has no separate fixed quota. Complete replay3.530s/exit0; no socket connected/bound and translator refused. Original-package replay does not qualify changed numerics or physical effects; new-source fixture/model parity and original-data counterfactuals are separate evidence.

Independent whole-branch review and focused follow-up reviewed correctness, numerical identities, authority and evidence honesty. A12/A13/C08/C09 and coverage gaps were fixed with regressions; final A18 review found no further important/critical issue. Reviewers did not reproduce all private numerical originals, broad final CI or physical hardware; this record does not claim otherwise. The complete available software scope is verified; installation, future outcomes, old missing provenance, radio commissioning and physical metrology remain the exact dependencies in release.md. No proof against undiscovered bugs is asserted.


## Approved deployment repair — final source gate

This supplement extends the original source/native evidence without replacing it. Exact source repair revision: **`1f23c674d03f7eb4b4100b72e2b094a4733cdc13`**. [Deployment source freeze](deployment-source-freeze.json) binds1717non-documentation files, unchanged workflow hashes and767test-entry files. A19 adds9normal shard0cases; the original766-file evidence remains historical. [Deployment CI](deployment-ci.json) records every command, environment, complete result, named skip and actual checkout/tree proof. Per-job counts overlap; no inflated repository-wide total is inferred.

| Workflow | Run | Result |
|---|---|---|
| Distributed sensor qualification | [39481010472](https://github.com/santyr/earthship-ui/actions/runs/39481010472) | completed success; all jobs success/exit0 |
| Household receipt integrity | [39481010562](https://github.com/santyr/earthship-ui/actions/runs/39481010562) | completed success; all jobs success/exit0 |
| Thermal delivery qualification | [39481010614](https://github.com/santyr/earthship-ui/actions/runs/39481010614) | completed success; all jobs success/exit0 |
| Forecast ML hardening | [39481010636](https://github.com/santyr/earthship-ui/actions/runs/39481010636) | completed success; all jobs success/exit0 |
| CI | [39481010480](https://github.com/santyr/earthship-ui/actions/runs/39481010480) | completed success; all jobs success/exit0 |

| Gate | Exact completed summary |
|---|---|
| [contracts](https://github.com/santyr/earthship-ui/actions/runs/39481010472/job/118829258820) | ======================== 69 passed, 11 skipped in 0.91s ======================== |
| [software-path](https://github.com/santyr/earthship-ui/actions/runs/39481010472/job/118829259276) | ======================== 11 passed in 66.86s (0:01:06) =========================; 2 passed (16.1s) |
| [receipt-integrity](https://github.com/santyr/earthship-ui/actions/runs/39481010562/job/118829259150) | 526 passed in 258.50s (0:04:18) |
| [encrypted-delivery](https://github.com/santyr/earthship-ui/actions/runs/39481010614/job/118829258496) | 8named checks passed |
| [forecast-ml](https://github.com/santyr/earthship-ui/actions/runs/39481010636/job/118829258654) | 1414 passed, 1 deselected in 996.02s (0:16:36) |
| [qualification-fit](https://github.com/santyr/earthship-ui/actions/runs/39481010636/job/118829259272) | 1 passed in 8.39s |
| [browser-fixtures](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259074) | 71 passed (1.5m) |
| [test](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259260) | Test Files  182 passed (182); Tests  2746 passed (2746); 557 passed, 101 skipped in 14.09s; 1396 passed, 3 skipped in 103.74s (0:01:43) |
| [OpenHAB tests (1/3)](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259369) | 2059 passed, 5 skipped, 103 subtests passed in 1034.97s (0:17:14); general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [OpenHAB tests (0/3)](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259403) | 2152 passed, 8 skipped, 68 subtests passed in 643.59s (0:10:43); general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [weathernext-foundation](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259516) | Ran 291 tests in 61.388s |
| [OpenHAB tests (2/3)](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259584) | 2304 passed, 7 skipped, 69 subtests passed in 1158.81s (0:19:18); 1 passed in 1.79s; general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [nak-authentication](https://github.com/santyr/earthship-ui/actions/runs/39481010480/job/118829259676) | 8named checks passed |

The source gate includes all three OpenHAB partitions, general browser fixtures, sensor contracts plus actual disposable software/browser path, pinned no-cloud WeatherNext contracts, dedicated hosted qualification fit, receipt integrity and exact-binary delivery/authentication. Named opt-in hosted skips remain separate from native executions below; no radio/cloud/physical qualification is implied.

A19 local evidence: original cold-cache regression failed1case/0.37s/exit1; the same case then passed1/0.34s. Expanded9controller +28preparer cases passed37/0.54s; related13module gate passed143/56.95s/exit0. No dedicated stdout/JUnit file was created for those focused runs; their captured tool output and curated private execution note are the evidence. Exact related command:

```bash
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$PWD/openhab/scripts:/home/sat/Solar_PV/analytics/src" /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 24 --seconds 300 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest openhab/scripts/test_household_native_activation.py openhab/scripts/test_household_native_daily.py openhab/scripts/test_household_native_geometry_prepare.py openhab/scripts/test_native_serving_preparer.py openhab/scripts/test_native_serving_geometry.py openhab/scripts/test_household_native_handoff.py openhab/scripts/test_native_serving_handoff.py openhab/scripts/test_native_serving_upgrade.py openhab/scripts/test_household_native_install_composition.py openhab/scripts/test_household_native_install_lifecycle.py openhab/scripts/test_household_native_install_files.py openhab/scripts/test_household_native_preparer_enable.py openhab/scripts/test_household_native_family.py -q
```

The focused command uses the same environment/launcher with120seconds and only activation/native_serving_preparer/household_native_geometry_prepare modules. RED/singleGREEN use activation only. Host Python3.12.3/pytest9.1.1; live companion7b70117. Hosted general/BMS companion profiles remain separate as declared by the workflow.

[Approved deployment](deployment.md), [fixed-route runtime readback](deployment-runtime.json), [original new-stage household replay](deployment-pipeline-proof.json) and [actual new calibrated receipt replay](deployment-calibrated-proof.json) distinguish installed source, natural execution, exact original replay and physical/statistical qualification. Independent review approved A19 and required precondition/rollback improvements to the separate deployment helper; six disposable helper fault-injection tests passed. No new actuator or score identity is inferred from these source-only helper tests.


Fresh final-code native executions completed at1f23c67:655isolated completion cases (164.85s) plus3disjoint disposable PostgreSQL cases (23.94s),19opted-in host resource/systemd cases (29.63s),5isolated receiver characterizations (0.18s),65advertised geometry cases (1.2min), all exit0/zero skipped. [deployment-native.json](deployment-native.json) retains JUnit/test-ID/log hashes and exact profile boundaries. Commands are the full native commands above with new output prefix `/tmp/earthship-audit-deployment-1f23-`; the PostgreSQL command additionally declares existingDocker PATH `/snap/bin:/usr/local/bin:/usr/bin:/bin`. Geometry runs the exact1f23archive outside .codex with matching lock dependencies and its separate result directory. The original native-final.json remains unchanged.

PR37 merge `bef677e1f9a8fe353f9b0c504ba19c48a1cc0c7a` and tested1f23c67 both have Git tree `2bb494491aceeacc551b0e6a08bc928a60b00423`. The actual new controller reader then verified the unchanged18:00Zmodel/deployment under production admission; only its exact source override changed. Installed/readback source is separate from the future18:50automatic model-handoff observation.


## Final scheduled-learning repair and fixture isolation

Exact final code: `444d7e9550a742d9662cc9bd85a68d4c5dafb8c1`, merged as `0b3f6fc0a5ec0e86cd4af65604241d9532b2f1ad`. This supersedes the earlier final-source labels only for current verification; all historical results are retained. [Source freeze](deployment-a20-source-freeze.json) binds all 1717 non-documentation files, unchanged workflow hashes and 767 discovered test-entry files with zero orphans. [Hosted evidence](deployment-a20-ci.json) includes full commands/environments, actual PR merge-checkout tree equivalence, runtime versions, job links, exits and named skips.

| Workflow | Immutable run | Result |
|---|---|---|
| Thermal delivery qualification | [39489200788](https://github.com/santyr/earthship-ui/actions/runs/39489200788) | completed success; all jobs exit 0 |
| Distributed sensor qualification | [39489200724](https://github.com/santyr/earthship-ui/actions/runs/39489200724) | completed success; all jobs exit 0 |
| Forecast ML hardening | [39489200725](https://github.com/santyr/earthship-ui/actions/runs/39489200725) | completed success; all jobs exit 0 |
| Household receipt integrity | [39489200754](https://github.com/santyr/earthship-ui/actions/runs/39489200754) | completed success; all jobs exit 0 |
| CI | [39489200744](https://github.com/santyr/earthship-ui/actions/runs/39489200744) | completed success; all jobs exit 0 |

| Gate | Completed summary |
|---|---|
| [encrypted-delivery](https://github.com/santyr/earthship-ui/actions/runs/39489200788/job/118857492122) | 8 named checks passed |
| [contracts](https://github.com/santyr/earthship-ui/actions/runs/39489200724/job/118857491317) | ======================== 69 passed, 11 skipped in 1.23s ======================== |
| [software-path](https://github.com/santyr/earthship-ui/actions/runs/39489200724/job/118857491715) | ======================== 11 passed in 82.72s (0:01:22) =========================; 2 passed (12.2s) |
| [qualification-fit](https://github.com/santyr/earthship-ui/actions/runs/39489200725/job/118857491863) | 1 passed in 9.00s |
| [forecast-ml](https://github.com/santyr/earthship-ui/actions/runs/39489200725/job/118857492156) | 1414 passed, 1 deselected in 763.91s (0:12:43) |
| [receipt-integrity](https://github.com/santyr/earthship-ui/actions/runs/39489200754/job/118857491396) | 526 passed in 252.82s (0:04:12) |
| [browser-fixtures](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857491613) | 71 passed (1.4m) |
| [nak-authentication](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857491880) | 8 named checks passed |
| [OpenHAB tests (2/3)](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857491891) | 2304 passed, 7 skipped, 69 subtests passed in 1165.86s (0:19:25); 1 passed in 1.91s; general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [OpenHAB tests (0/3)](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857492026) | 2162 passed, 8 skipped, 68 subtests passed in 854.47s (0:14:14); general_pytest_exit=0 bms_aux_pytest_exit=0 |
| [test](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857492059) | Test Files  182 passed (182); Tests  2746 passed (2746); 558 passed, 101 skipped in 15.80s; 1396 passed, 3 skipped in 107.22s (0:01:47) |
| [weathernext-foundation](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857492077) | Ran 291 tests in 65.871s |
| [OpenHAB tests (1/3)](https://github.com/santyr/earthship-ui/actions/runs/39489200744/job/118857492225) | 2059 passed, 5 skipped, 103 subtests passed in 1051.11s (0:17:31); general_pytest_exit=0 bms_aux_pytest_exit=0 |

Counts are per gate. Specialist, imported and native tests overlap and are never summed into a distinct repository total. The ML regression partition explicitly deselects the one real hosted qualification fit; its dedicated job executes that case with zero skips. Sensor contracts intentionally omit 11 container cases, all executed by software-path alongside two browser cases. Completion binary-pin and operational systemd skips are explicitly covered by the native profiles below. Other OpenHAB skips name real host-only receiver/SDK/resource dependencies in the linked job index. These tests establish neither actual Google availability nor radio, household operator receipt or physical metrology.

A20 RED: seven retention regressions failed before implementation (exit 1, 0.24s); final affected PV gate passed 87 cases with no skips (exit 0, 1.02s). A21 first full candidate `6a4ab8f1c6e251bc3ca5901fd40902307620f628` failed [CI39486153706 shard0](https://github.com/santyr/earthship-ui/actions/runs/39486153706/job/118846969785): one privacy assertion failed, 2161 passed, eight skipped and 68 subtests. Two in-process PV CLI cases leaked umask077, changing a subsequent intended public directory to private. An actual ordered child-process regression reproduced that failure and the incorrect final mask before repair. Restoring the fixture caller mask and explicitly marking private test files preserved production privacy behavior; the final ordered 50-case group passed without skips (exit 0, 16.90s). That failed candidate was never merged or deployed.

Exact affected commands (cwd is the isolated checkout; logs/JUnit are outside public source):

```bash
set -o pipefail
umask 022
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/home/sat/.codex/worktrees/d4ee/earthship-ui/openhab/scripts:/home/sat/Solar_PV/analytics/src /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 24 --seconds 180 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest openhab/scripts/test_pv_learning_refresh.py openhab/scripts/test_pv_pair_baseline.py openhab/scripts/test_pv_horizon_pair_baseline.py openhab/scripts/test_target_weighting.py openhab/scripts/test_weather_pv_calibration.py openhab/scripts/test_weather_directional_pv.py openhab/scripts/test_weather_pv_calibration_source.py openhab/scripts/test_pv_calibration_policy.py -q --junitxml=/tmp/earthship-a20-evidence/affected.xml 2>&1 | tee /tmp/earthship-a20-evidence/affected.log
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/home/sat/.codex/worktrees/d4ee/earthship-ui/openhab/scripts:/home/sat/Solar_PV/analytics/src /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 24 --seconds 180 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest openhab/scripts/test_pv_learning_refresh.py openhab/scripts/weather_learning/tests/test_pending_scores.py tests/completion/test_verification_gates.py::test_registered_scorer_fixture_preserves_later_qualification_fit tests/completion/test_verification_gates.py::test_pv_learning_cli_fixtures_preserve_later_process_umask -q --junitxml=/tmp/earthship-a20-evidence/umask-cross-modules.xml 2>&1 | tee /tmp/earthship-a20-evidence/umask-cross-modules.log
```

Fresh final-source native profiles completed with zero failures/errors/skips and exit 0:

| Profile | Result |
|---|---|
| completion-isolated | 656 passed, 3 deselected in 165.41s (0:02:45) |
| completion-pg | 3 passed in 25.69s |
| host | 19 passed in 29.89s |
| receiver | 5 passed in 0.18s |
| Advertised geometry | 65 passed (1.2m) |

The isolated and PostgreSQL completion partitions are disjoint (659 cases). [Native evidence](deployment-a20-native.json) binds testcase/JUnit/log hashes and exact remaining argv/cwd/exit receipts. The full isolated completion command above was rerun with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` before PYTHONPATH and JUnit `/tmp/earthship-audit-deployment-444d-completion-isolated.xml`. The exact remaining final commands were:

```bash
# cwd: /home/sat/.codex/worktrees/d4ee/earthship-ui
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 768 --tasks 64 --seconds 300 -- /usr/bin/env PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra tests/completion/test_thermal_nip04_ledger.py::test_default_sink_preflight_then_reply_stores_real_v2_action tests/completion/test_thermal_nip04_ledger.py::test_real_v2_journal_recovers_commit_before_ack_and_preserves_original_cipher tests/completion/test_thermal_primal_backup.py::test_full_primal_bundle_restores_real_v2_journal_and_durable_delivery --junitxml=/tmp/earthship-audit-deployment-444d-completion-pg.xml
# cwd: /home/sat/.codex/worktrees/d4ee/earthship-ui
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 64 --seconds 300 -- /usr/bin/env EARTHSHIP_ISOLATED_SYSTEMD_TEST=1 EARTHSHIP_RESOURCE_SMOKE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q -ra scripts/test_thermal_shadow_retry.py openhab/scripts/test_native_resource_admission.py openhab/scripts/test_score_production_cpu.py --junitxml=/tmp/earthship-audit-deployment-444d-host.xml
# cwd: /home/sat/.codex/worktrees/d4ee/earthship-ui
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 64 --seconds 300 -- /usr/bin/env PYTHONPATH=openhab/scripts:.ci/solar-pv/analytics/src /usr/bin/python3 -m pytest -q -ra openhab/scripts/test_weather_receiver_characterization.py --junitxml=/tmp/earthship-audit-deployment-444d-receiver.xml
# cwd: /tmp/earthship-audit-deployment-worker-444d7e9
python3 scripts/run-household-job.py --minimum-mib 1024 --preferred-mib 2048 --tasks 128 --seconds 600 -- /usr/bin/sudo -n /usr/bin/unshare --net -- /bin/sh -c '/usr/sbin/ip link set lo up; exec /usr/bin/env -u NODE_OPTIONS PATH=/tmp/earthship-audit-node22/package/bin:/usr/local/bin:/usr/bin:/bin PLAYWRIGHT_BROWSERS_PATH=/home/sat/.cache/ms-playwright RAYON_NUM_THREADS=1 ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 /tmp/earthship-audit-node22/package/bin/node /usr/local/bin/npm run test:geometry -- --workers=1 --output=/tmp/earthship-audit-deployment-444d-geometry-results'
```

Native Python/binary pins and Docker-daemon isolation limits are unchanged from the earlier explicitly described profiles. No household network relay or actuator was used. Independent source/release review covered A19/A20/A21 and the scoped installation helper. The final installed corrected PV learner passed an actual guarded import/schema/API probe and exact source/argv/env/timer/selected-byte readback without a manual fit or selection; its first natural daily execution remains separately clock-dependent.


## Combined daily-icon / terrain-sun follow-up

Source `bc4667790545804e81fdeff565823ae46fb18873`; [source binding](solar-presentation-source.json), current ownership/inventory and [operational record](../../operations/2026-10-20-weather-day-icons.md) supersede icon-only source for this follow-up. Local complete frontend182files/2778tests, buildexit0; isolated non-sensor browser77tests exit0; related geometry Python114tests/no skips exit0. Original five-workflow and native numerical proofs above remain historical exact-source evidence; final follow-up hosted checks and actual installation are recorded with exact revisions/counts at [PR40](https://github.com/santyr/earthship-ui/pull/40). Do not substitute the old73ede successful UI-only run for final combined-source verification.

Commands run from the isolated worktree using existing shared admission:

```bash
python3 scripts/run-household-job.py --minimum-mib 512 --preferred-mib 1024 --tasks 64 --seconds 300 -- /usr/bin/env PATH=/tmp/earthship-audit-node22/package/bin:/usr/local/bin:/usr/bin:/bin RAYON_NUM_THREADS=1 ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 /tmp/earthship-audit-node22/package/bin/node /usr/local/bin/npm run test:unit -- --maxWorkers=1
python3 scripts/run-household-job.py --minimum-mib 512 --preferred-mib 1024 --tasks 64 --seconds 120 -- /usr/bin/env PATH=/tmp/earthship-audit-node22/package/bin:/usr/local/bin:/usr/bin:/bin RAYON_NUM_THREADS=1 ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 /tmp/earthship-audit-node22/package/bin/node /usr/local/bin/npm run build
python3 scripts/run-household-job.py --minimum-mib 1024 --preferred-mib 2048 --tasks 128 --seconds 300 -- /usr/bin/sudo -n unshare --net -- sh -c '/usr/sbin/ip link set lo up; exec env -u NODE_OPTIONS PATH=/tmp/earthship-audit-node22/package/bin:/usr/local/bin:/usr/bin:/bin PLAYWRIGHT_BROWSERS_PATH=/home/sat/.cache/ms-playwright RAYON_NUM_THREADS=1 ROLLDOWN_WORKER_THREADS=1 ROLLDOWN_MAX_BLOCKING_THREADS=2 GOMAXPROCS=2 UV_THREADPOOL_SIZE=2 /tmp/earthship-audit-node22/package/bin/node /usr/local/bin/npm run test:e2e -- --output=/tmp/earthship-solar-ui-full-browser-results'
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/tmp/earthship-weather-day-icons/openhab/scripts:/home/sat/.codex/worktrees/d4ee/earthship-ui/.ci/solar-pv/analytics/src /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 24 --seconds 120 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest openhab/scripts/test_astro_geometry_series.py openhab/scripts/test_astro_geometry.py openhab/scripts/test_household_solar_horizon.py openhab/scripts/test_daily_pv_potential.py -q --junitxml=/tmp/earthship-daylight-related.xml
```

A successful read-only retained-cache projection used the same production launcher256–512MiB/24tasks/15seconds and `/usr/bin/python3 openhab/scripts/site_daylight.py`; no native acquisition, cloud request or Item update occurred. The normal repository horizon in the isolated checkout was664 and initially refused; it was tightened to644 without changing bytes. The installed immutable source must also meet these permissions. Generic refusal remains truthful and production policy was not relaxed.


## A22 thermal admission handoff follow-up

Source `c31d067a6e79f8e5fe23d26365de9a8a2e8a0018`, [source freeze](thermal-admission-source.json), normal existing test ownership and [solar-consumer map](../../operations/2026-10-20-thermal-admission-compatibility.md). The separate original-policy scheduler compatibility source is `520bdd81ba94a14908655bda2e83138131bb1986`, changing only its daily orchestrator. The native fitted/serving consumer source and numerical model are unchanged.

Local REDs and GREENs: original runtime mismatch, eight protocol cases, expired-target replacement and immutable-proof collision failed before repair. Final related98tests/11.18s/exit0/no skips; daily/post9tests/0.15s/exit0; actual compatibility scheduler3tests/0.13s/exit0 (six unrelated post tests deliberately deselected because that old source contains no new post worker). Source review approved the cold protocol and deadline/candidate routing. Actual retained replay at Python3.12.3/NumPy1.26.4 reproduced both original models over19686outdoor and20694irradiance pairs, with exact original/current residual+feature outputs. It wrote only a private qualification selector/proof/admission; global serving remained unchanged. The separate original expiry and confidence flags were preserved. These are not new fits, whole-trajectory parity or prospective skill measurements.

```bash
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=openhab/scripts:/home/sat/.codex/worktrees/d4ee/earthship-ui/.ci/solar-pv/analytics/src /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 24 --seconds 180 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q openhab/scripts/test_thermal_weather_admit.py openhab/scripts/test_thermal_weather_conditioning.py openhab/scripts/test_weather_site_calibration.py openhab/scripts/test_historical_weather_serving.py openhab/scripts/test_native_thermal_forecast.py openhab/scripts/test_household_solar_horizon.py openhab/scripts/test_daily_pv_potential.py openhab/scripts/test_pv_pair_baseline.py --junitxml=/tmp/earthship-thermal-readmit-related.xml
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=openhab/scripts /usr/bin/python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 512 --tasks 24 --seconds 120 -- /tmp/earthship-audit-20261020-venv/bin/python -m pytest -q openhab/scripts/test_historical_weather_daily.py
```

The real-original qualification CLI uses explicit original selection/source allowlist, immutable consumer source, private proof output and a separate disposable selector, with `--maximum-seconds120`. Its exact local private argv and original/proof hashes are retained in the deployment evidence; public scope/model/pair/environment data is curated above. It runs under the shared512–1024MiB/24task/150second launcher and a loopback-only namespace, reestablishing Nice≥15, idleIO and all three numerical-thread variables after sudo's environment reset. Initial missing-thread preflight refusals are runner setup failures, not passed reproduction or a production bypass.

Final complete five hosted workflows, fresh native profiles, exact tested/merged source, commands/counts/skips, scoped actual installation and natural conditioned capture readback are recorded at [PR41](https://github.com/santyr/earthship-ui/pull/41). They supersede pending candidate/install statements only when their final receipts exist. Earlier exact-source native and statistical evidence remains historical. The next scheduled morning candidate/post cycle is independently clock dependent; no immediate real training or manual forecast publication is part of qualification.
