# Radiation history, shade collision and Office Hallway display

## First natural qualified-current publication — October 3 03:36Z

The unchanged timer actually triggered at **03:36:03.554478Z**, with natural
invocation `8513301a55e846f5b55656c50ad2a4d8`. Its main process was observed
live at PID 1229712, then the same invocation exited successfully at
**03:36:07.513108Z**. No manual service start or restart was used. The original
decision is **03:36:05.250859Z**; live `Thermal_Model_JSON`, original capture
and JDBC state match canonical output SHA-256
`a293131eab07e966cd3e44b98b2e1fd34a54f6fca6afc9a001ce3f8d0866912d`.
JDBC stored it at **03:36:07.471Z**.

Original capture:
`20261003T033605Z-a293131eab07e966.json.gz`, compressed-file SHA-256
`3a67587ae2195eadf50d77438da7939670488f737886009b9975ec91775cf234`.
Native radiation was decoded at **03:35:31Z**, 34.251 seconds before decision,
with original expiry **03:37:31Z**. It is the qualified light-derived irradiance
proxy, not newly calibrated measured irradiance. Original decoder/receiver/
storage clocks and verified cumulative-fault metadata pass at decision; expiry
also passes at publication. Those historical times are not renewed freshness
at a later verification. All three current temperature expiries pass too.

The accepted artifact remains canonical `2435c019...`, trained under `7f57eb3f...`.
As-issued replay passes under the explicit installed publication runtime
`c732feed...`; the older training revision is not relabelled. A separate cold
replay of this **new** capture also passes using only the exact code restored
from the existing `99bce9cc...` private replay archive. Its temporary runtime
was removed; no redundant full archive was created.

`scripts/verify-thermal-natural-publication.py` now binds precise actual
systemd timer/start/exit times and invocation ID, immutable private capture,
unchanged installed code/configuration/artifact/drop-in, source expiry,
current Item, one ordered original JDBC record and explicit-runtime replay.
Default is read-only. Recording writes only `natural-publication.json` and
its SHA pin in the **existing private rollout receipt**, never models, source,
configuration, Items, journal, services or timers. The receipt now reports
**`installed_natural_publication_verified`**. Proof is owned mode 0600 with SHA
`c729efed79145da58124007bebc4d816f88e0d469b93f0f7f76fa3d2a7a7e99c`.
Repeated record verification returns that identical proof rather than replacing
the evidence. Interrupted proof-before-pin commits recover without rewriting
another invocation's evidence; proof drift refuses, and rollback preserves it.

Reverify the completed invocation while it is still the unit's latest run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify-thermal-natural-publication.py \
  --receipt /home/sat/.local/state/thermal-intel/deploy-receipts/radiation-current-20261003T015000Z-43f9a127
