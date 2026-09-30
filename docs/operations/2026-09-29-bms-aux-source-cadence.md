# Native BMS auxiliary publication cadence

At 20:42:56 MDT September 29, the guarded adapter
`scripts/bms-aux-source-cadence.py --apply` changed only
`updateUnchangedValuesEveryMillis` from 60000 to 0 on these managed data
Things:

| Thing suffix under `modbus:data:discoverBms190:bmsMain` | Native register | Item |
| --- | --- | --- |
| `capRemainAh` | 88, uint32 | `BMS_Capacity_Remaining_Ah` |
| `tempRaw` | 74, uint32 | `BMS_Temperature_Raw` |

Both remain native, default-transform, read-only channels. The existing
holding-register poller remains ONLINE at 30,000 ms, start 64, length 34.
Its entire configuration, channel links and consumer definitions compared
equal before and after. No Item command, forced refresh, OpenHAB restart,
actuator change or provider transfer was performed.

The [official Modbus binding documentation](https://www.openhab.org/addons/bindings/modbus/#data-thing)
specifies that zero publishes unchanged states on each successful poll.
This increases publication of already-read values, not Modbus request
frequency. Failed reads do not update the data channels. Freshness therefore
continues to require the collector's original, source-bound ItemStateEvent;
the existing 120-second TTL is unchanged. This addresses the diagnosed
missed-renewal margin without extending the life of stale measurements.

## Guard and recovery evidence

The adapter requires the exact native register/type/transform settings,
read-only write settings, existing poller cadence, exact two links and
known consumer inventory. The auxiliary rule body must equal the source
collector. The other consumers are the legacy display-only runtime rule
and the SoC/temperature scaling rule; the latter triggers only on temperature
**changes**, not unchanged temperature updates. No protected pump-rule body
references either native Item.

An owner-private preimage containing both complete data Thing definitions
and guard inventory is retained at:

`/home/sat/.local/state/openhab-config-migration/bms-aux-cadence-43fu9_cu/preimage.json`

The directory is 0700 and file 0600. Failed apply restores only an exact
adapter-owned postimage; an unexpected concurrent edit is never overwritten.
Offline tests cover the exact single-parameter delta on both Things, binding transform-array form,
unsafe/write-enabled refusal, idempotence, ambiguous HTTP failure restoration,
and refusing concurrent-edit overwrite (9 tests). The producer suite passes
15 tests, including unchanged 30-second events producing only the existing
60-second heartbeat writes and expiring exactly at 120 seconds after native
events stop. The live apply passed exact readback and both Things recovered
ONLINE. A later read-only preflight returned both intervals as zero.
The adjacent runtime-estimator suite also passed (13 tests), for 37 affected
adapter/producer/runtime tests in total.

## Natural observation and remaining gates

A 155.590-second natural observation received six ItemStateEvents for each
Item. Both fields had five unchanged renewals, with successive intervals
30.010, 30.201, 30.326, 30.193 and 30.204 seconds. The REST event DTO omits
source provenance; it is cadence evidence, **not** independently authenticated
measurement evidence. The unchanged, source-validating auxiliary collector
also advanced naturally to sequence 1313, with both fields `valid/ok` and
their original 120,000 ms validity bounds. Its rate-limited persisted output
can carry a previous poll for one field; do not confuse that output cadence
with the native channel cadence or fabricate a newer observation time.

Seven natural JDBC receipts from 20:43–20:50 MDT preserved consecutive
sequence identities 1308–1314, both fields `valid`, and exactly 120,000 ms
validity. A read-only 20:44–20:50 half-minute replay had 13 ticks (12 `bms`,
one initial `evening`), no `off` source snapshots and no noncharging
time-to-full reversal. This short post-change interval does not qualify an
entire night; its numeric runtime still uses the unqualified load fallback.

Historical September 29 gaps remain immutable. The complete-day reader,
Energy publication and runtime replacement gates remain unchanged; a short
healthy interval cannot make an earlier partial day complete. Verify a full
post-change local day and fault/restart recovery before qualifying downstream
consumers. The unqualified 155 W night-load fallback is a separate issue and
was not fixed by this publication adjustment. Managed ownership also remains
a file-first migration exception, not a completed file cutover.

## September 30 complete-day reader and scaler assessment

The first full September 29 read found 1,461 original auxiliary receipts.
Two pairs, sequences 661/662 and 805/806, share recording millisecond
`2026-09-29T16:16:29.992000+00:00` and
`2026-09-29T18:28:49.750000+00:00` respectively. In each pair, persistence
advances by one millisecond and capacity advances to a genuinely newer native
observation; temperature is unchanged. The original producer intentionally
orders persistence stamps, so recording-clock precision alone cannot order
two independent native-channel updates. No clock regression, sequence gap or
malformed envelope was found.

The shared `validate_receipt_successor` now permits only ordered same-epoch,
contiguous-sequence, changed snapshots at a recording-time tie. A changed valid
field must carry a new observation at that same recording time; conflicting
equal-source-time values, duplicates, durable-time collisions, recording/source
regressions and same-clock epoch changes remain refused. Original observation
times and expiry are never extended. Unavailable barriers remain barriers and
cannot improve coverage. Both the daily reader and Solar_PV's default-off
current-health consumer use this validator. Eighty affected tests pass,
including same-clock updates through real restricted PostgreSQL, UI/sanity
health and exact expiry failures; owned fixtures are cleaned up.

The corrected real-day assessment remains **partial**, not healthy by decree:
remaining-Ah coverage is 0.9920707986111111 (624 gaps), native-temperature
coverage is 0.9989049074074074 (71 gaps), and neither field has an unavailable
barrier in this day. These are genuine original-event expiry gaps from before
the cadence correction, not change-only numeric timestamps. The conservative
read cutover is the first durable bootstrap at
`2026-09-29T05:14:44.776000+00:00`; no earlier history was backfilled.

The same-day derived Fahrenheit scaler now passes all 13 settled actual native
temperature transitions with zero mismatches and zero skipped transitions.
This closes observed dynamic value parity, not full-day source quality or
physical-network/full-JVM recovery. A complete post-cadence local day is first
possible September 30, assessable after October 1 local midnight.

Three previously absent read-only libraries were installed byte-exact at
`/home/sat/openhab/scripts`: `bms_aux_evidence.py` (SHA-256
`8e33db9902b742fa190b7f16abb364b4b12c95828ea51d4c77d637317bfc9bec`),
`bms_aux_history.py` (`acfebbff8ee49c3f8d7ba24f43c68825ca199c33f23b2a0fd73733194441d218`)
and `bms_temperature_parity.py` (`76abe84969fc8692a6447218dd20dc7e5e54dfb36804c9c752b0277fe0030d48`).
A restricted read using these installed modules returned true current original-
source health for both fields. No collector/rule restart, publication opt-in,
estimator activation, SQL write, threshold or hardware change occurred.
