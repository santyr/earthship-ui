# Task 4 Report — Serialized night-load owner (source + simulations only)

Branch: `build/live-controls`. NOT DEPLOYED — a later operator-gated maintenance
transaction applies the graph. Zero live writes were performed; the live OpenHAB
REST API was read only for the Step 1 inventory.

## Step 1 — Live inventory (read-only)

`GET /rest/rules?summary=false` (24 rules) filtered for `OverrideSwitch`,
`Dish_Washer_Power`, `ShurefloPump_Power`, `Goat_Plugs_Outlet1_Switch`,
`FeederOverride`. Seven relevant rules, all `IDLE`:

| UID | Name | Trigger | Action |
|-----|------|---------|--------|
| `1f692c798b` | Override ON | TimeOfDay 20:00 | `OverrideSwitch`→ON, then RunRule[`ab8a59e1da`,`GoatCamOff`,`4e234eabea`] |
| `b1501047a9` | Override OFF | TimeOfDay 09:00 | `OverrideSwitch`→OFF, then RunRule[`e647476610`] |
| `ab8a59e1da` | Dishwasher Off | `OverrideSwitch` cmd ON | `Dish_Washer_Power`→OFF |
| `4e234eabea` | Shureflo OFF | `OverrideSwitch` cmd ON | `ShurefloPump_Power`→OFF |
| `e647476610` | Shureflo ON | `OverrideSwitch` stateUpdate OFF | `ShurefloPump_Power`→ON |
| `3e8f265498` | Goat Cam ON | `Goat_Plugs_Outlet1_Switch` cmd ON | `FeederOverride`→OFF (clears) |
| `GoatCamOff` | Goat Cam Off | `Goat_Plugs_Outlet1_Switch` cmd OFF | `FeederOverride`→ON (sets) |

Findings that shaped the canonical rule:

- **Duplicate child rules to retire** (their matrices move into the owner):
  `ab8a59e1da`, `4e234eabea`, `e647476610`. Retirement is declared in the
  manifest `graph` as `backedUp: true` + `transactional: true` under a
  `reversible: true` transaction — so it can only happen inside the reversible
  override-graph receipt, never as a standalone delete.
- **Coupling direction (preserve exactly):** Goat Cam ON → `FeederOverride` OFF
  (`3e8f265498`); Goat Cam OFF → `FeederOverride` ON (`GoatCamOff`). The owner
  **never** commands or updates `FeederOverride`; it only *observes* the
  downstream side effect before completing a goat-cam operation. Declared as
  `couplingDependencies` with `mutable: false`.
- **Consolidation gap fixed:** the live override-ON path runs `GoatCamOff`
  (which only sets `FeederOverride` ON) but *never actually commands the Goat
  Cam plug OFF*. The canonical Task 16 matrix (`targetsForOverride(true)`)
  requires `Goat_Plugs_Outlet1_Switch: OFF`, so the consolidated owner adds the
  missing goat-cam OFF command to the ON matrix.
- **Schedules preserved:** `1f692c798b` / `b1501047a9` still command
  `OverrideSwitch`; the owner also triggers on `OverrideSwitch` commands and
  treats each schedule/external command as a source-agnostic request carrying a
  synthetic id `override-switch:<CMD>:<time>:<seq>` through the same
  trace/result schema (no branching on source — operator constraint 2026-07-19).
- **Browser-write safety already in place:** all four actuator items are already
  in `UNSAFE_DIRECT_COMMAND_ITEMS` (`src/lib/controls/catalog.js`), so
  `DIRECT_COMMAND_ITEMS` excludes them and `isAllowedProxyRequest` denies direct
  POST/PUT in every release mode. No source change was needed to enforce this;
  `override-graph.test.js` asserts it statically.

## Step 2–5 — TDD

Strict RED→GREEN.

- **RED:** ran the three new suites with `night-load-owner.js` absent. The two
  simulation suites errored in `beforeAll` with exactly
  `ENOENT … night-load-owner.js`. `override-graph.test.js` (manifest-structure +
  static-safety, does not reference the rule) failed only its manifest-subset
  assertions; its static rest-safety assertions already passed because the proxy
  safety was established in a prior task. No test-bug, import, or unexpected-pass
  failures.
