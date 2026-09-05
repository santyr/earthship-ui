# Outcome source-health preflight — September 5

Read-only evidence supporting the approved advisory-outcome implementation.
No production database changes, source replacements, notifications or control
actions were performed. This is not an outcome score or deployment receipt.

## Calendar and producer boundary

The new pure advisory_windows module defines explicit UTC day/trough windows.
It is not yet called by the live forecast script. The existing measured_trough
function is also used in morning prediction equations; changing its behavior
globally would exceed the scoring-only repair. New completed-night assessment
must use its own validated outcome path and leave those prediction inputs intact.

The actual snapshot service is energy-forecast-snapshot.service, not
earthship-energy-forecast-snapshot.service. Its working directory is
/home/sat/Solar_PV/analytics; it invokes earthship_energy.scheduled forecast-snapshot
under flock. forecast-intel.service invokes the installed standalone Python script.
Consequently the shared pure-module installation/import path must be explicit
in the later release; checkout proximity is not an import contract.

The designated local manager independently listed the three forecast-related
services and their enabled timers after a successful private Hexmem MCP context
call. It performed only that bounded read-only task. Coordinator readback confirmed
the unit names and the snapshot service command. No authority was expanded.

After the immutable record-builder task, a bounded read-only schema check found
only applied migration 0001_energy_analytics and no advisory/outcome/decision-named
tables in energy_analytics. The discover_4_module_2026 epoch key exists. The next
storage increment therefore needs an explicit additive migration; neither this
check nor the record builders created any database schema or captured decisions.

## Historical source availability

Bounded JDBC queries used a read-only connection, five-second connection/statement
timeouts, the verified item registry, and identifier-quoted table names. The
window was September 4 local midnight through September 5 local midnight
(06:00Z to 06:00Z). The managed JDBC connection configuration is authoritative;
the legacy services/jdbc.cfg does not contain the active connection settings.
No credential values were printed or copied into this report.

| Source | In-window changes | Stored value type | Interpretation |
| --- | ---: | --- | --- |
| BMS_SOC_LastUpdate | 277 | timestamp with time zone | Timestamp values provide independent update evidence. |
| BMS_Comms_Status | 0 | character varying | A pre-window OK state exists; zero changes does not mean missing telemetry. |
| BMS_DevicePresent | 0 | double precision | A pre-window healthy state exists; zero changes does not mean absent hardware. |
| Indoor temperature | 245 | double precision | Changes are stored, but historical lastStateUpdate metadata is not a table column. |
| Outdoor temperature | 1,064 | double precision | Same distinction between historical changes and current update metadata. |

Using the heartbeat's original persisted event time and reported timestamp value,
including the last pre-window record, the existing checker's 12-minute heartbeat
allowance covers 100.0% of this day. None of those timestamps were later than
their persistence event. Both health companions had healthy carry-in values and
no intervening fault changes. This validates the usefulness of change-aware BMS
evidence; it does not authorize every historical epoch or prove absence of all
hardware faults. An eventual outcome scorer still validates values, source epoch,
fault intervals, exact target windows and provenance.

The live item-name inventory found BMS and Schneider heartbeat companions but no
explicit temperature-update companion under the searched update/heartbeat/health
names. This bounded search is not proof that no other source exists. Current REST
lastStateUpdate and live SSE ItemStateUpdatedEvent are available, but neither can
retroactively establish update times throughout a historical constant interval.
Historical temperature coverage therefore remains a source-contract question;
do not substitute present freshness or another sensor's activity for that proof.

### Follow-up: weather station packet-age evidence

A subsequent metric-source lookup located WeatherData_HealthStatus, and the
live item/link inventory identified WeatherData_WH65B_AgeSeconds (outdoor) and
WeatherData_WH32B_AgeSeconds (indoor). Both are persisted independently of
temperature changes. The earlier bounded name search did not establish their
absence. The two temperature Items map to http:url:weatherData; the health and
age Items map to http:url:weatherHealth. Both Things were ONLINE with a
30-second refresh. The health status is lowercase in the producer; existing
analytics normalizes case before comparing it.