```

The first live verifier attempt used the wrong registry directory and could
not load the artifact; it wrote no proof. The corrected verifier uses the
installed **pure parser**, not a registry load that could quarantine/restore
models, and selects the installed closure before recovery-helper imports.
The root registry lock predated the test (August 20); it was preserved.
All **92** affected delivery/file-transaction/replay tests pass without skips,
including early/manual/failed runs, missing/conflicting/future JDBC rows,
import ordering, private commit interruption, idempotency and exact rollback.
Owned temporary test storage is removed. OpenHAB remains active at PID 1696.

This closes the first natural **current-input delivery** gate only. Complete
clean-day radiation learning, confirmed-action collection, held-out predictive
skill, reviewed graduation thresholds and household automation remain separate.
Permanent Primal collector units remain off; no user report became a label.

## Approved scope

The operator approved durable read-only radiation history and the coincident
shade-timing correction on October 2. Radiation is observational; collection
does not authorize calibration, forecast promotion or household controls.
The subsequent UI clarification keeps Office Hallway on Home and removes its
Earthship-page reading and visible history series only. Sensor 223 collection,
its existing backend Item/history and thermal input remain unchanged.

## Source and isolated verification

The new file-owned `Weather_Radiation_Evidence_JSON` String is linked only to
`http:url:weatherRadiationEvidence:snapshot`. The HTTP Thing reads the existing
local receiver endpoint every 30 seconds. The complete original receipt is
stored by the existing JDBC `everyChange, restoreOnStartup` strategy; polling
does not renew decoder timestamps or expiry.

`scripts/qualify-weather-radiation-jdbc.py` exercised real OpenHAB 5.2.1 HTTP
and JDBC bindings against disconnected, disposable PostgreSQL/OpenHAB
containers. It verified unchanged polls, persisted expiry barriers, HTTP-503
fault and fresh-source recovery, Item/link withdrawal and recovery with history
prefix preservation, actual JVM restart with exact old-receipt restoration,
and a newly received post-restart receipt. The inherited persistence-provider
round trips explicitly report their collection gaps, not source continuity.
HTTP-503 does not require a framework OFFLINE status; the test proves the
binding fetched the error and checks that held state does not mint history or
renew source expiry. No host ports, devices or configuration mounts were used.
The script exited zero and removed both owned containers and test storage.
This is not a whole-host restart or production-continuity qualification.

Coincident quarter-hour-rounded shade times represent zero closed duration in
the existing cyclic model. The correction emits no contradictory simultaneous
transitions and reports open day/night state. Strict ordered-transition
validation is unchanged. Eight behavior cases and a full forecast regression
failed before the correction and passed afterward.

Only `thermal_model/behavior.py` is eligible for installation into the existing
thermal runtime: the repository contains other, undeployed thermal candidates.
The installed preimage predates the source-tested cyclic initial-state
correction, so this one-file release includes that correction as well as the
coincident-transition fix. It preserves a modeled closed interval spanning
midnight; this is a modeled schedule, not a claim of measured shade state.
An isolated copy of the actual installed runtime with just this file changed
has runtime revision
`7316fa8b1e408544463b3f44e64772e56c7f36b57a9d6325ccca3353bea03af5`,
versus installed preimage
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`.
The October 1 and October 2 saved forcing captures reproduced their as-issued
outputs exactly under the explicitly pinned candidate. The October 1
`--solar-scale 1.5` diagnostic failed on original installed source with the
schedule collision and produced a usable forecast with the correction.
These are replay/collision checks, not measured-radiation training or proof of
forecast accuracy. The trained model's revision must not be rewritten.

The modified full suites passed 3,044 Python tests and 74 subtests (no skips),
and 1,984 JavaScript tests across 135 files. The production frontend build
passed with the existing chunk-size warning.

## Production gates

Before installation, require unchanged runtime preimage, absent radiation
Item/Thing/link and destination files, current local receiver receipts, a
private narrow rollback backup, and an unchanged OpenHAB process. Install only
the new observational definitions and the single qualified thermal file.
Require natural HTTP/JDBC receipts and uniquely discover the new JDBC Item
mapping; never guess its table number. A restricted-reader grant, strict
interval/day reader and complete clean days are separate gates before learning.
October 2 includes receiver restart boundaries and is not a complete clean day.

Restart only the user-level UI service after merging the source tree, then
verify transformed production modules. Do not restart OpenHAB for this work.
Backend Office Hallway history must remain present; Home retains the reading.
The thermal collector, questions, training-label writes, household controls,
new learning/calibration and model graduation remain outside this release.

## October 2 live deployment

The reviewer accepted the final range through `1d63090`. Review found that an
identical HTTP poll could mask a failed radiation restore; the qualifier now
holds HTTP at 503 across JVM restart, removes the prior fetch marker, requires
a new observed 503, verifies restored state/history, then allows fresh recovery.
The corrected real-container run exited zero and removed its owned resources.
Merged-tree verification passed 3,044 Python tests and 74 subtests in 333.66
seconds, 1,984 JavaScript tests, and the frontend build before push/deployment.

The exact source was pushed to `origin/main` and installed at approximately
09:30 MDT. Private rollback source is retained mode 0600 in the mode-0700
directory `/home/sat/.local/state/thermal-intel/shade-source-rollback-pUa05Q`.
The preimage SHA-256 is
`f2bcbe5021a68cde2a824f50311acc99a499f828b490a9ba6dad57bf13489a8e`;
the installed candidate is
`80bfbfc70e53dad8063e0290a991d53bd3d8d6c6f6fa4b790a2cebd3a29d2b81`.
No other thermal runtime file or trained artifact was replaced.

