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
