# Attended source-bound battery-runtime estimator replacement

Status: **source-only plan; live release gate OFF; no production update made.**

## Exact scope and expected change

Replace only the managed `hex_bms_ttd_smooth` rule's ScriptAction source and
trigger list using `scripts/deploy-bms-runtime-estimator-evidence.py`.
Its UID, action ID, name, tags, other metadata and three existing output Items
remain unchanged. No Item/link/provider/persistence change, history rewrite,
database grant, equipment command, rule execution request, enable/disable,
OpenHAB restart or DM is authorized by this plan.

| Artifact | Exact SHA-256 |
| --- | --- |
| Legacy live estimator preimage | `8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794` |
| Qualified candidate source | `8b0e6533517c1ded06b1dd1e7c64b5cf9eb7a3ff3792d05a44ce3e4e5fc6e168` |
| Disabled candidate descriptor | `3031e528bb002dd4c0741b3da65a243624bf33f321c05e865b117eda17c9e458` |
| Already-live observation-preserving collector | `621f4ac7416de35e1b68f87f7d0ed4096c729319cad08e5b71bc95b1b0062c80` |

The legacy raw-TTD update trigger becomes the qualified runtime-evidence
Item-update trigger plus a 30-second expiry cron. The candidate consumes
original SoC, remaining-Ah, current/voltage, AC and PV receipts; it does not
mistake unchanged numeric history or collector health for fresh acquisition.
It prevents held BMS discharge mode through genuine charging, removes shallow
TTD samples even during mode dwell, requires distinct-sample re-entry, and
rejects retroactive qualification from a later current reading. Bank evidence
failure produces OFF/zero and clears state. Existing thresholds, dwell, reserve,
efficiency and EMA alpha are unchanged.

The displayed runtime/TTF may temporarily be unavailable or differ from the
legacy sampler because caches reset and source observations are weighted once.
Steady-night equality is qualified, not universal numerical parity or future
physical accuracy. Never tune coefficients merely to hide those differences.

## Evidence before release

See [source correction and qualification](2026-09-30-bms-night-average-verification.md#source-only-crossover-correction-and-revised-source-qualification).
The exact candidate passed 764 OpenHAB tests and 18 qualifier tests. The real
networkless JVM passed missing-input, shallow-admission, duplicate-read,
two-sample re-entry, charge-reversal, reload, actual held-input timer expiry,
full JVM restart, fresh recovery and exact managed rollback. Its owned fixture
was removed. Both immutable natural replay windows pass arithmetic and have
zero shallow admissions; all 121 nighttime medians still match independently.
Two natural charging reversals exit BMS promptly. Accuracy claims remain gated.

The live adapter and adjacent collector/qualifier tests pass 58 checks, including
closed-gate/no-I/O, exact delta/scope, private backup readback, symlink/overlap
refusal, unchanged natural-state fingerprints, unrelated-definition drift,
ambiguous PUT failure, readiness failure, exact rollback and unknown concurrent
edit preservation. These adapter fault tests use REST doubles; the isolated
JVM qualifies the actual source, not every production HTTP failure path.

The initial live read-only preflight passed under guard fingerprint
`91c0c76795d3764d301d0e9f3871aaa03f51d82d3e8667452c54d0b0ba12148a`.
This is a planning checkpoint, not a reusable authorization or frozen backup.
Repeat immediately before an attended apply; natural Item states are excluded
from the configuration fingerprint, but their original freshness is rechecked.

## Attended procedure

1. Obtain explicit approval of this exact plan and current physical attendance.
   The operator must be able to monitor both pumps/system during the change.
   Confirm both pumps physically OFF; REST output states must also be OFF.
   Never command a pump to satisfy this precondition.
   Coordinate a quiescent rule-edit window: no other agent/operator should edit
   this UID during the handoff. The process lock serializes this adapter, not
   the OpenHAB UI or other tools; REST offers no atomic compare-and-swap here.
2. From `/home/sat/earthship-ui`, run:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy-bms-runtime-estimator-evidence.py --check
   ```

   Require the qualified OpenHAB 5.2.1 runtime, exact old/candidate hashes, healthy estimator/protected rules,
   ONLINE native Things, `BMS_Comms_Status=OK`, valid original SoC/current/Ah/
   voltage/AC/PV receipts, and unchanged Item/link/persistence definitions.
   A failed check stops the release; no freshness or source gate is waived.
3. Only after approval/attendance, explicitly open the source release flag in
   the reviewed adapter for this operation. Do not add a CLI bypass or run a
   generic REST writer. Run:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy-bms-runtime-estimator-evidence.py --apply --attended
   ```

   The adapter takes a process-owned private lock, saves/fsyncs/readbacks the
   exact original RuleDTO and guard hashes, and repeats the complete preflight
   before its sole permitted rule PUT, with a final target-definition read
   immediately before dispatch. Backup directories are 0700 and the
   preimage is 0600 under `~/.local/state/openhab-config-migration/`.
4. Require exact definition readback, enabled/IDLE readiness and unchanged
   other-rule/native-Thing/Item/link/persistence fingerprints. Success is
   `definition_updated_natural_evidence_pending`, **not** final qualification.
5. Observe subsequent original native runtime receipts and natural outputs
   without `runnow`, synthetic Item writes or equipment commands. Require fresh
   observations after the update, valid cold-cache warmup, coherent basis/TTD/
   TTF, the registered expiry trigger, healthy protected rules, JDBC publication
   when outputs change and no new relevant errors. Unchanged output values
   need not create JDBC rows; freshness comes from original acquisition receipts.
   Do not interrupt telemetry deliberately to force an expiry test.
   Compare original observations,
   not just a held display value. Recheck output Item definitions/links and
   persistence settings; neither Item identity nor prior history is migrated.
6. Close the source apply flag, retain the verified operational recovery backup,
   and record actual source/trigger/status/natural-receipt evidence. Update the
   managed ownership source declaration only after real verification. Do not
   mark the broader managed-to-file migration or predictive accuracy complete.

## Failure and recovery

Any failure after PUT attempts exact managed rollback, including a lost/ambiguous
HTTP response. The adapter rereads the rule: it restores only its exact owned
candidate, or verifies that the original is already present. An unknown
concurrent edit is never overwritten. Other resources are never rolled back.
`apply_failed_rollback_verified` proves the original rule/readiness only;
unrelated configuration drift still needs operator review.

`apply_failed_rollback_unverified` stops all further mutation and prints only
the private backup location. Keep the operator attending; inspect actual live
definition/readiness and that backup before an exact, explicitly reviewed
recovery. Never retry blindly, rebuild from comments, force provider ownership,
or restart OpenHAB to clear an unknown state. A same-source numerical difference
alone is not authority to weaken fresh-input gates.

The empty process-lock file is intentional reusable infrastructure, not proof
of a running operation. Test scratch is removed separately; the private live
recovery backup is intentionally retained. No such live lock/backup was created
by the read-only check or the refused closed-gate invocation.
