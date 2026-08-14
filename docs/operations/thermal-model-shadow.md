# Thermal model shadow rollout and rollback

This is an attended, approval-gated runbook for the observational thermal
model. It is not an instruction to deploy automatically. Implementation
completion does **not** graduate model output to advice, change
`Thermal_Advisory`, or authorize actuation.

The only permitted OpenHAB configuration change is the receipt-bound
`Thermal_Model_JSON` String Item. Publication may write only that Item's state.
No rule, command, actuator, notification-policy, or generic RPC change is in
scope.

## Labels and private evidence

- **READ-ONLY** inspects tracked files, runtime state, or evidence.
- **SESSION-ONLY** sets shell variables without persistent state.
- **MUTATING — GATE A** requires operator approval of the staging packet.
- **MUTATING — GATE B** requires a second, attended approval after review of
  the exact Item apply and rollback plans.
- **DESTRUCTIVE — ROLLBACK ONLY** removes exact staged targets during rollback.

Receipts, Item snapshots, OpenHAB inventories, journal rows, raw household
history, DSNs, passwords, tokens, learned artifacts, backtest reports, and
journal/service output are private. Keep them outside Git, with `0700`
directories and `0600` files. Never print credentials or copy the protected
environment file into a receipt. Do not commit artifacts or journal data.

Run repository commands from `/home/sat/earthship-ui` at the reviewed commit.

## 1. Exact tracked-to-live manifest

Do not copy a file not listed here.

| Tracked source | Live target | Action |
| --- | --- | --- |
| `openhab/scripts/forecast_intel.py` | `/home/sat/openhab/scripts/forecast_intel.py` | Verify only; stop on mismatch |
| `openhab/scripts/thermal_intel.py` | `/home/sat/openhab/scripts/thermal_intel.py` | Back up, then install |
| `openhab/scripts/thermal_model/__init__.py` | `/home/sat/openhab/scripts/thermal_model/__init__.py` | Back up, then install |
| `openhab/scripts/thermal_model/actions.py` | `/home/sat/openhab/scripts/thermal_model/actions.py` | Back up, then install |
| `openhab/scripts/thermal_model/artifacts.py` | `/home/sat/openhab/scripts/thermal_model/artifacts.py` | Back up, then install |
| `openhab/scripts/thermal_model/behavior.py` | `/home/sat/openhab/scripts/thermal_model/behavior.py` | Back up, then install |
| `openhab/scripts/thermal_model/dataset.py` | `/home/sat/openhab/scripts/thermal_model/dataset.py` | Back up, then install |
| `openhab/scripts/thermal_model/dynamics.py` | `/home/sat/openhab/scripts/thermal_model/dynamics.py` | Back up, then install |
| `openhab/scripts/thermal_model/evaluation.py` | `/home/sat/openhab/scripts/thermal_model/evaluation.py` | Back up, then install |
| `openhab/scripts/thermal_model/journal.py` | `/home/sat/openhab/scripts/thermal_model/journal.py` | Back up, then install |
| `openhab/scripts/thermal_model/pipeline.py` | `/home/sat/openhab/scripts/thermal_model/pipeline.py` | Back up, then install |
| `openhab/scripts/thermal_model/schema.py` | `/home/sat/openhab/scripts/thermal_model/schema.py` | Back up, then install |

`openhab/thermal-model-items.json`, `scripts/thermal-model-config.mjs`, and
`openhab/scripts/validate_thermal_shadow.py` remain repository-side tools. The
four `deploy/thermal-model-*` units are installed only after all manual evidence
is green.

**READ-ONLY — revision, diff, and shared-helper identity:**

```bash
git rev-parse HEAD
git status --short
git diff --check
sha256sum openhab/scripts/forecast_intel.py
sha256sum /home/sat/openhab/scripts/forecast_intel.py
cmp --silent openhab/scripts/forecast_intel.py /home/sat/openhab/scripts/forecast_intel.py
```

Expected: the reviewed revision, no unexpected changes, no whitespace errors,
equal hashes, and `cmp` exit 0. This rollout never overwrites
`forecast_intel.py`.

**READ-ONLY — record exact tracked runtime hashes:**