- **Implement:** `openhab/rules/night-load-owner.js` — one serialized reducer.
  Feeder/southoutlet helpers reused verbatim: `parseBase` (requestId regex +
  ISO `requestedAt`), staleness window (2 min age / 30 s future skew), durable
  newest-32 ledger with the async-JDBC readback gate, `recoverInterruptedLedger`
  (accepted+running → `failed`/`restart_uncertain`), and the busy-lock idiom.
  Added: override vs device request parsing (`command` ON/OFF; `device` ∈
  {dishwasher,shureflo,goat-cam}); `commitOverrideSwitch` (postUpdate + persist +
  read-verify policy state, never a command echo); exact ON/OFF matrices;
  provider-generation verification on a timer before terminal `completed`;
  goat-cam completion gated on the observed `FeederOverride` coupling; cross-
  ledger + cron reconciliation recovery.
- **Manifest:** added subset `night-load` (capability `night-load-owner-v1`,
  rule `hex_night_load_override`) with the four String request/result items,
  `autoupdate=false` metadata for both request items and `OverrideSwitch`, JDBC
  everyChange/restoreOnStartup persistence covering both request ledgers +
  `OverrideSwitch`, four triggers (both requests + `OverrideSwitch` command +
  5-min reconcile cron), the reversible `graph` (retiredRules,
  couplingDependencies, schedules), and protectedDependencies (four actuators +
  `FeederOverride`).
- **Harness:** one additive, non-breaking extension to
  `tests/openhab/rule-harness.js` — `holdProvider(item)` / `releaseProvider(item)`
  record a command event without reflecting it into state, to simulate a
  provider-generation mismatch (device commanded but readback never follows).
  Default set is empty, so feeder/greywater behavior is unchanged.

### GREEN

```
npm test -- tests/openhab/night-load-override-rule.test.js \
  tests/openhab/night-load-recovery.test.js tests/openhab/override-graph.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/rest-safety.test.js
→ Test Files 5 passed (5) | Tests 59 passed (59)
```

Full `tests/openhab/` + `control-catalog` + `proxy-auth`: 134 passed.
Full `npm test`: 674 passed, 2 failed — the 2 failures are in
`tests/ui/WeatherDetailModal.test.js` (forecast staleness copy) and are
**pre-existing** (confirmed failing with my harness/manifest changes stashed);
they are unrelated to this task.

## Coverage vs the brief's enumerated simulations

- Exact ON/OFF matrices (ON → all three OFF; OFF → Shureflo ON only, dishwasher
  & goat-cam untouched). ✔
- Serialized: concurrent second request (device or override) → `denied` `busy`. ✔
- Persisted ledgers + readback gate; commit-before-command (accepted persist <
  OverrideSwitch commit < first load command). ✔
- Provider-generation matching → terminal `completed`; mismatch → `failed`
  `provider_mismatch`. ✔
- Restart-uncertain recovery (override + device, manual + cron paths), no
  re-actuation, no OverrideSwitch re-commit; completed stays idempotent. ✔
- Goat Cam coupling: owner issues zero `FeederOverride` writes; goat-cam
  completes only after the coupling side effect is observed, else
  `coupling_pending`. ✔
- Schedule interaction: `OverrideSwitch` command → synthetic-id override
  transition; owner never echoes a command to `OverrideSwitch`. ✔
- Malformed → `failed request_invalid`; duplicate → `denied duplicate`;
  stale/future-skew → `denied request_stale`; corrupt/oversize/restore-missing
  fail-closed; persist/readback failure branches. ✔
- `override-graph.test.js`: retirement only inside the reversible transaction;
  coupling + schedules preserved; static no-browser-write scan for all four
  items + both request items. ✔

## Deviations & notes

