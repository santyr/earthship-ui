# Thermal model shadow attended rollout and rollback

This runbook stages one observational `Thermal_Model_JSON` Item and two user
services. It never changes `Thermal_Advisory`, rules, notifications, or an
actuator. Implementation, artifact acceptance, and shadow evidence do **not**
graduate advice.

Every Bash fence is independently fail-closed: its first command is
`set -euo pipefail`. Run fences in one attended shell and in document order.
A missing exported variable stops the fence rather than selecting a default.
Expected missing resources and expected nonzero status are handled explicitly.
All `jq` checks use `-e`, so `curl`, validation, size, hash, and systemd failures
cannot be hidden by a later command.

Private receipts, inventories, histories, DSNs, journal rows, artifacts,
reports, logs, and household state stay outside Git. Never print or commit
secrets or private evidence. Directories below must have mode `0700`; private
files must have mode `0600`. No artifact or journal content is committed.

## Exact source-to-target manifest

The checked-in `scripts/thermal-model-files.py` owns this fixed manifest. It
creates durable verified backups with explicit absent markers. For each write,
it prevalidates the complete phase, writes a unique sibling temporary file,
sets its safe mode, performs file `fsync`, verifies SHA-256, calls
`os.replace`, then `fsync`s the parent directory. Nothing may execute until the
complete live phase equals the reviewed manifest.

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
`scripts/thermal-model-files.py`, and
`openhab/scripts/validate_thermal_shadow.py` are repository-side deployment
tools, not service runtime files.

## 1. Read-only preflight

**READ-ONLY — reviewed repository state:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
git rev-parse HEAD
test -z "$(git status --short)"
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

This digest length-prefixes each exact relative path and file body in the
service runtime manifest. It is independent of unrelated Git discovery.

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

**READ-ONLY — prior unit-file inventory with missing units allowed:**

```bash
set -euo pipefail
systemctl --user list-unit-files --no-pager \
  | awk '$1 ~ /^thermal-model-(train|shadow)\.(service|timer)$/ {print}'
```

## 2. Preliminary authorization: private receipt facts only

Pause. Obtain narrow preliminary authorization for only: creating private
receipt/evidence directories, one read-only Item snapshot plus local receipt,
and read-only capture of exact live file targets into durable private backups.
It authorizes no live file write, database change, model run, Item write, or
systemd change.

**SESSION-ONLY — bind exact private paths:**

```bash
set -euo pipefail
umask 077
REPO_ROOT=/home/sat/earthship-ui
EVIDENCE_ROOT=/home/sat/.local/state/thermal-intel/deploy-receipts/ATTENDED-ID
ITEM_RECEIPT="$EVIDENCE_ROOT/item"
FILE_RECEIPT="$EVIDENCE_ROOT/files"
STATE_ROOT=/home/sat/.local/state/thermal-intel
test "$REPO_ROOT" = /home/sat/earthship-ui
test "$STATE_ROOT" = /home/sat/.local/state/thermal-intel
export REPO_ROOT EVIDENCE_ROOT ITEM_RECEIPT FILE_RECEIPT STATE_ROOT
```

**PRELIMINARY MUTATION — create only the private evidence root:**

```bash
set -euo pipefail
umask 077
: "${EVIDENCE_ROOT:?set exact evidence root}"
test ! -e "$EVIDENCE_ROOT"
install -d -m 0700 "$EVIDENCE_ROOT"
test "$(stat -c %a "$EVIDENCE_ROOT")" = 700
```

**PRELIMINARY MUTATION — receipt-bound Item snapshot:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
node scripts/thermal-model-config.mjs snapshot --receipt-dir "$ITEM_RECEIPT"
test "$(stat -c %a "$ITEM_RECEIPT")" = 700
test "$(stat -c %a "$ITEM_RECEIPT/receipt.json")" = 600
test "$(stat -c %a "$ITEM_RECEIPT/pre-state.json")" = 600
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
test "$(stat -c %a "$FILE_RECEIPT")" = 700
test "$(stat -c %a "$FILE_RECEIPT/file-manifest.json")" = 600
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

**READ-ONLY — durable backup receipt facts and explicit absent markers:**