```bash
sha256sum openhab/scripts/thermal_intel.py \
  openhab/scripts/thermal_model/__init__.py \
  openhab/scripts/thermal_model/actions.py \
  openhab/scripts/thermal_model/artifacts.py \
  openhab/scripts/thermal_model/behavior.py \
  openhab/scripts/thermal_model/dataset.py \
  openhab/scripts/thermal_model/dynamics.py \
  openhab/scripts/thermal_model/evaluation.py \
  openhab/scripts/thermal_model/journal.py \
  openhab/scripts/thermal_model/pipeline.py \
  openhab/scripts/thermal_model/schema.py
```

Keep the reviewed digest list with the private deployment evidence, not Git.

## 2. Read-only Item and persistence inventory

Use the local Vite proxy so no token enters the shell transcript. Do not
redirect Item states or history into the repository.

**READ-ONLY — inspect the proposed Item while allowing an expected 404:**

```bash
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  http://127.0.0.1:5190/rest/items/Thermal_Model_JSON
```

Expected: HTTP 404, or the exact prior Item configuration.

**READ-ONLY — inspect advisory, known feeder actuator, and five inputs:**

```bash
for ITEM in \
  Thermal_Advisory \
  SouthOutlet_Outlet2_Switch \
  AmbientWeatherWS2902A_IndoorSensor_Temperature \
  AmbientWeatherWS2902A_WH31E_193_Temperature \
  Shelly_HT1_Indoor_Temperature \
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature \
  AmbientWeatherWS2902A_SolarRadiation
do
  curl --fail --silent --show-error \
    "http://127.0.0.1:5190/rest/items/${ITEM}" \
    | jq '{name,type,label,state}'
done
```

Expected: advisory/actuator baselines are recorded and all five sensors resolve.

**READ-ONLY — persistence service inventory:**

```bash
curl --fail --silent --show-error http://127.0.0.1:5190/rest/persistence \
  | jq 'map({id,label})'
```

Expected: `jdbc` is present.

**SESSION-ONLY — one-hour UTC coverage window:**

```bash
END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_UTC="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
```

**READ-ONLY — inspect counts and latest timestamps, not raw rows:**

```bash
for ITEM in \
  AmbientWeatherWS2902A_IndoorSensor_Temperature \
  AmbientWeatherWS2902A_WH31E_193_Temperature \
  Shelly_HT1_Indoor_Temperature \
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature \
  AmbientWeatherWS2902A_SolarRadiation
do
  curl --fail --silent --show-error \
    "http://127.0.0.1:5190/rest/persistence/items/${ITEM}?serviceId=jdbc&starttime=${START_UTC}&endtime=${END_UTC}" \
    | jq --arg item "$ITEM" '{item:$item,count:(.data|length),latest:(.data[-1].time // null)}'
done
```

Stop for stale or absent critical air, mass, outdoor, or radiation data.

**READ-ONLY — detect any prior thermal unit installation:**

```bash
systemctl --user status thermal-model-train.service thermal-model-train.timer \
  thermal-model-shadow.service thermal-model-shadow.timer --no-pager -l
```

`not-found`/inactive is normal. Reconcile an existing installation separately;
never overwrite it blindly.

## 3. Gate A: approval before staging mutations

Stop. Present the exact Git revision, repository verification totals, tracked
hashes, `forecast_intel.py` identity, Item/persistence inventory, protected
state baseline, the database commands below, the backup/copy commands below,
and an explicit attestation that implementation performed no live work.

Obtain explicit approval before any **MUTATING — GATE A** command. Gate A does
not approve the later OpenHAB Item write.

## 4. Receipt snapshot and rollback rehearsal

**SESSION-ONLY — choose a fresh private receipt and backup location:**

```bash
RECEIPT_DIR="/home/sat/.local/state/thermal-intel/deploy-receipts/2026-08-13-attended-01"
BACKUP_DIR="${RECEIPT_DIR}/tracked-script-backup"
```

Never reuse another attempt's receipt directory.

**MUTATING — GATE A — snapshot only `Thermal_Model_JSON`:**

```bash
node scripts/thermal-model-config.mjs snapshot --receipt-dir "$RECEIPT_DIR"
```

This performs one Item `GET` and writes private `receipt.json` and
`pre-state.json`; it does not write OpenHAB.

**READ-ONLY — inspect exact apply/rollback plans and receipt integrity:**

```bash
node scripts/thermal-model-config.mjs plan --receipt-dir "$RECEIPT_DIR" | jq .
jq '{schema,state,phase,itemName,createdAt,snapshotDigest,writeCount,checksum}' \
  "$RECEIPT_DIR/receipt.json"
sha256sum "$RECEIPT_DIR/pre-state.json" "$RECEIPT_DIR/receipt.json"
```