The new Item, Thing and sole READONLY link are noneditable file resources;
Thing status is ONLINE. Exact deployed definition hashes match Git. JDBC
uniquely mapped the radiation Item to **664 / `public.item0664`**, with its first
natural row at `2026-10-02T15:30:39.039114Z`. Multiple naturally advancing
original decoder receipts match the persisted raw JSON, with expiry exactly
120 seconds after decoder time. A checked receipt had decoder time 15:31:32Z,
receiver time 15:31:32.966989Z and expiry 15:33:32Z. The existing JDBC policy
hash is unchanged. The restricted `energy_power_reader` currently lacks
SELECT on the new table; no grant or strict-day reader was activated.

The user-level UI service restarted successfully at PID 346291. Served Svelte
modules preserve Office Hallway in Home and omit its Earthship reading/series.
Its existing backend identity remains 663 / `Bedroom_Temperature`; persisted
rows increased naturally from 321 to 322 rather than being deleted. The
sensor/parser, role mapping and thermal-input configuration were not edited.

Installed-runtime replay reproduced the October 1 as-issued output exactly and
passed the previously failing solar-sensitivity diagnostic at runtime pin
`7316fa8b...`. The existing shadow service then exited zero at 09:32:13 MDT.
Its 72-point low-confidence output generated at
`2026-10-02T15:32:11.579258Z` matches both the latest JDBC state and original
capture `20261002T153211Z-559a9d4532336f33.json.gz`, with output digest
`559a9d4532336f3363eb49d7b25d6a226cfde5ce233c718271ce8b11d3bae1a8`.
The embedded artifact still has its original training revision. OpenHAB stayed
at PID 1696; there were no new OpenHAB ERROR/Exception lines in the checked
post-deployment interval. No controls, questions, journal labels, collectors,
training, learning/calibration or graduation were activated.

Durable collection is live, but the restricted grant, strict clean-day reader,
complete-day evidence and later production restart continuity remain separate
gates. Preserve `item0664` if disabling collection. Source rollback must verify
the candidate/preimage hashes and atomically restore the private `behavior.py`;
observational-definition rollback parks only these two new definition files
outside watched directories. Neither rollback drops history or changes controls.

## Approved restricted-reader grant — October 2

The operator separately approved SELECT on only `public.item0664`. The live
Item-name lookup again uniquely returned 664 before the database owner applied
`GRANT SELECT ON TABLE public.item0664 TO energy_power_reader;`. Readback shows
SELECT true and INSERT/UPDATE/DELETE false. The actual restricted reader also
read the latest two original receipts in a bounded read-only repeatable-read
transaction. No other table privilege, writer, learner or collector was changed.

This supersedes the missing-grant gate in the deployment checkpoint above.
The strict radiation interval/day reader is still unimplemented. October 2 is
partial: the receiver restarted at 08:16 MDT and durable history began at
09:30 MDT. October 3 is the first possible complete day, assessable after
October 4 local midnight if source continuity passes. Neither held numeric
radiation nor HTTP polling may backfill missing source evidence. Production
restart continuity and learning remain separate gates.

## Thermal current-radiation worker — October 2 evening source candidate

The actual thermal shadow input builder still reads radiation through numeric
JDBC history and the Item's `lastStateUpdate`. The new independent opt-in
`thermal_radiation_runtime.py` supplies a **current native v2 receipt instead**.
It is wired into `_current_states`, while an absent opt-in preserves the
installed legacy contract. Explicit bad activation or missing/invalid evidence
refuses shadow publication; neither held numeric history nor Item-update times
can rescue the qualified radiation path.

Only the current target is needed by this input builder. The worker therefore
uses one bounded subprocess and one dedicated read-only repeatable-read
connection through `fetch_radiation_grid`, rather than reading another 24 hours
of radiation on every forecast. Original decoder/receiver/JDBC times, expiry,
epoch, sequence, cumulative fault count and original snapshot SHA remain in
`current.radiation.sourceEvidence`. The radiation reading's `at` is the native
decoder clock, not command time. The unchanged lux conversion remains a proxy,
not calibrated pyranometer or PV-energy evidence. Original source expiry is
checked again after model computation, inside the unavailable-output boundary.