```bash
set -euo pipefail
: "${FILE_RECEIPT:?}"
jq -e 'select(.schema == "earthship-thermal-file-deploy/v1")
  | select((.checksum | type) == "string" and (.checksum | length) == 64)
  | select((.entries | length) == 16)
  | {schema,checksum,entries:[.entries[]|{source,target,phase,source_sha256,prior,prior_sha256,backup,marker}]}' \
  "$FILE_RECEIPT/file-manifest.json"
test "$(find "$FILE_RECEIPT/backups" -maxdepth 1 -type f -printf . | wc -c)" -eq 15
test -z "$(find "$FILE_RECEIPT/backups" -maxdepth 1 -type f ! -perm 0600 -print -quit)"
find "$FILE_RECEIPT/backups" -maxdepth 1 -type f -printf '%f %m\n' | sort
```

**PRELIMINARY MUTATION — durable mapping from reviewed Git commit to digest:**

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
test "$(stat -c %a "$EVIDENCE_ROOT/revision-map.txt")" = 600
```

Present the Item snapshot digest, apply/rollback plan, file backup receipt,
explicit absent markers, reviewed Git commit, runtime-manifest SHA-256, current
inventory, and repository test totals before Gate A.

## 3. Gate A: code, database, and private model evidence

Gate A authorizes only atomic live code installation, dedicated journal schema
migration/grants after exact role audit, and private state, training, backtest,
artifact, and local-only shadow creation. It does not authorize Item
apply/state publication, credential provisioning, or systemd mutation.

**GATE A MUTATION — atomic code phase installation:**

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
```

No live Python command may run before both helper commands exit zero.

**READ-ONLY — verify live runtime provenance equals reviewed provenance:**

```bash
set -euo pipefail
: "${TRACKED_RUNTIME_REVISION:?}"
cd /home/sat/openhab/scripts
LIVE_RUNTIME_REVISION="$(/usr/bin/python3 -c 'import thermal_intel; print(thermal_intel._code_revision())')"
test "$LIVE_RUNTIME_REVISION" = "$TRACKED_RUNTIME_REVISION"
printf '%s\n' "$LIVE_RUNTIME_REVISION"
export LIVE_RUNTIME_REVISION
```

### Exact runtime-role authority

`thermal_intel_runtime` and its credentials must pre-exist through the separate
operator/DBA secret-provisioning process. This runbook never creates, alters,
or normalizes the role. If the same-name role is absent or elevated, stop and
return to that process. Credentials are provisioned out-of-band and never
printed.

The audit requires LOGIN, `NOINHERIT`, no superuser/create-role/create-db/
replication/bypass-RLS flags, no role memberships, no database or schema
ownership, no database or schema `CREATE`, and no effective privileges on any
non-system relation outside `thermal_intel`. PostgreSQL's built-in
`pg_catalog`/information-schema visibility is not application table authority.
The post-migration audit again refuses effective privileges outside `thermal_intel`
on every non-system relation.

**SESSION-ONLY — enter admin DSN without echo:**

```bash
set -euo pipefail
read -r -s -p 'THERMAL_DATABASE_ADMIN_URL: ' THERMAL_DATABASE_ADMIN_URL
printf '\n'
test -n "$THERMAL_DATABASE_ADMIN_URL"
export THERMAL_DATABASE_ADMIN_URL
```

**READ-ONLY — fail closed on role attributes, role memberships, and ownership:**

```bash
set -euo pipefail
: "${THERMAL_DATABASE_ADMIN_URL:?}"
psql "$THERMAL_DATABASE_ADMIN_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE r pg_roles%ROWTYPE;
BEGIN
  SELECT * INTO r FROM pg_roles WHERE rolname='thermal_intel_runtime';
  IF NOT FOUND THEN RAISE EXCEPTION 'thermal_intel_runtime must pre-exist'; END IF;
  IF NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreaterole
     OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls THEN
    RAISE EXCEPTION 'thermal_intel_runtime attributes are not exact';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
    RAISE EXCEPTION 'thermal_intel_runtime has role memberships';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid) THEN
    RAISE EXCEPTION 'thermal_intel_runtime owns database or schema';
  END IF;
END $audit$;
SQL
```

**READ-ONLY — fail closed on database/schema/outside-table authority:**

