# Earthship Live Control Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Earthship console control truthful and usable while routing protected equipment through correlated OpenHAB owner rules instead of direct browser commands.

**Architecture:** Direct living-room lights become single-tap controls and retain provider acknowledgement. Circadian and protected controls retain a 600 ms hold. Feeder, greywater, Night Load Override, Dishwasher, Shureflo, and Goat Cam become live only after their request/result items, serialized owners, persistence, rollback receipts, and capability gates are verified.

**Tech Stack:** Svelte 5, Vitest/jsdom, Playwright, Vite same-origin proxy, OpenHAB 5.2 REST API and ECMAScript rules, JDBC persistence, user-level systemd

## Global Constraints

- Target only Lenovo Tab M9 at 1340x800 landscape and laptops at 1280x720 or larger.
- The browser never receives or stores the OpenHAB token.
- Never edit OpenHAB JSONDB or configuration files directly; use supported REST APIs.
- Before creating any OpenHAB Item or rule, inventory related Items, metadata, links, persistence, rules, and MainUI references and reuse existing capabilities.
- Never command feeder or greywater actuator items directly from a household UI.
- HTTP 2xx means transport acceptance, not equipment success.
- No automatic retry follows a transport break, timeout, or outcome-unknown result.
- Every protected actuation requires a persisted accepted request and matching correlated result.
- Codex and subagents do not actuate feeder, Goat Cam, Night Load Override, or any other protected production control.
- The user performs real switch tests from the UI; Codex observes request, result, provider, rule, and log evidence.
- Any exceptional agent-operated actuation requires new control-specific contemporaneous authorization.
- South outlet sunny eligibility is existing Item `SkyCondition == CLEAR` with SoC >=90%; every other state requires SoC >=98%.
- Every South outlet cycle is exactly five minutes with the existing 230-minute minimum start-to-start gap.
- Preserve unrelated user changes and leave `test-results/` untracked.

---

## File Map

- `src/lib/actions/holdAction.js`: one interaction action supporting explicit `tap` and `hold` modes.
- `src/lib/controls/catalog.js`: typed activation mode and protected request/result targets.
- `src/lib/controls/controlState.js`: availability, ownership, and capability gates.
- `src/lib/controls/requestClient.js`: generated request IDs, correlated result parsing, and bounded acknowledgement.
- `src/lib/ui/Toggle.svelte`: visual state, interaction hint, pending/result presentation.
- `src/screens/Controls.svelte`: passes live capability and owner state into controls.
- `src/lib/openhab/proxyPolicy.js`: exact request-item allowlist; provider-item denial.
- `openhab/rules/feeder-owner.js`: versioned canonical feeder rule source.
- `openhab/rules/southoutlet-cycle.js`: versioned canonical greywater rule source.
- `openhab/rules/night-load-owner.js`: serialized override and owned-device reducer.
- `openhab/managed-resources.json`: exact item, metadata, persistence, rule, and protected-dependency manifest.
- `scripts/openhab-config.mjs`: receipt-bound snapshot, apply, rehearse, verify, rollback, and close operations.
- `scripts/feeder-ingress.mjs`: known external-caller capture, quiescence, restore, and receipt binding.
- `tests/hold-action.test.js`: tap/hold timing, cancellation, pending, and no-retry behavior.
- `tests/ui/typed-controls.test.js`: rendered interaction, color, ownership, and request behavior.
- `tests/openhab/*.test.js`: exact rule-source simulations, persistence, ingress, rollback, and safety.
- `docs/qa/ui-audit-matrix.csv`: canonical automated/live/operator verification status.

---

### Task 1: Make direct lights tappable and active states truthful

**Files:**
- Modify: `src/lib/actions/holdAction.js`
- Modify: `src/lib/controls/catalog.js`
- Modify: `src/lib/ui/Toggle.svelte`
- Test: `tests/hold-action.test.js`
- Test: `tests/control-catalog.test.js`
- Test: `tests/ui/typed-controls.test.js`
- Test: `tests/e2e/controls-layout.spec.js`

**Interfaces:**
- Consumes: `holdAction(node, options)` and `CONTROL_CATALOG`.
- Produces: `activationModeFor(control): 'tap' | 'hold'`; `holdAction` option `mode`; direct lights with `activationMode: 'tap'`.

- [ ] **Step 1: Write failing action and component tests**

Add tests proving:

```js
action = holdAction(node, {
  mode: 'tap',
  onSubmit: submit,
  onPhaseChange: (phase) => phases.push(phase),
});
node.click();
await settle();
expect(submit).toHaveBeenCalledTimes(1);
expect(phases.at(-1)).toBe('accepted');
```

