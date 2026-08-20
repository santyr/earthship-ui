# Thermal model shadow attended first-install and rollback

This runbook stages one observational `Thermal_Model_JSON` Item and two user
services. It is **first-install-only**. If any thermal unit is already installed,
loaded, active, or enabled, stop and use a separately reviewed upgrade procedure.
It never changes `Thermal_Advisory`, notifications, rules, or an actuator.
Implementation, artifact acceptance, and shadow evidence do **not** graduate
advice.

Every Bash fence is independently fail-closed and begins with
`set -euo pipefail`. Run the fences in document order in one attended shell.
Assignments that execute a command stand alone so their exit status cannot be
masked by `test`, `printf`, `chmod`, `wc`, a hash, or a later command. All jq
checks use `-e` and every curl uses `--fail --silent --show-error`. Exact
systemd probes reject user-manager, D-Bus, transport, mixed-state, and unknown
state failures.

Private receipts, inventory, DSNs, histories, journal rows, artifacts, reports,
logs, and household state stay outside Git. Never print or commit secrets or
private evidence. Private directories have mode `0700` and private files have mode `0600`.
No artifact or journal content is committed.

## Exact source-to-target manifest and transaction contract

The checked-in `scripts/thermal-model-files.py` owns the fixed CLI repository,
private receipt root, and manifest. Its component walker uses pinned directory
file descriptors, `O_NOFOLLOW` and `fstat` for every source, target, backup,
temporary file, receipt, and verification read. Each new directory is followed
by an immediate parent `fsync` and new-directory `fsync`.

For each phase, the helper prevalidates every source and live target, persists
`phase-state.json`, and writes and fsyncs an intent containing a unique sibling
exchange name before touching that target. It stages, fsyncs, and verifies exact
SHA-256 and mode through pinned directory descriptors. An expected-present
replacement uses Linux `renameat2(RENAME_EXCHANGE)`, verifies the atomically
displaced former target against the receipt, and exchanges back before refusing
any raced `unowned target drift`. An expected-absent create or capture uses
`renameat2(RENAME_NOREPLACE)`. Missing kernel/filesystem capability fails closed;
there is no unsafe replacement fallback. Parent directories are fsynced before
completion is persisted. Ordinary failure automatically restores completed
replacements. A crash requires explicit `thermal-model-files.py recover` before
any next helper operation; recovery reconciles target and journal-owned staged
or displaced sibling names on either side of each exchange. Restore accepts
only receipt-owned deployed state or already-restored original/absence and
never overwrites or deletes unowned drift. If an expected-present target is
externally deleted immediately before exchange/capture, ENOENT is journaled as
refused unowned drift; automatic rollback restores only earlier helper-owned
transitions, leaves the external absence untouched, and keeps the phase
`recovery-required`.

| Phase | Tracked source | Exact live target |
| --- | --- | --- |
| verify | `openhab/scripts/forecast_intel.py` | `/home/sat/openhab/scripts/forecast_intel.py` |
| code | `openhab/scripts/thermal_intel.py` | `/home/sat/openhab/scripts/thermal_intel.py` |
| code | `openhab/scripts/thermal_model/__init__.py` | `/home/sat/openhab/scripts/thermal_model/__init__.py` |
| code | `openhab/scripts/thermal_model/actions.py` | `/home/sat/openhab/scripts/thermal_model/actions.py` |
| code | `openhab/scripts/thermal_model/artifacts.py` | `/home/sat/openhab/scripts/thermal_model/artifacts.py` |
| code | `openhab/scripts/thermal_model/behavior.py` | `/home/sat/openhab/scripts/thermal_model/behavior.py` |
| code | `openhab/scripts/thermal_model/dataset.py` | `/home/sat/openhab/scripts/thermal_model/dataset.py` |
| code | `openhab/scripts/thermal_model/dynamics.py` | `/home/sat/openhab/scripts/thermal_model/dynamics.py` |
| code | `openhab/scripts/thermal_model/evaluation.py` | `/home/sat/openhab/scripts/thermal_model/evaluation.py` |
| code | `openhab/scripts/thermal_model/journal.py` | `/home/sat/openhab/scripts/thermal_model/journal.py` |
| code | `openhab/scripts/thermal_model/pipeline.py` | `/home/sat/openhab/scripts/thermal_model/pipeline.py` |
| code | `openhab/scripts/thermal_model/schema.py` | `/home/sat/openhab/scripts/thermal_model/schema.py` |
| unit | `deploy/thermal-model-train.service` | `/home/sat/.config/systemd/user/thermal-model-train.service` |
| unit | `deploy/thermal-model-train.timer` | `/home/sat/.config/systemd/user/thermal-model-train.timer` |
| unit | `deploy/thermal-model-shadow.service` | `/home/sat/.config/systemd/user/thermal-model-shadow.service` |
| unit | `deploy/thermal-model-shadow.timer` | `/home/sat/.config/systemd/user/thermal-model-shadow.timer` |

`openhab/thermal-model-items.json`, `scripts/thermal-model-config.mjs`,
`scripts/thermal-model-files.py`, `scripts/thermal-systemd-state.py`, and
`openhab/scripts/validate_thermal_shadow.py` are deployment/review tools, not
service runtime files.

## 1. Read-only preflight

**READ-ONLY — reviewed repository state:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
git rev-parse HEAD
WORKTREE_STATUS="$(git status --short)"
test -z "$WORKTREE_STATUS"
git diff --check
```

**READ-ONLY — compute the tracked runtime-manifest SHA-256:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui/openhab/scripts
TRACKED_RUNTIME_REVISION="$(/usr/bin/python3 -c 'import thermal_intel; print(thermal_intel._code_revision())')"
test "${#TRACKED_RUNTIME_REVISION}" -eq 64
printf '%s\n' "$TRACKED_RUNTIME_REVISION"
export TRACKED_RUNTIME_REVISION
```

The digest length-prefixes every exact relative path and file body in the
complete service runtime manifest and is independent of Git discovery.

**READ-ONLY — inspect proposed Item presence without an expected 404:**

```bash
set -euo pipefail
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items \
  | jq -e '[.[] | select(.name == "Thermal_Model_JSON")] | if length <= 1 then . else error("duplicate Item") end'
```

**READ-ONLY — inspect advisory, known actuator, and physical inputs:**

```bash
set -euo pipefail
for ITEM in Thermal_Advisory SouthOutlet_Outlet2_Switch \
  AmbientWeatherWS2902A_IndoorSensor_Temperature \
  AmbientWeatherWS2902A_WH31E_193_Temperature \
  Shelly_HT1_Indoor_Temperature \
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature \
  AmbientWeatherWS2902A_SolarRadiation
do
  curl --fail --silent --show-error "http://127.0.0.1:5190/rest/items/${ITEM}" \
    | jq -e '{name,type,label,state} | select(.name != null and .type != null)'
done
```

**READ-ONLY — persistence service inventory:**

```bash
set -euo pipefail
curl --fail --silent --show-error http://127.0.0.1:5190/rest/persistence \
  | jq -e 'map({id,label}) | select(any(.[]; .id == "jdbc"))'
```

**SESSION-ONLY — bounded UTC inventory window:**

```bash
set -euo pipefail
START_UTC="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
test "$START_UTC" != "$END_UTC"
export START_UTC END_UTC
```

**READ-ONLY — recent JDBC counts only:**

```bash
set -euo pipefail
: "${START_UTC:?run the inventory-window fence}"
: "${END_UTC:?run the inventory-window fence}"
for ITEM in AmbientWeatherWS2902A_IndoorSensor_Temperature \
  AmbientWeatherWS2902A_WH31E_193_Temperature \
  Shelly_HT1_Indoor_Temperature \
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature \
  AmbientWeatherWS2902A_SolarRadiation
do
  curl --fail --silent --show-error \
    "http://127.0.0.1:5190/rest/persistence/items/${ITEM}?serviceId=jdbc&starttime=${START_UTC}&endtime=${END_UTC}" \
    | jq -e --arg item "$ITEM" '{item:$item,count:(.data|length),latest:(.data[-1].time // null)} | select(.count > 0 and .latest != null)'
done
```

