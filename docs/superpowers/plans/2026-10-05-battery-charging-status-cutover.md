# Battery charging-status attended cutover plan

> **For agentic workers:** Use `superpowers:executing-plans` for this attended operation. Preserve the independent source/qualification review already completed.

**Goal:** Transfer the existing unlinked `BatteryChargingStatus` Switch to its qualified Git-owned file, preserving state, original JDBC history and sole display writer.

**Architecture:** Execute the unchanged, pinned one-Item transport once with an in-memory attended release. Exercise file -> original managed -> final file ownership while only `UpdateBatteryIcon` is paused. Record ownership after live readback; retain production restart and natural changed-output gates separately.

**Tech stack:** OpenHAB REST/file providers, native PostgreSQL JDBC history, the existing Python transport and private mode-0700 recovery capsules.

**Spec:** [Candidate, exact native qualification and remaining live gates](../../operations/2026-10-05-battery-charging-status-item.md); [file-first policy](../../../openhab/file-config/README.md).

## Global constraints

- Preserve Item name/type/label, no tags/groups/metadata/links, JDBC identity 154 and every original history row.
- Preserve writer source `bc6c0954...`, cron `0/30 * * * * ?`, original enabled state and current-based hysteresis.
- Use exact transport SHA256 `4c1ec58ad5696242d06d49e1554ece82cd01adda003a1875845a8a651862db6a`; the 4,159-test and exact-native qualification remains applicable to these unchanged bytes.
- Production source `RELEASE_READY = False` remains unchanged. A private attended bootstrap enables only its imported module for one call.
- Only selected Item DELETE/original PUT and the exact display-writer enable toggle are permitted. No Item state/command writes, `/runnow`, SQL writes, service operations, other publishers, notifications or household commands.
- Goats, pumps, battery safety, Task 82 and other deferred controls remain outside this resource's cutover.
- Unknown inode/source/provider/history drift refuses automatic recovery. Original private recovery points remain intact.

## Sequencing ruling

**Ruling:** Proceed with this qualified observational Item handoff under the operator's existing instruction to continue Item/rule/Thing migration and live handoff. The host file-first policy requires isolated restore/restart/rollback qualification before applicable migrations, which now passes for this exact resource. Production restart remains independently outstanding and requires host authentication. The earlier staging note describes its earlier state and does not add an operator-imposed restart prerequisite.

If this classification were wrong, downstream consumers could see the brief provider-withdrawal interval. Current live/source inspection finds the existing display writer and Home battery-direction display as literal consumers; the Item is unlinked and has no group/tag membership. The qualification/transport preserves name, state and history, guards all other definitions/sources/JVM, and commands no hardware. The literal census remains a review aid, not a proof that dynamic external consumers do not exist.

## Review focus

The source/qualification reviews cover all five lost-write acknowledgements, foreign-inode replacement, true cross-filesystem withdrawal, async provider disappearance and delayed genuine writer/JDBC recovery. The private bootstrap adds the independently retained original candidate history prefix to every preserved check and observes actual managed/file checkpoints. It changes no base provider method or request scope.

## Task 1: Verify attended readiness

**Files:** unchanged transport and qualified `.items` source; private `/tmp/attend-battery-charging-status-handoff.py`; original/native qualification capsules.

- [x] Verify the exact transport/source/native capsule hashes and original archive digest.
- [x] Read all live rule descriptors and installed file-owned sources; the sole literal live rule reference is `UpdateBatteryIcon`.
- [x] Run the private bootstrap `--preflight`: managed OFF, ID 154, 97,347 original rows, PID 1696, intact original candidate CSV prefix, zero production writes.
- [x] Independently review the immutable bootstrap and this plan before execution.

## Task 2: Execute the guarded provider round trip

- [x] Save current registry, disabled-rule set, log offset, source/plan/bootstrap pins and ownership preimage privately.
- [x] Run `python3 /tmp/attend-battery-charging-status-handoff.py --execute-one-shot` in the attended session. The transport itself takes fresh original/writer-paused history backups and the migration lock before withdrawal.
- [x] Require successful actual file -> original managed -> final file verification, exact source/inode/state, original history prefix, unchanged protected signature/PID, and writer IDLE/enabled afterward.
- [x] Retain actual managed rollback and both file-provider JSON checkpoints; verify all unrelated enabled/disabled rule states and inspect new logs.

## Task 3: Record the verified ownership and open gates

**Files:** `openhab/file-config/ownership.json`, its README, the candidate receipt and canonical outstanding-work queue.

- [x] Add exactly one file-provider ownership entry after independent live readback. Retain `production_restart_qualified: false` and a separate natural changed-output/JDBC gate if no genuine transition has occurred.
- [x] Run the read-only full registry inventory and exact source/provider/history checks. Require zero structural issues; do not infer whole-installation completion.
- [x] Request one read-only final review of the executed evidence/ownership/docs, then commit and integrate locally under the existing authorization. Keep source gate closed and do not push.

## Task 4: Refresh the approved production restart baseline

- [x] Preserve the earlier pre-restart capsule and mark its configuration snapshot superseded by this intentional Item transfer.
- [x] Capture the new source/provider baseline and exact native history prefixes for the prepared post-restart verifier, retaining private configuration/userdata/add-on recovery material.
- [ ] Qualify the real production restart only when the host JVM actually changes. Host sudo authentication is already the recorded blocker; do not request approval again or bypass its authentication policy.

## Completion contract for this stage

Live sole file provider, actual original managed rollback, valid recovered Switch state, unchanged original Item154 history, matching Git/watched bytes, original display writer enabled, zero unrelated definition/source/JVM changes, private recovery evidence and ownership inventory agree. Natural changed outputs and production restart remain explicit gates until their own native evidence exists. This stage advances the full outstanding-work goal; the remaining managed inventory, protected-control recovery, seasonal/action outcomes and hardware commissioning retain their original scope.


## Execution ledger

- Read-only preflight and original candidate prefix pass before release; independent bootstrap/plan review has no Important/Critical findings.
- Attended run succeeds; native readback at 20:58:16Z confirms sole file-owned OFF, original 97,347 rows, actual managed rollback and both file checkpoints. Protected signature/PID 1696 and original disabled rules are unchanged; writer IDLE/enabled; zero new runtime errors.
- Read-only managed JSONDB no longer contains the selected Item. Native inventory at 20:58:51Z has zero issues and 354 managed Items remaining; all prior ownership declarations remain unchanged.
- Private envelope: `/home/sat/.local/state/openhab-config-migration/charging-status-attended-20261005-37dz7c3f/`; actual recovery point: `charging-status-file-9spb743v` in the same private root. Both source and one-shot in-memory gates are closed.
- Genuine changed-output/JDBC and production restart gates remain unqualified. Full goal is active.

- At 21:12:38Z the approved production restart was attempted directly and refused by host sudo authentication. Fresh `restart-20261005-t2vrscku` baseline has 56 file sources, 40 native history prefixes and three validated private archives. At 21:13:16Z PID 1696 remains active, disabled rules/source hashes are preserved, battery telemetry is healthy and no new runtime errors appear. See [attempt receipt](../../operations/2026-10-05-production-restart-attempt.md). No restart qualification is claimed.

- Final independent review verifies all 99 manifested evidence files with no Critical/Important issues. Its Minor queue-clock correction is applied. Commit `1482018` is integrated by local fast-forward into main; all 74 focused transport/shared/inventory checks pass on the merged tree. Worktree remains retained for the pending restart verifier; no push occurred.
