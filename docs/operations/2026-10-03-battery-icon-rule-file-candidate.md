# Battery-icon display writer — attended file handoff verified

`UpdateBatteryIcon` is now file-owned after the October 3 attended handoff
recorded below. Its action/cron and both outputs are unchanged. No Item, link,
persistence mapping, household control or service was changed or restarted.
The earlier candidate checks below remain their original scoped evidence.

## October 3 attended production handoff

The operator confirmed current attendance. Fresh read-only preflight verified
the exact managed action/candidate pins, four Item types, healthy BMS/Schneider
communications, both greywater output Items OFF and no other literal rule
consumer of either display output among 42 live rules. This remains a literal,
not arbitrary dynamic/external, consumer review.

At **20:47:23.027391Z**, the corrected attended transaction privately backed
up the exact managed rule, source, definitions and two full CSV histories at:
`/home/sat/.local/state/battery-icon-rule-wxbdt3fh/` (directory 0700,
files 0600). Actual **file -> original managed rollback -> final file** passes
source/UID/cron/provider checks, all 41 unrelated rule definitions, all existing
JS sources, four Item definitions/links and unchanged OpenHAB PID **1696**.
Independent final readback repeats these checks. The file declaration was added
only afterward; no whole-OpenHAB restart or synthetic Item update occurred.

| Original output history | JDBC ID | Rows retained | Ordered CSV SHA-256 |
| --- | --- | --- | --- |
| BatteryIcon | 31 | 136,593 | `efc23e979e4249881cb622a6cda2b4135c07853c90158b8e57a02fcb8dd8b026` |
| BatteryChargingStatus | 154 | 97,335 | `c600417984aab5082d78674f8a528131662e028a860aafdbb35c5dfad921118d` |

All SQL was read-only. Each original prefix is compared through its own last
timestamp; genuine later rows are permitted, not treated as corruption. Four
known live REST bookkeeping fields (`state`, `lastState`, `lastStateChange`,
`lastStateUpdate`) are excluded from **definition** comparison, not from
history validation. All other definition fields remain exact.

The first attempt at 20:46Z passed file loading and managed rollback, then
automatically restored managed ownership when an ordinary current update
changed REST's `lastState`/timestamps. Independent comparison proves those
were the only differences; no actual definition/source/PID drift occurred.
The corrected preflight and complete second round trip—not the failed final
phase—qualify the deployment. The redundant first backup is cleaned only after
its original rule/histories are proven equal to the retained recovery point.

All 28 affected provider/parity/inventory tests were rerun successfully.
Independent final SQL readback repeats both original history checks, and the
live ownership inventory has zero issues (36 managed/six non-managed rules).
No new ERROR/Exception appears in the bounded post-handoff log. Original isolated JVM and
528-case output parity qualification are unchanged. The source's original
staging comment is intentionally retained to preserve qualified source bytes;
the manifest and this receipt describe current production ownership.

Current output remains `iconify:mdi:battery`, charging OFF, with SoC 100%.
This rule suppresses unchanged posts. A **source-attributed natural changed
output with matching new JDBC row remains pending**; do not force a charge
transition, run the rule manually or publish a fabricated value to close it.
Production whole-JVM recovery is a later, separately attended gate. The
general adapter gate remains false; this was a one-shot attended transaction.

### Retained guarded rollback

Use the retained `managed-rule.json` and the pinned adapter's REST/wait helpers
in `scripts/migrate-season-countdown-rule.py`. First recheck attendance,
protected state, sole file ownership and exact installed source SHA above;
abort on drift. Move **only** `/etc/openhab/automation/js/battery-icon.js`
into the retained private directory, wait for UID withdrawal, POST the exact
original fields named by the adapter's `FIELDS` (preserving absent fields),
and require `managed_rule_ok(actual, original)`. Recheck both JDBC prefixes,
unchanged other definitions/PID and remove only this rule's file declaration
after successful managed readback. Never add a managed duplicate while the
file rule exists, edit JSONDB directly or restart OpenHAB for this rollback.

## Exact scope and consumer review

Managed action SHA-256:
`834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f`.
It has one `0/30 * * * * ?` cron trigger and no conditions. The complete action
is retained byte-for-byte inside `automation/js/battery-icon.js`; complete source
SHA-256: `bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45`.
The exact original action includes a whitespace-only line (file line 107).
Its expected trailing-whitespace diff warning is retained deliberately; stripping
it would change the byte-preservation/source pins, not improve runtime behavior.

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

## Remaining natural-update and recovery gates

`RELEASE_READY['battery-icon']` remains **false**. The attended, backed-up
handoff and sole-provider/source/trigger/Item/JDBC checks are now complete.
The adapter preserves both outputs and their existing Item ownership; it never
commands or fabricates values. Natural charging transitions were allowed during
handoff, not mistaken for state corruption. Failed provider readback withdrew
only the exact owned candidate and restored the managed preimage.

The source-attributed natural display change/new JDBC row and production
whole-JVM recovery remain separate future gates. Retain rollback. Isolated
provider tests and Node parity alone do not prove production history or
unrelated controls; the live comparisons above supply the stated hot-handoff
evidence without claiming general protected-control restart qualification.
