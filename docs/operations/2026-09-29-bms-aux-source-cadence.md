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
