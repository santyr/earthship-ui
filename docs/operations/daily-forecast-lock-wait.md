# Daily forecast shared-lock wait

The October11 daily06:40 invocation exited75 while the thermal forecast held their existing shared consumer lock. The thermal job started06:39:45 and finished06:40:26. The daily unit's nonblocking flock returned immediately, and its success-exit75 policy hid the missing issue. The timer schedules one daily attempt, so no October11 prediction record was produced.

The additive `zzzz-daily-lock-wait.conf` replaces only the daily lock wrapper. It waits at most90seconds on the same lock before one unchanged worker execution. It does not own the lock while waiting. The existing thermal service is itself bounded to90seconds. The daily service's180-second total timeout includes the wait, so worst-case contention leaves up to90seconds for the worker. Timeout exhaustion stays bounded and must be visible; no automatic retry loop is added.

The existing CPU20%, memory256MiB, swap0, tasks24, nice15, idle IO and single numerical threads remain inherited from the existing bounded native-input profile. The timer, forecast policy, calculation code, credentials, database grants and actuator/request paths are unchanged.

Qualification uses actual util-linux flock with temporary private locks and counter-only workers. It verifies contention release permits exactly one execution, prolonged contention never runs a worker and uncontended execution occurs once. Fixture wait durations are scaled; production policy remains90seconds. These fixtures contact no network, household service or notification path.

Six focused qualification tests pass under strict local caps. Independent review found one missing other-consumer refusal guard, fixed with failing-then-passing tests before writes/reload. A minor fixture exclusivity coverage gap remains deferred; the actual template uses flock's exclusive default.

Live installation must compare exact reviewed template bytes and retained existing-profile bytes, require terminal/inactive states for the daily unit and named other forecast consumers, and verify its effective caps/timeout/wrapper and no automatic restart. `scripts/daily_forecast_lock_wait.py` performs the guarded preflight and additive install against an owned private expected-state receipt. Only the additive user drop-in may be created. Definition reload must not start any job or alter a timer. The next natural06:40 issue qualifies production behavior; source and effective-configuration checks do not prove that future issue occurred.

This is forecast scheduling work. Backup/recovery remains deferred, and full PR3 model-input, policy/action, observability and release requirements remain active.
