# Daily forecast shared-lock wait implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, TDD and one independent final review.

**Goal:** Prevent the normal06:40 forecast from being skipped when a bounded thermal consumer still holds their existing shared lock.
**Architecture:** An additive final service drop-in replaces nonblocking flock with a bounded90-second wait. The existing three-minute service timeout and CPU20%/256MiB resource envelope remain authoritative. Exhaustion stays exit75 but becomes visible failure. Install only the reviewed drop-in after exact existing-profile, terminal-service and effective-configuration checks; reload definitions without starting jobs.
**Tech stack:** Existing systemd user units, util-linux flock and Python qualification fixtures.
**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, phases2/7/9 and existing local resource/authority constraints.

## Global constraints

- No new task family, owner request, forecast calculation, notification policy, timer schedule, credential, database grant or recovery work.
- Local numerical/test scopes: serialCPU20%,memory256MiB,swap0,tasks24,IOWeight10,nice15,idleIO,threads1. Broad checks hosted.
- The existing thermal service timeout is90seconds; the daily service remains180seconds total. Lock waiting holds no shared lock and consumes the same bounded invocation budget.
- Install only when the named other forecast consumers and actual daily unit are terminal/inactive and the existing bounded native profile matches the retained expected bytes. Never stop/interrupt/restart a consumer or force a lock.
- Default source template is inert. Live install requires exact reviewed source/profile fingerprints and confirms effective caps, command, timeout and no automatic restart.

## Review focus

- Another unit still running or a changed source/profile must refuse installation.
- Lock timeout must never run the worker or become successful forecast publication.
- Waiting must use the original inode/path and acquire exclusive ownership before one worker execution.
- Definition reload must not trigger a timer or forecast/notification run.
- Full service timeout/caps must remain bounded despite lock waiting.

## Task1: Bounded wait source and behavioral qualification

Files:openhab/systemd/user/forecast-intel.service.d/zzzz-daily-lock-wait.conf,scripts/test_daily_forecast_lock_wait.py,scripts/daily_forecast_lock_wait.py.
- [ ] Write failing tests from actual template flags for contention release, prolonged contention and exclusive single execution; use only temporary fixture locks and counter workers, no network/OpenHAB/credentials.
- [ ] Watch missing-template tests fail, implement additive ExecStart reset/replacement and SuccessExitStatus reset, then run all focused qualification tests under strict caps.
- [ ] Commit source and ledger. Record wait budget and unchanged total timeout/caps.

## Task2: Definition qualification and authorized deployment

- [ ] Prepare owned private expected source/profile/manager-state receipts; inspect current terminal daily worker and validate effective resource envelope before writing anything.
- [ ] One independent whole-stage static review, fix Important/Critical findings in one TDD pass. Publish source and hosted checks.
- [ ] After verified reviewed source/hosted success, atomically add only the owned user drop-in, daemon-reload, check exact command/caps/timeout/failure/restart policy and unchanged source/profile fingerprints. No job start/restart/force; next natural issue qualifies production outcome.
- [ ] Record concrete readback and original next scheduled timer; keep PR3 full scope active and full actual model replay withheld until original inputs exist.