Expected apply: one exact `PUT /rest/items/Thermal_Model_JSON`. Expected
rollback: exact prior Item `PUT`, or exact `DELETE` if absent. Rehearsal means
reviewing the `rollback` member from `plan`; do not mutate the live Item merely
to test rollback.

## 5. Backup, install, and verify the runtime files

**MUTATING — GATE A — back up any prior thermal runtime:**

```bash
install -d -m 0700 "$BACKUP_DIR"
if test -f /home/sat/openhab/scripts/thermal_intel.py; then
  cp --archive /home/sat/openhab/scripts/thermal_intel.py "$BACKUP_DIR/thermal_intel.py"
fi
if test -d /home/sat/openhab/scripts/thermal_model; then
  cp --archive /home/sat/openhab/scripts/thermal_model "$BACKUP_DIR/thermal_model"
fi
```

**MUTATING — GATE A — install only the exact runtime manifest:**

```bash
install -d -m 0755 /home/sat/openhab/scripts/thermal_model
install -m 0755 openhab/scripts/thermal_intel.py \
  /home/sat/openhab/scripts/thermal_intel.py
install -m 0644 \
  openhab/scripts/thermal_model/__init__.py \
  openhab/scripts/thermal_model/actions.py \
  openhab/scripts/thermal_model/artifacts.py \
  openhab/scripts/thermal_model/behavior.py \
  openhab/scripts/thermal_model/dataset.py \
  openhab/scripts/thermal_model/dynamics.py \
  openhab/scripts/thermal_model/evaluation.py \
  openhab/scripts/thermal_model/journal.py \
  openhab/scripts/thermal_model/pipeline.py \
  openhab/scripts/thermal_model/schema.py \
  /home/sat/openhab/scripts/thermal_model/
```

**READ-ONLY — prove every pair is byte-identical:**

```bash
cmp --silent openhab/scripts/thermal_intel.py /home/sat/openhab/scripts/thermal_intel.py
for NAME in __init__ actions artifacts behavior dataset dynamics evaluation journal pipeline schema
do
  cmp --silent \
    "openhab/scripts/thermal_model/${NAME}.py" \
    "/home/sat/openhab/scripts/thermal_model/${NAME}.py" || exit 1
done
sha256sum /home/sat/openhab/scripts/thermal_intel.py \
  /home/sat/openhab/scripts/thermal_model/__init__.py \
  /home/sat/openhab/scripts/thermal_model/actions.py \
  /home/sat/openhab/scripts/thermal_model/artifacts.py \
  /home/sat/openhab/scripts/thermal_model/behavior.py \
  /home/sat/openhab/scripts/thermal_model/dataset.py \
  /home/sat/openhab/scripts/thermal_model/dynamics.py \
  /home/sat/openhab/scripts/thermal_model/evaluation.py \
  /home/sat/openhab/scripts/thermal_model/journal.py \
  /home/sat/openhab/scripts/thermal_model/pipeline.py \
  /home/sat/openhab/scripts/thermal_model/schema.py
```

Expected: every `cmp` exits 0 and live hashes correspond to the tracked list.
Stop and restore backup on mismatch.

## 6. Least-privilege PostgreSQL journal setup

The current migration API creates only schema `thermal_intel`, tables
`message_receipts`, `action_events`, and `mode_events`, their functions, and
append-only triggers. It revokes `PUBLIC`, grants the runtime role schema
`USAGE` and table `SELECT, INSERT`, and revokes `UPDATE`, `DELETE`, `TRUNCATE`,
`REFERENCES`, and `TRIGGER`. It does not modify OpenHAB-generated persistence
tables.

Provide the administrator DSN only in the attended shell. Never put it in the
service environment file or command history.

**READ-ONLY — check whether the dedicated role exists:**

```bash
psql "$THERMAL_DATABASE_ADMIN_URL" --no-psqlrc --tuples-only --no-align \
  --command "SELECT rolname FROM pg_roles WHERE rolname = 'thermal_intel_runtime'"
```

**MUTATING — GATE A — if absent, create only an unprivileged login and enter
its password interactively:**

```bash
createuser --dbname="$THERMAL_DATABASE_ADMIN_URL" --pwprompt \
  --no-createdb --no-createrole --no-superuser thermal_intel_runtime
```

**MUTATING — GATE A — run the code's explicit migration function:**