**READ-ONLY — first-install systemd quiescence:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py first-install
```

This requires all four units to report exactly `LoadState=not-found`,
`ActiveState=inactive`, and empty `UnitFileState`. Any installed, loaded,
active, enabled, mixed, or unqueryable state aborts this runbook.

## 2. Preliminary authorization: private receipt facts only

Pause. Obtain preliminary authorization for only secure 0700 private directory
creation, one read-only Item snapshot with local receipt, read-only capture of
exact live file targets into durable private backups, and one isolated offline
receipt rehearsal whose in-memory transport is seeded only by that snapshot and
the reviewed desired manifest. It authorizes no network call during rehearsal,
live file replacement, database change, model run, Item write, or systemd
mutation.

**SESSION-ONLY — bind exact private paths:**

```bash
set -euo pipefail
umask 077
REPO_ROOT=/home/sat/earthship-ui
EVIDENCE_ROOT=/home/sat/.local/state/thermal-intel/deploy-receipts/ATTENDED-ID
ITEM_RECEIPT="$EVIDENCE_ROOT/item"
PHOTOSENSOR_RECEIPT="$EVIDENCE_ROOT/photosensor"
FILE_RECEIPT="$EVIDENCE_ROOT/files"
STATE_ROOT=/home/sat/.local/state/thermal-intel
test "$REPO_ROOT" = /home/sat/earthship-ui
test "$STATE_ROOT" = /home/sat/.local/state/thermal-intel
export REPO_ROOT EVIDENCE_ROOT ITEM_RECEIPT PHOTOSENSOR_RECEIPT FILE_RECEIPT STATE_ROOT
```

**PRELIMINARY MUTATION — securely prepare exact private directories:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py prepare \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
for DIR in "$STATE_ROOT" "$STATE_ROOT/models" "$STATE_ROOT/review" \
  "$STATE_ROOT/evidence" "$EVIDENCE_ROOT" "$ITEM_RECEIPT" \
  "$PHOTOSENSOR_RECEIPT" "$FILE_RECEIPT"
do
  DIR_MODE="$(stat -c %a "$DIR")"
  test "$DIR_MODE" = 700
done
```

The helper validates every component without following symlinks and fsyncs
each newly created parent and directory.

**PRELIMINARY MUTATION — receipt-bound Item snapshot:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs snapshot --receipt-dir "$ITEM_RECEIPT"
ITEM_RECEIPT_MODE="$(stat -c %a "$ITEM_RECEIPT")"
ITEM_STATE_MODE="$(stat -c %a "$ITEM_RECEIPT/receipt.json")"
ITEM_SNAPSHOT_MODE="$(stat -c %a "$ITEM_RECEIPT/pre-state.json")"
test "$ITEM_RECEIPT_MODE" = 700
test "$ITEM_STATE_MODE" = 600
test "$ITEM_SNAPSHOT_MODE" = 600
```

**PRELIMINARY MUTATION — durable backup of every code and unit target:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py snapshot \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
FILE_RECEIPT_MODE="$(stat -c %a "$FILE_RECEIPT")"
FILE_MANIFEST_MODE="$(stat -c %a "$FILE_RECEIPT/file-manifest.json")"
test "$FILE_RECEIPT_MODE" = 700
test "$FILE_MANIFEST_MODE" = 600
```

**READ-ONLY — exact apply plan and rollback facts:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs plan --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.apply|length == 1) | select(.rollback|length == 1)'
```

**PRELIMINARY PRIVATE MUTATION — isolated offline apply/verify/rollback/verify/close rehearsal:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs rehearse --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.itemName == "Thermal_Model_JSON")
    | select(.transitions == ["applying","applied","desired","rolling-back","rolled-back","closed:rolled-back"])
    | select(.terminal == {state:"closed",phase:"rolled-back",closedPhase:"rolled-back"})
    | select(.writeCounts.total == 2)
    | select(([.operations[] | select(.method != "GET")] | length) == 2)
    | select(all(.operations[];
        .path == "/rest/items/Thermal_Model_JSON"
        and (.method == "GET" or .method == "PUT" or .method == "DELETE")
        and (.bodyDigest == null or ((.bodyDigest | type) == "string" and (.bodyDigest | length) == 64))))'
```

This command does not load the OpenHAB credential file and cannot construct a
REST client. It copies only the checksum-verified receipt and snapshot into a
private isolated directory, exercises the production transaction state machine
against an in-memory exact-Item transport, reports every exact path/body digest,
transition, and write count, verifies the real receipt bytes did not change,
and removes only the isolated copy.

**READ-ONLY — durable file receipt facts and explicit absent markers:**

```bash
set -euo pipefail
: "${FILE_RECEIPT:?}"
jq -e 'select(.schema == "earthship-thermal-file-deploy/v1")
  | select((.checksum | type) == "string" and (.checksum | length) == 64)
  | select((.entries | length) == 16)
  | {schema,checksum,entries:[.entries[]|{source,target,phase,source_sha256,prior,prior_sha256,backup,marker}]}' \
  "$FILE_RECEIPT/file-manifest.json"
BACKUP_COUNT="$(find "$FILE_RECEIPT/backups" -maxdepth 1 -type f -printf . | wc -c)"
WEAK_BACKUP="$(find "$FILE_RECEIPT/backups" -maxdepth 1 -type f ! -perm 0600 -print -quit)"
test "$BACKUP_COUNT" -eq 15
test -z "$WEAK_BACKUP"
find "$FILE_RECEIPT/backups" -maxdepth 1 -type f -printf '%f %m\n' | sort
```

**PRELIMINARY MUTATION — durable reviewed-commit-to-runtime mapping:**

```bash
set -euo pipefail
umask 077
: "${EVIDENCE_ROOT:?}"
: "${TRACKED_RUNTIME_REVISION:?compute tracked runtime digest}"
MAP_TMP="$(mktemp --tmpdir="$EVIDENCE_ROOT" .revision-map.XXXXXX)"
chmod 0600 "$MAP_TMP"
REVIEWED_GIT_REVISION="$(git -C /home/sat/earthship-ui rev-parse HEAD)"
test "${#REVIEWED_GIT_REVISION}" -eq 40
printf 'git=%s\nruntime_sha256=%s\n' "$REVIEWED_GIT_REVISION" "$TRACKED_RUNTIME_REVISION" > "$MAP_TMP"
sync -f "$MAP_TMP"
mv -- "$MAP_TMP" "$EVIDENCE_ROOT/revision-map.txt"
sync -f "$EVIDENCE_ROOT"
REVISION_MAP_MODE="$(stat -c %a "$EVIDENCE_ROOT/revision-map.txt")"
test "$REVISION_MAP_MODE" = 600
```

Present the Item snapshot digest, apply/rollback plan, closed offline rehearsal
evidence, exact backup receipt, explicit absent markers, reviewed Git commit,
runtime-manifest SHA-256, first-install quiescence, inventory, and repository
totals before Gate A. The attended operator must re-run the rehearsal and review
its exact packet before Gate B if any tracked desired manifest or receipt fact
changes.

## 2a. Photosensor acquisition authorization

Pause for the photosensor acquisition authorization. It permits only the
receipt-owned creation of these observation resources for the ONLINE hallway
Philips SML003 Thing `zigbee:device:a7351eb531:001788011024c307`:

| Item | Type | Exact channel suffix |
| --- | --- | --- |
| `LivingOffice_Shade_Illuminance` | `Number` | `001788011024C307_2_illuminance` |
| `LivingOffice_Shade_Occupancy` | `Switch` | `001788011024C307_2_occupancy` |
| `LivingOffice_Shade_Temperature` | `Number:Temperature` | `001788011024C307_2_temperature` |

The hallway position represents the living-room/office windows. This gate does
not change the Thing, persistence policy, metadata, rules, Item values, or any
unlisted Item/link. It begins raw observation collection only. There are no
photosensor-derived shade labels until a later calibrated design has adequate
history and confirmed shade transitions.

**PHOTOSENSOR PRIVATE MUTATION — sanitized snapshot and exact evidence:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs snapshot \
  --receipt-dir "$PHOTOSENSOR_RECEIPT"
PHOTOSENSOR_DIR_MODE="$(stat -c %a "$PHOTOSENSOR_RECEIPT")"
PHOTOSENSOR_RECEIPT_MODE="$(stat -c %a "$PHOTOSENSOR_RECEIPT/receipt.json")"
PHOTOSENSOR_SNAPSHOT_MODE="$(stat -c %a "$PHOTOSENSOR_RECEIPT/pre-state.json")"
test "$PHOTOSENSOR_DIR_MODE" = 700
test "$PHOTOSENSOR_RECEIPT_MODE" = 600
test "$PHOTOSENSOR_SNAPSHOT_MODE" = 600
jq -e 'select(.thing.uid == "zigbee:device:a7351eb531:001788011024c307")
  | select(.thing.status == "ONLINE")
  | select((.thing.channels | length) == 3)
  | select(.jdbc.serviceId == "jdbc" and .jdbc.editable == true)
  | select(.jdbc.wildcardStrategies | index("everyChange"))
  | select(.jdbc.wildcardStrategies | index("restoreOnStartup"))' \
  "$PHOTOSENSOR_RECEIPT/pre-state.json"
```

The snapshot contains only normalized Item/link DTOs and sanitized Thing/JDBC
evidence. The existing editable JDBC wildcard `*` policy already includes
`everyChange` and `restoreOnStartup`; it is verified read-only and never
written by this procedure.

**READ-ONLY — exact six-write apply and reverse rollback packet:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs plan \
  --receipt-dir "$PHOTOSENSOR_RECEIPT" \
  | jq -e 'select((.apply | length) == 6)
    | select((.rollback | length) == 6)
    | select([.apply[0:3][].path] == [
        "/rest/items/LivingOffice_Shade_Illuminance",
        "/rest/items/LivingOffice_Shade_Occupancy",
        "/rest/items/LivingOffice_Shade_Temperature"])
    | select(all(.apply[0:3][]; .method == "PUT"))
    | select(all(.apply[3:6][]; .method == "PUT"))'
```

