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

## Heartbeat provenance reproduction after storage integration

On Solar_PV main 7f0b583, a pure in-memory reproduction through
`normalize_window_text_series` and `assess_source_quality` confirmed two distinct
failures for the ten-minute window beginning September 4 at 00:00 UTC:

- A heartbeat observed at window start but reporting a time one day after the
  window ends produces coverage 1.0 and quality `ok`.
- A carry-in observed an hour before window start but reporting window start
  also produces coverage 1.0 and quality `ok`. The text reader replaces the
  original observation time with window start before quality assessment sees it.

The production path in `daily.py` obtains freshness points through that same
text reader. Checking a reported timestamp only against the normalized boundary
would leave the second defect intact. The correction must preserve the original
observation timestamp for health validation, reject reports future-dated at that
observation, and clip valid coverage to the requested window. General text
duration consumers still need their existing clipped intervals; do not change
their meaning incidentally. No live data, learned state, database or service was
modified by this reproduction. Both defects remain unfixed at this checkpoint.

## Follow-up: BMS producer heartbeat is not validated SoC evidence

The historical reader/quality defects above were subsequently corrected and
released; see `2026-09-05-analytics-corrective-release.md` in the plans directory.
That correction does not validate what the heartbeat producer actually observed.

Read-only retrieval of live rule `hex_bms_soc_scale` on September 5 yielded
script SHA256 `45dcb2234e30ae954b8f6e661fef34cf2e1975593cbb11d21a249cf2a10ce8a8`.
It refreshes its raw-last-seen cache and five-minute heartbeat before numeric
validation, on either a raw SoC update or a scale-factor change. Invalid raw
65535 is rejected for scaled output; an unavailable scale factor falls back to
zero. Neither prevents that earlier heartbeat refresh.

A Node VM replay of that exact retrieved script used only in-memory Item/cache
stubs, an Instant-only Java stub and no network or notifier access. At fixed
time 2026-09-05T19:40:00Z, retained SoC 99 and a four-hour-old cached observation:

| Trigger/input | Retained SoC | Heartbeat posted | Comms posted |
| --- | --- | --- | --- |
| Raw update: raw 99, scale 0 (control) | 99 | Current fixed time | OK |
| Raw update: raw 65535, scale 0 | 99 | Current fixed time | OK |
| Raw update: raw 99, scale UNDEF | 99 | Current fixed time | OK |
| Scale-factor change: raw 99, scale 0 | 99 | Current fixed time | OK |

Thus heartbeat plus comms OK alone cannot establish a newly validated SoC
observation. This is a deterministic synthetic reproduction, not evidence that
these invalid cases occurred in the sampled live day. Healthy unchanged raw
updates must continue to count as fresh; persistence remains change-only.

A targeted read-only REST event sample omitted event-source metadata. That
omission does not establish the rule-internal source value or restart behavior.
The installed core bundles are version 5.2.1; restoration versus binding-update
provenance still needs verification before selecting the corrective contract.
No production rule, control gate, heartbeat, learned state or history was changed.
Existing historical heartbeat coverage must not be relabeled as validated SoC
coverage until this producer gap and source epochs are addressed.

### Binding/restoration distinction verified in version-matched source

Read-only tracing of official openhab-core tag 5.2.1 establishes the following
mechanism, without restarting OpenHAB or injecting an event:

- `PersistenceManagerImpl` restores through `GenericItem.setState` with source
  `org.openhab.core.persistence`, retaining the persisted update/change times.
- `GenericItem` emits `ItemStateUpdatedEvent` with the supplied source.
- `ItemStateTriggerHandler` subscribes to that updated event for
  `core.ItemStateUpdateTrigger` and passes the original event to the action.
- `ProfileCallbackImpl` publishes binding updates with delegated source
  `org.openhab.core.thing` plus the linked channel identity.
- The installed JavaScript bundle's `node_modules/openhab.js` and globals bundle
  both convert the original event's `getSource()` to `event.eventSource`.