```bash
cd /home/sat/openhab/scripts
/usr/bin/python3 -c 'import os; from thermal_model.journal import migrate; migrate(os.environ["THERMAL_DATABASE_ADMIN_URL"], runtime_role="thermal_intel_runtime")'
cd /home/sat/earthship-ui
```

**MUTATING — GATE A — use a secret-safe editor to add only the runtime-role DSN
as `THERMAL_DATABASE_URL` to the existing protected environment file:**

```bash
/usr/bin/vi /home/sat/.config/hex/openhab.env
chmod 0600 /home/sat/.config/hex/openhab.env
unset THERMAL_DATABASE_ADMIN_URL
```

Do not display or copy the file. The runtime DSN selects the existing OpenHAB
`openhab` database as `thermal_intel_runtime`, never an administrator.

**SESSION-ONLY — enter the runtime DSN without echoing it:**

```bash
read -r -s -p 'THERMAL_DATABASE_URL: ' THERMAL_DATABASE_URL
printf '\n'
export THERMAL_DATABASE_URL
```

**READ-ONLY — verify exact tables and runtime grants:**

```bash
psql "$THERMAL_DATABASE_URL" --no-psqlrc --tuples-only --no-align \
  --command "SELECT schemaname,tablename FROM pg_tables WHERE schemaname = 'thermal_intel' ORDER BY tablename"
psql "$THERMAL_DATABASE_URL" --no-psqlrc --tuples-only --no-align \
  --command "SELECT table_name,privilege_type FROM information_schema.role_table_grants WHERE table_schema = 'thermal_intel' AND grantee = current_user ORDER BY table_name,privilege_type"
```

Expected: exactly three application tables and only `INSERT`/`SELECT` table
privileges. No OpenHAB-generated persistence table is a migration target.

**SESSION-ONLY — discard the attended runtime DSN:**

```bash
unset THERMAL_DATABASE_URL
```

## 7. Gate B and receipt-bound Item apply

Stop again. Present the exact `snapshotDigest`, apply/rollback plans,
tracked/live hashes, database grants, and protected state baseline. Obtain
explicit attended approval for the one Item configuration write. Gate A is not
Gate B.

**MUTATING — GATE B — apply the receipt-owned Item configuration:**

```bash
node scripts/thermal-model-config.mjs apply --receipt-dir "$RECEIPT_DIR"
```

**READ-ONLY — verify desired configuration and receipt phase:**

```bash
node scripts/thermal-model-config.mjs verify --receipt-dir "$RECEIPT_DIR" | jq .
jq '{state,phase,snapshotDigest,writeCount,checksum}' "$RECEIPT_DIR/receipt.json"
```

Expected: `ok: true`, `expected: "desired"`, phase `desired`, and one write.
The Task 8 CLI has no `close` command. Receipt completion is exact desired
readback plus the retained private receipt, not an invented transition.

If transport failed in phase `applying`, inspect exact live configuration:

**READ-ONLY — ambiguous-write readback:**

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Model_JSON | jq .
jq '{state,phase,writeCount,checksum}' "$RECEIPT_DIR/receipt.json"
```

**MUTATING — GATE B — settle only when the intended write landed exactly:**

```bash
node scripts/thermal-model-config.mjs settle --receipt-dir "$RECEIPT_DIR"
node scripts/thermal-model-config.mjs verify --receipt-dir "$RECEIPT_DIR" | jq .
```

If readback is not exact, stop and roll back. Never retry an ambiguous Item
mutation blindly.

## 8. Manual train, backtest, and local-only shadow

These commands read live JDBC/weather inputs and the journal. They write local
model state under `/home/sat/.local/state/thermal-intel`; the first three do not
publish any OpenHAB Item.

**MUTATING — GATE A — train and promote one shadow-only candidate:**

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py train
```

Expected: exit 0 and compact JSON containing `status: "promoted"`, exact
`codeRevision`, and `trainedThrough`. A refusal is a stop condition, never a
reason to bypass acceptance gates.

**MUTATING — GATE A — write a fresh chronological backtest report:**

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py backtest
```

Expected: exit 0, `status: "backtested"`, and the exact report path.

**MUTATING — GATE A — produce a local shadow file without publication:**

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow \
  --output /home/sat/.local/state/thermal-intel/shadow-review.json
```

Expected: exit 0, valid v1 `shadow`, below 16 KiB, no Item state write. Do not
add `--publish` yet. Current CLI truth: `train`/`backtest` accept optional
`--start`, `--end`, and `--state-dir`; `shadow` accepts `--output` and
`--publish`, but no `--state-dir`.

