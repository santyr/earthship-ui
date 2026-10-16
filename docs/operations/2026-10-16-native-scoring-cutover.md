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