The proposed explicit private settings are:

```text
THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE=1
THERMAL_RADIATION_DB_CONFIG=/home/sat/.config/hex/energy-power-reader.jdbc
THERMAL_RADIATION_POLICY=/home/sat/.config/hex/weather-radiation-policy.json
THERMAL_RADIATION_EVIDENCE_CUTOVER=2026-10-02T20:00:09.206165+00:00
```

These settings are **not installed or enabled**. The worker reuses only the
already approved private local `energy_power_reader` configuration, with a
closed, bounded, no-symlink loader and read-only connection startup. It refuses
implicit libpq service files. No new database grant or credential is needed.
This gate applies only to the current shadow observation; training and daily
radiation scoring still require their separate complete-clean-v2-window/day
qualification and must not be enabled by this flag.

The deployment manifest and runtime hash now bind the worker and all four
radiation dependencies. Replay bundles accept the exact new 26-file inventory
and the exact original 21-file inventory, retaining old bundle/runtime/training
identities rather than relabeling them. Regression checks reject changed,
missing or reordered inventory, bind each new dependency to the runtime hash,
and reopen the entire source receipt in an immutable forcing capture. An
isolated file rehearsal used the **actual candidate code manifest** with
temporary target preimages: an interrupted installation restored original
bytes/modes and removed newly introduced radiation files; successful install,
verification and explicit restore also passed. This is an isolated file
transaction proof, not an attended production deployment or live publication.

The complete affected weather/thermal-input/publication/capture/deploy/replay
slice passed **769 tests in 43.24 seconds**, with no skips, including actual
disposable restricted PostgreSQL. Test containers and owned temporary storage
were removed. No bytecode/test-cache artifacts were created.

A separate actual worker subprocess, using only the existing restricted live
reader, qualified a receipt at `2026-10-03T00:44:30.398706Z`: decoder time
`00:44:03Z`, receiver `00:44:04.209737Z`, original JDBC storage
`00:44:09.379230Z`, expiry `00:46:03Z`, native age **27.398706 seconds**,
verified fault visibility and **1.71 W/m² irradiance proxy**. Original snapshot
SHA-256 is `f1a1bbf32af9223a0ad131c1f929f37d3c17e721b6e3eeaac21a0802b8595887`.
This was read-only diagnostic execution, not a shadow publication, model
update, action label, completed-day proof or installed worker activation.

The production digest comparison finds all five radiation modules absent and
the expected entrypoint difference. It also identifies **pre-existing separate
source/runtime differences** in `thermal_model/artifacts.py`, `dynamics.py`,
`evaluation.py`, `journal.py` and `schema.py`; the forecast helper and remaining
temperature/publication modules match. Do **not** install the whole repository
manifest as a radiation-only rollout. The next deployment candidate must pin
and recover the exact installed runtime, change only the entrypoint plus these
five radiation modules, independently qualify its resulting publication
revision and original accepted-artifact replay, and retain rollback/config
evidence before enabling the current-input flag. Complete v2 days and thermal
skill/action gates remain separate. No production source, private environment,
service, model, collector, forecast publication or household control changed.

### Exact installed-runtime qualification — October 3 01:07Z

`scripts/qualify-thermal-radiation-runtime.py` now freezes the **actual installed
runtime**, not the broader repository candidate. The installed entrypoint's
SHA-256 exactly matches the pre-radiation commit:
`8d7873a0b37dc252cdc2fb59175a18952df229e69505402d28ec40e2bb88fcc2`.
The reviewed installed full runtime remains
`7316fa8b1e408544463b3f44e64772e56c7f36b57a9d6325ccca3353bea03af5`.
Only the six-file radiation delta is overlaid; **21 other files**, including
the separately differing model/journal modules, remain byte-identical to
installation. The resulting qualified mixed runtime revision is
`b700545b101e5aa441d35f4d1d4214ae2df5cb5a030aa3af0e0ce9275a0a7da6`.

Both original immutable publications replay exactly under the installed and
mixed candidate runtimes and again after an isolated file handoff:

| Original capture | Unchanged output SHA-256 |
| --- | --- |
| `20261002T193405Z-930f9e4af7b20516.json.gz` | `930f9e4af7b205166e9432afa37fb490e5b339cbddf352cb031512fc4b4faa32` |
| `20261002T233514Z-c52967e2973b64e1.json.gz` | `c52967e2973b64e1f31eb59f28da92e088751b216e4c12a9ac28ea2db061e499` |

The captures' original embedded training revision remains `7f57eb3f...`,
distinct from both publication runtimes. No artifact or historical capture
was rewritten. Actual original bytes are guarded again after qualification.
The existing durable file adapter verifies all unchanged dependencies, exercises
an interrupted six-file update and a successful update/restore in temporary
targets, removes new radiation files on rollback, and restores the exact old
full runtime hash. No service or production path is installed by this script.

The optional actual-current-input probe first refused because its temporary
service lacked the existing qualified-temperature **drop-in** settings. The
actual shadow unit already has those settings; no production defect or
configuration change is inferred from that deliberately incomplete probe.
After supplying the exact three nonsecret existing drop-in settings alongside
the process-local radiation settings, qualification passed at
`2026-10-03T01:07:29.173995Z`. Indoor, mass and outdoor readings all have valid
native receipt expiry. Radiation is **0 W/m²**, from a native receipt **46.174
seconds old**, expiring at `01:08:43Z`, with verified fault visibility and
snapshot SHA `e67069d6afc13ebd805def2fb4a28ce5c85c386d25713bfc694604676821b200`.
This zero is measured proxy evidence, not an astronomical/nighttime fill.
The check uses the existing private environment and explicit process-local
overrides; it performs no shadow publication, training, journal write,
recurring listener, control or permanent unit/configuration change.

The **235 directly affected qualifier/worker/deploy/hash/replay tests** pass
in 2.87 seconds; the earlier full affected 769-test result remains unchanged.
Tests cover pre-allocation refusal, unrelated-source preservation, source and
capture drift, replay identity divergence, optional-probe refusal and cleanup.
The actual transient units were collected and temporary trees removed.

These gates now qualify the narrow **runtime/source/input** candidate. Before
production handoff, still take a private exact installed-code/config recovery
point, recheck idle workers and unchanged source pins, install dependencies
before the entrypoint, retain the existing temperature drop-in, and qualify a
separate current-radiation drop-in and its rollback. Require a natural shadow
publication and preserved original artifact/capture identities afterward.
Do not promote training, daily calibration, action collection or the wider
repository models as part of this rollout; complete clean v2 days and skill
gates remain separate. Production runtime and source activation remain unchanged.

### Guarded rollout and receipt-clock correction — October 3 01:42Z

Pre-apply review found that the final expiry check added total command elapsed
time to a decision clock that already included input-fetch latency. A 60-second
fetch followed by 10 seconds of computation was assessed as 130 seconds rather
than 70, incorrectly withholding a genuinely fresh 120-second receipt. The
regression failed before anchoring elapsed time to command start. The check
still honors a forward decision clock and refuses genuinely expired receipts;
no TTL is extended. This affects both qualified temperatures and radiation.

The corrected six-file candidate is now pinned to
`c732feed23f4a9dd323a85a77dec9872d821c626d6619a642548dc7b752baaac`
(superseding the earlier `b700545b...` candidate). Both original publications
again replay exactly, interrupted/successful isolated install and restore pass,
and actual current receipt input passes at `2026-10-03T01:42:10.798560Z`.
The new entrypoint SHA is
`9cdb624727122d65b50ab6d80f742ee562b78d99087f1e2f02434e767f26161d`.
The complete affected suite now passes **819 tests in 44.67 seconds**, with no
skips and actual disposable PostgreSQL; test storage is cleaned.

`scripts/thermal-radiation-files.py` uses the existing durable file adapter.
`prepare` creates only a new private receipt containing the frozen mixed
runtime, original code/absence markers, exact current configuration snapshots
and accepted artifact. `apply` and `restore` require `--allow-apply` and refuse
active jobs, changed source/configuration, or a natural forecast deadline less
than 90 seconds away. Dependencies are installed before the entrypoint. Only
the new `qualified-radiation.conf` is added; existing temperature/capture
drop-ins and both timers remain unchanged. Readback requires the exact runtime
revision and four current-radiation environment settings. Failed apply restores
the complete original file state and reloads the user manager; `recover`
handles an interrupted file transaction before restoring. No service/timer is
started, stopped or restarted by the adapter, and no OpenHAB restart occurs.