```bash
set -euo pipefail
: "${THERMAL_DATABASE_ADMIN_URL:?}"
psql "$THERMAL_DATABASE_ADMIN_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE role_oid oid := (SELECT oid FROM pg_roles WHERE rolname='thermal_intel_runtime');
BEGIN
  IF role_oid IS NULL THEN RAISE EXCEPTION 'runtime role absent'; END IF;
  IF has_database_privilege(role_oid,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'runtime role has database create';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace n WHERE has_schema_privilege(role_oid,n.oid,'CREATE')) THEN
    RAISE EXCEPTION 'runtime role has schema CREATE';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r','p','v','m','S','f')
      AND has_table_privilege(role_oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  ) THEN RAISE EXCEPTION 'runtime role has effective table privileges outside thermal_intel';
  END IF;
END $audit$;
SQL
```

**GATE A MUTATION — migrate only the application schema and grants:**

```bash
set -euo pipefail
: "${THERMAL_DATABASE_ADMIN_URL:?}"
cd /home/sat/openhab/scripts
/usr/bin/python3 -c 'import os; from thermal_model.journal import migrate; migrate(os.environ["THERMAL_DATABASE_ADMIN_URL"], runtime_role="thermal_intel_runtime")'
```

The migration targets only `thermal_intel`; OpenHAB-generated persistence
tables are never modified.

**READ-ONLY — exact post-migration role, schema, and table authority:**

```bash
set -euo pipefail
: "${THERMAL_DATABASE_ADMIN_URL:?}"
psql "$THERMAL_DATABASE_ADMIN_URL" -X --set ON_ERROR_STOP=1 <<'SQL'
DO $audit$
DECLARE r pg_roles%ROWTYPE;
DECLARE bad_count integer;
BEGIN
  SELECT * INTO r FROM pg_roles WHERE rolname='thermal_intel_runtime';
  IF NOT FOUND THEN RAISE EXCEPTION 'runtime role absent'; END IF;
  IF NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreaterole
     OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls THEN
    RAISE EXCEPTION 'runtime role attributes changed during migration';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) THEN
    RAISE EXCEPTION 'runtime role memberships changed during migration';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid) THEN
    RAISE EXCEPTION 'runtime role gained database or schema ownership';
  END IF;
  IF has_database_privilege(r.oid,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'runtime role has database create';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace n WHERE has_schema_privilege(r.oid,n.oid,'CREATE')) THEN
    RAISE EXCEPTION 'runtime role has schema CREATE';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname <> 'thermal_intel'
      AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r','p','v','m','S','f')
      AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  ) THEN
    RAISE EXCEPTION 'runtime role has effective table privileges outside thermal_intel';
  END IF;
  IF NOT has_schema_privilege(r.oid,'thermal_intel','USAGE')
     OR has_schema_privilege(r.oid,'thermal_intel','CREATE') THEN
    RAISE EXCEPTION 'thermal schema privileges are not exact';
  END IF;
  SELECT count(*) INTO bad_count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='thermal_intel' AND c.relkind IN ('r','p')
     AND NOT (has_table_privilege(r.oid,c.oid,'SELECT')
       AND has_table_privilege(r.oid,c.oid,'INSERT')
       AND NOT has_table_privilege(r.oid,c.oid,'UPDATE')
       AND NOT has_table_privilege(r.oid,c.oid,'DELETE')
       AND NOT has_table_privilege(r.oid,c.oid,'TRUNCATE')
       AND NOT has_table_privilege(r.oid,c.oid,'REFERENCES')
       AND NOT has_table_privilege(r.oid,c.oid,'TRIGGER'));
  IF bad_count <> 0 OR (SELECT count(*) FROM pg_tables WHERE schemaname='thermal_intel') <> 3 THEN
    RAISE EXCEPTION 'thermal table privileges or inventory are not exact';
  END IF;
END $audit$;
SQL
```

**READ-ONLY — confirm the out-of-band runtime credential file without reading it:**

```bash
set -euo pipefail
test -f /home/sat/.config/hex/openhab.env
test ! -L /home/sat/.config/hex/openhab.env
test "$(stat -c %a /home/sat/.config/hex/openhab.env)" = 600
unset THERMAL_DATABASE_ADMIN_URL
```

Never display the file. Its runtime-role credentials are provisioned
out-of-band; no gate in this runbook authorizes creating or editing it.

### Private state before model execution

**GATE A MUTATION — create and harden exact private directories:**

