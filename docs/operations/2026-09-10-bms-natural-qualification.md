# BMS natural source qualification — September 10

Authority: approved atomic observation design43ccb08 / Hexmem8691. Disabled
installation was verified at2b430f2. This checkpoint qualifies the two new
observational sources, not the observer output or any downstream reader.

## Method and safety

The REST event stream exposes topic/type/payload but omits original source
identity. A short-lived rule therefore logged only the two new original
ItemStateEvents. It made no Item writes, commands, persistence queries or network
calls. The root helper enabled only the two reviewed read-only source Things;
it never invoked runnow, changed the shared poller or enabled the observer.

Acceptance required at least five events per field, exact Item topic and binding
String-channel provenance, closed version1 envelopes, strict ASCII integer
values, increasing original timestamps bounded by activation and receipt, and
unchanged numeric values with advancing timestamps. Existing rule definitions,
raw/scale/poller configurations, links and persistence were compared before/after.
Observer DISABLED and output NULL were independently checked.

The helper was independently reviewed. Review found failure cleanup initially
stopped at the first disable error; corrected cleanup independently attempts
every source, aggregates errors, and disables sources if diagnostic removal fails.
Two offline failure-path tests had missing-function RED then GREEN. Nine offline
validator checks and three strict version/ASCII parity checks passed. Final PASS
is emitted only after ownership-checked diagnostic removal and absence readback.
Helpers remain in the preserved worktree's ignored `.superpowers/sdd` directory.

## Live wrapper discovery and observer defect

The first attempt failed with `Original event unavailable`. It was not counted
as qualification: both sources were disabled and the diagnostic removed.
A subsequent metadata-only natural-event probe showed `event.raw` is a Java
HashMap with keys `[raw.event, ruleUID]` for trigger id `raw`, rather than a plain
`event` key. That probe was also removed and its source disabled.

This exposes a deployed-but-disabled observer defect: its initial accessor only
looked up `event`. Offline fixtures had not represented the live trigger-prefixed
map. Do not enable that observer until the accessor fix passes live-shape tests
and independent review. No fallback to Item snapshots or receipt timestamps is
authorized. Missing or ambiguous original events must not qualify observations.

## Successful source receipt

After correcting only the diagnostic accessor to accept exact trigger-prefixed
keys and reject ambiguous candidates, independent delta review passed. Probe
`hex_bms_natural_probe_b954b1b8534240fcbc3d265962b187b8` qualified five natural
events per field. Both streams spanned original timestamps1789076498270 through
1789076518846 (20.576seconds), with unchanged raw100 / scale0 and fresh timestamps.
Exact sources matched `org.openhab.core.thing$` plus each reviewed String channel.
The diagnostic was removed and absence verified; both sources remained ONLINE.
Existing baseline definitions were unchanged. Observer remained DISABLED and
`BMS_SOC_Evidence_JSON` remained NULL.

Read-only JDBC history queries found all five matching records for each source.
Persistence-minus-source timestamp lags were raw[2,8,7,7,8]ms and
scale[3,7,6,8,9]ms. This confirms natural source history, including unchanged
numeric observations, under existing everyChange persistence. It is a short
cadence sample, not a long-term physical storage-growth measurement.

Earlier failed-probe source observations remain in history; none were fabricated
or deleted. They are not observer output and do not authorize downstream coverage.
The source timestamp remains binding read-processing time, not hardware sample
time or independent gateway freshness. Next gates: fix/review/deploy the disabled
observer, qualify its natural outputs and persisted coverage, then migrate readers
under their own reviewed contracts. Task82 remains held.

## Observer correction and healthy-window qualification

The accessor correction is now integrated and published at9840831, comprising
c363392 and639424b. Actual trigger-prefixed wrappers are accepted. Recognized
ambiguous wrappers clear both inputs and establish a fresh barrier; null or
malformed recognized source wrappers invalidate evidence. Eventless timer/startup
maps remain neutral. Review rejected the first ambiguity test because it retained
valid cached data; corrected regressions cover hidden health events and fresh
post-barrier recovery. Focused105 and isolated full1261 tests passed (excluding
one root-owned standalone Node helper from Vitest discovery). Fresh merged-main
verification passed1280 tests in91files and build; only the existing large-chunk
warning remained. No UI source changed.