**PHOTOSENSOR PRIVATE MUTATION — isolated offline receipt rehearsal:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs rehearse \
  --receipt-dir "$PHOTOSENSOR_RECEIPT" \
  | jq -e 'select(.writeCounts == {put:6,delete:6,total:12})
    | select(.terminal == {state:"closed",phase:"rolled-back"})'
```

Rehearsal cannot load authorization or contact OpenHAB. Review its exact paths
and body digests before the live apply.

**PHOTOSENSOR MUTATION — receipt-owned three-Item/three-link apply:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs apply \
  --receipt-dir "$PHOTOSENSOR_RECEIPT"
```

If the command returns ambiguously, do not retry. Run settlement once; it
accepts only the exact receipt-owned prefix and never repeats the pending write:

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
PHOTOSENSOR_PHASE="$(jq -e -r '.phase' "$PHOTOSENSOR_RECEIPT/receipt.json")"
PHOTOSENSOR_PENDING="$(jq -e -r '.pendingOperation' "$PHOTOSENSOR_RECEIPT/receipt.json")"
if test "$PHOTOSENSOR_PHASE" = applying && test "$PHOTOSENSOR_PENDING" != null; then
  node scripts/thermal-photosensor-config.mjs settle \
    --receipt-dir "$PHOTOSENSOR_RECEIPT"
fi
PHOTOSENSOR_PHASE="$(jq -e -r '.phase' "$PHOTOSENSOR_RECEIPT/receipt.json")"
PHOTOSENSOR_PENDING="$(jq -e -r '.pendingOperation' "$PHOTOSENSOR_RECEIPT/receipt.json")"
case "$PHOTOSENSOR_PHASE:$PHOTOSENSOR_PENDING" in
  applying:null)
    node scripts/thermal-photosensor-config.mjs apply \
      --receipt-dir "$PHOTOSENSOR_RECEIPT"
    ;;
  desired:null)
    ;;
  *)
    printf '%s\n' 'unexpected photosensor receipt state after settlement' >&2
    exit 1
    ;;
esac
```

The final `apply` only resumes a prefix that settlement proved exact. It fails
if the receipt is already terminal, so skip it when settlement reports
`phase=desired`.

**READ-ONLY — exact Item/link verification and receipt closure:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs verify \
  --receipt-dir "$PHOTOSENSOR_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "desired" and .phase == "desired")'
node scripts/thermal-photosensor-config.mjs close \
  --receipt-dir "$PHOTOSENSOR_RECEIPT"
jq -e 'select(.state == "closed" and .phase == "desired"
  and .closedPhase == "desired" and .writeCount == 6)' \
  "$PHOTOSENSOR_RECEIPT/receipt.json"
```

**READ-ONLY — bounded JDBC acquisition check:**

```bash
set -euo pipefail
START_UTC="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for ITEM in LivingOffice_Shade_Illuminance \
  LivingOffice_Shade_Occupancy LivingOffice_Shade_Temperature
do
  COUNT="$(curl --fail --silent --show-error \
    "http://127.0.0.1:5190/rest/persistence/items/${ITEM}?serviceId=jdbc&starttime=${START_UTC}&endtime=${END_UTC}" \
    | jq -e '.data | length')"
  case "$COUNT" in
    0) printf '%s\n' "$ITEM pending first acquisition" ;;
    *) printf '%s %s\n' "$ITEM" "$COUNT" ;;
  esac
done
```

Present the closed receipt and either each first JDBC point or its explicit
`pending first acquisition` result before continuing. This acquisition is not
Gate B publication and does not create `Thermal_Model_JSON`.

## 3. Gate A: code, database, and private model evidence

Gate A authorizes only atomic live code installation, exact role/schema
audit and `thermal_intel` migration/grants, and private training, backtest,
artifact, and local-only shadow creation. It authorizes no Item write,
publication, credential provisioning, unit installation, or systemd mutation.
The train/backtest commands below omit explicit date bounds and therefore use
exactly 400 rolling days ending at their training origin.

**READ-ONLY — repeat quiescence immediately before code replacement:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py first-install
```

**GATE A MUTATION — transactional code phase installation:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py install-code \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
/usr/bin/python3 scripts/thermal-model-files.py verify-code \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
jq -e 'select(.schema == "earthship-thermal-file-phase/v1" and .operation == "install-code" and .status == "complete")' \
  "$FILE_RECEIPT/phase-state.json"
```

If the helper reports explicit recovery required, stop. Do not run Python from
the live target. Under Gate A, the only permitted recovery command is:

**GATE A RECOVERY MUTATION — reconcile and restore the interrupted code phase:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py recover \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
jq -e 'select(.status == "rolled-back")' "$FILE_RECEIPT/phase-state.json"
```

After recovery, return to the Gate A approval boundary before retrying.

**READ-ONLY — live runtime provenance equals reviewed provenance:**

```bash
set -euo pipefail
: "${TRACKED_RUNTIME_REVISION:?}"
cd /home/sat/openhab/scripts
LIVE_RUNTIME_REVISION="$(/usr/bin/python3 -c 'import thermal_intel; print(thermal_intel._code_revision())')"
test "$LIVE_RUNTIME_REVISION" = "$TRACKED_RUNTIME_REVISION"
printf '%s\n' "$LIVE_RUNTIME_REVISION"
export LIVE_RUNTIME_REVISION
```

### Exact PostgreSQL authority and migration

`thermal_intel_runtime` and its credentials must pre-exist through a separate
operator/DBA process. This runbook never creates, alters, normalizes, or prints
that role or its credentials. The database policy is exact: `CONNECT=true`,
`TEMP=true` (the database's existing PUBLIC default, explicitly accepted but
unused), and `CREATE=false`. The runbook does not broadly revoke PUBLIC.
Built-in system catalog visibility is allowed; application authority is not.
The audit refuses effective privileges outside `thermal_intel`.

The exact schema inventory after migration is three ordinary tables only:
`action_events`, `message_receipts`, and `mode_events`. The exact non-internal
trigger graph is three enabled `reject_mutation` BEFORE UPDATE/DELETE row
triggers (`tgtype=27`) plus two enabled, deferrable, initially-deferred
`reject_correction_cycle` AFTER INSERT row triggers (`tgtype=5`), with exact
target-table OIDs, function schema/name, zero arguments, no WHEN clauses, and
empty `tgattr` (never an `UPDATE OF` subset). Each expected relation must be an
ordinary persistent, nonpartitioned, non-RLS table; a same-name partitioned
table, view, materialized view, sequence, foreign table, or any extra non-index
relation is refused. The only functions are
the three non-security-definer trigger functions
`reject_action_correction_cycle`, `reject_journal_mutation`, and
`reject_mode_correction_cycle`. There are no views, materialized views,
foreign tables, partitions, sequences, procedures, overloaded extras, or
unexpected ACL grantees. Runtime authority is schema USAGE and table
SELECT/INSERT only. The deterministic catalog fingerprint additionally covers
columns, types, type modifiers, nullability, defaults, identity and generated
attributes, collations, exact constraint and index definitions (including key
order, INCLUDE fields, expressions, and predicates), trigger/function bodies,
relation persistence, RLS/forced-RLS, replica identity, partition and access
method properties, object owner, explicit ACL grantor/grantee identities, grantability,
column and function ACLs, relevant expected-owner default ACLs, role-membership edges,
and effective PUBLIC/runtime/owner privileges. Only the receipt-bound admin owner and
runtime role are normalized to stable tokens; every unexpected identity remains literal
and changes the fingerprint. Migration computes this exact fingerprint before any DDL
when the schema is nonempty; only an absent or empty schema may proceed without a match.
The post-migration and runtime audit command returns only schema, status, and fingerprint
JSON and never prints either DSN.

**GATE A MUTATION — secret-safe pre-audit, migration, and exact post-audit:**

```bash
set -euo pipefail
(
  set -euo pipefail
  umask 077
  : "${EVIDENCE_ROOT:?}"
  read -r -s -p 'THERMAL_DATABASE_ADMIN_URL: ' THERMAL_DATABASE_ADMIN_URL
  printf '\n'
  test -n "$THERMAL_DATABASE_ADMIN_URL"
  export THERMAL_DATABASE_ADMIN_URL
  THERMAL_DATABASE_RUNTIME_ROLE=thermal_intel_runtime
  export THERMAL_DATABASE_RUNTIME_ROLE
  THERMAL_DATABASE_EXPECTED_OWNER="$(psql "$THERMAL_DATABASE_ADMIN_URL" \
    -X --set ON_ERROR_STOP=1 --tuples-only --no-align --quiet \
    --command 'SELECT current_user')"
  test -n "$THERMAL_DATABASE_EXPECTED_OWNER"
  case "$THERMAL_DATABASE_EXPECTED_OWNER" in
    *$'\n'*) exit 1 ;;
  esac
  export THERMAL_DATABASE_EXPECTED_OWNER
  EXPECTED_OWNER_RECEIPT="$EVIDENCE_ROOT/database-expected-owner"
  test ! -e "$EXPECTED_OWNER_RECEIPT"
  test ! -L "$EXPECTED_OWNER_RECEIPT"
  EXPECTED_OWNER_TMP="$(mktemp "$EVIDENCE_ROOT/.database-expected-owner.XXXXXX")"
  printf '%s\n' "$THERMAL_DATABASE_EXPECTED_OWNER" >"$EXPECTED_OWNER_TMP"
  chmod 600 "$EXPECTED_OWNER_TMP"
  ln -- "$EXPECTED_OWNER_TMP" "$EXPECTED_OWNER_RECEIPT"
  sync -f "$EXPECTED_OWNER_RECEIPT"
  unlink -- "$EXPECTED_OWNER_TMP"
  sync -f "$EVIDENCE_ROOT"
  EXPECTED_OWNER_MODE="$(stat -c %a "$EXPECTED_OWNER_RECEIPT")"
  test "$EXPECTED_OWNER_MODE" = 600
  trap 'unset THERMAL_DATABASE_ADMIN_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER' EXIT HUP INT TERM

  psql "$THERMAL_DATABASE_ADMIN_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE r pg_roles%ROWTYPE;
