# Verification evidence

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
