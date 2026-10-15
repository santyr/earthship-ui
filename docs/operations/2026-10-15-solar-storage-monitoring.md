# Solar and storage outcome monitoring

This batch continues the existing PR #3 architecture. It adds an Earthship
observation beneath the existing household content and matched SoC outcomes for
the provisional terrain-aware PV/load scenario. Full PR #3 remains incomplete.

## Forecast and comparison

The public view retains the original 24 elapsed hourly intervals, potential PV,
conditional captured PV, nominal battery SoC, source issue and original constant
household AC load assumption. It uses the already sealed forecast and plan;
HTTP requests never execute a model. Potential generation and accepted energy
are distinct. The provisional map skyline excludes nearby obstacles and the
model leaves system overhead, charge-rate limits and taper unqualified.

For each retained original, the scenario is compared with the original plan's
constant net battery power reference and hold-SoC reference. All three use the
same original issue, nominal capacity, initial SoC and measured endpoint. Targets
are 1, 6, 12 and 24 hours after issue, with five minutes allowed for persistence.
The atomic BMS source must meet the existing source epoch, latest-row barrier,
quality, expiry and original collection-clock checks. Invalid or missing actuals
never become numerical scores or fall back to an older good row.

A bounded seven-day cohort samples one original per UTC hour. Cohort identity
binds the numerical model sources, array, horizon, topology, physical bank,
nominal capacity and BMS stream epoch. Each terminal endpoint is retained once;
errors use the original prediction, not a revised hindsight forecast. Reports
include attempts, matched counts, independent Denver origin days, MAE, bias,
RMSE and RMSE skill against both references. Empty comparisons remain null;
a zero reference RMSE has no defined skill. This measures conditional prediction
under actual household behavior, not causal benefits of proposed actions.

PV energy accuracy stays `unavailable_unmatched_meter_scope`: available array
DC, accepted controller output and the device-reported daily-energy meter are
not automatically comparable. Calibrated usable energy and actuator graduation
remain separate unfinished requirements.

## Execution and public transport

The existing battery outcome opportunity runs first with its original budget.
Solar scoring receives at most fifteen seconds from the unused portion of the
same slot, reserving ten seconds for final guards. The existing timers, shared
resource pool, pressure checks and absolute deadlines remain in force. No new
fit or manual production forecast/qualification probe is part of this batch.

Original forecasts/plans and endpoint receipts remain private. Curated files
are owned mode 600 under a mode 700 state directory. The fixed GET-only routes
`/api/household-energy-observation` and `/api/household-energy-performance`
reject query arguments, links, races and malformed/oversized data. They expose
only the bounded observation/report schema. Forecast freshness expires fifteen
minutes from the original issue; reports expire thirty minutes after generation.
A cache read cannot renew source freshness. The Earthship view labels expiry,
missing evidence, unmatched model cohorts and provisional quantities.

## Verification status

The broad household/backend suite passes 1,500 cases in 302.55 seconds. All
2,439 frontend cases across 155 files pass, and the frontend build passes. The
final immutable review, live deployment and naturally issued outcome evidence
are pending. Prior-revision hosted Python CI has environment/fixture failures;
its ML, encrypted delivery, authentication and GitGuardian checks pass. These
local results do not claim that hosted merge checks are clear.