## 9. Evidence review, manual publish, and readback

**READ-ONLY — parameters, constraints, provenance, and exclusions:**

```bash
jq '{schema,created_at,trained_from,trained_through,code_revision,dynamics,behavior,metrics,data_manifest:{start:.data_manifest.start,end:.data_manifest.end,sample_count:.data_manifest.sample_count,rejected_counts:.data_manifest.rejected_counts,auxiliary_exclusion_counts:.data_manifest.auxiliary_exclusion_counts,event_counts_by_source:.data_manifest.event_counts_by_source,fit_diagnostics:.data_manifest.fit_diagnostics,constraints:.data_manifest.constraints,canonical_rows_sha256:.data_manifest.canonical_rows_sha256}}' \
  /home/sat/.local/state/thermal-intel/models/accepted.json
```

**READ-ONLY — fold boundaries, baseline metrics, and shadow-only gates:**

```bash
jq '{schema,generated_at,data_range,fold_count:(.folds|length),folds,baselines:{model:.metrics.overall.model,persistence:.metrics.overall.persistence,recent_cycle:.metrics.overall.recent_cycle},by_horizon:.metrics.by_horizon,by_regime:.metrics.by_regime,prediction_interval_coverage:.metrics.prediction_interval_coverage,promotion:.metrics.promotion}' \
  /home/sat/.local/state/thermal-intel/models/backtest-report.json
jq -e 'all(.folds[]; .train_end < .prediction_start)' \
  /home/sat/.local/state/thermal-intel/models/backtest-report.json
/usr/bin/python3 openhab/scripts/validate_thermal_shadow.py \
  < /home/sat/.local/state/thermal-intel/shadow-review.json
wc -c /home/sat/.local/state/thermal-intel/shadow-review.json
```

Expected: exact code/data ranges; every fold has
`train_end < prediction_start`; finite model, persistence, and recent-cycle
metrics; reviewed exclusions/provenance; `promotion.shadow_only: true`; valid
shadow; fewer than 16384 bytes. Stop on leakage, invalid physics, unexplained
exclusions, missing baselines, unavailable confidence, or size failure.

**MUTATING — GATE B — manually publish one fresh shadow:**

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow --publish \
  --output /home/sat/.local/state/thermal-intel/shadow-published.json
```

This validates the payload and performs one state `PUT` to
`Thermal_Model_JSON`; it never retries ambiguity.

**MUTATING — GATE B — retain exact readback privately, outside Git:**

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Model_JSON/state \
  > "$RECEIPT_DIR/published-readback.json"
chmod 0600 "$RECEIPT_DIR/published-readback.json"
```

**READ-ONLY — validate size and canonical equality:**

```bash
/usr/bin/python3 openhab/scripts/validate_thermal_shadow.py \
  < "$RECEIPT_DIR/published-readback.json"
wc -c "$RECEIPT_DIR/published-readback.json"
jq -S -c . /home/sat/.local/state/thermal-intel/shadow-published.json | sha256sum
jq -S -c . "$RECEIPT_DIR/published-readback.json" | sha256sum
```

Expected: valid available v1 `shadow`, fewer than 16384 bytes, equal hashes.

**READ-ONLY — verify protected state and inspect UI logs:**

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Advisory | jq '{name,state}'
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch | jq '{name,state}'
journalctl --user -u earthship-ui.service -n 100 --no-pager
```

Expected: both protected values equal step 2, no actuator changed, and no UI
parse/render error. Visually confirm a non-interactive `SHADOW` card. Exercise
stale/unavailable through existing test fixtures, never by aging or corrupting
the live Item.

## 10. Units and timers only after steps 1–9 are green

Do not install units until all prior evidence is reviewed and green.

**MUTATING — GATE B — install exact user units and reload:**

```bash
install -m 0644 deploy/thermal-model-train.service \
  /home/sat/.config/systemd/user/thermal-model-train.service
install -m 0644 deploy/thermal-model-train.timer \
  /home/sat/.config/systemd/user/thermal-model-train.timer
install -m 0644 deploy/thermal-model-shadow.service \
  /home/sat/.config/systemd/user/thermal-model-shadow.service
install -m 0644 deploy/thermal-model-shadow.timer \
  /home/sat/.config/systemd/user/thermal-model-shadow.timer