The installed rule was first verified DISABLED with its exact prior definition
and source hash. Only its action script was replaced; full DTO readback matched
and the rule remained DISABLED. A private pre-update snapshot was generated at
`/tmp/bms-observer-before-accessor-jzib_x4o.json` (temporary evidence, not durable
backup). Installed corrected source SHA-256:
`b55d4e002379087fb5cc8f39dc56761951f3c87a4e1519d27bfc680e752d824b`.

The independently reviewed natural-output helper then enabled only the observer
with POST text/plain true. No runnow, synthetic inputs, commands, reader changes
or history deletion occurred. PostgreSQL queries were read-only with5second
connect timeout,3second statement timeout,1000-row caps and a180second observation
deadline. They matched output timestamps to exact version/field/numeric source
envelopes, checked the closed output shape, common UUID epoch, original timestamp
bounds, scaled SoC, nonzero-underflow rejection and exact120second validity end.

Verifier review found two acceptance gaps: filtering unavailable records before
heartbeat detection could bridge a fault, and nonzero underflow could be accepted
as zero. Regression tests failed before correction and then passed3/3; seven
other validator cases had passed. Heartbeat detection now uses adjacency in the
full persisted output history, with equal SoC, epoch and at least60seconds elapsed.

Live qualification PASS:

- Epoch `864142d5-99ee-4b7a-b5fc-e6a96e7274d8`.
- Initial unavailable record recordedAt1789077092793, then five valid records.
- First valid recordedAt1789077103661, SoC99, raw timestamp1789077103659,
  scale timestamp1789077098023, validUntil1789077218023.
- Final accepted valid recordedAt1789077223464, SoC100, raw timestamp1789077223463,
  scale timestamp1789077218137, validUntil1789077338137.
- Adjacent unchanged100percent records at1789077160079 and1789077223464 establish
  a63.385second heartbeat. Intermediate99/100 changes earlier in the window were
  immediate value publications, not falsely counted as heartbeats.
- Final current output was valid/unexpired; companions were OK/device1 and the
  observer was IDLE. Other rule definitions, persistence, links and existing
  raw/scale/poller configurations matched the pre-enable baseline.

Observer and both observational sources remain enabled and collecting real
history. The earlier disabled/NULL descriptions above are historical checkpoints.
This establishes natural healthy output and steady-value heartbeat behavior,
not live fault/expiry/restart qualification or sufficient full-window outcome
coverage. Existing UI/checker/analytics readers remain unchanged. Migration must
preserve the approved source/persistence-time coverage and epoch boundaries;
legacy history cannot be promoted into this newly established evidence stream.

## Natural expiry and source recovery

A reviewed bounded check paused only `socRawObservation` and
`socScaleObservation`. Existing BMS acquisition/poller, controls, health Items,
reader definitions and observer triggers remained unchanged. No synthetic Item
states or manual rule executions were used. The helper tracked attempted source
changes before requests and independently restored each source in finally;
an offline first-restoration-failure check proved the second restoration was still
attempted. Recovery cannot turn a failed expiry assertion into a successful test.

Both new sources were confirmed DISABLED, then their source envelopes remained
unchanged throughout the pause. The observer naturally published an exact accepted
source anchor: raw/scale observedAt1789077489701, recordedAt1789077600793,
validUntil1789077609701, SoC100. This tied expiry to accepted data, not assumed
Item snapshot association. Original BMS comms/device and poller health were checked
throughout the wait.

At now1789077609963, the current record still said valid although its validity
deadline had passed262ms earlier. That is expected with a one-minute cron:
**readers must reject expired validUntil independently of status**, and historical
coverage must end at validUntil rather than a later unavailable publication.

The natural cron published unavailable/input_stale at1789077660794,51.093seconds
after the exact expiry deadline. All four measurement fields were null. Both
sources were restored and independently verified ONLINE. Fresh recovery was
recorded at1789077665425 with raw/scale observations1789077665422, SoC99 and
validUntil1789077785422, all after restoration began. The stream epoch remained
`864142d5-99ee-4b7a-b5fc-e6a96e7274d8` throughout.

Bounded read-only JDBC queries verified the exact anchor, expiry and recovery
records, with persistence time no earlier than recordedAt. Baseline comparisons
for rules, links, persistence and existing raw/scale/poller configuration passed;
the observer was IDLE at final acceptance. The helper completed with
`expiry_recovery_qualification=PASS`. Both observational sources and observer
remain enabled. Preserve the real observation gap; no history was deleted.

This closes the live source-pause expiry/recovery check. It is not an induced
physical BMS fault or a process/cache restart test. Reader migration and sufficient
completed-window outcome coverage remain unfinished; task82 remains held.
