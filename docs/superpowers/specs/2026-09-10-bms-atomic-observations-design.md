# BMS atomic source observations — approved replacement

Sat approved extending the design to source-generated value/timestamp records
(Hexmem 8689), then approved this written design at 43ccb08 (Hexmem 8691).
Implementation may proceed under this contract. The September 5 staged rule
remains unusable and undeployed; approval does not qualify it for activation.

## Source boundary

Use two dedicated observational Modbus data Things under the existing
`battery802Core` poller, extracting the existing unsigned raw SoC register 40255
and signed scale register 40300. Do not change the existing Things, scaler,
poll interval or control inputs. New Things must have no write configuration
and no command-producing links. Verify that they subscribe to the existing
poll result rather than registering additional poll requests before deployment.

Link only each new Thing's String channel to its new observational String Item.
Each Thing uses a dedicated read transformation that returns one closed JSON
envelope containing version, field identity, strict raw input text and a UTC
millisecond timestamp generated in that same transformation invocation.

This timestamp means **binding read-processing observation time**, not a BMS
hardware clock or an independently measured physical sampling instant. It is
attached before event-bus delivery and travels with the exact transformed value.
Delayed delivery cannot acquire a new timestamp by joining a later heartbeat.
The observer never fills in a missing timestamp from its own invocation time.

The version-matched binding processes extracted registers through
`processUpdatedValue` and then `ModbusTransformation.transformState`; transformed
text is parsed to the linked channel's accepted state type before publication.
The live binding offers a String channel and JavaScript Scripting is installed.
This supports the proposed seam but does not replace an installed-runtime
transformation test. Missing transformation support is a failed preflight, not
permission to silently use an event-receipt timestamp.

Separate native timestamp links are no longer used to pair samples. Their
previously established independent cadence and unordered publication cannot
provide the required association. Do not install redundant timestamp Items.

## Envelope and observer

Proposed input envelope fields: version=1, field=`raw` or `scale`,
observedAt=integer UTC milliseconds, value=the original numeric state text.
No Item snapshot lookup, network call, persistence call, timer, command, or
dependency import belongs in the transformation. It must return invalid inputs
as explicit invalid evidence rather than substituting a previous numeric value.
Transformation errors or blank/malformed output do not qualify a sample.

The observer receives original ItemStateEvent for each exact new Item topic.
Check exact new binding/channel sources inside the rule, not in the generic
trigger's source filter; foreign events must invalidate the corresponding cache.
Source text is provenance within the trusted OpenHAB installation, not protection
against privileged code that can forge event sources.

Reject unknown envelope fields/version/field, malformed JSON, invalid numeric
text, unqualified or future timestamps, timestamps older than the observer's
current cache epoch, and observations older than 120 seconds. Preserve original
timestamps on accepted state; duplicates or earlier trusted observations cannot
refresh it. Retain unsigned raw 0–65534, signed scale -32767–32767, finite scaled
SoC 0–100, and nonzero-underflow rejection from the existing design.

Keep raw and scale independently fresh; this does not assert simultaneous
register acquisition. On an actual scale-value change, invalidate raw evidence
and require a newly observed raw value at or after that scale change. Repeated
unchanged scale envelopes refresh scale freshness without invalidating raw or
refreshing raw time. Initial unknown-to-known scale establishes the same barrier.
This can conservatively delay startup readiness by one poll; do not synthesize
a sample to avoid that delay.

Comms must remain OK and device present must remain 1. Faults, missing health
companions or observer-cache restart clear both inputs and require post-barrier
binding observations. Never restore qualifying state from persisted Items.

## Atomic output and history

Keep one `BMS_SOC_Evidence_JSON` output with the original closed record shape:
version, streamEpoch, recordedAt, status, reason, observedAt, scaleObservedAt,
validUntil and soc. The clarified observedAt fields now mean the source envelope
times defined above; no record from the invalid original proposal was deployed.
ValidUntil is min(raw observedAt, scale observedAt)+120000. Invalid records have
null measurement fields. Publish status/reason/value changes immediately and
otherwise a valid heartbeat no more often than every 60 seconds. Publication
failure must not advance the successful-publication cache.

Coverage starts no earlier than original output persistence time and recordedAt,
ends at validUntil, and breaks on faults and stream-epoch changes. This is an
observational validity contract, not proof of battery calibration or upstream
gateway freshness beyond the read source's own guarantees.

Preserve everyChange plus restoreOnStartup. The timestamped input envelopes
will change on each successfully transformed poll, so assess their incremental
JDBC storage volume explicitly before activation; never alter global persistence
or add a parallel history store to conceal that cost. No legacy history backfill,
learned-state reset or change to existing freshness/control gates is included.

## Verification and rollout

Tests must exercise the real transformation scripts with injected source clocks,
and exact observer script events. Cover delayed/reordered delivery, malformed or
missing transformation output, both field arrival orders, unchanged values,
scale changes, clock rollback/future data, source mismatch, restart and faults.
Tests must deny every output except the observer's single JSON Item and deny
all commands and networking from scripts.

Release prerequisites: verify exact installed transformation syntax and engine;
verify the shared poller subscription and absence of write configuration; estimate
event/storage volume; review create-only resource descriptor; snapshot affected
resources; and verify existing control/scaler/persistence hashes unchanged.
Install new resources disabled, then qualify natural original events and atomic
timestamps before any reader migration. UI, sanity checker and analytics must
not switch to this signal until the live contract is demonstrated.

Rollback disables the new observer and observational sources, preserves their
history, and restores only changed reader configuration. It does not restore the
broken draft or modify physical controls. Task 82 remains held; broader weather
source validation, outcomes and threshold tuning remain unfinished.