Also prove pointer hold behavior remains unchanged in `mode: 'hold'`, disabled
tap does nothing, a second tap while pending does nothing, Living Room 1 calls
`sendCommand('living_room_1_Switch', 'OFF')` after one click, Circadian still
requires 600 ms, and a disabled `ON` Dishwasher pill retains the active class.

- [ ] **Step 2: Run RED**

Run:

```bash
npm test -- tests/hold-action.test.js tests/control-catalog.test.js tests/ui/typed-controls.test.js
```

Expected: FAIL because `mode: 'tap'` and the active disabled-state styling do
not exist.

- [ ] **Step 3: Implement the minimal interaction split**

Add `activationMode: 'tap'` to direct living-room catalog entries and return
`'hold'` for all other kinds. In `holdAction`, register a click handler only in
tap mode; call the same `submitOnce` state machine exactly once and suppress
new clicks while pending. Keep pointer/keyboard hold listeners only in hold
mode. Include `mode` in `sameActionContract`.

In `Toggle.svelte`, pass the catalog mode, render `Tap to toggle` for tap mode,
retain `Hold 600 ms` for hold mode, and change:

```css
.control.on:not(:disabled) .pill
```

to:

```css
.control.on .pill
```

Add a separate disabled border/tone treatment without removing active color.

- [ ] **Step 4: Run GREEN and geometry regression**

Run:

```bash
npm test -- tests/hold-action.test.js tests/control-catalog.test.js tests/ui/typed-controls.test.js
npm run test:e2e -- tests/e2e/controls-layout.spec.js --workers=1
npm run build
```

Expected: all selected tests and the build pass with no overflow at 1340x800
or 1280x720.

- [ ] **Step 5: Commit**

```bash
git add src/lib/actions/holdAction.js src/lib/controls/catalog.js \
  src/lib/ui/Toggle.svelte tests/hold-action.test.js \
  tests/control-catalog.test.js tests/ui/typed-controls.test.js \
  tests/e2e/controls-layout.spec.js
git commit -m "fix: make living room controls tablet-native"
```

---

### Task 2: Deploy the correlated feeder owner

**Files:**
- Create: `openhab/rules/feeder-owner.js`
- Create: `openhab/managed-resources.json`
- Create: `scripts/openhab-config.mjs`
- Create: `scripts/feeder-ingress.mjs`
- Create: `tests/openhab/feeder-rule.test.js`
- Create: `tests/openhab/feeder-compatibility.test.js`
- Create: `tests/openhab/feeder-ingress.test.js`
- Create: `tests/openhab/request-ledger.test.js`
- Create: `tests/openhab/rest-safety.test.js`
- Modify: `src/lib/controls/catalog.js`
- Modify: `src/lib/openhab/proxyPolicy.js`

**Interfaces:**
- Consumes: the exact Task 14 contract and transaction procedure in `docs/superpowers/plans/2026-07-17-earthship-ui-tablet-audit-implementation.md:2982`.
- Produces: String items `GoatFeeder_ManualRequest` and `GoatFeeder_ManualResult`; verified capability `feeder-request-v1`.

- [ ] **Step 1: Execute Task 14 RED exactly**

First inventory the live feeder-related Items, metadata, links, persistence,
rules, and MainUI references. Extend canonical rule UID `88bd9ec4de`; do not
create a second feeder owner or duplicate an equivalent request capability.
Then write the sentinel tests and exact-source simulations specified by the
canonical Task 14. Run its `expect-failure.mjs` RED commands and require only
the named missing-owner sentinel failures.

- [ ] **Step 2: Implement the canonical owner and ledgers**

Implement the complete Task 14 rule source, newest-32 durable request ledger,
JDBC persist/readback gate, busy/cooldown denial, one-second pulse, counter
receipt, finally-OFF cleanup, payment/runnow compatibility, and proxy denial of
`Goat_Plugs_Outlet2_Switch`.

- [ ] **Step 3: Run Task 14 GREEN**

Run:

```bash
npm test -- tests/openhab/feeder-rule.test.js \
  tests/openhab/feeder-compatibility.test.js \
  tests/openhab/feeder-ingress.test.js tests/openhab/request-ledger.test.js \
  tests/openhab/rest-safety.test.js
```

Expected: all feeder simulations pass without contacting the physical outlet.

- [ ] **Step 4: Apply the receipt-bound feeder transaction**

