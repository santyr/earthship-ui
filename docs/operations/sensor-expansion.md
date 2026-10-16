# Subsequent distributed sensing work

This change delivers working typed interfaces and synthetic examples. The following
installation and model work remains separate from the contact commissioning.

## Water

The property has four interconnected Norwesco1200-gallon buried cisterns.4800gallons
is nominal capacity;3600gallons is the operator's current usable estimate, **not a
measured observation or calibration**. Neither number is emitted as sensor truth.

Commission water-depth observations using an installation-appropriate ultrasonic,
hydrostatic or other sensor. Document mounting offsets, sensor reference surface,
pressure/temperature compensation, dead zones, condensation and maintenance access.
Measure a monotonic depth-volume curve; do not infer a linear relationship from
nominal capacity. `services/observations/water.py` demonstrates bounded interpolation,
refuses extrapolation and binds derived volume to calibration and parent evidence.

Its calibration curve refers explicitly to a set of tank IDs. Each estimate must
verify the current hydraulically connected set and equalization. Closed valves,
isolated tanks and unequal levels invalidate the combined estimate. A single tank
sensor cannot describe isolated tanks by multiplication. Identify inaccessible
reserve and usable-volume policy separately, preserving uncertainty and revision.

The generic registry also supports cumulative litres, L/min, kPa, pump-runtime
seconds, equipment temperature and binary leak readings. Commission pulse scales,
counter rollover/reset, meter direction, clock basis and missing-pulse behavior
before estimating consumption or refill events. Existing OpenHAB pump state remains
its original source; no new pump or valve writer exists.

Days remaining, consumption/refill forecasts, rain capture, continuous flow and
pump-health analytics require qualified real histories, source availability,
calibration/valve context and separately reviewed domain policies. Synthetic fixtures
are demonstrations, never production training data.

## Greenhouse and thermal sensing

Use existing Zigbee/wired sensors where already suitable. LoRaWAN is an additional
transport for distant or difficult-to-wire locations, not a migration of working
integrations. Register air/soil temperature, humidity, raw/calibrated soil moisture,
conductivity, light and CO2 with explicit units and calibration metadata.

Raw soil ADC/device values remain `soil_moisture_raw`; changing an Item label does
not make them volumetric moisture percent. Record soil-specific references, salinity,
temperature dependence, sensor drift and replacement epochs. Condensation risk,
stratification and irrigation recommendations need qualified co-timed measurements.
Unattended irrigation is outside this change.

## Ventilation evaluation

Qualified binary openings may eventually help explain temperature trajectories
alongside outdoor forcing, wind, humidity and irradiance. They do not provide
opening percentage, airflow or ACH. Keep observational ventilation separate from
existing operator action/shade history and any assumed ventilation forcing.

The optional `household/sensor_observations.py` extension attaches original-bound
observations to a frozen canonical parent only when explicitly enabled. It does
not enter existing native thermal issuance or change model equations. Existing
model schemas remain unchanged.

`services/observations/replay.py` supplies deterministic decision replay and an
explicit chronological train/holdout split with a purge horizon. It refuses synthetic
or unspecified provenance for evaluation extraction. A future experiment must
freeze original forcing, group independent days, purge at least its full target/
feature horizon, prevent future/availability leakage, compare against the same
baseline chronological holdout and retain missingness/quality barriers. No model
is trained, selected, installed or granted authority by this scaffolding.

## Gate and security

The simulated gate demonstrates configurable identity and the same contact evidence
path, not a selection or proof of a weatherproof installed device. A real outdoor
sensor must be qualified for its enclosure, magnet/switch arrangement, battery,
mounting and radio conditions. The DS03A documented profile is available for an
appropriate single-channel installation.

Perform repeated RF tests at the gate several hundred yards away, including berms,
terrain, metal, trees, wet conditions, antenna mounting and seasonal changes.
Collect RSSI/SNR and missed-supervision/transition evidence; healthy bench reception
is insufficient.

Security has explicit `observe_only`/`disabled` metadata and separate future policy.
A ventilation contact can have security relevance without changing thermal quality
rules or controlling equipment. Tamper, motion, perimeter contacts, outbuilding
state and equipment vibration require their own thresholds and alerting semantics.
No certified alarm claim, guaranteed delivery or new security notification/control
behavior is implemented.

## Onboarding checklist for every future source

1. Preserve the working provider/transport owner and inspect its existing evidence.
2. Choose stable logical identity, distinct physical identity and a replacement epoch.
3. Declare capabilities, physical types, units, clock basis, calibration and freshness.
4. Add a source-specific validator or adapt a mature qualified receipt; never qualify
   an undated mutable Item value by assigning the browser receipt time.
5. Add real documented vectors, explicit synthetic fixtures and fault/replay tests.
6. Stage OpenHAB observational metadata and verify provider/Item identity collisions.
7. Commission physical behavior, health and outages; explicitly record qualification.
8. Review any new household/model/alert consumer independently. Observation registration
   never grants an automation request or actuator capability.
