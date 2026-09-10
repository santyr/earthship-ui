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