The recovery command, run as `sat` from the repository, is:

```sh
python3 scripts/thermal-radiation-files.py restore --receipt /home/sat/.local/state/thermal-intel/deploy-receipts/RADIATION_RECEIPT_NAME --allow-apply
```

Use the actual recorded receipt name; use `recover` instead of `restore` only
for an interrupted transaction. A configuration/artifact change after capture
is deliberately a refusal, not permission to overwrite later operator work.
Configuration snapshots are same-host mode-0600 recovery evidence inside a
mode-0700 directory, never Git or an off-host copy.

Read-only live registry inspection reports **42 rules, none referencing
`Thermal_Model_JSON`**. The selected accepted artifact has canonical SHA
`2435c019...`, identical to the latest original capture. Its on-disk JSON byte
SHA is `0a6a9ae0f224642f65ccfd72deef74626eb349e0c091436a7211120c2faeb72c`;
canonical data identity and serialized file identity are distinct. The
existing natural shadow job exited zero at 19:36 MDT without a source change.
The new adapter/drop-in are source-qualified here; actual private preparation,
production apply, writer/capture verification and natural timer proof are
recorded separately after execution. No learning or thermal graduation is
implied by the current-input rollout.

### Production current-input rollout — October 3 01:50Z

The guarded adapter installed the exact six-file mixed runtime
`c732feed23f4a9dd323a85a77dec9872d821c626d6619a642548dc7b752baaac`
and the four-setting current-radiation user drop-in at **01:50:59Z**.
All 21 unrelated runtime files, existing temperature/capture drop-ins, timers,
private configuration and accepted artifact are preserved. The pre-apply
native zero was 32.38 seconds old with original expiry 01:52:27Z. No OpenHAB,
protected-control, training or scheduled service was restarted.

Private mode-0700 recovery receipt:
`/home/sat/.local/state/thermal-intel/deploy-receipts/radiation-current-20261003T015000Z-43f9a127`.
It contains frozen source, durable original-file/absence markers and mode-0600
configuration/artifact snapshots. Restore uses the command above with this
exact receipt; changed later configuration/artifacts deliberately refuse.
The receipt remains `installed_waiting_natural_publication`.

A bounded transient writer using the actual installed source and existing
production settings then published at **2026-10-03T01:58:02.671486Z**.
An initial verification-wrapper invocation had failed before `_shadow` on a
missing required helper argument; it produced neither output nor capture.
The corrected invocation completed successfully. OpenHAB `Thermal_Model_JSON`
readback matches canonical output SHA-256
`5f053eec5272386de340274a349d664cdba7203a24fc3b93f77829def3281520`.
Original capture is
`20261003T015802Z-5f053eec5272386d.json.gz`; full as-issued replay matches under
the explicit installed publication revision. Native radiation was 39.67
seconds old at decision with original expiry 01:59:23Z and verified fault
visibility; these are historical receipt facts, not renewed freshness.
The trained artifact retains its original `7f57eb3f...` source identity and
low/shadow confidence. No chat report or shade preview became a training label.

The independently verified private `publication-replay.tar.gz` inside that
receipt contains 144 members: exact runtime/capture helper, four model-state
files and 113 original captures. Its SHA-256 is
`99bce9cce7fe9c430bf1cbfc2018929499ad40f9a227573c07463ee8038672b9`.
Explicit publication binding distinguishes current publisher from the older
trained artifact; this is not off-host/full-host recovery or a claim that all
older captures replay under new code.

Post-apply exact source/unit/configuration/artifact checks pass. OpenHAB stays
active at PID 1696; Primal service/timer remain absent/inactive. Transients and
task-owned test storage are cleaned; purposeful recovery evidence is retained.
The unchanged two-hour natural shadow timer is next due **October 2 21:35:56
MDT**. The successful one-shot is not that natural-run gate. Verify its next
original capture, publication/readback and explicit-runtime replay before
closing that gate. Complete-clean-v2-day learning and graduation remain off.

## Strict reader and v2 fault visibility — October 2

