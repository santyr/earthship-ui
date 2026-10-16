# Household planning from same-issue energy trajectories

The approved bounded extension connects the deployed PV/storage and hourly
learned-load scenarios to a separate shadow plan. The existing daily energy
forecast, v6 model/plan, constant-load PV/storage receipt, learned-load receipt
and their existing outcome scores remain unchanged.

The adapter replays the original v6 model/plan and the externally pinned energy
and optional learned-load receipts. Their issue, snapshot, configuration, source
closure and availability clocks must agree. A resealed output, another snapshot
with the same SoC, a changed numerical runtime or a later decision cannot be
substituted. The decision remains within 120 seconds of the original issue.

An available and unexpired learned-load scenario is preferred. Otherwise the
original constant-AC scenario is selected with an explicit fallback reason.
An invalid supplied receipt refuses the new domain; it is not silently replaced
with an apparently valid fallback. Missing storage inputs yield an unavailable
energy projection and no energy candidates. Source freshness is checked again
at the new decision time.

Only the original configured 6-, 12- or 24-hour horizon is used. Its retained
hourly SoC trajectory and cumulative modeled energy determine the nominal
minimum SoC and unaccepted PV energy. The minimum includes the initial SoC.
Values beyond that horizon do not influence the candidate scores.

Positive modeled unaccepted PV energy can generate an existing-owner greywater
candidate. A nominal minimum below the existing configured low-trough threshold
can generate an existing-owner night-load override OFF candidate. Both remain
hypothetical: no action effect, wear benefit or causal energy saving is inferred.
The new version explicitly labels surplus preference points per nominal
unaccepted DC kWh, rather than reusing the old curtailment-proxy-hour label.
Reserve preference points remain per nominal SoC percentage point.

Qualified current battery and AC measurements support intent evidence. Forecast
provenance remains `retained_forecast_context`, separately pinned as a forecast
reference; it is not promoted to measured evidence. A selected learned model has
its own artifact, runtime, projected-load, availability and expiry references.
The original thermal projection remains pinned to the same shared snapshot.

The existing constraint engine receives the original coordination packet,
reserve threshold and registry unchanged. All candidate effects remain unknown,
confidence remains unavailable and actuator requests remain disabled. Even when
all declared owner gates and the baseline reserve pass, unknown effects keep
these hypothetical options inadmissible. A nominal model minimum does not become
a qualified reserve-permission fact.

The existing scheduled forecast cycle retains the new
`earthship-household-trajectory-shadow-receipt/v1` under a content-addressed
`.household-trajectory-shadow-v1.json` filename. New-domain failure is isolated
from existing publication and caches. There is no new timer, reader, training
job, database permission or request transport. Original schemas remain readable;
the new adapter is outside their numerical runtime closure.

`household_trajectory_plan.py --receipt ... --plan ... --energy ... [--profiled ...]`
replays external private originals through the executing runtime, verifies them
again afterward and emits only the original result. It performs no live reads,
fitting, new issue or mutation. The receipt is bounded to 2 MiB; energy and load
originals retain their existing 256 KiB bounds.

Verification passes all 1,655 affected household/backend cases with two
explicit resource-scope smoke skips. The existing real scope checks passed
separately before this batch, which changes no resource policy. All 54 affected
operational-tooling tests pass after binding historical qualification tests to
their exact original source fixture. Runtime-hash checks confirm the original
v1 PV numerical closure, fitted thermal source closures and protected control/
release helpers are unchanged. The single final review found no Critical or Important issues. Source
`521762d` activated at 19:36:36 UTC on October 15 as
`6ea305c7385578ac2f3fc7f7261c11f39209af01258f15e24a59799ec9985cd3`.
All five owned definitions, three timers, both scoring calendars and shared
budgets pass effective readback. The complete thermal artifact `188a42a8`
remains unchanged; no restart, refit or manual forecast/qualification occurred.
The clean daily source checkout is updated while its service unit remains
byte-identical and was not manually started. The learned-load model remains
scheduled for its first normal morning preparation on October 16 at 06:50 MDT.

The original read-only Milestone 1 is independently verified on the actual
October 15 18:55:15 UTC issue: qualified battery/load/temperature measurements,
a common snapshot and registry, energy plus thermal projections, a typed
candidate, twelve hard constraints, a sealed empty selected action set and
identical complete activated CLI replay. Its plan receipt is
`fd8cfec6f4c572b6c6bb201fdd76a939116c4078ef81d2eecb76b29033e92836`.
The empty set correctly reflects unknown effects/permission facts. This proves
the specified read-only milestone; it does not complete the broader architecture,
qualify action effects, establish model skill or permit physical requests.

The first natural issue at 19:40:15 UTC completed successfully and retained
`fef4edd90851d38b104ebcb21f9c9f39401b622b5e0017834c3acd4dd3b6c3c7`.
It used the same-issue constant-load PV scenario while the learned model remains
collecting. Its trajectory generated hypothetical greywater and night-load OFF
candidates. The original coordination packet remained identical and the selected
action set remained empty (`input_incomplete`). Exact activated CLI replay matches
the saved receipt; the original v1 energy receipt also replays identically and
all original files remain unchanged. No live forecast was manually initiated.
