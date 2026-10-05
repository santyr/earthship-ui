# South planter fan at 98% battery SoC

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
Every invalid/below-threshold case selects OFF. The threshold applies at any
time, without hysteresis or a fan duty cycle.

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
