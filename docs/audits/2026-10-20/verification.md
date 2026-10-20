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
