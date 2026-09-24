# Discover BMS counter comparison: receipt preflight

Read-only OpenHAB/JDBC check on September 23, 2026. No BMS register, Thing,
Item, persistence policy, poller, or accounting value was changed.

The two existing counters are `BMS_Charge_Cycles` and
`BMS_Discharge_Count`. They link directly to the corresponding numeric
channels of two `modbus:data:discoverBms190:bmsCounters:*` Things. Their shared
poller is configured for a 30-second refresh; each data Thing requests an
unchanged-value update every 60 seconds. Both data Things and the poller were
ONLINE/NONE at readback, and both Item states were `1`.

The retained current OpenHAB event log shows both Items receiving state-update
events to `1` approximately once per minute through 12:33 MDT. JDBC maps them
to `item0557` and `item0558`, but neither table has a row since September 20.
Each table's latest persisted row is July 18, 2026, value `1`, preceded by a
July 14 row with value `2`. The absence of later JDBC rows is consistent with
the installed change-only persistence strategy and **does not** establish that
the counter poller is stale. Conversely, an ONLINE Thing and Item update do not
by themselves prove physical counter provenance or the meaning of a decrement.

The qualified EFC series and these manufacturer counters use different units
and time/epoch semantics. Do not equate today's held counter value with a
qualified daily receipt, subtract it from available-epoch EFC, or call the
July decrease a battery cycle. Before a defensible independent comparison,
establish the Discover register definitions and reset/replacement semantics,
capture original counter values with acquisition receipts, and define a
same-bank, same-interval comparison that treats missing/invalid/reset periods
explicitly. Keep existing counters and qualified EFC unmodified.

September 23 documentation follow-up: this OpenHAB path is the Conext Gateway
port-503, unit-190 Battery Monitor *device interface*, not a direct read of a
Discover battery's internal lifetime counter. Schneider's official
[990-6278A gateway Modbus map](https://solar.se.com/us/wp-content/uploads/sites/7/2022/02/Conext-Gateway-InsightHome-InsightFacility-Modbus-Maps.zip)
identifies register 110 (`0x006E`) as read-only uint16 “Battery Number of
Charge Cycles” and register 112 (`0x0070`) as read-only uint16 “Battery Number
of Discharges,” both unscaled. Those identities match the live OpenHAB data
Things. The [Conext Battery Monitor owner's guide](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/Conext-Battery-Monitor-Owners-Guide_975-0691-01-01_ENG.pdf)
describes its own history H1.6 as charge/discharge cycles and H1.8 as full
discharges reaching 0% SoC; it also documents a reset-battery-status function.
The installed LYNK II presents a *compatible interface*, but these references
do not prove how it derives or resets the values for this four-module Discover
bank. In particular, register 112 is not evidence of ordinary daily discharge
or EFC, and the observed July 2→1 decrement remains unexplained. The Energy
card now labels register 110 “Charge cycles” with an explicit separate-from-EFC
tooltip. A real comparison still needs original-device provenance and a
same-bank counter epoch, not just the gateway register names.