systemctl --user daemon-reload
```

**MUTATING — GATE B — prove both services before enabling timers:**

```bash
systemctl --user start thermal-model-train.service
systemctl --user start thermal-model-shadow.service
```

**READ-ONLY — exact service evidence:**

```bash
systemctl --user show thermal-model-train.service thermal-model-shadow.service \
  --property=Id --property=Result --property=ExecMainStatus --property=InactiveExitTimestamp
journalctl --user -u thermal-model-train.service -u thermal-model-shadow.service \
  -n 200 --no-pager
```

Expected: `Result=success`, `ExecMainStatus=0`, and no credential, advisory,
rule, or actuator activity in logs.

**MUTATING — GATE B — only now enable persistent timers:**

```bash
systemctl --user enable --now thermal-model-train.timer thermal-model-shadow.timer
```

Training is daily at 06:50, ten minutes after the existing 06:40 forecast job.
Shadow first runs 15 minutes after boot and every two hours. Enabling after the
boot offset may schedule immediate catch-up; that is why publication/service
evidence must already be green.

**READ-ONLY — schedule and installed definitions:**

```bash
systemctl --user list-timers thermal-model-train.timer thermal-model-shadow.timer \
  --all --no-pager
systemctl --user cat thermal-model-train.service thermal-model-train.timer \
  thermal-model-shadow.service thermal-model-shadow.timer
```

Expected: intended next runs and definitions exactly matching tracked units.

## 11. Rollback

Rollback is attended. Retain the private receipt, journal, accepted/candidate
artifacts, backtest report, and logs. Never delete/rewrite journal rows or
commit retained evidence.

**MUTATING — ROLLBACK — disable timers first:**

```bash
systemctl --user disable --now thermal-model-train.timer thermal-model-shadow.timer
```

**MUTATING — ROLLBACK — restore/remove the Item from its receipt, then verify:**

```bash
node scripts/thermal-model-config.mjs rollback --receipt-dir "$RECEIPT_DIR"
node scripts/thermal-model-config.mjs verify --receipt-dir "$RECEIPT_DIR" | jq .
```

Expected: `ok: true`, `expected: "original"`, phase `rolled-back`. The receipt
chooses exact restore versus delete from `pre-state.json`. If phase is
`rolling-back`, read exact Item state and run `settle` only after the captured
original landed exactly.

Restore exact prior runtime state from the backup. Removal targets are fixed,
and this step is destructive; review `BACKUP_DIR` first.

**READ-ONLY — confirm backup presence before exact restore/removal:**

```bash
find "$BACKUP_DIR" -maxdepth 2 -type f -printf '%P\n' | sort
```

**DESTRUCTIVE — ROLLBACK ONLY — exact runtime restore or absence:**

```bash
if test -f "$BACKUP_DIR/thermal_intel.py"; then
  install -m 0755 "$BACKUP_DIR/thermal_intel.py" \
    /home/sat/openhab/scripts/thermal_intel.py
else
  rm -- /home/sat/openhab/scripts/thermal_intel.py
fi
rm -rf -- /home/sat/openhab/scripts/thermal_model
if test -d "$BACKUP_DIR/thermal_model"; then
  cp --archive "$BACKUP_DIR/thermal_model" /home/sat/openhab/scripts/thermal_model
fi
```

Never alter either target path. `forecast_intel.py` remains untouched.

**DESTRUCTIVE — ROLLBACK ONLY — exact installed units, then reload:**

```bash
rm -- \
  /home/sat/.config/systemd/user/thermal-model-train.service \
  /home/sat/.config/systemd/user/thermal-model-train.timer \
  /home/sat/.config/systemd/user/thermal-model-shadow.service \
  /home/sat/.config/systemd/user/thermal-model-shadow.timer
systemctl --user daemon-reload
```

**READ-ONLY — final rollback verification:**

```bash
systemctl --user status thermal-model-train.service thermal-model-train.timer \
  thermal-model-shadow.service thermal-model-shadow.timer --no-pager -l
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Advisory | jq '{name,state}'
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch | jq '{name,state}'
```

Expected: units absent/inactive, observational Item exactly restored/absent,
protected states unchanged, evidence retained privately.

## Completion boundary

Artifact staging, tests, and successful shadow operation do not graduate
advice. `Thermal_Advisory`, notification policy, rules, and actuators remain
unchanged. Warm-season or winter graduation requires separate evidence review
and explicit approval; actuation requires an independent threat model and
narrow authority grant.