```bash
set -euo pipefail
umask 077
: "${STATE_ROOT:?}"
test "$STATE_ROOT" = /home/sat/.local/state/thermal-intel
install -d -m 0700 "$STATE_ROOT" "$STATE_ROOT/models" "$STATE_ROOT/review" "$STATE_ROOT/evidence"
for DIR in "$STATE_ROOT" "$STATE_ROOT/models" "$STATE_ROOT/review" "$STATE_ROOT/evidence"
do
  test "$(stat -c %a "$DIR")" = 700
done
```

**GATE A MUTATION — harden only known existing private files:**

```bash
set -euo pipefail
umask 077
: "${STATE_ROOT:?}"
for FILE in "$STATE_ROOT/models/candidate.json" "$STATE_ROOT/models/accepted.json" \
  "$STATE_ROOT/models/backtest-report.json" "$STATE_ROOT/shadow.json" \
  "$STATE_ROOT/review/shadow-local.json" "$STATE_ROOT/review/shadow-published.json"
do
  if test -e "$FILE"; then chmod 0600 "$FILE"; test "$(stat -c %a "$FILE")" = 600; fi
done
```

Both services set `UMask=0077`, so systemd cannot weaken these defaults.

**GATE A MUTATION — one manual training run:**

```bash
set -euo pipefail
umask 077
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py train
```

**GATE A MUTATION — one manual chronological backtest:**

```bash
set -euo pipefail
umask 077
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py backtest
```

**GATE A MUTATION — one local-only shadow, never publish:**

```bash
set -euo pipefail
umask 077
: "${STATE_ROOT:?}"
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow \
  --output "$STATE_ROOT/review/shadow-local.json"
test "$(stat -c %a "$STATE_ROOT/review/shadow-local.json")" = 600
```

## 4. Review artifact and backtest evidence

**READ-ONLY — parameters, code/data ranges, exclusions, and provenance:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
jq -e '{schema,created_at,trained_from,trained_through,code_revision,dynamics,behavior,metrics,data_manifest:{start:.data_manifest.start,end:.data_manifest.end,sample_count:.data_manifest.sample_count,rejected_counts:.data_manifest.rejected_counts,auxiliary_exclusion_counts:.data_manifest.auxiliary_exclusion_counts,event_counts_by_source:.data_manifest.event_counts_by_source,fit_diagnostics:.data_manifest.fit_diagnostics,constraints:.data_manifest.constraints,canonical_rows_sha256:.data_manifest.canonical_rows_sha256}} | select(.metrics.promotion.shadow_only == true)' \
  "$STATE_ROOT/models/accepted.json"
```

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
BYTES="$(wc -c < "$STATE_ROOT/review/shadow-local.json")"
test "$BYTES" -lt 16384
for FILE in "$STATE_ROOT/models/accepted.json" "$STATE_ROOT/models/backtest-report.json" "$STATE_ROOT/review/shadow-local.json"
do
  test "$(stat -c %a "$FILE")" = 600
done
```

Stop on refusal, leakage, invalid physics, unexplained exclusions, missing
baseline, unavailable confidence, revision mismatch, size failure, or weak
mode. Present exact evidence before Gate B.

## 5. Gate B: sole observational Item and state writes

Gate B authorizes exactly one receipt-bound Item configuration apply and one
manual valid state publish/readback/UI/log review. It authorizes no systemd or
other OpenHAB mutation.

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
jq -e 'select(.state == "open" and .phase == "desired" and .writeCount == 1)' "$ITEM_RECEIPT/receipt.json"
```

The Task 8 CLI has no artificial close state. Exact desired readback plus the
retained receipt is closure. If apply returned ambiguously, do not retry.

**GATE B SETTLEMENT — only after exact readback proves intended state:**

```bash
set -euo pipefail
: "${REPO_ROOT:?}"
: "${ITEM_RECEIPT:?}"
cd "$REPO_ROOT"
PHASE="$(jq -e -r '.phase' "$ITEM_RECEIPT/receipt.json")"
if test "$PHASE" = applying; then
  curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/Thermal_Model_JSON \
    | jq -e 'select(.name == "Thermal_Model_JSON" and .type == "String")'
  node scripts/thermal-model-config.mjs settle --receipt-dir "$ITEM_RECEIPT"