DECLARE schema_oid oid;
DECLARE actual_tables text[];
DECLARE table_oids oid[];
DECLARE actual_functions text[];
DECLARE actual_triggers text[];
BEGIN
  SELECT * INTO r FROM pg_roles WHERE rolname='thermal_intel_runtime';
  IF NOT FOUND THEN RAISE EXCEPTION 'runtime role must pre-exist'; END IF;
  IF NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreaterole
     OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls THEN
    RAISE EXCEPTION 'runtime role attributes are not exact';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
    RAISE EXCEPTION 'runtime role has role memberships';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner=r.oid) THEN
    RAISE EXCEPTION 'runtime role owns database or application objects';
  END IF;
  SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname='thermal_intel';
  IF schema_oid IS NOT NULL THEN
    SELECT COALESCE(array_agg(concat_ws('|',
      relname,
      relkind,
      relpersistence,
      CASE WHEN relispartition THEN '1' ELSE '0' END,
      CASE WHEN relrowsecurity THEN '1' ELSE '0' END,
      CASE WHEN relforcerowsecurity THEN '1' ELSE '0' END
    ) ORDER BY relname),ARRAY[]::text[])
      INTO actual_tables FROM pg_class
      WHERE relnamespace=schema_oid AND relkind NOT IN ('i','I');
    SELECT COALESCE(array_agg(oid ORDER BY relname),ARRAY[]::oid[])
      INTO table_oids FROM pg_class
      WHERE relnamespace=schema_oid
        AND relname IN ('action_events','message_receipts','mode_events')
        AND relkind='r' AND relpersistence='p'
        AND NOT relispartition AND NOT relrowsecurity
        AND NOT relforcerowsecurity;
    SELECT COALESCE(array_agg(proname||'/'||pronargs||'/'||prokind ORDER BY proname),ARRAY[]::text[])
      INTO actual_functions FROM pg_proc WHERE pronamespace=schema_oid;
    IF actual_tables IS DISTINCT FROM ARRAY[
         'action_events|r|p|0|0|0',
         'message_receipts|r|p|0|0|0',
         'mode_events|r|p|0|0|0'
       ]::text[]
       OR cardinality(table_oids) <> 3
       OR actual_functions IS DISTINCT FROM ARRAY[
         'reject_action_correction_cycle/0/f',
         'reject_journal_mutation/0/f',
         'reject_mode_correction_cycle/0/f'
       ]::text[] THEN
      RAISE EXCEPTION 'pre-migration thermal_intel inventory is not exact';
    END IF;
    IF EXISTS (
      SELECT 1 FROM pg_proc
      WHERE pronamespace=schema_oid
        AND (prosecdef OR prokind <> 'f' OR pronargs <> 0 OR pg_get_function_result(oid) <> 'trigger')
    ) THEN RAISE EXCEPTION 'pre-migration trigger attributes are not exact'; END IF;
  SELECT COALESCE(array_agg(
      concat_ws('|',
      c.relname,
      t.tgname,
      fnn.nspname,
      p.proname,
      t.tgenabled,
      t.tgtype::integer::text,
      CASE WHEN t.tgdeferrable THEN '1' ELSE '0' END,
      CASE WHEN t.tginitdeferred THEN '1' ELSE '0' END,
      t.tgnargs::integer::text,
      CASE WHEN t.tgqual IS NULL THEN '1' ELSE '0' END,
      CASE WHEN t.tgisinternal THEN '1' ELSE '0' END,
      COALESCE(NULLIF(t.tgattr::text,''), '-')
    ) ORDER BY c.relname,t.tgname
  ),ARRAY[]::text[]) INTO actual_triggers
  FROM pg_trigger t
  JOIN pg_class c ON c.oid=t.tgrelid
  JOIN pg_proc p ON p.oid=t.tgfoid
  JOIN pg_namespace fnn ON fnn.oid=p.pronamespace
  WHERE c.oid = ANY(table_oids) AND NOT t.tgisinternal;
  IF actual_triggers IS DISTINCT FROM ARRAY[
    'action_events|reject_correction_cycle|thermal_intel|reject_action_correction_cycle|O|5|1|1|0|1|0|-',
    'action_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'message_receipts|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'mode_events|reject_correction_cycle|thermal_intel|reject_mode_correction_cycle|O|5|1|1|0|1|0|-',
    'mode_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-'
  ]::text[] THEN
    RAISE EXCEPTION 'thermal trigger graph is not exact: %',actual_triggers;
  END IF;
    IF NOT has_schema_privilege(r.oid,schema_oid,'USAGE')
       OR has_schema_privilege(r.oid,schema_oid,'CREATE') THEN
      RAISE EXCEPTION 'pre-migration schema privileges are not exact';
    END IF;
    IF EXISTS (
      SELECT 1 FROM pg_namespace n,
        LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
      WHERE n.oid=schema_oid
        AND (a.grantee NOT IN (n.nspowner,r.oid)
          OR (a.grantee=r.oid AND (a.privilege_type <> 'USAGE' OR a.is_grantable)))
    ) THEN RAISE EXCEPTION 'pre-migration schema ACL has unexpected grants'; END IF;
    IF EXISTS (
      SELECT 1 FROM pg_class c
      WHERE c.oid = ANY(table_oids)
        AND NOT (
          has_table_privilege(r.oid,c.oid,'SELECT')
          AND has_table_privilege(r.oid,c.oid,'INSERT')
          AND NOT has_table_privilege(r.oid,c.oid,'UPDATE')
          AND NOT has_table_privilege(r.oid,c.oid,'DELETE')
          AND NOT has_table_privilege(r.oid,c.oid,'TRUNCATE')
          AND NOT has_table_privilege(r.oid,c.oid,'REFERENCES')
          AND NOT has_table_privilege(r.oid,c.oid,'TRIGGER')
        )
    ) THEN RAISE EXCEPTION 'pre-migration table privileges are not exact'; END IF;
    IF EXISTS (
      SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
      WHERE c.oid = ANY(table_oids)
        AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
    ) THEN RAISE EXCEPTION 'pre-migration column ACLs are not allowed'; END IF;
    IF EXISTS (
      SELECT 1 FROM pg_class c,
        LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
      WHERE c.oid = ANY(table_oids)
        AND (a.grantee NOT IN (c.relowner,r.oid)
          OR (a.grantee=r.oid AND (a.privilege_type NOT IN ('SELECT','INSERT') OR a.is_grantable)))
    ) THEN RAISE EXCEPTION 'pre-migration table ACL has unexpected grants'; END IF;
    IF EXISTS (
      SELECT 1 FROM pg_proc p,
        LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.pronamespace=schema_oid AND a.grantee <> p.proowner
    ) OR EXISTS (
      SELECT 1 FROM pg_proc p
      WHERE p.pronamespace=schema_oid
        AND has_function_privilege(r.oid,p.oid,'EXECUTE')
    ) THEN RAISE EXCEPTION 'pre-migration function ACL has unexpected grants'; END IF;
  END IF;
  IF NOT has_database_privilege(r.oid,current_database(),'CONNECT')
     OR NOT has_database_privilege(r.oid,current_database(),'TEMP')
     OR has_database_privilege(r.oid,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'database CONNECT TEMP CREATE policy is not exact';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n
    WHERE n.nspname !~ '^pg_(temp|toast_temp)_'
      AND has_schema_privilege(r.oid,n.oid,'CREATE')
  ) THEN RAISE EXCEPTION 'runtime role has schema CREATE'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r','p','v','m','f')
      AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  ) THEN RAISE EXCEPTION 'effective privileges outside thermal_intel'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind='S'
      AND has_sequence_privilege(r.oid,c.oid,'USAGE,SELECT,UPDATE')
  ) THEN RAISE EXCEPTION 'effective sequence privileges outside thermal_intel'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND has_function_privilege(r.oid,p.oid,'EXECUTE')
  ) THEN RAISE EXCEPTION 'effective function or procedure privileges outside thermal_intel'; END IF;