- The version-matched REST SSE `EventDTO` contains only topic, payload and type.
  Its source omission is therefore a transport limitation, not evidence that
  the rule cannot distinguish persistence from binding updates.

The live raw and scale links are respectively
`modbus:data:schneiderBatterySunSpec:battery802Core:socRaw:number` and
`modbus:data:schneiderBatterySunSpec:battery802Core:socSf:number`.
Installed persistence and profile class constant pools agree with the source
identifiers above. This verifies an available qualification mechanism; it is
not an end-to-end live restart test or permission to trust arbitrary delegated
source strings. A corrective implementation must test exact source matching,
invalid values, delayed/restored events, scale-only updates and startup with
unchanged scaling. Merely rejecting scale-change heartbeat updates does not
establish fresh scale provenance after restart.

Primary references: official openhab-core 5.2.1
[persistence restoration](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.persistence/src/main/java/org/openhab/core/persistence/internal/PersistenceManagerImpl.java),
[Item updates](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core/src/main/java/org/openhab/core/items/GenericItem.java),
[trigger handling](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.automation/src/main/java/org/openhab/core/automation/internal/module/handler/ItemStateTriggerHandler.java),
[binding profile](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.thing/src/main/java/org/openhab/core/thing/internal/profiles/ProfileCallbackImpl.java), and
[REST event DTO](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.rest.sse/src/main/java/org/openhab/core/io/rest/sse/internal/dto/EventDTO.java).

### Live WebSocket follow-up supersedes the trigger-source assumption

The WebSocket event DTO, unlike REST SSE, can expose source. A bounded,
authenticated, read-only subscription on September 5 observed both raw and
scale `ItemStateUpdatedEvent` messages with no source field. A second targeted
subscription observed the same raw input path at both stages:

- `ItemStateEvent`, topic `openhab/items/BMS_SOC_Raw/state`: exact source
  `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:socRaw:number`.
- `ItemStateUpdatedEvent`, topic `openhab/items/BMS_SOC_Raw/stateupdated`:
  source omitted, with payload keys lastStateUpdate/type/value.

Only connection filter/heartbeat management messages were sent. No Item event,
command, state mutation, rule invocation or credentials were printed or stored.
Both bounded observation sessions completed normally.

Root cause is in official 5.2.1 `ItemEventFactory`: event reconstruction routes
updated events through `createStateUpdatedEvent(topic, payload)`, which passes
null for source. The earlier investigation traced creation and trigger handling
but missed this reconstruction boundary. Its conclusion that source-qualified
ordinary UPDATE triggers were usable on this runtime was premature. Installed
core/thing/WebSocket cache bundles all identify as 5.2.1; the cached thing bundle
hash matches the distribution JAR.

The draft independent producer in worktree `.worktrees/bms-soc-evidence` has
42 passing exact-script tests and 274 passing OpenHAB tests, but their constructed
updated events carry a source the live events lack. It is paused before source
commit or deployment. Green tests do not validate this runtime assumption.

Safe next contract investigation: the live `core.GenericEventTrigger` supports
exact topic/type selection and returns the original event. Both raw and scale
Modbus Things also expose native DateTime `lastReadSuccess` and `lastReadError`
channels. The binding's version-matched `processUpdatedValue` stamps success
after processing a register response, even if a field transformation failed;
numeric field validity must therefore remain independently checked. Do not
substitute rule receipt time for a sensor/read timestamp without explicitly
changing that contract. Do not loosen the exact source match or patch the
installed OpenHAB core merely to make this draft pass.

Other live release facts: the proposed output Item and rule are absent (404),
startlevel100 is supported, and JDBC already has wildcard everyChange plus
restoreOnStartup with no cron strategies. Adding the observer does not require
changing that persistence configuration. Original scaler/watchdog/SouthOutlet/
night-load script hashes remained unchanged during these read-only checks.