fi
node scripts/thermal-model-config.mjs verify --receipt-dir "$ITEM_RECEIPT" \
  | jq -e 'select(.ok == true and .expected == "desired")'
```

**GATE B MUTATION — one manual valid shadow state publish:**

```bash
set -euo pipefail
umask 077
: "${STATE_ROOT:?}"
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow --publish \
  --output "$STATE_ROOT/review/shadow-published.json"
test "$(stat -c %a "$STATE_ROOT/review/shadow-published.json")" = 600
```

**GATE B PRIVATE EVIDENCE — durable exact Item readback:**

```bash
set -euo pipefail
umask 077
: "${EVIDENCE_ROOT:?}"
READBACK_TMP="$(mktemp --tmpdir="$EVIDENCE_ROOT" .published-readback.XXXXXX)"
chmod 0600 "$READBACK_TMP"
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/Thermal_Model_JSON/state > "$READBACK_TMP"
sync -f "$READBACK_TMP"
mv -- "$READBACK_TMP" "$EVIDENCE_ROOT/published-readback.json"
sync -f "$EVIDENCE_ROOT"
test "$(stat -c %a "$EVIDENCE_ROOT/published-readback.json")" = 600
```

**READ-ONLY — validate and compare publication exactly:**

```bash
set -euo pipefail
: "${STATE_ROOT:?}"
: "${EVIDENCE_ROOT:?}"
/usr/bin/python3 /home/sat/earthship-ui/openhab/scripts/validate_thermal_shadow.py < "$EVIDENCE_ROOT/published-readback.json"
BYTES="$(wc -c < "$EVIDENCE_ROOT/published-readback.json")"
test "$BYTES" -lt 16384
LOCAL_SHA="$(jq -e -S -c . "$STATE_ROOT/review/shadow-published.json" | sha256sum | awk '{print $1}')"
LIVE_SHA="$(jq -e -S -c . "$EVIDENCE_ROOT/published-readback.json" | sha256sum | awk '{print $1}')"
test "$LOCAL_SHA" = "$LIVE_SHA"
```

**READ-ONLY — protected state, UI, and logs:**

```bash
set -euo pipefail
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/Thermal_Advisory \
  | jq -e '{name,state} | select(.name == "Thermal_Advisory")'
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch \
  | jq -e '{name,state} | select(.name == "SouthOutlet_Outlet2_Switch")'
journalctl --user -u earthship-ui.service -n 100 --no-pager
```

Compare protected values to preflight. Visually confirm the non-interactive
`SHADOW` card. Test stale/unavailable with fixtures, never live corruption.
Present this evidence before Gate C.

## 6. Gate C: service and timer activation

Gate C authorizes atomic unit installation, daemon reload, one manual run of
each service, and timer enablement only after Gate B evidence is green.

**READ-ONLY — verify tracked units offline:**

```bash
set -euo pipefail
cd /home/sat/earthship-ui
systemd-analyze verify deploy/thermal-model-train.service deploy/thermal-model-train.timer \
  deploy/thermal-model-shadow.service deploy/thermal-model-shadow.timer
```

**GATE C MUTATION — atomic unit phase installation:**

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
```

**GATE C MUTATION — reload only after complete unit equality:**

```bash
set -euo pipefail
systemctl --user daemon-reload
systemctl --user cat thermal-model-train.service thermal-model-train.timer \
  thermal-model-shadow.service thermal-model-shadow.timer
```

**GATE C MUTATION — attended manual service checks:**

```bash
set -euo pipefail
systemctl --user start thermal-model-train.service
systemctl --user start thermal-model-shadow.service
```

**READ-ONLY — both oneshots exited successfully:**

```bash
set -euo pipefail
for UNIT in thermal-model-train.service thermal-model-shadow.service
do
  test "$(systemctl --user show "$UNIT" --property=Result --value)" = success
  test "$(systemctl --user show "$UNIT" --property=ExecMainStatus --value)" = 0
done
journalctl --user -u thermal-model-train.service -u thermal-model-shadow.service -n 200 --no-pager
```

**GATE C MUTATION — enable timers only now:**

```bash
set -euo pipefail
systemctl --user enable --now thermal-model-train.timer thermal-model-shadow.timer
```

**READ-ONLY — intended schedules and next runs:**