Obtain the Task 14 maintenance-window approval. Capture and quiesce only known
external callers, snapshot the exact OpenHAB subset, bind receipts, apply with
the old and new rules disabled, rehearse rollback/reapply, verify the provider
remains OFF, restore callers, and close both receipts. Do not send a manual
feeding request during deployment.

- [ ] **Step 5: Commit**

Stage only the Task 14 paths and commit:

```bash
git commit -m "feat: add correlated feeder requests"
```

---

### Task 3: Deploy safety-gated greywater requests

**Files:**
- Create: `openhab/rules/southoutlet-cycle.js`
- Create: `tests/openhab/greywater-rule.test.js`
- Create: `tests/openhab/greywater-recovery.test.js`
- Modify: `openhab/managed-resources.json`
- Modify: `scripts/openhab-config.mjs`
- Modify: `src/lib/controls/catalog.js`
- Modify: `src/lib/openhab/proxyPolicy.js`

**Interfaces:**
- Consumes: exact Task 15 contract at `docs/superpowers/plans/2026-07-17-earthship-ui-tablet-audit-implementation.md:3346`.
- Produces: `SouthOutlet_ManualRequest`, `SouthOutlet_ManualResult`, `SouthOutlet_LastCycleStart`, `SouthOutlet_LastCycle`; verified capability `greywater-request-v1`.

- [ ] **Step 1: Run Task 15 RED**

First inventory all live South outlet Items, metadata, links, persistence,
rules, and MainUI references and reuse any equivalent implemented capability.
Then add the exact gate, migration, restart, duplicate, race, and OFF-cleanup
sentinels and verify they fail only because the candidate rule is absent.

- [ ] **Step 2: Implement the canonical rule**

Set `cycleMs` to `5 * 60 * 1000` and preserve the 230-minute start-to-start
gap, BMS/freshness chain, voltage sanity checks, and automatic schedule. Use
existing Item `SkyCondition` rather than creating a duplicate sunny Item.
Require SoC >=90% only when `SkyCondition == CLEAR`; require SoC >=98% for
every other or unavailable SkyCondition value. Remove charger-`Float` and
curtailment-only requirements. The former 24-hour aerobic fallback must never
bypass the charged-system threshold. Add correlated manual requests through
the same evaluator and keep `SouthOutlet_Outlet2_Switch` denied by the
household proxy.

- [ ] **Step 3: Run Task 15 GREEN**

```bash
npm test -- tests/openhab/greywater-rule.test.js \
  tests/openhab/greywater-recovery.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/rest-safety.test.js
```

Expected: all exact-source tests pass without starting the pump.

- [ ] **Step 4: Apply the attended disabled transaction**

Obtain the exact Task 15 approval with an observer able to see the pump.
Snapshot, verify a local non-start result, require provider OFF, disable the
rule, apply and rehearse while disabled, then re-enable only after hashes,
persistence, timestamps, rules, Things, and logs are clean. Use the
pre-authorized emergency OFF only if a maintenance race unexpectedly starts
the provider.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add safety-gated greywater requests"
```

---

### Task 4: Deploy the serialized night-load owner

**Files:**
- Create: `openhab/rules/night-load-owner.js`
- Create: `tests/openhab/night-load-override-rule.test.js`
- Create: `tests/openhab/night-load-recovery.test.js`
- Create: `tests/openhab/override-graph.test.js`
- Modify: `openhab/managed-resources.json`
- Modify: `scripts/openhab-config.mjs`
- Modify: `src/lib/controls/catalog.js`
- Modify: `src/lib/controls/controlState.js`
- Modify: `src/lib/openhab/proxyPolicy.js`

**Interfaces:**
- Consumes: exact Task 16 contract at `docs/superpowers/plans/2026-07-17-earthship-ui-tablet-audit-implementation.md:3544`.
- Produces: both Night Load request/result pairs; one owner for override and three devices; verified capability `night-load-owner-v1`.

- [ ] **Step 1: Run Task 16 RED**

First inventory all live override, Dishwasher, Shureflo, and Goat Cam Items,
metadata, links, persistence, rules, and MainUI references. Consolidate existing
owners by UID and do not deploy a duplicate owner capability. Then add exact
ownership, matrix, race, restart, provider-receipt, Goat Cam coupling,
schedule, proxy, and MainUI sentinels. Require only expected missing-owner
failures.

- [ ] **Step 2: Implement the serialized reducer**

Implement the exact ON/OFF matrices, persistent ledgers, commit-before-command
gates, provider-generation matching, supersession, restart-uncertain recovery,
and existing Goat Cam coupling direction. Retire duplicate child rules only
inside the reversible graph transaction.

- [ ] **Step 3: Run Task 16 GREEN**

Run the full Task 16 focused test list from the canonical plan. Expected: every
rule and graph simulation passes, and static proxy scans find no direct browser
write to `OverrideSwitch`, Dishwasher, Shureflo, or Goat Cam.

- [ ] **Step 4: Apply and rehearse the owner graph**

Obtain attended approval outside both schedules. Snapshot the owner, schedules,
child rules, item metadata, persistence, provider states, and protected
coupling-rule hashes. Keep schedules disabled until the owner is verified
healthy. Rehearse rollback/reapply, activate owner first and schedules last,
then close the receipt only after provider states, policy state, rule status,
and logs agree.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: serialize night load controls"
```

