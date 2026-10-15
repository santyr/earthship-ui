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
same original issue, nominal capacity, initial SoC and measured endpoint. The
constant-power reference is independently rederived from the original snapshot,
metric semantics, configured horizon and decision time. Shorter 6/12-hour
references remain explicitly unavailable to this fixed 24-hour comparison. Targets
are 1, 6, 12 and 24 hours after issue, with five minutes allowed for persistence.
The atomic BMS source must meet the existing source epoch, latest-row barrier,
quality, expiry and original collection-clock checks. Invalid or missing actuals
never become numerical scores or fall back to an older good row.

A bounded seven-day cohort samples one original per UTC hour. Cohort identity
binds the complete retained forecast runtime, array, horizon, topology, physical bank,
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

## Verified deployment and first scheduled observation

Source `a5397426f0ca0d9a5b2cc700c9aea6eda354fc31` is activated as
`dbc1369cb9e43a225475fb2ea32f5cd0abe0a909141df71a1885eabd48d8523c`.
The complete trained artifact `188a42a8` is unchanged. Effective readback verifies
all five owned files, three timers, both score calendars, the shared pool and
HTTP availability. The clean idle daily checkout advances with its unit bytes
unchanged and without starting training. Five committed UI files are installed
without restarting the UI service; protected thermal overlays remain unchanged.

The normal 16:50:15Z issue is retained and publishes its original clock. It
projects 16.4638 kWh potential over the next 24 hours and a separate 9.9176 kWh
conditional capture scenario from 98% SoC, holding the original 353 W AC load
constant. These different quantities are provisional predictions, not measured
outcomes or the previous whole-day forecast. Its external-original replay and
exact staged file-only CLI are identical; original forecast and plan bytes are
unchanged. The fixed public GET returns 200 and the 24-hour chart/inspection
control renders at 1280x800 and 800x1024 with no page errors, write attempts or
horizontal document overflow. Actual screenshots are retained privately.

The new accuracy cache is initially unavailable pending its first scheduled
mature comparison. The earliest retained eligible PV origin is 15:50:15Z; its
one-hour endpoint matures at 16:55:15Z and the next independent battery/solar
opportunity is 16:58:20Z. This checkpoint does not claim any scored scenario
outcome. The 16:46:33Z scoring launch was refused shared admission during the
handoff; the ordinary 16:48:20Z opportunity and geometry preparer subsequently
completed normally, without manual retry or safeguard changes.

The broad household/backend suite passes 1,500 cases in 302.55 seconds. All
2,439 frontend cases across 155 files pass, and the frontend build passes. One
immutable review received one correction pass: independently rederive reference
numerics, bind the complete forecast source closure in cohorts and handle
shorter reference horizons explicitly. Four red regressions reproduce these
issues; 53 affected cases pass after correction. An additional cache-isolation
case preserves the original publication path and unrelated target bytes.

Prior-revision hosted Python CI has interpreter-permission and real-resource
environment failures; its ML, encrypted delivery, authentication and GitGuardian
checks pass. These local results do not claim that hosted merge checks are
clear. Full PR #3 and comparable PV energy calibration remain incomplete.

## First matched production outcome — 16:58 UTC

The ordinary 16:58:20Z battery/solar opportunity exits zero at16:58:25Z. It
scores the original15:50:15Z issue against the atomic16:50:15Z BMS endpoint:
actual98%, solar/load scenario98.1210122%, constant net-power96.5019531% and
hold-SoC87%. Absolute errors are0.1210122,1.4980469 and11 percentage points.
This is one original from one day; it does not establish general forecasting
skill. Six-, twelve- and twenty-four-hour outcomes remain collecting.

The compact receipt `4f6aa73f51c2706bf8574eff7f8aa00cdef2b49ac2283086bf2ef77ab1d9aa0e`
replays identically from both external original documents through the exact
staged CLI. Original forecasts, plans, source index and score bytes are unchanged.
The fixed accuracy GET and matched table render on laptop/tablet with no page
errors, blocked write attempts or horizontal document overflow. Automatic
actuation and physical/causal qualification remain false; comparable PV energy
accuracy remains unavailable. The earlier missing-cache state is now superseded
by this measured result.
