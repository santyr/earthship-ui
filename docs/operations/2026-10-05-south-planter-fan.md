# South planter fan at 98% battery SoC

## October 5 daylight restriction

The operator subsequently required **daylight only**. The qualified rule is
hot-loaded, file-owned and IDLE with nine exact triggers. At 00:28Z October 6
(18:28 MDT October 5), native SoC is **98%**, sun elevation **1.62°**, and a
read-only TP-Link query confirms the fan physically ON, with outlet 2 OFF.

ON requires the original fresh battery gates, SoC >=98%, a fresh positive
`Sun_Position_Elevation`, and current time inside the existing
`Sun_Daylight_Start`–`Sun_Set_Start` window. Elevation must be at most 90° and
its native update timestamp must be present, non-future and less than 120 seconds
old. Event bounds must be valid, ordered and less than 24 hours apart. The
daily bounds prevent an old positive elevation restored at startup from
authorizing ON after sunset. Outside this window, at elevation <=0, or on
missing/invalid/stale sun input, the fan selects OFF. No new astronomical or
ventilation calculation is introduced.

Three additional Item-update triggers cover elevation and both daily bounds.
The unchanged 30-second cron also enforces clock boundaries and source expiry.
The rule uses the [native Item update timestamp API](https://openhab.github.io/openhab-js/items_items.js.html);
its behavior is verified in the actual isolated OpenHAB/Graal runtime.

Source SHA-256:
`bc269d77427c1fcf197844345992c30a240c7ca9922dbd984f035efa0373dedf`.
Thirty-two focused checks and **4,175** repository tests pass (10 skipped,
91 subtests). Independent source review is clear. Isolated native execution
passes threshold/daylight boundaries, positive-elevation sun-data expiry while
the battery evidence stays fresh, missing-input cold-JVM recovery and safe
source withdrawal. Its owned networkless container is removed; no hardware
links or production states enter the fixture.

The attended source update retains all **1,876** current Item-46 history rows
as an exact recoverable prefix. All other Item/rule/link definitions and all
55 other installed-source hashes match the preimage. Exactly two Open-Meteo
binding `last-updated` timestamps advance; their values are recorded explicitly.
PID **1696** is unchanged. A brief 404 while the file rule deregistered during
hot reload is reconciled by subsequent exact nine-trigger IDLE readback; the
one-shot installer is not rerun.

Private source preimage, history, isolated proof, tests, native registry and
physical readback are retained in the mode-0700 directory
`/home/sat/.local/state/openhab-config-migration/south-planter-fan-daylight-20261005-3_r5djhk/`.
The first natural post-update OFF occurs at **18:33:05 MDT**, with fresh SoC
97% and source-attributed `reason=soc_threshold`; its native Item-46 OFF row
is retained. At **18:38:09 MDT**, elevation is **−0.354°** and a separate
physical query confirms fan OFF and outlet 2 OFF. Because SoC already fell
below 98%, this pose does not uniquely attribute a live stop to daylight.
That specific >=98% night transition and household whole-JVM recovery remain
separate observation gates; native isolated >=98% night refusal is qualified.
The [current private restart baseline](2026-10-05-production-restart-attempt.md#daylight-rule-baseline-refresh)
now includes the daylight source, all 56 current source pins and 40 original
history prefixes; production restart still requires host authentication.
The earlier sections below describe the original deployment before this
operator-requested daylight restriction.

The operator requested automatic control of `SouthOutlet_Outlet1_Switch` and
confirmed **ON at SoC >=98%, OFF below 98%, OFF on stale/invalid telemetry**.
The file-owned rule `hex_south_planter_fan` is enabled and verified IDLE.
Its first natural evaluation at **2026-10-05 17:49:00.637Z** commanded ON using
fresh source-bound SoC **99%**. A read-only native TP-Link query independently
confirmed outlet 1, named `South Socket 1 Fan`, physically ON. Outlet 2, named
`South Socket 2 Fountain`, remained OFF.

## Behavior and ownership

Canonical source: `openhab/file-config/automation/js/south-planter-fan.js`.
Installed destination: `/etc/openhab/automation/js/south-planter-fan.js`.
SHA-256: `04fec2e147272c5726a1717a714cf08b9f0e1b938a67275a942262ea90fa2868`.

The fan uses the exact atomic `BMS_SOC_Evidence_JSON` validity contract already
used by the protected pump owner. It validates the closed schema, source epoch,
value range, source/record clocks and 120-second source expiry. A held `BMS_SOC`
display value cannot authorize ON. BMS comms must be `OK`, Schneider telemetry
must start with `OK,`, and native DC voltage must be valid and within 40–60 V.
Every invalid/below-threshold case selects OFF. This original deployment had
no daylight gate; the later restriction above supersedes that behavior. There
is no SoC hysteresis or fan duty cycle.

Six triggers cover atomic SoC updates, BMS/Schneider status changes, voltage
updates, fan state changes and a 30-second cron. The cron detects expired
receipts even when the producer stops updating. Commands go only to outlet 1;
matching states produce no redundant command. Repeated unacknowledged or failed
commands retry at most every 30 seconds. A changed target overrides that delay;
clock rollback cannot indefinitely suppress an OFF retry. Fan commands remain
subject to normal device communication and acknowledgement.

Live consumer review found no existing rule reference to outlet 1. The existing
`hex_southoutlet_cycle` uses outlet 2 and its source, triggers, ownership, daylight
curfew and scheduling are unchanged. The fan Item/provider, metadata and original
single empty-profile TP-Link link are unchanged.

## Evidence

- Offline execution of the actual JavaScript covers threshold boundaries,
  invalid schemas/clocks/values, missing inputs, stale health, receipt expiry,
  exclusive outlet 1 commands, pending/failed retries and clock rollback.
  Failed-command throttling and clock rollback were exercised RED then GREEN.
- Seven focused tests, including adjacent protected SoC deployment tests, pass;
  JavaScript syntax validation passes. Fresh independent review reports no
  Important/Critical findings and independently repeats the fan execution test.
- An owned networkless OpenHAB 5.2.1 runtime with unlinked synthetic Items
  verifies all six actual triggers, ON/OFF boundaries and fail-closed cases.
  Full JVM restart restores the rule, missing telemetry selects OFF, valid 98%
  selects ON, and expired evidence selects OFF. Source withdrawal restores the
  prior absent rule with the isolated switch OFF. The container was removed.
  These fixtures had no hardware links or production access.
- Live registration is file-owned, enabled and IDLE. The first command was
  natural; no production `/runnow` or fabricated source states were used.
  Native device readback confirms actual ON beyond optimistic Item prediction.
  The new Item-46 JDBC row is ON and matches the live Item.
- All **1,875 original Item-46 history rows** retain their exact fixed-prefix
  hash and mapping. Existing Item/rule/link definitions and OpenHAB PID **1696**
  are unchanged. Registry inventory has zero issues and exactly one additional
  non-managed rule: 35 managed / 8 non-managed rules.

Private preimages, exact gzip CSV history backup, qualified source, isolated
proof/log, actual device before/after snapshots and independent readback:
`/home/sat/.local/state/openhab-config-migration/south-planter-fan-20261005-ag06dyxd/`.
The backup was synced before installing the exclusive source file. All retained
evidence is private; no credentials or live telemetry were committed.

Actual live below-98% and telemetry-failure OFF transitions await natural
conditions; their logic and command effects passed in the isolated runtime.
Production whole-JVM restart recovery remains a separate attended gate.
For rollback, withdraw the exact owned source from the watched directory and
return outlet 1 to its original OFF state through its existing Item; verify
absence of this rule and native fan OFF. Retain the private recovery point.
No production service restart, other household command, forecast vent calculation
or thermal action label was added.