END $audit$;
SQL

  cd /home/sat/openhab/scripts
  /usr/bin/python3 -c 'import os; from thermal_model.journal import migrate; migrate(os.environ["THERMAL_DATABASE_ADMIN_URL"], runtime_role=os.environ["THERMAL_DATABASE_RUNTIME_ROLE"], expected_owner=os.environ["THERMAL_DATABASE_EXPECTED_OWNER"])'
  /usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py schema-audit \
    | jq -e 'select(.schema == "thermal_intel" and .status == "exact" and .fingerprint == "786e9b7bf3ca5587f08bcdcd960239a88bf887a8b31c4ea5eddcbc808c496efb")' >/dev/null

  psql "$THERMAL_DATABASE_ADMIN_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE r pg_roles%ROWTYPE;
DECLARE schema_oid oid;
DECLARE actual_tables text[];
DECLARE table_oids oid[];
DECLARE actual_functions text[];
DECLARE actual_triggers text[];
BEGIN
  SELECT * INTO r FROM pg_roles WHERE rolname='thermal_intel_runtime';
  IF NOT FOUND OR NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper
     OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls THEN
    RAISE EXCEPTION 'runtime role attributes changed';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
     OR EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner=r.oid) THEN
    RAISE EXCEPTION 'runtime role membership or ownership changed';
  END IF;
  IF NOT has_database_privilege(r.oid,current_database(),'CONNECT')
     OR NOT has_database_privilege(r.oid,current_database(),'TEMP')
     OR has_database_privilege(r.oid,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'database CONNECT TEMP CREATE policy changed';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n
    WHERE n.nspname !~ '^pg_(temp|toast_temp)_'
      AND has_schema_privilege(r.oid,n.oid,'CREATE')
  ) THEN RAISE EXCEPTION 'runtime role has schema CREATE'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r','p','v','m','f')
      AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  ) THEN RAISE EXCEPTION 'effective privileges outside thermal_intel'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind='S'
      AND has_sequence_privilege(r.oid,c.oid,'USAGE,SELECT,UPDATE')
  ) THEN RAISE EXCEPTION 'effective sequence privileges outside thermal_intel'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND has_function_privilege(r.oid,p.oid,'EXECUTE')
  ) THEN RAISE EXCEPTION 'effective function or procedure privileges outside thermal_intel'; END IF;

  SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname='thermal_intel';
  IF schema_oid IS NULL THEN RAISE EXCEPTION 'thermal_intel schema absent'; END IF;
  SELECT COALESCE(array_agg(concat_ws('|',
    relname,
    relkind,
    relpersistence,
    CASE WHEN relispartition THEN '1' ELSE '0' END,
    CASE WHEN relrowsecurity THEN '1' ELSE '0' END,
    CASE WHEN relforcerowsecurity THEN '1' ELSE '0' END
  ) ORDER BY relname),ARRAY[]::text[])
    INTO actual_tables FROM pg_class
    WHERE relnamespace=schema_oid AND relkind NOT IN ('i','I');
  SELECT COALESCE(array_agg(oid ORDER BY relname),ARRAY[]::oid[])
    INTO table_oids FROM pg_class
    WHERE relnamespace=schema_oid
      AND relname IN ('action_events','message_receipts','mode_events')
      AND relkind='r' AND relpersistence='p'
      AND NOT relispartition AND NOT relrowsecurity
      AND NOT relforcerowsecurity;
  IF actual_tables IS DISTINCT FROM ARRAY[
    'action_events|r|p|0|0|0',
    'message_receipts|r|p|0|0|0',
    'mode_events|r|p|0|0|0'
  ]::text[]
     OR cardinality(table_oids) <> 3 THEN
    RAISE EXCEPTION 'thermal relation inventory is not exact: %',actual_tables;
  END IF;
  SELECT COALESCE(array_agg(proname||'/'||pronargs||'/'||prokind ORDER BY proname),ARRAY[]::text[])
    INTO actual_functions FROM pg_proc WHERE pronamespace=schema_oid;
  IF actual_functions IS DISTINCT FROM ARRAY[
    'reject_action_correction_cycle/0/f',
    'reject_journal_mutation/0/f',
    'reject_mode_correction_cycle/0/f'
  ]::text[] THEN
    RAISE EXCEPTION 'thermal function inventory is not exact: %',actual_functions;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_proc
    WHERE pronamespace=schema_oid
      AND (prosecdef OR prokind <> 'f' OR pronargs <> 0 OR pg_get_function_result(oid) <> 'trigger')
  ) THEN RAISE EXCEPTION 'thermal trigger function attributes are not exact'; END IF;
  SELECT COALESCE(array_agg(
    concat_ws('|',
      c.relname,
      t.tgname,
      fnn.nspname,
      p.proname,
      t.tgenabled,
      t.tgtype::integer::text,
      CASE WHEN t.tgdeferrable THEN '1' ELSE '0' END,
      CASE WHEN t.tginitdeferred THEN '1' ELSE '0' END,
      t.tgnargs::integer::text,
      CASE WHEN t.tgqual IS NULL THEN '1' ELSE '0' END,
      CASE WHEN t.tgisinternal THEN '1' ELSE '0' END,
      COALESCE(NULLIF(t.tgattr::text,''), '-')
    ) ORDER BY c.relname,t.tgname
  ),ARRAY[]::text[]) INTO actual_triggers
  FROM pg_trigger t
  JOIN pg_class c ON c.oid=t.tgrelid
  JOIN pg_proc p ON p.oid=t.tgfoid
  JOIN pg_namespace fnn ON fnn.oid=p.pronamespace
  WHERE c.oid = ANY(table_oids) AND NOT t.tgisinternal;
  IF actual_triggers IS DISTINCT FROM ARRAY[
    'action_events|reject_correction_cycle|thermal_intel|reject_action_correction_cycle|O|5|1|1|0|1|0|-',
    'action_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'message_receipts|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'mode_events|reject_correction_cycle|thermal_intel|reject_mode_correction_cycle|O|5|1|1|0|1|0|-',
    'mode_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-'
  ]::text[] THEN
    RAISE EXCEPTION 'thermal trigger graph is not exact: %',actual_triggers;
  END IF;
  IF NOT has_schema_privilege(r.oid,schema_oid,'USAGE')
     OR has_schema_privilege(r.oid,schema_oid,'CREATE') THEN
    RAISE EXCEPTION 'thermal schema privileges are not exact';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n,
      LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
    WHERE n.oid=schema_oid
      AND (a.grantee NOT IN (n.nspowner,r.oid)
        OR (a.grantee=r.oid AND (a.privilege_type <> 'USAGE' OR a.is_grantable)))
  ) THEN RAISE EXCEPTION 'thermal schema ACL has unexpected grants'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c
    WHERE c.oid = ANY(table_oids)
      AND NOT (
        has_table_privilege(r.oid,c.oid,'SELECT')
        AND has_table_privilege(r.oid,c.oid,'INSERT')
        AND NOT has_table_privilege(r.oid,c.oid,'UPDATE')
        AND NOT has_table_privilege(r.oid,c.oid,'DELETE')
        AND NOT has_table_privilege(r.oid,c.oid,'TRUNCATE')
        AND NOT has_table_privilege(r.oid,c.oid,'REFERENCES')
        AND NOT has_table_privilege(r.oid,c.oid,'TRIGGER')
      )
  ) THEN RAISE EXCEPTION 'thermal table effective privileges are not exact'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
    WHERE c.oid = ANY(table_oids)
      AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
  ) THEN RAISE EXCEPTION 'thermal column ACLs are not allowed'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c,
      LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
    WHERE c.oid = ANY(table_oids)
      AND (a.grantee NOT IN (c.relowner,r.oid)
        OR (a.grantee=r.oid AND (a.privilege_type NOT IN ('SELECT','INSERT') OR a.is_grantable)))
  ) THEN RAISE EXCEPTION 'thermal table ACL has unexpected grants'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_proc p,
      LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
    WHERE p.pronamespace=schema_oid AND a.grantee <> p.proowner
  ) OR EXISTS (
    SELECT 1 FROM pg_proc p
    WHERE p.pronamespace=schema_oid
      AND has_function_privilege(r.oid,p.oid,'EXECUTE')
  ) THEN RAISE EXCEPTION 'thermal function ACL has unexpected grants'; END IF;
