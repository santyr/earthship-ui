# Battery-icon display writer — qualified, uninstalled candidate

The next file-first rule candidate is `UpdateBatteryIcon`. Production remains
managed. No live rule, Item, link, persistence mapping, control or service was
changed, and no rule ownership declaration has been added.

## Exact scope and consumer review

Managed action SHA-256:
`834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f`.
It has one `0/30 * * * * ?` cron trigger and no conditions. The complete action
is retained byte-for-byte inside `automation/js/battery-icon.js`; complete source
SHA-256: `bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45`.

| Item | Role | Preserved type |
| --- | --- | --- |
| `BMS_SOC` | SoC input | Number |
| `DCData_Current` | Charging-current input | Number:ElectricCurrent |
| `BatteryIcon` | Icon output | String |
| `BatteryChargingStatus` | Charging-status display output | Switch |

The action only reads Items and posts changed display states. It has no device
commands, timer creation, network calls, credential access or persistence API.
The October 3 live 42-rule census finds literal references to either output only
in this writer. Repo references include Home's BatteryIcon selection and
observational migration/sanity tooling. This is a literal consumer review,
not proof against arbitrary computed or external consumers. Recheck downstream
consumers before handoff; do not classify safety solely from an Item name.

This preserves charging hysteresis (ON above 2.5 A, retained down to 1.0 A),
icon thresholds, change-only posts, quantity parsing and legacy invalid-SoC
behavior. Invalid SoC updates the unknown icon but does not overwrite charging
status. This is not a freshness fix or new authorization from held values.

## Verification

Offline Node tests execute the original action and file wrapper across **528
boundary/invalid/unit-string/charging-state combinations**. Writes and final
states match. Sequential checks cover hysteresis, unchanged-value suppression
and invalid SoC. Source/trigger pins and the default-off adapter gate are tested.
With the display-rule transaction/harness tests, **30 tests pass**, no skips.

The actual networkless OpenHAB 5.2.1 rehearsal passed:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/qualify-season-rule-provider.py --kind battery-icon --restart
```

The owned container has no network, production mounts, devices or exposed ports.
Managed withdrawal loads one healthy file rule with the original UID and cron.
An actual server JVM shutdown/restart preserves file ownership and trigger.
File withdrawal then restores the original managed action and trigger exactly.
The container and volumes were removed; exit zero reports `production_writes=0`
and `natural_updates=not_tested`.

The first attempt stopped at an absent optional `description` field and removed
its container. The harness now preserves absent descriptive fields rather than
inventing them; a regression test covers omission versus explicit empty values.
The completed second rehearsal, not the failed attempt, is the evidence.

Fresh GET-only production preflight also passes:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/migrate-season-countdown-rule.py --kind battery-icon --check
```

At 17:31:07Z production OpenHAB remains PID 1696; inventory has zero issues,
37 managed/five non-managed rules. The staged target is absent. The candidate
is not automatically added to the earlier three-rule `display-set` scope.

## Remaining release and recovery gates

`RELEASE_READY['battery-icon']` remains **false**. An attended handoff needs a
fresh consumer/source/type/provider/control-state check and private managed
backup. The adapter preserves both outputs and their existing Item ownership;
it never commands or fabricates values. Natural charging transitions are allowed
during handoff, not mistaken for state corruption. Failed provider readback
withdraws only the exact owned candidate and restores the managed preimage.
No production restart is proposed.

After handoff, independently verify sole file ownership, exact source/trigger,
unchanged Item/JDBC identities and history, and a source-attributed natural
display change. Declare file ownership only after readback and retain rollback.
Production JVM recovery is a separate future attended gate. Isolated provider
tests and Node parity do not prove production history or unrelated controls.
