# Retire scheduled legacy scoring

The operator requested cutting over instead of repairing the archived legacy
pressure guard. The legacy v1 scorer is no longer needed for future maturity:
its 773 retained original forecasts end at 2026-10-14T04:35:15Z. Even the
longest 24-hour outcome plus its five-minute acquisition delay had elapsed
before this change. Existing legacy originals and reports remain historical
evidence; missing outcomes are not invented or relabeled as current skill.

The live coordinator no longer dispatches a legacy worker. Current native
scoring remains at minutes 1 and 11 of each twenty-minute cycle. Native history
now rotates at both minutes 6 and 16, using a ten-minute index so every explicit
retained stage receives a turn. With no native history, those slots refresh the
current model. The timer, number of scheduled jobs, original 31-model per-process
envelope, shared lock, deadlines, resource policy, fitted numerical sources and
actuator permissions are unchanged. Independent battery/PV/load outcome slots
remain at minutes 8 and 18, second 20.

New family metadata records the native-only roles. The new staged source marker
keeps older sealed family metadata and expected unit bytes unchanged. Original
legacy dispatch references remain sealed provenance and retain their original
validation; they are not scheduled for execution. Native historical workers
remain useful for maturing forecasts issued before a native model update.

The uncommitted legacy-monitor repair was stopped before any product-code
change or deployment. No production fit, forecast, score or qualification probe
is manually triggered by this cutover. First natural execution and effective
readback are recorded after activation.

Verification: all 105 affected scheduling, dispatch, current/battery scoring,
retained-worker diagnostics, family upgrade/effective readback/handoff and
resource-policy cases pass in 19.05 seconds, including the explicit real
shared-pool pressure-monitor smoke check. Five initial regressions failed under
the original legacy routing. Full-day scheduling proves zero legacy slots,
unchanged current/battery cadence and no additional timer invocations. Both
32- and 63-stage inventories rotate completely. Earlier sealed family metadata
and timer bytes remain valid through owned upgrade preparation.

The final review identified one Important pre-existing dispatch gap directly
relevant to the cutover: a selected compatible historical stage outside the
last 31 was not executed by either route. One correction dispatches that stage
through its own sealed worker. A failing-to-passing boundary regression proves
execution outside the envelope and continued bounded in-process execution
inside it. No model selection limit was widened. The review had no Critical
or Minor findings. All 107 final affected cases pass in 19.04 seconds; an
additional 59 owned install/family/daily lifecycle regressions pass in 12.35
seconds. No repeated review pass was needed.

Source `a9ee9b2` activated at 2026-10-16T13:31:43.842014Z as deployment
`6eec3bf274528a73e07bb271d7dc99233a77c2099bc314d25927454f361aaec2`.
The complete thermal artifact `284139ee`, including original model admission,
was reused unchanged; no fitting or qualification probe ran. Effective
readback at 13:32:17Z verified all five owned definitions, three active timers,
both score calendars, shared resource limits and provisional model/forecast
HTTP 200 responses. The idle daily source checkout advanced to this commit;
its unit bytes are unchanged.

The normal current-model score started automatically at 13:31:43Z after timer
restoration and completed successfully at 13:32:09Z. The next ordinary native
history opportunity is 13:36Z. The legacy-pressure repair was not deployed:
scheduled legacy execution has been retired instead.

The first normal post-cutover forecast published provisionally at13:35:15Z.
The normal13:36 native-history opportunity then completed successfully at
13:36:26Z. Current native scoring, history scoring and forecast continuity are
therefore verified after the cutover, without manual invocations. Retiring
legacy execution does not qualify learned-load skill, physical effects or
actuator release; the full PR#3 objective remains incomplete.


## Hosted CI assertion follow-up

The completed full backend job for deployed-correction headcbb0f6f
([run38918858993](https://github.com/santyr/earthship-ui/actions/runs/38918858993))
passes6261 tests and91 subtests, skips24, and fails only two assertions that
still require a scheduled legacy slot. The oldera24f31f run had one additional
retained-slot example failure, already corrected by1a3d5d8.

Both remaining stale assertions were reproduced against the current approved
native-only coordinator before test changes. The dispatch expectation now
requires current/history/battery slots and explicitly excludes a legacy role.
The score-window file's duplicate obsolete role check is removed; its work-budget,
old-family compatibility, atomic installed timeout/schedule and effective-family
checks remain. All31 focused dispatch, window, capacity, current-worker and
nonrenewing-deadline tests pass in2.27seconds. No production source, scheduler,
model, resource policy or owner behavior changed, and no deployment is needed.

This repairs verification of the approved cutover rather than restoring legacy
production work. A fresh full hosted CI result, including subsequent operational
tooling steps, remains required before claiming all checks pass. The chronological
shadow-summary design and full PR #3 qualification are still pending.