END $audit$;
SQL

  unset THERMAL_DATABASE_ADMIN_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER
  trap - EXIT HUP INT TERM
)
unset THERMAL_DATABASE_ADMIN_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER
```

The audit is refusal-only outside the dedicated migration. It never modifies
OpenHAB-generated persistence tables and never changes database-wide PUBLIC
grants. If the existing database cannot meet this exact contract, stop and use
a separately reviewed storage plan.

**READ-ONLY — out-of-band service credential file without reading it:**

```bash
set -euo pipefail
test -f /home/sat/.config/hex/openhab.env
test ! -L /home/sat/.config/hex/openhab.env
ENV_MODE="$(stat -c %a /home/sat/.config/hex/openhab.env)"
test "$ENV_MODE" = 600
```

`EnvironmentFile` applies only to systemd. It does not configure the attended
operator shell.

**GATE A MUTATION — secret-safe runtime audit, train, backtest, and local shadow:**

```bash
set -euo pipefail
(
  set -euo pipefail
  umask 077
  : "${REPO_ROOT:?}"
  : "${FILE_RECEIPT:?}"
  cd "$REPO_ROOT"
  /usr/bin/python3 scripts/thermal-model-files.py prepare \
    --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
  read -r -s -p 'THERMAL_DATABASE_URL: ' THERMAL_DATABASE_URL
  printf '\n'
  test -n "$THERMAL_DATABASE_URL"
  export THERMAL_DATABASE_URL
  THERMAL_DATABASE_RUNTIME_ROLE=thermal_intel_runtime
  export THERMAL_DATABASE_RUNTIME_ROLE
  EXPECTED_OWNER_RECEIPT="$EVIDENCE_ROOT/database-expected-owner"
  test -f "$EXPECTED_OWNER_RECEIPT"
  test ! -L "$EXPECTED_OWNER_RECEIPT"
  EXPECTED_OWNER_MODE="$(stat -c %a "$EXPECTED_OWNER_RECEIPT")"
  test "$EXPECTED_OWNER_MODE" = 600
  EXPECTED_OWNER_LINES="$(wc -l <"$EXPECTED_OWNER_RECEIPT")"
  test "$EXPECTED_OWNER_LINES" -eq 1
  IFS= read -r THERMAL_DATABASE_EXPECTED_OWNER <"$EXPECTED_OWNER_RECEIPT"
  test -n "$THERMAL_DATABASE_EXPECTED_OWNER"
  export THERMAL_DATABASE_EXPECTED_OWNER
  trap 'unset THERMAL_DATABASE_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER' EXIT HUP INT TERM

  psql "$THERMAL_DATABASE_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE r pg_roles%ROWTYPE;
DECLARE schema_oid oid;
DECLARE actual_tables text[];
DECLARE table_oids oid[];
DECLARE actual_functions text[];
DECLARE actual_triggers text[];
BEGIN
  IF current_user <> 'thermal_intel_runtime' THEN
    RAISE EXCEPTION 'current_user is not thermal_intel_runtime';
  END IF;
  SELECT * INTO r FROM pg_roles WHERE rolname=current_user;
  IF NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreaterole
     OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls
     OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
    RAISE EXCEPTION 'runtime role attributes or memberships are not exact';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
     OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner=r.oid) THEN
    RAISE EXCEPTION 'runtime role owns database or application objects';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n
    WHERE n.nspname !~ '^pg_(temp|toast_temp)_'
      AND has_schema_privilege(r.oid,n.oid,'CREATE')
  ) THEN RAISE EXCEPTION 'runtime role has schema CREATE'; END IF;
  IF NOT has_database_privilege(r.oid,current_database(),'CONNECT')
     OR NOT has_database_privilege(r.oid,current_database(),'TEMP')
     OR has_database_privilege(r.oid,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'database CONNECT TEMP CREATE policy is not exact';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r','p','v','m','f')
      AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  ) OR EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind='S'
      AND has_sequence_privilege(r.oid,c.oid,'USAGE,SELECT,UPDATE')
  ) OR EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND has_function_privilege(r.oid,p.oid,'EXECUTE')
  ) THEN RAISE EXCEPTION 'runtime has authority outside thermal_intel'; END IF;
  SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname='thermal_intel';
  SELECT COALESCE(array_agg(concat_ws('|',
    relname,
    relkind,
    relpersistence,
    CASE WHEN relispartition THEN '1' ELSE '0' END,
    CASE WHEN relrowsecurity THEN '1' ELSE '0' END,
    CASE WHEN relforcerowsecurity THEN '1' ELSE '0' END
  ) ORDER BY relname),ARRAY[]::text[])
    INTO actual_tables FROM pg_class
    WHERE relnamespace=schema_oid AND relkind NOT IN ('i','I');
  SELECT COALESCE(array_agg(oid ORDER BY relname),ARRAY[]::oid[])
    INTO table_oids FROM pg_class
    WHERE relnamespace=schema_oid
      AND relname IN ('action_events','message_receipts','mode_events')
      AND relkind='r' AND relpersistence='p'
      AND NOT relispartition AND NOT relrowsecurity
      AND NOT relforcerowsecurity;
  SELECT COALESCE(array_agg(proname||'/'||pronargs||'/'||prokind ORDER BY proname),ARRAY[]::text[])
    INTO actual_functions FROM pg_proc WHERE pronamespace=schema_oid;
  IF actual_tables IS DISTINCT FROM ARRAY[
    'action_events|r|p|0|0|0',
    'message_receipts|r|p|0|0|0',
    'mode_events|r|p|0|0|0'
  ]::text[]
     OR cardinality(table_oids) <> 3
     OR actual_functions IS DISTINCT FROM ARRAY[
       'reject_action_correction_cycle/0/f',
       'reject_journal_mutation/0/f',
       'reject_mode_correction_cycle/0/f'
     ]::text[] THEN
    RAISE EXCEPTION 'runtime object inventory is not exact';
  END IF;
  SELECT COALESCE(array_agg(
    concat_ws('|',
      c.relname,
      t.tgname,
      fnn.nspname,
      p.proname,
      t.tgenabled,
      t.tgtype::integer::text,
      CASE WHEN t.tgdeferrable THEN '1' ELSE '0' END,
      CASE WHEN t.tginitdeferred THEN '1' ELSE '0' END,
      t.tgnargs::integer::text,
      CASE WHEN t.tgqual IS NULL THEN '1' ELSE '0' END,
      CASE WHEN t.tgisinternal THEN '1' ELSE '0' END,
      COALESCE(NULLIF(t.tgattr::text,''), '-')
    ) ORDER BY c.relname,t.tgname
  ),ARRAY[]::text[]) INTO actual_triggers
  FROM pg_trigger t
  JOIN pg_class c ON c.oid=t.tgrelid
  JOIN pg_proc p ON p.oid=t.tgfoid
  JOIN pg_namespace fnn ON fnn.oid=p.pronamespace
  WHERE c.oid = ANY(table_oids) AND NOT t.tgisinternal;
  IF actual_triggers IS DISTINCT FROM ARRAY[
    'action_events|reject_correction_cycle|thermal_intel|reject_action_correction_cycle|O|5|1|1|0|1|0|-',
    'action_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'message_receipts|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    'mode_events|reject_correction_cycle|thermal_intel|reject_mode_correction_cycle|O|5|1|1|0|1|0|-',
    'mode_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-'
  ]::text[] THEN
    RAISE EXCEPTION 'thermal trigger graph is not exact: %',actual_triggers;
  END IF;
  IF NOT has_schema_privilege(r.oid,schema_oid,'USAGE')
     OR has_schema_privilege(r.oid,schema_oid,'CREATE')
     OR EXISTS (
       SELECT 1 FROM pg_class c
       WHERE c.oid = ANY(table_oids)
         AND NOT (
           has_table_privilege(r.oid,c.oid,'SELECT')
           AND has_table_privilege(r.oid,c.oid,'INSERT')
           AND NOT has_table_privilege(r.oid,c.oid,'UPDATE')
           AND NOT has_table_privilege(r.oid,c.oid,'DELETE')
           AND NOT has_table_privilege(r.oid,c.oid,'TRUNCATE')
           AND NOT has_table_privilege(r.oid,c.oid,'REFERENCES')
           AND NOT has_table_privilege(r.oid,c.oid,'TRIGGER')
         )
     )
     OR EXISTS (
       SELECT 1 FROM pg_proc p
       WHERE p.pronamespace=schema_oid
         AND (p.prosecdef OR p.prokind <> 'f'
           OR has_function_privilege(r.oid,p.oid,'EXECUTE'))
     ) THEN
    RAISE EXCEPTION 'runtime thermal_intel authority is not exact';
  END IF;
END $audit$;
SQL

  /usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py schema-audit \
    | jq -e 'select(.schema == "thermal_intel" and .status == "exact" and .fingerprint == "786e9b7bf3ca5587f08bcdcd960239a88bf887a8b31c4ea5eddcbc808c496efb")' >/dev/null
  /usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py train
  /usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py backtest
  /usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow \
    --output "$STATE_ROOT/review/shadow-local.json"
  LOCAL_SHADOW_MODE="$(stat -c %a "$STATE_ROOT/review/shadow-local.json")"
  test "$LOCAL_SHADOW_MODE" = 600

  unset THERMAL_DATABASE_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER
  trap - EXIT HUP INT TERM
)
unset THERMAL_DATABASE_URL THERMAL_DATABASE_RUNTIME_ROLE THERMAL_DATABASE_EXPECTED_OWNER
```

The runtime DSN is neither printed nor inherited after this fence. The exact
fingerprint receipt contains no connection string or credentials.

## 4. Review artifact and backtest evidence

**READ-ONLY — parameters, ranges, exclusions, and provenance:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
jq -e '{schema,created_at,trained_from,trained_through,code_revision,dynamics,behavior,metrics,data_manifest:{start:.data_manifest.start,end:.data_manifest.end,sample_count:.data_manifest.sample_count,sample_counts_by_mode:.data_manifest.sample_counts_by_mode,rejected_counts:.data_manifest.rejected_counts,auxiliary_exclusion_counts:.data_manifest.auxiliary_exclusion_counts,event_counts_by_source:.data_manifest.event_counts_by_source,fit_diagnostics:.data_manifest.fit_diagnostics,constraints:.data_manifest.constraints,canonical_rows_sha256:.data_manifest.canonical_rows_sha256}} | select(.metrics.promotion.shadow_only == true)' \
  "$STATE_ROOT/models/accepted.json"
```