Natural native radiation arrives about every 16 seconds, versus the unchanged
30-second HTTP poll. Legitimate sequence jumps therefore cannot by themselves
prove a missed fault: an invalid packet could be overwritten by the next valid
packet before OpenHAB reads it. The v2 envelope adds cumulative `faultCount`;
the original nested source record remains v1. Invalid selected-source packets
and expiry each count once. Expiry is checked before a new packet can overwrite
it, not only on GET. Counters reset only with a visible new receiver epoch.
Unchanged GETs/duplicates still cannot renew source time, expiry or sequence.

`weather_radiation_reader.py` now provides pure strict as-of and elapsed-window
qualification with a one-pass uncertainty sweep; `weather_radiation_history.py` supplies bounded SELECT-only
Item-name mapping and stable SQL reads, plus completed local-day/DST handling.
Explicit policy, original source/cutover times, exact conversion, finite numbers,
closed JSON schemas, canonical epochs and monotonic native/counter progress are
required. Malformed/NULL/oversized rows, source replays, expiry and restart stay
barriers. Hidden faults conservatively invalidate time since the preceding
source observation; recovery never backfills those intervals.

Clean totals additionally require a valid native closing receipt at/past end,
within one TTL and the assessment time. Post-window values never contribute to
the integral. Valid v2 downsampling with unchanged fault count is supported;
legacy v1 remains diagnostic-only/unverified. Partial windows expose no qualified
total. The integral is explicitly **persisted sample-and-hold lux-derived
irradiance proxy in Wh/m²**, not calibrated radiation or PV kWh. Imports do not
connect, publish, train or activate a service.

Four new receiver regressions failed before their respective fixes. The final
complete weather/qualifier-CLI slice passed **312 tests in 11.64 seconds**, with no skips,
including actual restricted PostgreSQL permission/timeout/mapping barriers,
23/25-hour DST days and unchanged existing temperature/rain/legacy responses.
A separate 2,001-receipt overlapping-fault regression passes with exact gap
accounting; the sweep avoids quadratic rescanning of every fault at every sample.
The real disconnected OpenHAB/PostgreSQL HTTP/JDBC qualifier passed unchanged
poll, v2 expiry, HTTP fault/recovery, provider withdrawal/history preservation
and HTTP-unavailable JVM restore/new receipt checks; owned containers/storage
were removed. This proves the v2 transport contract, not production JVM or
whole-host recovery. Its entrypoint previously ignored `--help` and launched the
fixture; argument parsing now exits before allocation, with two passing CLI
regressions. No repeated full fixture was needed for that CLI-only correction.

A bounded live pre-upgrade read under `energy_power_reader` returned 900 seconds
of apparent coverage but correctly marked v1 fault visibility/closing evidence
unverified and withheld its total. No old history is relabelled clean.

Only `/home/sat/bin/weather_radiation_receiver.py` was installed. Exact preimage
`c4ff6cdede9ae9448c57d7223be106687c0fcc4206fd64b08201221a50e2a550`
is retained mode 0600 under private rollback directory
`/home/sat/.local/state/weather-radiation-v2-rollback-IDkZQY73`.
Candidate/deployed SHA-256 is
`9f49e459fbc0ef4c984c144691bc87825c4f0a723910565d4702e980548bcc92`.
The sudo restart was unavailable; its guarded failure path restored the exact
preimage without stopping the running service. The actual installed Gunicorn
20.1.0 HUP handler was inspected, then the exact sat-owned master was gracefully
reloaded after guarded candidate installation. OpenHAB PID 1696 and weather
master PID 80148 remain active/unchanged; no radio restart or unit/policy edits.
Unchanged wrapper, temperature and rain source pins were verified before apply.

All four temperature streams, rain and natural v2 radiation recovered with new
radiation epoch `c75b060e-09dc-4637-8b03-8e26a951dba3`, fault count zero.
First natural v2 JDBC receipt is **`2026-10-02T20:00:09.206165Z`**; the unique
file-owned Item/table remains **664 / `public.item0664`**, with old v1 rows still
present. Four advancing v2 rows passed a restricted-reader check. The elapsed
`20:00:39.206669Z`–`20:01:09.206002Z` interval qualifies at 29.999333/29.999333
seconds, with original input digest
`571b6c8c19f9a85a825302dff97b6b41d39046a87c2799dd53131fe8fd79cb61`.
Its 5.064637393725 Wh/m² proxy is a read-only diagnostic, not published or used
for training. SQL/persistence strategy, grants, Item/Thing definitions and all
forecast/model/control release gates are unchanged.

