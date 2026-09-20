# Qualified temperature collection and hourly learning activation

Operator approval: indoor WH32B ID235 confirmed; live learning explicitly
preapproved. This receipt supersedes the temperature activation blocker in
`2026-09-19-pump-and-temperature-followthrough.md`. It does not authorize changing
pump timings, protected control gates, or the held task82.

## Live collection

Weather service restarted at18:09MDT on September19 with the four previously
staged evidence modules. Existing0.0.0.0:5000 listener is unchanged; the new
`/temperature_evidence` route admits loopback only. Installed policy is owned0600
at `/home/sat/.config/hex/weather-temperature-policy.json`. Its identities are
outdoor WH65B206, indoor WH32B235, north-wall WH31E193. All three produced natural
valid receipts. Bounds remain -40..140F and120-second expiry.

Original service/weather backups: `/tmp/weather-evidence-release-C6hXHs` (0700).
Collector epoch: `bf34218f-7c1d-4303-b63f-a4d6b13e27ef` (will change on restart).

Added managed resources from `openhab/weather-temperature-evidence-resources.json`:

- HTTP Thing `http:url:weatherTemperatureEvidence`,30-second polling, READONLY
  whole-envelope String channel `snapshot`.
- String Item `Weather_Temperature_Evidence_JSON` and default-profile link.
- Existing JDBC wildcard everyChange policy preserved; no periodic numeric
  persistence, sensor state injection, or persistence configuration change.

Installer initially stopped safely with its new Thing disabled because HTTP
binding adds authMode=BASIC,ignoreSSLErrors=false,delay=0,commandMethod=GET.
Readback established these defaults and absence of Item/links. Explicit
`--resume-disabled-thing` then checked exact configuration/channel, used
ManagedItemProvider.add/ManagedItemChannelLinkProvider.add, verified definitions,
and enabled the Thing. The temporary triggerless metadata installer was removed;
no control/forecast rule was forced. Final Thing ONLINE/NONE; no installer remains.

Natural JDBC mapping is646, table`public.item0646`. First observed row was
2026-09-20T00:17:03.187413Z,1099bytes. Strict historical selection qualified all
three sources with original receipt, persistence, expiry and epoch metadata.

## Hourly learning

Activation cutover: **2026-09-20T00:30:09+00:00** (September19,18:30:09MDT).
User-systemd drop-in:
`/home/sat/.config/systemd/user/forecast-intel.service.d/qualified-temperature.conf`.
It sets HOURLY_TEMP_QUALIFIED_ENABLE=1 and the explicit cutover, policy path,
and private database-config path. Both forecast timers remained active;
neither forecast service was started manually. Existing06:40 daily scoring
schedule is unchanged. Hourly denotes the model's target resolution, not a new
hourly training timer.

Database role`weather_temperature_reader` is non-superuser, has a read-only
transaction default,2-second statement/1-second lock limits, and verified SELECT
access to only public.items/public.item0646 with no table-write privilege.
Credential lives only in owned0600
`/home/sat/.config/hex/weather-temperature-db.json`; it is not in this repository.
Each worker connection has3-second connect timeout; the parent enforces30seconds
for the entire at-most24-target read batch. Failure skips hourly learning without
numeric-history fallback. Missing/invalid/future/expired/wrong-identity observations
cannot become learning targets. Prior learned parameters are retained, not reset
or relabelled as qualified. Receipts distinguish new qualified updates.

Only the reviewed `score_hourly_targets` function and its main call were
transplanted into the older installed forecast script. All other functions and
module statements were AST-compared and identical. Pending advisory-capture
changes on repository main were NOT silently deployed or enabled.

- Original installed forecast SHA256:
  `6a3d176a9e8e852c8da9890e4c5d8a4731a912124065b8cf8ae7af7f72b23412`.
- New installed forecast SHA256:
  `39ce12e0a600aaef71cb94904b41884d1faf5367bf48ef3019713e8088b85743`.
- Private original script/model backup:
  `/tmp/hourly-temperature-release-fbmthqoc` (0700).
- Installed dependencies: hourly_temperature_runtime.py and the temperature
  reader/history/config/evidence modules; each matched repository source hash.

Installed worker accepted a natural outdoor receipt received00:30:29.838189Z,
persisted00:30:33.175503Z, after cutover. Model-file hash still matched its backup:
no manufactured training observation, manual model update, forecast publication,
test DM, or synthetic weather packet occurred.

First natural qualified model update is **not yet observed**. Forecast targets
must have been captured after cutover and before their target time, and must
mature before a normal scoring run. Pre-cutover queued targets are not promoted.
Thermal-model training/authority, completed-night outcome scoring, and bandit
threshold tuning are separate work and are not claimed activated here.

## Verification and operational recovery

Feature suite:966passed,42subtests,1expected disposable-PostgreSQL skip.
Dedicated PostgreSQL test subsequently passed against the intended
`advisory-trough-assessment/analytics/tests` fixture (1passed), verifying actual
query timeout, revoked permission, row barriers and duplicate mapping behavior.
An initial run used the older Solar main fixture lacking advisory_assessor;
that fixture failure was not a production failure. Main before merge also had
two known relay AST-fixture failures; the merged feature supplies the observer
fixture correction and regression without changing the live radio relay.
Installer safety tests:7passed. Post-merge focused regression:62passed.
Final merged-main suite:973passed,42subtests,1expected disposable-PostgreSQL
skip (that test separately passed as described above). Recent-log review found
an18:01:59 pump timer closed-context warning predating collection installation;
it is consistent with the earlier concurrent rule reload, not this activation.

To pause qualified hourly learning, explicitly set the drop-in enable flag to0
and reload user-systemd: supplied non-1 values skip scoring, not legacy fallback.
Do not simply remove the opt-in, which intentionally selects legacy behavior.
Collection can be independently disabled through the managed Thing if needed;
retain its Item/table/history. No database schema migration or history rewrite
was performed. Backups under/tmp are local recovery artifacts, not durable offhost
backups. An old-script rollback would restore legacy scoring and needs that
consequence explicitly considered.

Pump rule remained IDLE/NONE with SHA256
`e28f2616dcd830cd41bf7433f4f0ee6e36de7d6e32d2a3d00c5a6913eec8b375`.
Concurrent15-minute cycle setting was preserved. Full natural pump-cycle completion
remains unverified by this work.
