# Forecast-led passive-solar advice

The advisory planner compares the unchanged model's full 24-hour air/mass
trajectory with two-hour indoor-shade settings beginning now or 1, 2, 4 or 6
hours ahead. Each scenario retains the same initial latent thermal mass,
weather, irradiance, exterior-shade state and fitted coefficients. After the
two-hour trial window, it uses the original journal assumption again; this is
receding-horizon advice, not an unattended schedule. It reconsiders each issue.

The 70–76°F preference remains the future comfort objective. Current temperature
crossing that band is no longer the trigger. A candidate must reduce integrated
future discomfort by at least 0.1°F-hours and change the predicted temperature
path by at least 0.2°F. Ties prefer a later action. Heating advice and cooling
ventilation are not proposed together. Recent shade movement retains the
existing ten-minute settling hold. Ventilation also requires a modeled benefit
from a fifteen-minute opening, present cooler-air evidence and a forecast heat
risk; wind/rain/smoke/security remain explicit checks for the person.

The planner reads the native forecast's original timestamped solar elevation and
azimuth. Direct-beam incidence onto glazing is:

`sin(elevation)*cos(tilt) + cos(elevation)*sin(tilt)*cos(solar_azimuth-glazing_azimuth)`

Tilt is measured from horizontal. Negative incidence and nighttime become zero.
The irradiance-times-incidence proxy screens low-access action windows; it is
not a DNI/DHI decomposition or a claimed heat flux through glass. Solar angles
vary by the actual date, time and site; they are not inferred from month labels.

Optional private `~/.local/state/household-intel/advice-glazing.json` declares:

```json
{"schema":"earthship-advice-glazing/v1","azimuth_degrees":180,"tilt_from_horizontal_degrees":90,"basis":"operator_report"}
```

Those example angles describe the explicit nominal south/vertical fallback,
not a surveyed house measurement. The operator confirmed on 2026-10-29 that glazing leans 25.5° from vertical
(64.5° from horizontal) and faces approximately 165°, like the PV array.
The installed private configuration uses these confirmed glazing values. Geometric configuration is retained with each report and
rechecked before publication; replay uses original retained configuration.

The fitted v4 thermal model learns separate air/mass responses to irradiance in
four shade regimes. It currently masks night using elevation; it does not fit
window-incidence, solar penetration depth, glazing SHGC, overhang dimensions or
nighttime shade insulation. The new angular timing screen does not silently
change its learned irradiance feature or represent angle-specific benefit as
calibrated. Adding such features requires a versioned fit and held-out seasonal
validation. Closed shades reduce solar input; they are not an active cooling
source, and on cold nights insulation can reduce heat loss.

DOE's passive solar guidance describes collecting/storing solar heat in thermal
mass and controlling summer gains:
https://www.energy.gov/sites/default/files/2021-08/ES-Passive%20Solar%20design_081321.pdf
The operator's Solar_PV repository and local current-system documentation supply
PV context; array geometry must remain distinct from glazing geometry.

## Publication and rollback

A bounded advisory-only postprocessor can run after the existing forecast cycle.
It reads the exact currently published report's retained original snapshot and
forecast context, evaluates fresh advisory comparisons, retains its source
manifest and inputs, publishes through the existing validated atomic writer,
and verifies exact replay. It does not acquire weather, fit a model, alter
forecast originals or command equipment. Missing/expired original inputs yield
unavailability rather than a new reactive suggestion. Historical callers without
forecast context retain their original legacy behavior for compatibility.

The numerical forecast service and immutable numerical release remain selected.
An ExecStartPost companion uses the existing resource admission launcher and
limits. Removing only the proactive-advice service drop-in and reloading systemd
restores the original advisory publisher on its next normal cycle. Old reports,
models, source releases and private configuration remain available.


## Confirmed geometry and existing nighttime history (2026-10-29)

The operator confirms **no front overhang** and **no historical shade-position
data yet**. The private geometry configuration is v2 with `front_overhang:false`,
azimuth165° and tilt64.5° from horizontal. No overhang correction is applied.

Always inspect actual OpenHAB Items/persistence before declaring thermal inputs
unavailable. A read-only OpenHAB JDBC REST acquisition from October15–29 found
3495 indoor-air,11820 outdoor-temperature,2384 north-wall,1722 south-wall,27587
wind-speed and16301 measured-radiation state changes. These are numeric
change histories, not complete qualified heartbeat streams.

An explicitly exploratory nighttime baseline used 20:00–05:00 America/Denver,
retained radiation<=5W/m² and hourly changes with all 13 five-minute grid states
available. State changes are carried at most30minutes for air/outdoor/wind,
120minutes for slow-changing north-wall mass and14hours for nighttime zero
radiation. Non-numeric/NULL states remain barriers; no interpolation bridges
those barriers or expired carry windows. These carry rules are retrospective
analysis assumptions, not production freshness extensions.91 retained hourly
intervals span14 nights; gaps are excluded, and first/last retained temperatures
must not be interpreted as endpoints of a fully covered night.

A bounded regression predicts the next hourly indoor-temperature change using
only initial outside-minus-air, mass-minus-air, wind times outside-minus-air,
and a bias. Nonnegative exchange coefficients and bounded bias avoid inverted
heat-flow signs.65 intervals before October26 were fitted;26 intervals from
October26–28 were held out chronologically. Holdout MAE was0.098°F/hour versus
0.233°F/hour for the training mean and0.803°F/hour for unchanged temperature.
The overall retained average change was−0.682°F/hour. This demonstrates useful
nighttime predictive signal in existing OpenHAB history; it does not identify
shade insulation, exclude occupancy/ventilation effects or qualify a new
production model. Sensor epochs and full receipt quality were not validated
in this numeric diagnostic. The existing production thermal model remains
selected, with unchanged fitted coefficients.

Raw REST responses, acquisition boundaries/counts, runnable `analyze.py`, hourly
samples, nightly summaries and fit metrics are retained under
`artifacts/nighttime-thermal-history-20261029.local/`. Future shade-position
history can distinguish open/closed thermal-loss regimes while controlling for
outdoor temperature, stored heat, wind, ventilation and other observed changes.


## Existing OpenHAB energy schedules (operator clarification, 2026-10-31)

The operator requires no new discretionary task: existing tasks are already
configured in OpenHAB. Read-only live registry inspection confirms the existing
`hex_southoutlet_cycle` and `hex_night_load_override` owners and their schedules.
Provisional household advice therefore reports energy scheduling managed by
OpenHAB, with no missing approval blocker or duplicate scheduler. It does not
reschedule those owners, convert essential/protected demand into optional work,
or require the user to enter another appliance profile. The separate optional
explicit-policy energy evaluator retains its approval/attribution requirements
for any future deliberately introduced standalone task.
