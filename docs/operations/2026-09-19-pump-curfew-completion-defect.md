# Natural pump curfew and stale completion callback

Live rule remained hash
e28f2616dcd830cd41bf7433f4f0ee6e36de7d6e32d2a3d00c5a6913eec8b375,
including the concurrent15-minute timing and earlier hour/busy repairs. No rule
edit or hardware command was issued during this observation.

Natural evidence September19MDT:

1.18:53:03.334: automatic South cycle start recorded; SouthON/EastOFF observed.
2.19:04:51.935: the rule commanded SouthOFF; status after_dark,sunElev=-0.7.
3.19:04:52.269: subsequent binding update confirmed SouthOFF. East stayedOFF.
4.19:08:03.336: the old timer commanded OFF again, advanced LastCycle and posted
  cycle_completed despite the earlier curfew interruption.

Source explains the result: forceOff removes BUSY_KEY and de-energizes pumps,
but beginCycle's callback does not recheck its invocation token before posting
completion or commands. A superseded timer must not claim completion or affect
a newer owner. A full15-minute uninterrupted physical cycle was NOT verified.

The bounded monitor exited after LastCycle advanced900.002seconds after start.
Its narrow expected-duration/both-off check reported true, but the actual event
sequence disproves continuous operation. That monitor output is not completion
evidence. Future verification must include interruption/ownership history and
must not infer success solely from LastCycle or a terminal OFF state.

Next correction: reproduce curfew interruption and superseded-token callback
in the isolated rule harness; preserve all curfew/SoC/comms gates and exact live
15-minute timing; guard callback ownership before commands, ledger or completion
writes. Inspect manual interrupted-ledger behavior as part of the fix. No
historical LastCycle value should be rewritten to fabricate a corrected history.
Actual uninterrupted natural-cycle verification remains outstanding.