**READ-ONLY — exact rolling window, seasonal coverage, and Kiva exclusions:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
jq -e 'select(
    ((.data_manifest.end | fromdateiso8601)
      - (.data_manifest.start | fromdateiso8601)) == 34560000)
  | select(.data_manifest.sample_counts_by_mode.fall_charge > 0)
  | select(.data_manifest.sample_counts_by_mode.winter > 0)
  | select(.data_manifest.sample_counts_by_mode.spring > 0)
  | select(.data_manifest.sample_counts_by_mode.warm > 0)
  | select((.data_manifest.sample_counts_by_mode | add)
      == .data_manifest.sample_count)
  | select(.data_manifest.fit_diagnostics.excluded_passive_pairs > 0)
  | select(.data_manifest.event_counts_by_source.model_inferred > 0)
  | {trained_from,trained_through,sample_counts_by_mode:.data_manifest.sample_counts_by_mode,
     excluded_passive_pairs:.data_manifest.fit_diagnostics.excluded_passive_pairs,
     model_inferred_events:.data_manifest.event_counts_by_source.model_inferred}' \
  "$STATE_ROOT/models/accepted.json"
```

The final two predicates retain evidence that inferred Kiva intervals were
present and excluded from passive fitting; inspect their private journal rows
alongside this bounded manifest summary.

**READ-ONLY — folds, leakage, baselines, and promotion gates:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
jq -e 'select(all(.folds[]; .train_end < .prediction_start)) | {schema,generated_at,data_range,folds,overall:.metrics.overall,by_horizon:.metrics.by_horizon,by_regime:.metrics.by_regime,promotion:.metrics.promotion}' \
  "$STATE_ROOT/models/backtest-report.json"
```

**READ-ONLY — artifact provenance equals complete live runtime:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
: "${LIVE_RUNTIME_REVISION:?}"
ARTIFACT_REVISION="$(jq -e -r '.code_revision | select(type == "string" and length == 64)' "$STATE_ROOT/models/accepted.json")"
test "$ARTIFACT_REVISION" = "$LIVE_RUNTIME_REVISION"
```

**READ-ONLY — local shadow validation, size, and private modes:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
/usr/bin/python3 /home/sat/earthship-ui/openhab/scripts/validate_thermal_shadow.py \
  < "$STATE_ROOT/review/shadow-local.json"
LOCAL_BYTES="$(wc -c < "$STATE_ROOT/review/shadow-local.json")"
test "$LOCAL_BYTES" -lt 16384
for FILE in "$STATE_ROOT/models/accepted.json" \
  "$STATE_ROOT/models/backtest-report.json" \
  "$STATE_ROOT/review/shadow-local.json"
do
  FILE_MODE="$(stat -c %a "$FILE")"
  test "$FILE_MODE" = 600
done
```

Stop and present this evidence before Gate B. Stop on refusal, leakage,
invalid physics, unexplained exclusions, missing
baseline, unavailable confidence, revision mismatch, size failure, or weak
mode.

## 5. Gate B: sole observational Item and state writes

Gate B authorizes exactly one receipt-bound `Thermal_Model_JSON` configuration
apply and one manual valid state publication/readback/UI/log review. It
authorizes no systemd change and no other OpenHAB mutation.

**GATE B MUTATION — receipt-owned Item apply:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs apply --receipt-dir "$ITEM_RECEIPT"
```

**READ-ONLY — exact desired receipt verification:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs verify --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "desired" and .phase == "desired")'
jq -e 'select(.state == "open" and .phase == "desired" and .writeCount == 1)' \
  "$ITEM_RECEIPT/receipt.json"
```

**GATE B SETTLEMENT — exact readback only:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
PHASE="$(jq -e -r '.phase' "$ITEM_RECEIPT/receipt.json")"
if test "$PHASE" = applying; then
  curl --fail --silent --show-error \
    http://127.0.0.1:5190/rest/items/Thermal_Model_JSON \
    | jq -e 'select(.name == "Thermal_Model_JSON" and .type == "String")'
  node scripts/thermal-model-config.mjs settle --receipt-dir "$ITEM_RECEIPT"
fi
node scripts/thermal-model-config.mjs verify --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "desired" and .phase == "desired")'
```

If apply returned ambiguously, never retry the write. Settle only after exact
receipt-aware readback. The exact terminal phase must be `desired` before
closure.

**GATE B LOCAL RECEIPT MUTATION — GET-only close after exact desired readback:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs close --receipt-dir "$ITEM_RECEIPT"
jq -e 'select(.state == "closed" and .phase == "desired"
  and .closedPhase == "desired" and .writeCount == 1
  and (.closedAt | type) == "string")' "$ITEM_RECEIPT/receipt.json"
```

`close` performs only the exact Item GET/readback and a durable private receipt
write. It cannot PUT or DELETE an Item. Closing preserves the snapshot and all
rollback/closure evidence; a later audited rollback from closed `desired`
explicitly reopens to `rolling-back` before its sole restore-or-delete write.

**GATE B MUTATION — one manual valid shadow state publish:**

```bash
set -euo pipefail
umask 077
: "${STATE_ROOT:?}"
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow --publish \
  --output "$STATE_ROOT/review/shadow-published.json"
PUBLISHED_MODE="$(stat -c %a "$STATE_ROOT/review/shadow-published.json")"
test "$PUBLISHED_MODE" = 600
```

**GATE B PRIVATE EVIDENCE — durable exact Item readback:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
: "${EVIDENCE_ROOT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py prepare \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
READBACK_TMP="$(mktemp --tmpdir="$EVIDENCE_ROOT" .published-readback.XXXXXX)"
chmod 0600 "$READBACK_TMP"
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Model_JSON/state > "$READBACK_TMP"
sync -f "$READBACK_TMP"
mv -- "$READBACK_TMP" "$EVIDENCE_ROOT/published-readback.json"
sync -f "$EVIDENCE_ROOT"
READBACK_MODE="$(stat -c %a "$EVIDENCE_ROOT/published-readback.json")"
test "$READBACK_MODE" = 600
```

**READ-ONLY — validate and compare publication exactly:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
: "${EVIDENCE_ROOT:?}"
/usr/bin/python3 /home/sat/earthship-ui/openhab/scripts/validate_thermal_shadow.py \
  < "$EVIDENCE_ROOT/published-readback.json"
READBACK_BYTES="$(wc -c < "$EVIDENCE_ROOT/published-readback.json")"
test "$READBACK_BYTES" -lt 16384
LOCAL_SHA="$(jq -e -S -c . "$STATE_ROOT/review/shadow-published.json" | sha256sum | awk '{print $1}')"
LIVE_SHA="$(jq -e -S -c . "$EVIDENCE_ROOT/published-readback.json" | sha256sum | awk '{print $1}')"
test "$LOCAL_SHA" = "$LIVE_SHA"
```

**READ-ONLY — protected state, UI, and logs:**

```bash
set -euo pipefail
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Advisory \
  | jq -e '{name,state} | select(.name == "Thermal_Advisory")'
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch \
  | jq -e '{name,state} | select(.name == "SouthOutlet_Outlet2_Switch")'
journalctl --user -u earthship-ui.service -n 100 --no-pager
```

Compare protected values to preflight. Visually confirm the non-interactive
`SHADOW` card. Present this evidence before Gate C.

## 6. Gate C: service and timer activation

Gate C authorizes atomic unit installation, daemon reload, one manual train
service run, one manual shadow-service publication to exact Thermal_Model_JSON,
the required post-service readback, and—only after that evidence is green—
future timer-driven private training, backtest, and artifact replacement plus
future timer-driven PUTs to exact Thermal_Model_JSON. It authorizes no
`Thermal_Advisory`, other Item, rule, notification, or actuator write.

**READ-ONLY — verify tracked units offline:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
systemd-analyze verify deploy/thermal-model-train.service \
  deploy/thermal-model-train.timer deploy/thermal-model-shadow.service \
  deploy/thermal-model-shadow.timer
```

**GATE C MUTATION — transactional unit installation and complete equality:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py install-units \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
/usr/bin/python3 scripts/thermal-model-files.py verify-code \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
/usr/bin/python3 scripts/thermal-model-files.py verify-units \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
jq -e 'select(.operation == "install-unit" and .status == "complete")' \
  "$FILE_RECEIPT/phase-state.json"
```

If interrupted, stop. Gate C authorizes only this unit-phase recovery before
returning to the Gate C approval boundary:

**GATE C RECOVERY MUTATION — reconcile and restore interrupted unit writes:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py recover --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
jq -e 'select(.operation == "install-unit" and .status == "rolled-back")' "$FILE_RECEIPT/phase-state.json"
```

**GATE C MUTATION — reload only after complete manifest equality:**

```bash
set -euo pipefail
systemctl --user daemon-reload
systemctl --user cat thermal-model-train.service thermal-model-train.timer \
  thermal-model-shadow.service thermal-model-shadow.timer
