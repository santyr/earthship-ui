# September 19 pump repair and temperature collection

The operator confirmed indoor WH32B ID235. Live mappings also establish outdoor
WH65B/WH24 ID206 and north-wall WH31E ID193; numeric temperature Items already
carry Point/Temperature tags. Semantic tags are not sensor identity. The new
whole-envelope String evidence Item does not need invented temperature tags.

The temperature reader feature was merged into main and128focused tests passed.
The corrected HTTP channel descriptor includes empty defaultTags/properties.
Proposed collection policy and service override are tracked alongside it:
120-second receipt expiry, explicit -40..140F acceptance bounds for three named
streams. These are operational acceptance bounds, not manufacturer specs.
26configuration/integration tests passed. Direct loading of the group-writable
repository policy correctly failed its ownership/mode guard; deployment must
install it as an owned0600file before validation. No policy/drop-in was installed:
permission review rejected the activation command before execution, citing
persistent service activation/restart and listener exposure. The existing live
service already binds0.0.0.0:5000; the proposed override preserves that listener
and the new evidence endpoint accepts loopback requests only. Activation still
requires resolution of that permission block. Neither qualified receipt
collection nor its learning consumer is enabled by this receipt.

## Pump failure and repair

Live errors September16–19 showed now().getHour() is not a function. OpenHAB's
JavaScript clock is JS-Joda; the API is hour(). Selection failed after acquiring
the shared busy token, explaining subsequent reason=busy with both pumps OFF
and LastCycleStart still September16. The repository's older canonical rule
does not match live timing/alternation, so it was NOT used to overwrite live.

Commit d27784a adds a live-derived snapshot in southoutlet-cycle-current.js,
corrects the hour call and clears only parseable expired busy tokens when both
pumps are explicitly OFF. Recent/future/unparseable tokens retain the interlock.
All1365unit tests/96files passed, including48greywater cases and401OpenHAB cases.
The offline regression reproduces both the old exception and subsequent latch.

Exact original backup: /tmp/hex-southoutlet-original-20260919.json, mode0600.
Original action SHA256:
8e89e09a95bce4b180c344c3e4d711de3b8ab286afbd62510fd9653b15ecd79f.
Our installed action SHA256:
14548b736d091ae2e5af5098a45fde6e308f783074dd1cefb457bd7cd67a59be.
Installation checked exact current definitions and pumpsOFF, disabled/read back,
replaced only the action, verified unchanged triggers/configuration and restored
enabled IDLE/NONE. No manual pump command or forced rule execution was used.

The natural17:51:59MDT evaluation started East; binding updates confirmed ON
while South stayed OFF. At17:53:16/20, another live rule update changed cycleMs
from10to15minutes. The new current SHA is
e28f2616dcd830cd41bf7433f4f0ee6e36de7d6e32d2a3d00c5a6913eec8b375.
Our hour/latch fixes remain present. The rule reload interrupted its active
cycle; orphan protection commanded EastOFF at17:53:20 and cooldown followed.
Do not overwrite that concurrent15-minute change or deploy the10-minute
snapshot without resolving ownership with the operator. Natural start and
orphan safety are verified, but a full timed cycle is NOT verified. The bounded
monitor was stopped after identifying this conflict; no background monitor
remains. Pump/source-health and broader learning work remain open.