---

### Task 5: Wire correlated UI outcomes and activate capabilities

**Files:**
- Create: `src/lib/controls/requestClient.js`
- Modify: `src/lib/controls/outcomeStore.js`
- Modify: `src/lib/controls/controlState.js`
- Modify: `src/lib/ui/Toggle.svelte`
- Modify: `src/screens/Controls.svelte`
- Modify: `src/lib/openhab/proxyPolicy.js`
- Test: `tests/control-state.test.js`
- Test: `tests/outcome-store.test.js`
- Test: `tests/openhab-proxy-policy.test.js`
- Test: `tests/ui/typed-controls.test.js`

**Interfaces:**
- Consumes: the three verified capabilities and matching result payloads.
- Produces: `submitControlRequest(control, target, client): Promise<RuleOutcome>` and live protected controls.

- [ ] **Step 1: Write and run failing correlated-request tests**

Prove request IDs are unique, only matching result IDs resolve pending state,
denied/failed/unknown remain distinct, timeouts do not retry, owned devices are
disabled during override or owner transition, and proxy POST allowlists only
the four request items plus the existing four direct light/policy items.

- [ ] **Step 2: Implement the request client and UI state machine**

Serialize exact JSON request payloads, send them to request items, observe
matching result-item updates, and feed the terminal phase into
`outcomeStore.js`. Never infer completion from provider state alone for a
protected request.

- [ ] **Step 3: Run focused and full verification**

```bash
npm test -- tests/control-state.test.js tests/outcome-store.test.js \
  tests/openhab-proxy-policy.test.js tests/ui/typed-controls.test.js
npm test
npm run test:e2e -- --workers=1
npm run build
```

Expected: all unit and route tests pass and production build succeeds.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: activate correlated household controls"
```

---

### Task 6: Deploy, observe user-operated tests, and obtain sign-off

**Files:**
- Modify: `docs/qa/ui-audit-matrix.csv`
- Verify: `deploy/earthship-ui.service`

**Interfaces:**
- Consumes: committed UI and closed OpenHAB receipts.
- Produces: live `safe-compat` or `full` service with exact verified capabilities and operator sign-off.

- [ ] **Step 1: Restart only the user UI service**

```bash
systemctl --user restart earthship-ui.service
systemctl --user is-active earthship-ui.service
systemctl --user is-enabled earthship-ui.service
ss -ltn | rg ':5190'
```

Expected: active, enabled, and listening on port 5190.

- [ ] **Step 2: Run read-only live verification**

Verify all request/result items, rules IDLE/RUNNING, provider Things ONLINE,
final item states, persistence, proxy denials, no browser token, and no new
OpenHAB `ERROR` or `Exception` entries.

- [ ] **Step 3: Expose the live UI for user-operated tests**

Do not issue commands for feeder, Goat Cam, Night Load Override, or any other
protected production control. Ask the user to operate controls from the live
UI one at a time. While the user operates them, observe:

- a normal tap toggles and restores each living-room light;
- a hold toggles and restores Circadian;
- each owned load produces matching owner and provider receipts;
- feeder produces one pulse, one count increment, and confirmed OFF;
- circulation either produces an explicit safety denial or one approved cycle
  with matching result and final OFF;
- Night Load Override follows the exact matrix and restores the approved final
  policy state.

Stop immediately on mismatch or outcome unknown.

- [ ] **Step 4: Record only confirmed sign-off**

Update `docs/qa/ui-audit-matrix.csv` to `verified-live` only for evidence
actually observed. Run:

```bash
npm test -- tests/audit-matrix.test.js
git diff --check
git status --short
```

Record the receipt summary in Hexmem, commit the matrix, and leave
`test-results/` untracked.