```

**READ-ONLY — exact installed, disabled, inactive state:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py installed-disabled
```

**GATE C MUTATION — attended manual service checks:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py prepare \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
systemctl --user start thermal-model-train.service
systemctl --user start thermal-model-shadow.service
```

The shadow service's exact ExecStart performs one separately Gate-C-authorized
publication to `Thermal_Model_JSON`.

**READ-ONLY — exact service exit state:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py services-succeeded
journalctl --user -u thermal-model-train.service \
  -u thermal-model-shadow.service -n 200 --no-pager
```

**GATE C PRIVATE EVIDENCE — post-service state readback:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
: "${EVIDENCE_ROOT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py prepare \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
POST_SERVICE_TMP="$(mktemp --tmpdir="$EVIDENCE_ROOT" .post-service-readback.XXXXXX)"
chmod 0600 "$POST_SERVICE_TMP"
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Model_JSON/state > "$POST_SERVICE_TMP"
sync -f "$POST_SERVICE_TMP"
mv -- "$POST_SERVICE_TMP" "$EVIDENCE_ROOT/post-service-readback.json"
sync -f "$EVIDENCE_ROOT"
POST_SERVICE_MODE="$(stat -c %a "$EVIDENCE_ROOT/post-service-readback.json")"
test "$POST_SERVICE_MODE" = 600
```

**READ-ONLY — validate and digest-match the service publication:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
: "${EVIDENCE_ROOT:?}"
/usr/bin/python3 /home/sat/earthship-ui/openhab/scripts/validate_thermal_shadow.py \
  < "$EVIDENCE_ROOT/post-service-readback.json"
SERVICE_BYTES="$(wc -c < "$EVIDENCE_ROOT/post-service-readback.json")"
test "$SERVICE_BYTES" -lt 16384
SERVICE_LOCAL_MODE="$(stat -c %a "$STATE_ROOT/shadow.json")"
test "$SERVICE_LOCAL_MODE" = 600
SERVICE_LOCAL_SHA="$(jq -e -S -c . "$STATE_ROOT/shadow.json" | sha256sum | awk '{print $1}')"
SERVICE_LIVE_SHA="$(jq -e -S -c . "$EVIDENCE_ROOT/post-service-readback.json" | sha256sum | awk '{print $1}')"
test "$SERVICE_LOCAL_SHA" = "$SERVICE_LIVE_SHA"
```

Stop before timers unless the service state, validator, byte limit, digest,
UI, log, advisory, and actuator evidence is green.

**GATE C MUTATION — explicitly authorize catch-up and future scheduled work:**

```bash
set -euo pipefail
systemctl --user enable --now thermal-model-train.timer thermal-model-shadow.timer
```

Enabling and starting `Persistent=true` timers can cause immediate catch-up
training and an immediate catch-up publication. This command therefore requires
explicit authorization for those possible immediate effects, all future daily
private training/backtest/artifact replacement, and all future two-hour valid
state PUTs to the exact `Thermal_Model_JSON` Item.

**READ-ONLY — exact enabled timer state and schedules:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py timers-enabled
systemctl --user list-timers thermal-model-train.timer \
  thermal-model-shadow.timer --all --no-pager
```

Training is daily 06:50 after the existing 06:40 forecast. Shadow starts 15
minutes after boot and every two hours thereafter.

## 7. Attended rollback

Retain receipts, journal, artifacts, reports, readbacks, and logs. Never delete
or rewrite evidence. Rollback first establishes a concurrency barrier so
shadow cannot republish and training cannot race restoration.

**ROLLBACK MUTATION — exact profile, disable timers, stop both services:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
ROLLBACK_PROFILE="$(/usr/bin/python3 scripts/thermal-systemd-state.py rollback-precheck)"
case "$ROLLBACK_PROFILE" in
  missing)
    ;;
  installed)
    systemctl --user disable --now thermal-model-train.timer thermal-model-shadow.timer
    systemctl --user stop thermal-model-train.service thermal-model-shadow.service
    /usr/bin/python3 scripts/thermal-systemd-state.py rollback-quiescent
    ;;
  *)
    printf '%s\n' 'unexpected rollback profile' >&2
    exit 1
    ;;
esac
printf '%s\n' 'both oneshot services are inactive'
```

This explicitly handles only the complete first-install missing profile or the
complete helper-installed profile. Any mixed state or systemctl transport
failure aborts before restoration.

**ROLLBACK MUTATION — receipt-based Item rollback and verify:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs rollback --receipt-dir "$ITEM_RECEIPT"
node scripts/thermal-model-config.mjs verify --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "original" and .phase == "rolled-back")'
```

**ROLLBACK SETTLEMENT — exact original readback only:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
PHASE="$(jq -e -r '.phase' "$ITEM_RECEIPT/receipt.json")"
if test "$PHASE" = rolling-back; then
  node scripts/thermal-model-config.mjs settle --receipt-dir "$ITEM_RECEIPT"
fi
node scripts/thermal-model-config.mjs verify --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "original" and .phase == "rolled-back")'
```

The exact terminal phase must be `rolled-back` before closure.

**ROLLBACK LOCAL RECEIPT MUTATION — GET-only close after exact original readback:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs close --receipt-dir "$ITEM_RECEIPT"
jq -e 'select(.state == "closed" and .phase == "rolled-back"
  and .closedPhase == "rolled-back" and (.closedAt | type) == "string")'   "$ITEM_RECEIPT/receipt.json"
```

**ROLLBACK MUTATION — receipt-based photosensor Item/link restoration:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-photosensor-config.mjs rollback \
  --receipt-dir "$PHOTOSENSOR_RECEIPT"
```

If rollback returned ambiguously, never retry its pending write. Reconcile and
resume only the exact receipt-owned reverse prefix:

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${PHOTOSENSOR_RECEIPT:?}"
cd "$REPO_ROOT"
PHOTOSENSOR_PHASE="$(jq -e -r '.phase' "$PHOTOSENSOR_RECEIPT/receipt.json")"
PHOTOSENSOR_PENDING="$(jq -e -r '.pendingOperation' "$PHOTOSENSOR_RECEIPT/receipt.json")"
if test "$PHOTOSENSOR_PHASE" = rolling-back && test "$PHOTOSENSOR_PENDING" != null; then
  node scripts/thermal-photosensor-config.mjs settle \
    --receipt-dir "$PHOTOSENSOR_RECEIPT"
fi
PHOTOSENSOR_PHASE="$(jq -e -r '.phase' "$PHOTOSENSOR_RECEIPT/receipt.json")"
PHOTOSENSOR_PENDING="$(jq -e -r '.pendingOperation' "$PHOTOSENSOR_RECEIPT/receipt.json")"
case "$PHOTOSENSOR_PHASE:$PHOTOSENSOR_PENDING" in
  rolling-back:null)
    node scripts/thermal-photosensor-config.mjs rollback \
      --receipt-dir "$PHOTOSENSOR_RECEIPT"
    ;;
  rolled-back:null)
    ;;
  *)
    printf '%s\n' 'unexpected photosensor rollback receipt state' >&2
    exit 1
    ;;
esac
node scripts/thermal-photosensor-config.mjs verify \
  --receipt-dir "$PHOTOSENSOR_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "original" and .phase == "rolled-back")'
node scripts/thermal-photosensor-config.mjs close \
  --receipt-dir "$PHOTOSENSOR_RECEIPT"
jq -e 'select(.state == "closed" and .phase == "rolled-back"
  and .closedPhase == "rolled-back" and .writeCount == 12)' \
  "$PHOTOSENSOR_RECEIPT/receipt.json"
```

**ROLLBACK MUTATION — recover interrupted phase, then restore exact files:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
if test -f "$FILE_RECEIPT/phase-state.json"; then
  FILE_PHASE_STATUS="$(jq -e -r '.status' "$FILE_RECEIPT/phase-state.json")"
  case "$FILE_PHASE_STATUS" in
    applying|recovering|recovery-required)
      /usr/bin/python3 scripts/thermal-model-files.py recover \
        --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
      ;;
    complete|rolled-back)
      ;;
    *)
      printf '%s\n' 'unknown file phase state' >&2
      exit 1
      ;;
  esac
fi
/usr/bin/python3 scripts/thermal-model-files.py restore \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
systemctl --user daemon-reload
```

The restore prevalidates all targets before its first change. It refuses
unowned drift, automatically reverses ordinary partial failure, atomically
restores prior bytes/modes, removes only receipt-proven absent targets, and
re-verifies the entire original manifest.

**READ-ONLY — first-install systemd state restored:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
/usr/bin/python3 scripts/thermal-systemd-state.py first-install
```

**READ-ONLY — final protected-state verification:**

```bash
set -euo pipefail
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/Thermal_Advisory \
  | jq -e '{name,state} | select(.name == "Thermal_Advisory")'
curl --fail --silent --show-error \
  http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch \
  | jq -e '{name,state} | select(.name == "SouthOutlet_Outlet2_Switch")'
```

## Completion boundary

No gate authorizes advisory graduation or actuation. A later warm/winter
review must define evidence-derived graduation thresholds. Actuation requires
a separate threat model, capability owner, reconciliation, manual override,
and fail-safe proof.