```bash
set -euo pipefail
systemctl --user is-enabled --quiet thermal-model-train.timer
systemctl --user is-enabled --quiet thermal-model-shadow.timer
systemctl --user list-timers thermal-model-train.timer thermal-model-shadow.timer --all --no-pager
```

Training is daily 06:50 after the 06:40 forecast. Shadow starts 15 minutes
after boot, then every two hours; `Persistent=true` may cause catch-up.

## 7. Attended rollback

Retain receipts, journal, artifacts, reports, and logs. Never delete or rewrite
journal evidence. Rollback begins with a concurrency barrier so shadow cannot
republish and training cannot race restoration.

**ROLLBACK MUTATION — disable timers first:**

When both units exist this is the exact equivalent of
`systemctl --user disable --now thermal-model-train.timer thermal-model-shadow.timer`;
an absent, inactive unit is explicitly accepted for rollback before Gate C.

```bash
set -euo pipefail
for TIMER in thermal-model-train.timer thermal-model-shadow.timer
do
  if systemctl --user cat "$TIMER" >/dev/null 2>&1; then
    systemctl --user disable --now "$TIMER"
  elif systemctl --user is-active --quiet "$TIMER"; then
    printf '%s is active but its unit file is unavailable\n' "$TIMER" >&2
    exit 1
  fi
done
```

**ROLLBACK MUTATION — stop both oneshot services:**

When both units exist this is the exact equivalent of
`systemctl --user stop thermal-model-train.service thermal-model-shadow.service`;
an absent, inactive unit is explicitly accepted for rollback before Gate C.

```bash
set -euo pipefail
for SERVICE in thermal-model-train.service thermal-model-shadow.service
do
  if systemctl --user cat "$SERVICE" >/dev/null 2>&1; then
    systemctl --user stop "$SERVICE"
  elif systemctl --user is-active --quiet "$SERVICE"; then
    printf '%s is active but its unit file is unavailable\n' "$SERVICE" >&2
    exit 1
  fi
done
```

**READ-ONLY — assert both oneshot services are inactive:**

```bash
set -euo pipefail
for UNIT in thermal-model-train.service thermal-model-shadow.service
do
  if systemctl --user is-active --quiet "$UNIT"; then
    printf '%s is still active\n' "$UNIT" >&2
    exit 1
  fi
done
printf '%s\n' 'both oneshot services are inactive'
```

Only after that barrier may restoration begin.

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

**ROLLBACK SETTLEMENT — only exact original readback resolves ambiguity:**

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
  | jq -e 'select(.ok == true and .expected == "original")'
```

`settle` itself performs exact receipt-aware readback and refuses mismatch.

**ROLLBACK MUTATION — exact verified file restoration/removal:**

```bash
set -euo pipefail
umask 077
: "${REPO_ROOT:?}"
: "${FILE_RECEIPT:?}"
cd "$REPO_ROOT"
/usr/bin/python3 scripts/thermal-model-files.py restore \
  --repo-root "$REPO_ROOT" --receipt-dir "$FILE_RECEIPT"
systemctl --user daemon-reload
```

The helper prevalidates every backup/absent marker before its first restore,
atomically restores prior bytes/modes, removes only receipt-proven absent exact
targets, fsyncs parents, and re-verifies every target.

**READ-ONLY — unit state remains disabled and no service is active:**

```bash
set -euo pipefail
for UNIT in thermal-model-train.timer thermal-model-shadow.timer
do
  if systemctl --user is-enabled --quiet "$UNIT"; then exit 1; fi
done
for UNIT in thermal-model-train.service thermal-model-shadow.service
do
  if systemctl --user is-active --quiet "$UNIT"; then exit 1; fi
done
```

**READ-ONLY — final protected-state verification:**

```bash
set -euo pipefail
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/Thermal_Advisory \
  | jq -e '{name,state} | select(.name == "Thermal_Advisory")'
curl --fail --silent --show-error http://127.0.0.1:5190/rest/items/SouthOutlet_Outlet2_Switch \
  | jq -e '{name,state} | select(.name == "SouthOutlet_Outlet2_Switch")'
```

## Completion boundary

No gate authorizes advisory graduation or actuation. A later warm/winter
review must define and approve evidence-derived graduation thresholds.
Actuation requires a separate threat model, capability owner, reconciliation,
manual override, and fail-safe proof.