References: [WebSocket API](https://www.openhab.org/docs/configuration/websocket.html),
[5.2.1 event reconstruction](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core/src/main/java/org/openhab/core/items/events/ItemEventFactory.java),
[5.2.1 Modbus processing](https://github.com/openhab/openhab-addons/blob/5.2.1/bundles/org.openhab.binding.modbus/src/main/java/org/openhab/binding/modbus/internal/handler/ModbusDataThingHandler.java).

## Nonfinite numeric carry can become apparently healthy zero power

An isolated pure probe of Solar_PV main 3b82b94 confirmed the numeric reader
accepts NaN/+Infinity/-Infinity in pre-window carry while rejecting identical
in-window values. It creates synthetic start/end points from that carry.
`aggregate_power` clips NaN and negative infinity to zero before shared finite
validation, yielding energy0, coverage1 and qualityOK for a one-hour synthetic
window. Positive infinity is rejected downstream. This proves a reader validation
gap, not an observed invalid production sample or historical corruption. Apply
the same finite-value check to carries before normalization/clipping; preserve
change-only semantics and existing history. No backfill or source edit was made.

Follow-up release: the finite-carry correction was tested, independently reviewed
and fast-forwarded into Solar_PV main/origin at `91867f8c79bf894d608ec0f052d343fe19eb2bc6`.
Its only production-code change applies the existing finite check to selected
carry values. Regression evidence: RED17fail/10pass, GREEN27pass, full296pass,
and integrated296pass in7.29seconds. The full September4 read-only snapshot
remained identical to baseline, with canonical JSON SHA256
`16c37713e2855d93a892c4b573c5828656f3f90dfc24f5e744f809a034c0d080`.
The normal daily service's working directory and PYTHONPATH point to this main
checkout; no service invocation/restart or data rewrite was needed. Timer remains
active for September6 00:20MDT, and its next result remains unverified. Source
rollback can revert this exact commit without restoring or deleting history.

## UI history boundary audit

The main page requests local-midnight-to-now for temperature extrema, load
energy and gust maximum. `createClient.getHistory` sends starttime/endtime but
does not request boundary evidence; `historyExtrema` uses returned values plus
the current value without obtaining the state in effect at window start.

Read-only JDBC REST requests for outdoor temperature on September4 confirm the
distinction. The complete local day returned1064 change records, first at
06:02:45.525Z rather than midnight06:00Z. With boundary=true it returned1066
records: a start record65.48 at06:00Z and an end record57.92 at next midnight.
The last actual in-window change was57.74 at05:59:16.420Z.

A bounded historical window06:01Z through06:03Z returned only65.3 at
06:02:45.525Z without boundaries. With boundaries it returned65.48 at06:01Z,
that65.3 change, and65.48 at06:03Z. The current pure extrema helper therefore
reports H/L65.3/65.3 from changes alone, versus65.48/65.3 when the known prior
state is included. This is a concrete carry-in omission, not proof that the
full-day September4 extrema happened to be wrong.

Version-matched PersistenceResource source explains both synthetic boundaries:
the last record before start is moved to start; the first record after end is
moved back to end. Enabling boundary=true globally would therefore introduce
look-ahead. It would also lose the carry's original observation timestamp.
Boundary records cannot establish source freshness or learning coverage.

A UI-only repair must explicitly distinguish plotting/statistical carry from
telemetry freshness: obtain the start state, exclude end/look-ahead values,
retain the requested local-day identity across midnight and delayed responses,
and leave missing/invalid state explicit. Any extension to the query end must
use the last earlier state, not the API's future boundary. Source-health/epoch
qualification remains a separate requirement; this audit does not authorize
carrying values across faults as verified measurements. Do not alter the
rolling24h Item contracts used by Weather/Earthship to fix Home's local-day view.

Also identified for follow-up: Home retains its previous day arrays until the
five-minute history refresh completes; its wall-clock tick does not invalidate
the day identity. The shared Sparkline uses a category axis, placing irregular
change events at equal horizontal spacing. Those are code-derived review
targets, not yet browser-reproduced regressions or completed fixes.

Reference: [OpenHAB5.2.1 PersistenceResource](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.rest.core/src/main/java/org/openhab/core/io/rest/core/internal/persistence/PersistenceResource.java).
All requests were read-only. No production source, persistence configuration,
historical data or live controls were modified during this audit.
