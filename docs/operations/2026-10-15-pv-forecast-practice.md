# PV forecast practice and recovery-day diagnosis

This research applies to PR #3's existing rolling energy and outcome requirements. It does not create a separate household architecture. Findings were checked on October 15, 2026 against primary documentation and the current local Solar_PV knowledge base.

## What the guidance actually covers

IEC 61724-1:2021 specifies PV performance monitoring terminology, equipment and methods; its public description does not prescribe a particular forecast algorithm. We reviewed that description, not the purchased full standard, and make no IEC compliance claim. The IEA PVPS/NREL fourth-edition solar-resource handbook provides forecasting and uncertainty practice. These are distinct kinds of guidance ([IEC](https://webstore.iec.ch/en/publication/65561), [handbook publication](https://research-hub.nlr.gov/en/publications/best-practices-handbook-for-the-collection-and-use-of-solar-resou-4/)).

A practical physical model transforms weather irradiance into irradiance on the panel plane, then accounts for module temperature, DC conversion and losses. pvlib's ModelChain exposes those steps separately. Its transposition interface requires surface tilt and azimuth plus solar geometry and irradiance components. This supports correcting our current daily horizontal-radiation multiplier rather than treating it as a physical array model ([ModelChain](https://pvlib-python.readthedocs.io/en/stable/reference/modelchain.html), [transposition](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.get_total_irradiance.html)).

SAM treats generation, household demand and battery dispatch separately. Battery SoC, available capacity and charging limits affect absorption; generation and load forecasts have independent horizons. For this off-grid installation, the engineering implication is to predict available PV first and then simulate how much the loads and storage can accept. More recharge demand permits more captured energy; it does not create irradiance ([SAM battery dispatch](https://samrepo.nlr.gov/help/battery_dispatch_btm.html)).

Solar Forecast Arbiter specifies the forecasted variable, issue/lead time, units and interval labeling, alongside observation quality. It separately represents AC power, DC power, availability and curtailment. Its reference methods include weather-model forecasts and persistence, including clear-sky-index variants. Forecast hourly means must not be silently treated as point measurements ([data model](https://forecastarbiter.epri.com/datamodel/), [reference forecasts](https://solarforecastarbiter-core.readthedocs.io/en/stable/reference-forecasts.html)).

Use MAE, signed bias and RMSE with sample counts and matched reference errors. Skill compares forecast RMSE with reference RMSE. Daily percentage error alone obscures systematic underprediction and overweights low-production days; that is an engineering consequence of its division by observed production. Power normalization requires a known corresponding capacity; daily energy must not be divided by a kW rating and called a percentage. Quantile scores are appropriate only after actual probabilistic forecasts exist ([metrics](https://forecastarbiter.epri.com/metrics/)).

## Current installation and shared solar inputs

The current local `Solar_PV/docs/architecture/current-system.md`, at checkout `26ccc7aaa54ca0f9830e23ec8c31e9bd7e99fe5b`, records twelve Qcells 350 W modules, **4.2 kW DC**, installed August 6, 2021, feeding the MPPT 60-150 and XW Pro. The quote rating is operator-transcribed, not field-nameplate verification. That document explicitly rejects the unsupported 4.8 kW value in older prose. The bank is four Discover modules, 20.48 kWh nominal; historical AGM settings do not apply.

The operator now reports an array approximately **15 degrees east of south: azimuth 165 degrees**, and a tilt optimized for December. The operator subsequently measured 32.6 degrees with an inclinometer whose horizontal reference is 90 degrees. Therefore the panel tilt above horizontal is 90 − 32.6 = **57.4 degrees**. The raw reading and convention, 165 degree azimuth and quoted 4.2 kW capacity are retained in `openhab/household-pv-system.json`; this is source configuration for the next model, not an already active PV algorithm. Exact module model, string arrangement, shading and temperature coefficients remain unknown. These unknowns permit an explicitly provisional model; they must not be represented as measured parameters or stop unrelated production.

Thermal and PV models should share the same retained, as-issued weather and Astro geometry. They need separate receiving-plane/response models: glazing, mass, ventilation and shades determine thermal response; array orientation, module temperature and electrical constraints determine PV response. Forecast radiation remains distinct from measured lux/radiation proxies. Open-Meteo hourly shortwave is a preceding-hour mean, requiring interval-end integration and correct partial-hour/UTC boundaries ([provider documentation](https://open-meteo.com/en/docs)).

## Valley terrain and seasonal sunlight

The operator reports seasonal mountain shadows at this valley location.
The [terrain-horizon diagnosis](2026-10-15-terrain-horizon-diagnosis.md) retains
a location-specific PVGIS map estimate and a read-only comparison with twelve
days of original station receipts. Use the map as a provisional skyline prior,
then test corrections against repeated clear-weather observations and later
days. Preserve direct/diffuse light separation, native Astro event times and
receiver-specific obstruction uncertainty. This is not an already deployed
horizon correction or annual validation.

## Actual recovery-day check

Read-only analysis used the retained daily prediction and source-qualified scoring state, not a new fit or a forecast probe. Private sanitized proof is `weather-energy-20261015/pv-recovery-diagnosis.json` under the common-cycle workspace.

| Local day | Starting SoC | Forecast PV, kWh | Recorded PV, kWh |
|---|---:|---:|---:|
| September 29 | 72% | 5.36 | 10.396 |
| September 30 | 85% | 1.78 | 2.738 |
| October 1 | 69% | 6.58 | 6.697 |
| October 14 | 83% | 2.01 | 3.792 |
| October 15 | 76% | 5.51 | Not complete |

Today's original inputs already allow approximately 5.17 kWh of recharge plus 5.40 kWh of direct demand: 10.58 kWh total. The limiting branch is the solar resource estimate: 4.2389 kWh/m² forecast horizontal radiation times gain 1.3 equals 5.5106 kWh. Gain 1.3 is at its configured upper bound; retained qualified days explicitly report `release_gate_closed`, and current daily code disables qualified PV calibration.

The operator's 8.5 kWh estimate is plausible but unverified. September29 shows a comparable large underprediction; October1 shows that lower SoC alone does not imply such an uplift. Across all 14 retained source-qualified daily pairs, 11 underpredict; diagnostic bias is −0.7505 kWh, MAE 1.0669 kWh and RMSE 1.5992 kWh. Issue-lead comparability has not been audited, so these are diagnostic errors, not a forecast skill or graduation result. These records do not identify how much error comes from irradiance forecasts, array-plane conversion, losses or curtailment. Do not add recharge demand onto the existing forecast or overwrite its original value.

## Applied decisions and next implementation

The deployed flow model separates source-qualified household AC consumption, net battery charging/discharging and measured controller output. It leaves system DC overhead and conversion losses unknown and preserves original source semantics. Its sidecar keeps existing forecast and outcome versions unchanged. This is the immediate prerequisite for the researched model structure, not a new PV forecasting algorithm.

Next, implement an hourly provisional array model using the shared retained forecast/geometry and source-bound array specification. Calculate potential generation separately from captured generation, load and storage; retain every issued trajectory. Use documented controller/battery limits only when available, preserving uncertainty rather than inventing a fully closed balance. Treat verified curtailed production as a censored potential-generation target; unknown limitation status stays unknown. This censoring decision is our engineering inference from the distinction between available and captured power, not a quoted standard requirement.

Evaluate chronologically by horizon and by independently observed operating conditions, including recovery days. Use only information available before issue; preserve the existing forecast as a reference and add a clearly named persistence reference where original source support permits. Report counts, missingness, bias, MAE/RMSE and reference skill. Introduce calibrated uncertainty as enough independent days accumulate. Never learn the physical solar gain from unclassified curtailed output as if it measured all available solar. Any revision of the old gain bound/calibration gate needs this diagnosis and source evaluation, rather than a forced 8.5 kWh forecast. Existing actuator ownership and host resource coordination remain intact.

## Provisional implementation checkpoint

The current development batch adds a dependency-free scalar array model checked
against 27 independent pvlib 0.16.1 reference cases. It integrates the retained
hour-ending radiation means over partial UTC hours and the original native
five-minute geometry. Its response uses Erbs decomposition, isotropic
transposition, a Faiman temperature proxy and PVWatts-style DC output with
explicit provisional temperature/loss assumptions. Exact module coefficients
and losses remain unmeasured.

A source-bound PVGIS skyline now masks direct beam and its ground reflection,
while retaining diffuse sky irradiance. Its site fingerprint must match the
original native geometry. The model labels the map unvalidated and leaves
nearby obstructions and diffuse sky-view correction unmodeled. Missing, malformed, unsupported or mismatched horizon configuration withholds
only the new PV/storage projection. The pure numerical integrator retains an
unobstructed reference for independent comparison, without using that as a
serving fallback. It does
not replace native Astro events or the existing thermal model's forcing.

The separate `household_energy_forecast.py` receipt retains PV potential and a
conditional nominal-storage scenario against an external unchanged plan.
Storage holds the original current household AC load constant, uses fresh
source-qualified initial SoC and declared nominal capacity, and exposes its
assumed efficiencies, zero overhead assumption, unaccepted PV and unserved
energy. It has no measured charge-rate/taper limits, learned load trajectory,
usable-energy qualification or actuation authority. This scenario is a baseline
for later comparisons, not a calibrated captured-PV forecast.

Cycle source v7 retains the original array and horizon files; old source and
plan contracts remain supported. Neither new model code nor configuration is
inside the original fitted thermal closure. The new receipt explicitly binds
its executing sources and replays without readers or providers. Scheduled
collection/deployment and actual production replay are still pending at this
checkpoint. No manually triggered fitting or production inference probe is
part of the verification.

## Verified deployment — October 15

Source `522241e1e25dbb8f7a8ef59f5968bef29bf68758` is deployed as
`b5a73ec302c1959f85d0614347249a8140820a0e61378471eff2752156677013`.
The complete trained candidate `188a42a8` is unchanged. Activation finished at
15:46:45Z without restart, fitting or manual forecast/qualification probes.
Five owned unit files, all three timers, both score calendars, unchanged shared
resource limits and the public UI/model endpoints pass effective readback.
The clean idle daily checkout advances to this source with its unit unchanged.

The scheduled geometry preparer completed at 15:48:09Z. The first scheduled
forecast process ran 15:49:45–15:50:32Z, approximately 47 seconds at systemd's
displayed timestamp resolution, and exited zero. Its original issue is
15:50:15Z. The new PV/storage receipt
`834b31dbc5fc7cebcb4cf27f65a3d9f90d23cad0799746936342d3ec1eb3b1ff`
binds original plan
`2592c6b0617e26fae3846a92a857e29876617fde4392dc3e39c04cea5ad428db`.
Original configuration bytes match the staged files; receipt rederivation and
its exact staged file-only CLI output are identical, preserving both documents.

That original projects 19.9206 kWh of potential array DC over the **next 24
hours**, with 15.6527 kWh potential remaining before local midnight. Thirteen
retained geometry steps are mountain-blocked. Its separate storage scenario
uses source-qualified 427 W household AC held constant, 87% initial SoC and
declared nominal capacity. It models 10.4988 kWh captured over the next 24 hours
and 82.4374% final nominal SoC under the stated assumptions. These are different
quantities and intervals from the existing daily captured-PV prediction; they
are not measured outcomes, calibrated skill or a replacement for that issued
forecast. The new receipt remains private pending chronological PV outcome and
public UI integration.

Verification: 1,462 household Python tests pass after the single review
correction; 2,419 frontend tests across 152 files pass. A separate deployment
history fix aligns model-admission lookup with 63 retained stages plus the
current stage; 43 affected admission/dispatch/family cases pass. It preserves
the earliest exact model admission rather than deleting evidence or retraining.
The immutable review found one Important fallback issue and one minor integrity
edge; missing or unusable terrain now withholds only PV/storage, and source
wrapper integrity is checked even without geometry. Live owner rules and
original thermal predictions remain unchanged. Full PR #3 is still incomplete.

## Monitoring follow-up — October 15

Operational source `a539742` now adds a public 24-hour solar/storage chart and
independently verified original-reference SoC comparison under the existing
shared scoring schedule. The normal 16:50:15Z receipt, original plan and exact
staged file-only replay match; laptop/tablet rendering and the fixed public GET
are verified. This later original uses its own retained weather/load/SoC inputs;
it does not revise the earlier 15:50 forecast. The first mature scheduled
comparison is pending at this checkpoint, and PV energy accuracy remains
unavailable until meter scope is comparable. See the [monitoring deployment and
validation record](2026-10-15-solar-storage-monitoring.md). Full PR #3 remains
incomplete.