October 2 is still partial. October 3 remains the first possible complete clean
v2 day, assessable after October 4 midnight plus its natural closing receipt.
The strict reader is source-ready and manually verified, not installed into a
live learner. Complete-day and production JVM continuity qualification, then
explicit evidence-gated learner integration remain next. Rollback must guard
the deployed candidate hash, atomically restore the retained preimage and
gracefully reload the currently verified sat-owned weather master; preserve
all v1/v2 JDBC history and recognize the new epoch/collection gap.

## October 2 evening: source-only batched radiation grid foundation

`select_radiation_grid` and `fetch_radiation_grid` now provide bounded,
**as-of v2-only** receipt observations for future thermal integration. At most
301 strictly increasing targets span at most 25 elapsed hours, accommodating
a five-minute grid across the long DST day. Each original snapshot is parsed
once; one dedicated read-only repeatable-read PostgreSQL connection fetches
the original carry plus intervening rows through two source SELECTs. The
existing unique Item mapping, row/payload limits and query/lock timeouts remain.
Invalid requests refuse before connecting, and connections close on failure.

Results retain original decoder, receiver, persistence, expiry, epoch, sequence,
fault counter, conversion and snapshot digest. Target timestamps never replace
receipt clocks. Missing/expired/malformed/replayed evidence is unavailable, not
filled or interpolated. Legacy v1 cannot qualify: an unverified legacy row also
blocks a later v2 wrapper around its same old native record until a genuinely
newer decoder/receiver receipt arrives. That edge regression failed before its
fix. Existing single-point diagnostic and interval/day APIs remain unchanged.

This grid does **not** prove complete exposure or authorize training. A hidden
fault disclosed by a later counter can invalidate a past interval even though
the earlier point was usable as-of its own timestamp. The existing complete
v2 window/day and native closing-receipt gates remain independently required
before learned forcing or calibration. Grid points must not bypass them.

Verification:

- New reader/transport tests failed against the missing APIs before implementation.
- The 25-hour fixture parses exactly 3,001 snapshots once for 301 targets.
  Fifty deterministic v2 fault/restoration histories produce **3,800** exact
  matches against the unchanged single-point engine; legacy-grid refusal is
  deliberately stricter than that engine's retained v1 diagnostic behavior.
- The actual disposable restricted PostgreSQL test now exercises the grid's
  future-value exclusion, malformed/oversized barriers, permission denial,
  ambiguous mapping and closure alongside the original point/window checks.
  The full weather/qualifier-CLI slice passes **335 tests in 12.63 seconds**,
  with no skips. Owned fixtures, containers and pytest directories are removed;
  bytecode and pytest-cache writes were disabled.
- At `2026-10-03T00:12:09.870254Z` (October 2, 18:12 MDT), a real SELECT-only
  check under the existing restricted `energy_power_reader` qualified **37/37**
  five-minute targets from `2026-10-02T21:10:00Z` to `2026-10-03T00:10:00Z`,
  using one connection that closed cleanly. Its explicit v2 cutover remains
  `2026-10-02T20:00:09.206165Z`. Canonical result SHA-256 is
  `866ff49d4b1d0846029aa2e4eb0b99f6f06df9f61b1c2014fc6d8f947bf2e98d`;
  a fixed-original-assessment recheck after the legacy-barrier fix matches it
  exactly. This short grid is not complete-day qualification or calibration.

Both radiation reader modules remain absent from `/home/sat/openhab/scripts`;
the new API is repository source, manually exercised read-only, not installed
into the active thermal worker. No new credential/grant, source opt-in, service,
artifact, SQL row, forecast publication or household control was changed.
The next step is an explicit fail-closed worker/manifest/cutover integration
with original-input replay and coordinated recovery; learner activation still
waits for complete clean v2 days. October 3 local remains the first possible
full day, assessable after October 4 midnight and its closing receipt.
