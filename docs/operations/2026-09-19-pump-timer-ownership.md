# Pump timer ownership repair — September 19, 2026

## Result

The enabled `hex_southoutlet_cycle` rule now verifies that its timer still owns
the shared invocation token before any actuator lookup, command, completion
publication, or manual-ledger mutation. An interrupted or superseded callback
returns without entering its old cleanup block; it cannot stop a newer cycle.

This fixes the [observed curfew defect](2026-09-19-pump-curfew-completion-defect.md).
It does not claim that an uninterrupted natural fifteen-minute run has occurred.

## Verification

- Five new regressions failed on the old callback: after-dark, low SoC, invalid
  voltage, a newer pump owner, and an already-recovered interrupted manual request.
- The healthy South/East fifteen-minute completion tests remain passing.
- OpenHAB tests: 24 files, 406 tests passed.
- Complete unit suite: 96 files, 1,370 tests passed. Production build passed;
  its existing large-chunk advisory remains.
- The legacy single-pump source received the same ownership guard, with no
  configuration changes. It was not deployed over the live two-pump source.

## Live release

At approximately 19:22 MDT, the exact live source baseline was checked before
updating the managed rule via REST. Both pumps were explicitly OFF. The rule
was disabled, its unchanged definition rechecked, updated, read back exactly,
then enabled. Final status was `IDLE/NONE`; both pumps remained OFF. No restart,
forced run, manual pump command, or history rewrite was performed.

- Previous SHA256: `e28f2616dcd830cd41bf7433f4f0ee6e36de7d6e32d2a3d00c5a6913eec8b375`
- Installed SHA256: `f045608ba43d08f6bcaa53d70d5c1851df0f3c0410ef480ac6cef4ca98b969f6`
- Private original rule: `/tmp/pump-ownership-release-4_2opo1_/original-rule.json`
  (0700 directory, 0600 file).

The complete live-definition comparison preserved triggers, metadata and all
other configuration. The only live script change is the two-line ownership
guard. The tracked current snapshot also catches up to the preexisting live
15-minute cycle; this release did not retune it. Its old inline ten-minute
comment is retained from that exact baseline, not used as timing authority.
The 60-minute start-to-start gap and all safety gates remain unchanged.

## Outstanding evidence

Observe an actual daylight automatic run from ON through OFF, including all
intervening safety/ownership events. A changed LastCycle plus OFF state alone
is not proof of uninterrupted operation. Do not force a nighttime run or bypass
gates to obtain a completion receipt. No monitor was left running.
