# Evidence-gated thermal forecast graduation

The approved October 7 goal continues after PR #2, merged as `68364dd`.
PR #3's household intelligence/planner architecture is deferred. This design
covers the existing thermal forecast, its qualification, publication and rollback.

October 8 operator update: backup and disaster recovery, including cold recovery,
restored-journal tests and recovery installation, are deferred to a separate later
finishing stage and do not block current algorithm improvement or ML deployment.
The operator accepts rebuilding from GitHub code and fresh data after catastrophe.
Historical recovery requirements below are superseded for this stage. Runtime
forecast withdrawal, evidence gates and host resource limits remain required.

October 8 execution update: local fitting and qualification are authorized under
serial CPU/memory/no-swap/process/time limits and current resource checks.
Off-host execution is optional and is not a prerequisite.

The current fit artifact remains a shadow fit artifact. A separate versioned
`earthship-thermal-release/v1` contract binds a frozen artifact, runtime, source
and sensor epochs to a preregistered policy and independently reproduced
qualification evidence. No field flip or caller-supplied active override grants
production authority. Existing v4/v5 readers continue rejecting incompatible
contracts. A production publication is explicitly version 2 and distinguishes
`shadow`, `forecast_active`, `advisory_active` and `unavailable`.

Qualification retains original captured forcing, origin state, known actions,
artifact/runtime identities and native qualified outcome receipts. UTC elapsed
windows determine non-overlap; Denver local dates determine independent days.
Scores are stratified by immutable candidate identity, horizon and regime.
Historical conditional hindcasts remain development evidence. Outcomes already
examined, including the October 7 reassessment, cannot become untouched holdout.

Before opening a final holdout, freeze policy, candidate and evaluation intervals.
Policy derivation uses development baseline errors and a declared statistical
confidence level. It records numerical absolute-error/bias/calibration/support
limits and their derivation. Required skill is positive against both same-origin
persistence and qualified recent-cycle baselines, with a confidence bound below
zero on paired absolute-error differences; arbitrary permitted loss is forbidden.
Every declared horizon (at least 1/6/12/24 hours) and supported regime is assessed.
Do not silently pool changing models or claim unobserved seasons.

Stage A evaluates forecasting, conditioning, independent-day coefficient stability,
source qualification, freshness and epoch compatibility. Missing confirmed action
outcomes are an advisory blocker, not by themselves a forecast blocker. Stage B
additionally requires genuine confirmed action states and qualified comparative
outcomes for the actions recommended. Reconstructed states remain exploratory.
No automatic actuation, new ventilation scenarios or household alert-policy changes.
The operator's November default remains no venting until changed.

Current input, model or contract failures produce an explicit unavailable result.
The UI presents operating mode, separate forecast/action confidence, revision,
freshness and uncertainty. Active status requires a valid qualification binding.
Rollback retains the compatible prior runtime, artifact and v1 shadow output;
prospective baseline regression, calibration failure, source epoch change or
corruption withdraws production eligibility. Existing safety alerts remain independent.

When qualified independent evidence physically does not exist, implement and test
the remaining engineering, leave activation closed, and report the exact missing
observations. Engineering completion does not complete this goal.