The same September 4 local-day read-only query, bounded to 10,000 rows per
source, found:

| Companion | In-window changes | Maximum age | Packet-age-only coverage at 180 seconds |
| --- | ---: | ---: | ---: |
| WH65B age | 2,878 | 52 seconds | 100.0% |
| WH32B age | 2,880 | 91 seconds | 100.0% |
| Aggregate health | 2 | Not applicable | Changed between ok and degraded |

That exploratory coverage clips each original persistence event's age allowance
at the next event and the window end, with pre-window carry-in. It measures
packet-age evidence only, not validated temperature coverage or outcome quality.
The 180-second allowance matches the live sky-condition rule's WH65B gate; it
is not yet an approved outcome-source contract. Do not hold a numeric age
constant indefinitely or replace its original event time with a synthetic
window boundary. Producer ages are rounded to whole seconds, which a final
contract must account for conservatively.

Verified source path: weather.service runs weather:app from /home/sat/bin;
rtl_weather.service runs /home/sat/bin/rtl_weather.py. The receiver's /health
endpoint derives age from in-memory per-model receive timestamps and declares
degraded if any recorded model exceeds five minutes. The live sky-condition
rule deliberately accepts OK or DEGRADED when the WH65B age passes, because an
unrelated add-on sensor can degrade aggregate status. A global OK-only gate
therefore does not express source-specific health.

Remaining provenance limits are concrete: weather.py refreshes a model's
timestamp before validating its fields and can reuse a persisted temperature
when a field is missing or invalid. The normal RTL producer requires temperature
keys, but that is not a per-field freshness guarantee for every receiver request.
The WH65B producer filters station ID 206; the inspected WH32B path does not pin
one station ID. An empty receiver sensor map also reports aggregate ok, which
cannot prove any particular sensor is present after restart. Thus the new
companions improve the available evidence but do not alone close per-quantity
validation, source-epoch, restart, or field-fallback gaps. No producer, binding,
persistence, or quality policy was changed during this preflight.

## Reproduced daily-quality defect

Current Solar_PV earthship_energy/quality.py computes timestamp-threshold coverage
from expiry alone. A pure synthetic probe supplied a one-day window and a
heartbeat dated one day after its end at both boundary records. With a 720-second
expiry, assess_source_quality returned coverage=1.0 and quality=ok.

That is a reproducible validation defect, not evidence that live heartbeat values
were future-dated. Future evidence must not authorize earlier time, and synthetic
boundary carries must preserve the original evidence timestamp needed to validate
that relationship. The upcoming outcome assessor must not blindly reuse this
path. Its tests need future stamps, carry-in provenance, known faults, unknown
epochs, restart gaps, and genuine unchanged-but-healthy intervals.

This defect is part of the requested all-algorithm change-only audit. No existing
EFC totals or learned parameters were recomputed, relabeled, or changed here.

## Reproduced hourly-learning change-event selection

The existing forecast_intel.score_hourly_targets queries temperature changes
within 15 minutes of elapsed targets, selects the nearest event (earlier on a
tie), updates the local-hour Kalman bucket, and consumes that target. It does
not query an independent source-health companion or explicitly obtain the
value in effect at the target from pre-window history.

A pure in-memory probe of the current function used a raw prediction of 74 F
at September 4 noon, evaluated 30 minutes later. With no change events it
scored zero and retained the target. With only an 80 F change five minutes
after the target it scored once, set the initial bucket bias to -3.173 F, and
consumed the target. No live model or persisted state was changed by the probe.
This proves event-time selection, not that either synthetic case represents
actual sensor conditions. A known healthy 70 F carry at noon followed by an
80 F later change would require different target-time treatment; missing
health evidence must still remain unscored rather than assuming that carry
is valid. An empty change window is likewise not proof of a failed sensor.

The existing unit tests explicitly pin nearest-event matching and therefore
must change with an approved change-aware hourly assessment contract; they do
not currently verify target-time carry plus independent source freshness.
Do not replay or reset existing learned state based on this synthetic probe.
