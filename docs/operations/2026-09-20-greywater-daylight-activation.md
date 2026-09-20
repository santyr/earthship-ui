# Timer-driven daylight greywater operation — September 20

Operator explicitly requested replacing08:00–20:00 with dynamic sunrise/sunset
operation, then simplifying automatic evaluation to a timer. Source93b0975 was
refined bya2f50be before deployment; the intermediate sun/voltage/SoC trigger
plan was never installed.

The enabled live `hex_southoutlet_cycle` now has exactly two triggers:

- `cron`: `timer.GenericCronTrigger`, `0 * * * * ?` — once per minute.
- Existing `SouthOutlet_ManualRequest` command trigger — immediate UI requests.

There are no outer time-of-day conditions. Voltage, SoC and sun-elevation change
triggers are removed. The unchanged script checks sun elevation>0 on each tick;
zero, negative, missing or invalid elevation refuses operation and stops an active
cycle. Sunset and other safety changes are acted on at the next timer evaluation,
normally within one minute. This uses reported Astro elevation, not a new solar
calculation or a new irradiance threshold.

All existing controls remain:15-minute cycle timer,60-minute start spacing,
local-hour South/East alternation,90%SoC threshold under CLEAR skies and98%
otherwise, low-SoC stop, voltage/comms gates, manual-request ledger and callback
ownership protection. The24-hour fallback label does not bypass SoC eligibility.
No actuator command, forced rule run, gate bypass or OpenHAB restart was used.

## Verification and recovery

- Full unit suite:97files,1381tests passed. New tests cover timer-only automatic
  triggers, preserved manual requests, known-window-only removal, drift refusal,
  daytime outside old hours, sunset interruption and retained safety gates.
- Live script is byte-identical to the prior repaired source:
  `f045608ba43d08f6bcaa53d70d5c1851df0f3c0410ef480ac6cef4ca98b969f6`.
- Both pumps were OFF and SoC below automatic eligibility before the transaction.
  Backed up the complete rule, disabled it, rechecked the exact original definition,
  replaced only conditions/triggers, read back the exact desired definition,
  and re-enabled it. Final statusIDLE/NONE; pumps remained OFF.
- Private successful receipt:
  `/tmp/greywater-daylight-c_bkdego/` (0700 directory;0600 original,desired,verified JSON).
  The original-rule JSON is the rollback definition. Recheck ownership and both
  pump states before any later rollback; do not overwrite concurrent changes.
- An earlier attempt stopped before replacement on an incorrect disabled-status
  assertion, then re-enabled and verified the unchanged original rule. Correct
  OpenHAB status is UNINITIALIZED/DISABLED, not a top-level DISABLED status.
- Natural timer evaluation verified07:38:01MDT, without `/runnow`:
  `reason=low_soc,soc=84.0,threshold=98,sky=PARTLY_CLOUDY`.
  Both pumps OFF, no outer conditions, only the two intended triggers.
- No new rule ERROR/Exception appeared in the checked post-update log window.

Natural eligible full-cycle and sunset-interruption evidence remains outstanding.
The managed-resource builder and manifest retain the new trigger/condition policy;
this narrow live update intentionally did not deploy the historical single-pump
source or its older metadata over the current two-pump rule.