1. **Lock held across the verification timer** (feeder donor pattern) rather than
   the Task 16 "release the lock while waiting, callbacks reacquire with a
   generation id" nuance. Task 4 is source+simulation and is told to reuse the
   feeder helpers verbatim; holding the lock is the simplest correct way to
   guarantee one-in-flight and makes `busy` deterministic. The deeper
   lock-release/generation-tombstone semantics are Task 16 depth.
2. **`FeederOverride` observation scoped to the goat-cam device leg**, not the
   override-ON matrix leg. The override-ON matrix verifies the three provider
   states; coupling correctness is proven by (a) the owner never writing
   `FeederOverride` and (b) the goat-cam device request waiting on the coupling.
   This keeps the matrix test focused while still fully exercising the coupling.
3. **Override request carries `command` (ON/OFF)** to mirror the device request's
   `command` field and keep the JSON "identical to feeder/greywater + additions",
   rather than the contract's `target` key. Behaviorally identical.
4. **`override-graph.test.js` is manifest/static-safety only** (it cannot
   reference a not-yet-created rule), so in RED its failures were the absent
   manifest subset; the rule-absent ENOENT drives the two simulation suites.
5. Added `holdProvider` to the shared harness — additive, default-empty, verified
   not to change feeder/greywater/request-ledger behavior (all still green).

## Self-review

- No live writes; inventory was GET-only.
- Rule never branches on requesting source; synthetic schedule ids are
  behavior-identical to manual requests.
- Commit-before-command and policy-commit-before-load orderings are asserted.
- Fail-closed on every ledger corruption / persistence fault; ownership is
  retained ON on any ON- or OFF-transition failure (no false terminal OFF).
- Shared harness change is additive and regression-checked.

## Fix round 1

**Finding (Important):** the override-ON verify path posted terminal `completed`
after checking only the three provider load states, omitting the Goat Cam leg's
downstream `FeederOverride` coupling side effect. Deviation #2 in this report
explicitly scoped the coupling observation to the device leg only; the canonical
contract (plan lines 3769-3774) requires it "including its role in the override
matrix." Fixed.

**Change (`openhab/rules/night-load-owner.js`, `scheduleOverrideVerify` ON-branch):**
after the `ON_MATRIX` provider states are confirmed, the owner now additionally
observes `FeederOverride == 'ON'` before writing terminal `completed`. Commanding
Goat Cam OFF must drive `FeederOverride` ON via the preserved `GoatCamOff`
coupling rule (cam OFF sets it; cam ON clears it). If the side effect is absent
the leg fails instead of completing. The catch-block reason allow-list was
widened to preserve the coupling reason alongside `provider_mismatch`.

**Mismatch reason: `coupling_pending`** (not `coupling_mismatch`). The rule
already distinguishes two failure modes on the goat-cam device leg:
`provider_mismatch` (a commanded provider Item did not reflect its command) and
`coupling_pending` (provider confirmed but the `FeederOverride` side effect not
yet observed). The override-matrix leg hits the identical condition, so reusing
`coupling_pending` keeps the reason convention consistent across both legs rather
than introducing a third synonym.

**Override OFF leg: no observation added.** `OFF_MATRIX` commands only
`ShurefloPump_Power ON`; it never touches the goat cam, so there is no coupling
side effect to observe on that leg. Documented here per the finding's request.

**Owner still never writes `FeederOverride`.** The change only reads it via
`state()`; both new tests assert zero `FeederOverride` commands and zero updates,
and the pre-existing zero-write assertions remain green.

**Simulations (`tests/openhab/night-load-override-rule.test.js`):**
- (a) Extended the ON happy path (and the schedule-ON path) to set
  `FeederOverride = 'ON'` via the harness before verification, mirroring the
  async `GoatCamOff` coupling → `completed`.
- (b) New test: `FeederOverride` never flips (broken/disabled coupling rule) →
  the provider matrix is satisfied yet the leg reports `failed`/`coupling_pending`
  with NO `completed` and a `failed` ledger entry. Mutation-verified: deleting the
  new observation line fails exactly this test (1 failed / 19), passes with it.

**Verification:** `npm test` over the five named suites — 60 passed (5 files).
