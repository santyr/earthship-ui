# Window/skylight journal vocabulary: isolated v2 candidate

**Current status:** the operator-approved journal-only cutover is live, and
the September 30 post-v2 recovery check below passes under installed consumer
`7f57eb3f...`. Earlier v1/pre-cutover statements are historical checkpoints.
The collector and model/control release gates remain off.

The operator chose separate window and skylight states. The production
`thermal_intel.action_events` journal still permits only legacy actions,
including the ambiguous `vent`, and its exact v1 schema fingerprint is
`786e9b7bf3ca5587f08bcdcd960239a88bf887a8b31c4ea5eddcbc808c496efb`.
No household journal row or schema was changed here.

`thermal_model/airflow_migration.py` is an **explicit, default-off** candidate.
It accepts only that exact v1 schema/ACL/owner preimage, requires the actual
database owner, and changes only the `action_events_action_check` constraint
inside one PostgreSQL transaction to add `window` and `skylight`. Its exact
normalized PostgreSQL 16 postimage is
`f3e09cdd6cbd82bcd34475485bbf326bbc4789f4bcb1f4e050d9fba213378790`.
An unexpected preimage, owner, postimage or lock timeout fails closed and
rolls back; a second call on an exact v2 schema is a no-op. The release flag
remains `False`, so the migration refuses before connecting to a database.

Disposable PostgreSQL tests created a fresh exact v1 journal and runtime
role, rehearsed the constraint change and rolled it back to measure the
postimage, then proved the actual migration preserved an existing `vent` row,
accepted independently named window/skylight rows, preserved same-action
correction links, rejected a cross-action correction atomically, and passed
v2 audit. A deliberately wrong expected fingerprint restored the exact v1
schema. The migration and existing journal/history suites passed 39 tests;
the later correction test passed again. All owned test containers were removed.

The source-side as-of-origin reader now preserves its historical v1 output
shape by default. A pure, explicitly versioned v2 projection keeps window and
skylight states separate, marks `vocabulary_version: 2`, refuses a later
correction at an earlier origin, and leaves legacy `vent` missing rather than
deriving it. The database-backed v2 reader is still default-off; it refuses
before connecting until a coordinated household cutover qualifies that path.
The v1 reader rejects unexpected v2 rows instead of silently discarding them.
The migration, existing journal, schema, origin and action-history suites pass
84 tests; no production model forcing or action label changed.

The gated v2 database reader now also requires the named restricted runtime
role and distinct owner, verifies the exact v2 schema fingerprint in the same
read-only repeatable-read transaction as its bounded as-of-origin queries, and
refuses a legacy v1 schema or wrong connection role. A disposable PostgreSQL
test then reads independently recorded window and skylight states without
deriving a vent state. The gate remains `False`; the related action, journal
and origin suites passed 72 tests. No household v2 query was run.

The source-only confirmation storage path now keeps three independent release
barriers: `POSITION_INGRESS_RELEASE_READY`, `V2_WRITE_RELEASE_READY`, and the
delivery/inbox gate are all `False`. Legacy v1 journal calls refuse window or
skylight actions before connecting. When explicitly enabled in a disposable
test, a v2 append requires a configured restricted runtime role and distinct
owner, locks the three journal tables, audits the exact v2 schema in the same
transaction, and only then inserts the receipt and action rows. The attended
ingress also runs a read-only exact-schema preflight before accepting even a
`skip` reply into its spool. A disposable v1 schema refuses both skipped and
confirmed replies before spooling; after v2 migration, an induced readback
failure leaves a durably spooled confirmation unacknowledged. Its retry gets
exact readback without adding duplicate action rows. A separate `skip` reply
is acknowledged only after the v2 preflight and creates no action row. The
test uses a decoder double, not a genuine signed Nostr
reply. All 277 adjacent journal, confirmation, origin and messaging tests pass. No
household journal, spool, collector or model was changed.

The matching encrypted delivery path now has its own default-off
`POSITION_DELIVERY_RELEASE_READY` gate. Even if that gate is deliberately
enabled, constructing v2 delivery requires the v2 ingress gate and exact
restricted journal preflight; direct v2 inbox polling still refuses under
`POLL_RELEASE_READY = False`. A source-only fake-relay/keyer test queued the
versioned state question, accepted a fixture reply through the same spool
and sink interface, and built a distinct `THERMAL STATE RECEIPT v2` only after
commit. Queued prompts were withheld after gate revocation or a failed fresh
storage preflight, and later sent only after recovery. The full completion
and adjacent journal/origin suites passed 488 tests. This is transport-logic
evidence, **not** a household signature,
delivery, operator-read or physical-state confirmation. No live question,
relay event, listener or control was started.

A later full **synthetic** recovery rehearsal used the existing private v3
thermal state bundle format: two SQLite databases, private policy/route
fixtures, and a `pg_dump` custom archive of a populated exact-v1 PostgreSQL
journal. The bundle's five files passed digest/structure verification; both
SQLite snapshots reopened with their original rows. `pg_restore` loaded the
journal into a second disposable database with the original runtime-role ACLs
and legacy action row intact. That restored database passed the exact v1 audit,
then the guarded v2 migration and exact v2 audit. The migration and legacy
journal/history suites passed 42 tests. The test's private temporary tree and
all owned PostgreSQL containers were removed. This proves the recovery code
path on synthetic data, **not** a backup or restore of the household journal.

A subsequent read-only **household journal** qualification used
`scripts/qualify-thermal-journal-live-restore.py` under a transient user unit
with the restricted runtime database role. It required the exact live v1
schema/ACL/owner fingerprint, exported one PostgreSQL snapshot to a private
temporary custom archive, and compared ordered row digests for all three
tables against a disposable PostgreSQL 16 restore. The restored database
passed exact v1 audit and the isolated v2 constraint postimage audit. On
September 29 the result was `qualified_disposable_restore`: 10 action events,
4 message receipts and 4 mode events, with all three row digests equal. The
source transaction was read-only; the disposable container and temporary
archive were removed and their absence verified. This is recovery-path
evidence, **not** a retained rollback backup or a full household v3 bundle.

This is **not ready for household application**. The installed v4 trainer and
publisher still use the legacy model contract. Their old exact schema-audit
command would reject a v2 journal, but a later live-unit inspection confirmed
that neither service runs that command as a startup preflight. This is not
proof that a v2 migration would stop both services; the substantive legacy
support-counter defect and remaining compatibility checks are recorded below.
Before live migration, qualify a coordinated runtime/reader upgrade and
rollback, a retained private full **household** v3 backup containing the journal
and SQLite/config state, and an attended maintenance window. The exact
production owner/role preflight and disposable household-journal restore have
passed but must be repeated immediately before a cutover. Only
then enable the migration under specific authorization. Keep the v2
confirmation sender and ingress gated until their own genuine signed
question/reply, durable-storage and recovery checks pass. Legacy `vent` rows
must never be recoded as window or skylight observations, and neither new
state may silently feed legacy `vent_open` model forcing.

The September 29 runtime trace confirms a second compatibility dependency:
`ActionJournal.effective_events` reads all action kinds, but
`dataset._project_actions` currently projects only legacy `vent` and shade
fields into `ThermalSample`. Merely accepting the v2 schema fingerprint would
therefore leave window/skylight rows unused by training. The coordinated model
upgrade must preserve distinct airflow inputs and their provenance through
dataset, dynamics, evaluation and forecast construction. Independent state
collection can prepare that evidence, but cannot be reported as learned
window/skylight effects while this legacy model path is in use.

The source dataset now restricts `confirmed_action_rows` to the legacy action
kinds actually consumed by the current model. Previously, a confirmed window
or skylight event could add a row to that qualification counter despite having
no model forcing field. Regression checks avoid inferring a vent label and
show that a new airflow event cannot add
confirmed-action support even when other legacy states are fully labeled.
Supported vent confirmations still count. This source correction enabled no
v2 collector gate. At this earlier checkpoint it had not been
copied into the installed v4 runtime; the deployment below closes that gap.

## Source-only split-airflow dataset and identification seed

`thermal_model/airflow.py` now provides an explicit alternative dataset path:
`build_airflow_samples` retains independent `window_open` and `skylight_open`
values, confidence, event ID and source. An absent state remains unknown.
Legacy vent labels and seasonal vent reconstruction do not supply either
state; the v2 sample's legacy `vent_open` is deliberately absent. Shade,
temperature, radiation and exceptional-heat exclusions retain the existing
dataset quality construction. The versioned manifest binds the distinct
sample fields in its canonical digest and reports known/unknown state counts.
It cannot supply the legacy confirmed-action promotion counter.

The same module implements a **five-minute identification seed**, not a
replacement for the accepted multihorizon trainer. It fits independent window
and skylight exchange coefficients plus a joint-opening interaction, alongside
envelope, mass and solar terms. It requires full-rank independent variation;
identical window/skylight histories cannot identify two separate effects.
Unknown openings, zero-confidence labels, nonconsecutive pairs and exceptional
heat cannot fit. Positive bounded exchange and ordered shade gains are
required, with a combined-opening exchange cap, spectral checks for all four
opening combinations and the corresponding 72-hour bounded simulations.

The split simulator consumes explicit window/skylight states at consecutive
timezone-aware five-minute timestamps. It does not recode them as legacy vent
forcing. The legacy fitter, endpoint builder, predictor and simulator now
explicitly refuse split-airflow sample fields, preventing accidental silent
omission or use of the wrong model family. The ordinary legacy sample/output
contracts remain unchanged.

Twenty-one new offline tests retain independent labels and their provenance,
recover all known coefficients from synthetic transitions, distinguish each
opening and the joint effect, reverse heat-transfer direction with outdoor
temperature, reject unknown/invalid/collinear states and refuse cross-version
model use. The existing dataset/dynamics suites passed 101 tests, and the
pipeline, evaluation, behavior and artifact suites passed 287 tests. None of
these synthetic tests establishes household causal effects, a forecast
improvement or sufficient state variation in the real journal.

This source candidate was **not installed**. The installed optimized dynamics
remain SHA-256 `2850ce20b4df5d39866dcead43f809c81b7501153af2f6d7377b9931e65a393c`;
the September 30 06:50 trainer is still the natural gate for that previously
installed optimization. `airflow.py` is not yet included in the accepted
runtime manifest or artifact loader, and no v2 household journal migration,
question, listener, label collection or control activation occurred.

At this seed-only checkpoint, remaining coordinated work was substantive:
extend the multihorizon objective
and fold-only identifiability/held-out-forcing gates to the split feature map;
version the artifact, runtime manifest and forcing captures; preserve
origin-time knowledge in independent baseline/candidate schedules and output
markers; qualify as-issued forecasting and genuine signed observations; then
rehearse the complete household backup/upgrade/rollback before live release.
The seed is only the initial fitting component of that work, not a substitute
for it or a reason to graduate the model from shadow.
The following checkpoint implements the source objective and diagnostic-fold
part, without releasing the accepted trainer or operational forecasting path.

## Source-only multihorizon fit and retrospective fold

`airflow_training.py` now refines the split-airflow seed against open-loop air
and mass endpoints at 5 minutes, 1, 6, 12 and 24 hours. It retains independent
window, skylight and joint-opening terms. Every horizon requires at least two
daily origins, uniformly capped at 64 across the available training range.
Unknown states, exceptional heat, zero-confidence labels and nonconsecutive
prefixes cannot contribute. Bounded coefficients, ordered shade gains,
combined-opening exchange, sensitivity rank, final physics and a nonincreasing
objective are checked; an optimizer success flag alone does not qualify a fit.

Fold fitting may explicitly keep **exactly zero** action-feature columns
inactive, rather than inventing an identified effect. A corresponding held-out
activation is withheld. Nonzero but collinear window/skylight histories still
refuse identification. This lets a closed-skylight training fold be described
honestly without authorizing prediction of an unlearned open-skylight effect.

The optional dataset `known_by` cutoff excludes later-received action/mode
confirmations and later timestamped temperature/radiation points before
projection. It cannot prove the journal's storage commit time; the operational
as-of reader must separately enforce `created_at`. The retrospective evaluator
accepts one explicit origin and an independently rebuilt prior-training reader,
requires fourteen days of prior time span, refuses origin/future training rows,
and compares the model with same-origin persistence at complete 1–72 hour
targets. It simulates the longest eligible prefix once and reuses shorter
targets. A later missing/unknown state withholds only horizons crossing it.

Its report is explicitly `observed_held_out_not_as_issued` and
`promotion_eligible: false`: it uses observed future weather/action forcing to
diagnose physical dynamics. Neither temperature chronology nor a received-time
cutoff turns this into a qualified as-issued forecast or proof of journal
commit-time availability. The true forecast/capture integration remains open.

The recurrence batches daily origins, caches coefficient-independent forcing
features, and retains only the latest optimizer value/Jacobian cache entry.
An 18-day synthetic benchmark had 19 daily origins at the four shorter
horizons and 18 at 24 hours. Retained prepared arrays occupied 537,720 bytes.
Three batched loss-plus-analytic-gradient calls took 0.010386, 0.010182 and
0.010135 seconds, versus 0.068873, 0.068686 and 0.068455 seconds for equivalent
scalar recurrences using the same prepared forcings. The loss difference was
`6.94e-18`; the maximum gradient difference was `1.36e-12`. This is roughly
6.7× for **one objective/gradient evaluation**, not a household whole-trainer,
peak-memory, swap or predictive-skill claim.

The 24 added multihorizon/fold tests and 21 existing split-airflow tests pass,
along with the affected legacy dataset/dynamics/evaluation tests (168 total).
Checks include centered finite-difference gradients, independent scalar
simulation, reduced synthetic long-horizon drift, deterministic fits, bounded
origin sampling, inactive-feature handling, malformed optimizer results,
nonfinite evidence, worse-objective refusal, received-time cutoffs and held-out
mutation isolation. No household data was relabeled or used to fit this
candidate, no runtime file was installed, and no collector or control gate
changed. The next release work is the versioned artifact/runtime/forcing-capture
contract and origin-aware forecast construction, plus the coordinated
household journal/backup/reader transition. Observational evidence collection
and eventual model graduation remain distinct gates.

## Source-only origin-aware artifact and replay

`airflow_artifact.py` defines a separate, closed
`earthship-split-airflow-shadow-artifact/v1` candidate. It does not write the
accepted artifact or its pointer. Its runtime digest covers the existing
thermal dependency closure plus the split-airflow and origin-reader modules
(28 files), and exact Python/NumPy/SciPy versions. It refuses hashing a
different installed tree or mixing imported module roots. The fitter records
that revision and the canonical training-row digest, checks both again after
optimization, and artifact construction requires those exact identities.
Sensor mappings, quality/count vocabularies, independent state counts,
objective evidence, bounded daily origins and physical dynamics are validated.
The candidate always declares `shadow_candidate` and `control_enabled: false`.

`airflow_forecast.py` now consumes origin-qualified archived hourly weather,
three current source receipts and the separate v2 journal snapshot. Forecasts
must have complete hourly brackets and have been issued and captured by the
origin, within the existing six-hour issue-age limit. Weather is interpolated
to five-minute endpoints before the existing normalized solar calculation.
Windows, skylights and both shade states must be independently known; legacy
vent state cannot substitute. Passive scenarios require a confirmed Kiva-off
state and the same two-hour cooldown used by dataset construction. Unidentified
inactive forcing cannot be activated by a forecast.

The mass state is initialized by a causal exponential observer over 24 hours
of complete, receipt-qualified north-wall readings. Its five-minute step and
120-minute time constant match dataset construction, with an explicitly bounded
24-hour initialization window. The raw north-wall endpoint remains separately
visible and must equal the current north-wall receipt; it is not mislabeled as
latent mass. Neither later sensor observations nor later journal storage may
enter the origin inputs. Artifacts created after the origin or trained more
than 26 hours before it are refused.

The forecast explicitly labels its action assumption
`qualified_origin_states_held_not_future_confirmation`: holding an observed
state is a scenario assumption, not a promise of future operator behavior or
a learned behavioral schedule. It returns a bounded, data-only capture of the
exact artifact, weather, actions, source receipts, observer history and output.
Canonical JSON round trips replay the exact trajectory at 1–72 hours. Replay
checks the capture digest, revalidates every input and requires exact output
agreement, including when a modified payload has a recomputed transport digest.
The archive's `rows_sha256` binds original per-metric capture times, which are
not exposed by its projected weather rows; this module validates its format
and retains it, rather than claiming to reconstruct that source digest.

All 56 new offline origin/artifact/replay checks pass. They include independent
observer and first-step equations, distinct window/skylight trajectories,
exact-hour and fractional-hour origins, maximum-length capture/replay, missing
or unqualified actions, Kiva cooldown, history gaps, stale/late source evidence,
inactive-feature activation, code/data changes during fitting, training-data
substitution and transport/output tampering. Synthetic reader fixtures do not
qualify household source readers, real signed labels or actual forecast skill.
The final affected suite passed **538 tests in 74.61 seconds**, including
legacy dataset, dynamics, evaluation, pipeline, behavior, artifact, archived
weather/action/temperature readers, operational origins and forcing captures.

This checkpoint performs **no production installation, journal migration,
capture-file retention, Item publication, DM, listener or control activation**.
The accepted trainer/publisher still use their installed legacy contract.
Remaining release work includes coordinated journal/reader/runtime recovery,
private retained household backup and policy/routes, genuine signed collection,
durable operational capture and qualified same-origin candidate/baseline outcome
comparison. Collection can prepare honest separate state evidence while the
model remains in shadow; eventual graduation still requires actual skill.

## Installed legacy support-counter correction

A fresh live-unit inspection found no `ExecStartPre` schema audit on either
thermal service. The legacy `schema-audit` CLI still requires the exact v1
fingerprint; do not confuse that manual-command incompatibility with the
actual startup path. More importantly, the installed dataset's counter had
not yet received the source guard for action kinds actually modeled.

The new read-only `scripts/verify-thermal-legacy-action-support.py` reproduced
that installed defect with synthetic states: four supported legacy states at
one bucket supplied one support row, and adding independently named window
and skylight observations incorrectly raised it to three. Those unsupported
observations alone supplied two support rows despite no vent forcing. The
corrected source supplied counts 1, 1 and 0. Both versions produced exactly
the same legacy sample digest
`02e9eeca0f27f879a4da82177e69294afd72e5ae0a2d43b4d61e851f692aab49`.
These are fixture counts, not additional household observations.

Under idle-service checks and briefly paused thermal timers, only installed
`thermal_model/dataset.py` was atomically replaced. Exact preimage SHA-256 was
`111beb36aadf52943b40e50ba5df5cc4b0792b01e8ce5302f6c5bdcb6c2cbc5d`;
postimage is `075aa4920735e3aa3c233356ea48494425ed3391aa4db6f474b5386339e52696`.
The diff imports the supported action vocabulary and restricts the promotion
counter to it, and extracts the unchanged two-hour Kiva cooldown constant.
The private rollback copy is at
`/home/sat/.local/state/openhab-config-migration/thermal-dataset-support-kV18U9CU/dataset.py`.
Timers recovered active; no OpenHAB restart or control change occurred.

Installed runtime revision is now
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`.
Dynamics remain exactly
`2850ce20b4df5d39866dcead43f809c81b7501153af2f6d7377b9931e65a393c`.
The accepted artifact bytes remained
`4315cc86d03b94d7f82d99539201acc42e74973a9806546844966ceea872304f`,
with training revision `00611a5ef1e5b64347143b3dc04b423d519f7ccbd7bc237bd029b69b7ef2cd5a`.
The verifier used direct payload validation, not registry loading/recovery,
so it could not quarantine, restore or rewrite that artifact.

The next natural shadow job ran September 29 22:29:47–22:29:50 MDT and
succeeded. Its decision at `2026-09-30T04:29:48.888588+00:00` matched the live
Item, exactly one JDBC receipt, and the existing private forcing capture.
Publication SHA-256 is
`ff12b7a0214005ffaed44e73e86a136f66e7f5cb07b1a3fd760048c4a498eada`.
Exact as-issued replay passed under the new explicit installed runtime pin;
the older artifact training revision was retained, not relabeled as current.
All 43 verifier/dataset regressions passed, following the prior 538 affected
thermal tests. The next daily trainer remains September 30 06:50 MDT.

This deployment corrects promotion bookkeeping without recoding legacy vents
or interpreting windows/skylights as their forcing. It does not migrate the
journal or enable collection. Actual v2 journal/reader coexistence, retained
household backup, reviewed private policy/routes and signed confirmation trial
remain release work. The operator explicitly deferred off-host backups; that
deferred destination is not a request to repeatedly ask for one during this
same-host qualification. No off-host copy was performed.

## Household-copy installed-consumer coexistence qualification

`qualify-thermal-journal-live-restore.py` now optionally accepts
`--consumer-runtime` together with a full `--expected-consumer-revision` pin.
It still exports production using the restricted role in a read-only
repeatable-read transaction, restores into an owned disposable PostgreSQL 16
container, compares all original ordered table digests, audits exact v1 and
then rehearses the exact v2 constraint postimage. Only after those steps does
it add six explicitly labeled fixture observations to the **disposable**
journal: supported legacy states plus independently named window/skylight
states. Their times precede the earliest restored action/mode so a fixture
window cannot accidentally borrow household context.

The separate `verify-thermal-restored-consumer.py` runs in a fresh process
using the selected installed module tree and exact code revision. Its
connection refuses production port/database names and non-loopback hosts,
requires startup read-only mode and the restricted runtime role, and checks
both against PostgreSQL before invoking the installed `ActionJournal` reader.
All six independent observations must survive that reader. The installed
dataset must preserve exact legacy samples and retain exactly one supported
action bucket, not three. The runtime pin is rechecked afterward. No registry
recovery, model training, shadow publication, relay or actuator is invoked.

The September 29 household-copy trial ran under a private transient user unit
and completed in 2.232 seconds. Production writes were **zero**. Original
10 action rows, 4 receipt rows and 4 mode rows restored with equal digests;
both schema stages passed. Installed revision
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`
passed the role/read-only checks, retained all six fixture observations, left
legacy samples unchanged, and reported one supported bucket. The disposable
fixture sample digest was
`9297230d3cf6cd0e9b704527418d795cb1292ded0a35a7a7fda1c3c29308405a`.
Its value depends on the fixture dates selected from this particular restore;
it is not a household dataset digest or learned thermal effect.

All 62 affected consumer/migration/journal/action-history/origin tests passed.
Negative tests refuse production or writable connection arguments before
connecting. The owned test/restore containers were removed and their absence
verified; the temporary custom archive was removed. No private household
backup was retained by this disposable trial.

This closes the tested installed legacy-reader/support-counter coexistence
gate on a real household restore. It does not turn the legacy model into a
window/skylight model, qualify signed state labels, enable the source v2
as-of reader, migrate production, or graduate shadow predictions. Independent
observational collection may coexist with the legacy shadow model once its
own retained-backup, private configuration, exact migration and signed-trial
gates pass; it need not wait for eventual predictive skill. The next concrete
release work is preparing that retained same-host rollback bundle and reviewed
private route/question policy, followed by an authorized journal cutover and
genuine signed operator reply. Off-host backup remains explicitly deferred.

## Retained same-host journal anchor and signed-route snapshot

The household qualifier's optional `--retain-dir` now copies the exact private
custom archive into a **new** private recovery directory, refuses an existing
destination, checks structure/digest equality, and publishes its manifest only
after successful disposable restore/consumer checks and owned-container cleanup.
The manifest explicitly says `thermal_intel_journal_only_recovery`,
`full_collector_bundle: false` and `off_host_copy: false`. This is not a substitute
for the collector's paired SQLite/config/journal bundle or signing authority.
Public parents, existing recovery points and changed archives are refused.
Failures cannot silently overwrite a prior recovery point or be presented as
a completed backup; a newly retained partial directory is reported for inspection.

On September 29 a fresh read-only export observed at
`2026-09-30T05:00:56.595427+00:00` retained the verified 10-action/4-receipt/4-mode
preimage at
`/home/sat/.local/state/thermal-intel/journal-recovery/2026-09-29-pre-v2`.
Its 37,856-byte `journal.dump` SHA-256 is
`0ee00415d660e476ba26f42d54848bf172aa3b28f5dce8a17d05a508614ae4f3`.
The dump and manifest are owned by sat with mode 0600 under a mode-0700
directory. A separate read rechecked private permissions, archive structure
and manifest/file digest agreement. The disposable v1/v2 and installed-consumer
checks passed again, and owned containers/temporary archives were removed.
All 65 affected journal/consumer tests pass. No production journal write occurred.

The current Hex sender also passed the real pinned-nak configured-keyer
sign/encrypt/decrypt self-roundtrip under its existing private environment.
This was local and published no event: it is not an operator DM receipt or
signed state label. `bunker_verified: false` is expected for Hex's current
local sender key; the separate verified operator bunker is not being substituted
as Hex's identity. The operator's choice to retain Hex's current npub remains
unchanged. No key or client credential was printed or committed.

Fresh public queries returned the approved Hex and operator kind-10050 events
on nos.lol and Damus with exact authors, signatures and the three approved
relay tags. Primal failed both initial reads and one bounded retry (exit 3,
zero event lines); that is a query failure, not proof that an event is absent.
No announcement was republished and no relay route was changed.

`scripts/prepare-thermal-route-snapshot.py` now reads **only** those two frozen,
previously approved event IDs, verifies them with the actual pinned keyer and
`Routes` contract, and optionally saves a new private snapshot without signing,
publishing or overwriting a file. Bounded source failover does not change the
approved destination relay lists or claim universal availability/completeness.
All seven offline artifact/permission/failover tests pass; their verifier is
explicitly a fixture double, unlike the real snapshot verification below.

The real snapshot was read from nos.lol and saved at
`/home/sat/.local/state/thermal-intel/collector-config/routes.json`, mode 0600
under a private directory. Exact file SHA-256 is
`5860ad656eef83f603f470cfc1d673d7666daef32e1579ef2bc5456f6a897604`.
It contains Hex event `f75b3a5fd8fc5a6734af6cee3a4c5a64009e86bc0efd57e6926b9ec434a16c84`
and operator event `defe6a8571ae87261278bcae968f88d821e304930e7fad5e7e486f46e1fb20d2`.
It is an approved frozen signed inventory, not a new private question policy.

Migration, v2 writer, ingress, delivery, polling and v2 as-of reader release
flags were all rechecked false. No collector state was initialized, state
question sent, journal migrated, hardware commanded or model graduated. The
next remaining bundle components are a reviewed private question policy and
the collector's baseline SQLite pair; then capture/rehearse the complete
same-host bundle while independent journal writers are quiescent. The pending
chat question only chooses a truthful trial question, never a training label.
Production cutover and a genuinely signed operator reply remain separate gates.

## Inactive five-component baseline recovery

The subsequent same-host rehearsal completed successfully, without a production
journal write or relay publication. `scripts/prepare-thermal-collector-baseline.py`
created a new private empty SQLite pair and `policy.proposed.json`; it refuses
existing destinations, an operational policy filename or any open release gate.
The window-open/skylight-closed values are only a question proposal based on the
earlier chat report. They are **not** confirmed actions, signed labels or an
approved sending policy. The sole proposed reply author remains the approved
operator; Sat's NIP-46 client key is not substituted for that identity.

The proposal at
`/home/sat/.local/state/thermal-intel/collector-config/policy.proposed.json`
has SHA-256 `63c226f2895b3ebba8a1868c05717f33eb6fc36aa9a299091a397d4ca79daf99`.
Its question ID is
`6c0d64817c5bd21275d2dad0f7378612c8b466ccff2e00ddf7e4a205c463b8de`
and it expires at `2026-10-02T05:21:20.208228+00:00`. No operational
`policy.json` was installed. The copied filename within the recovery archive is
the backup format's `policy.json`, not permission to use that proposal for sending.

`scripts/qualify-thermal-collector-baseline-bundle.py` exported a fresh
read-only household PostgreSQL snapshot while holding the inactive collector's
state lock. It checked zero **other sessions using the journal runtime role**;
this is not proof that unrelated database-owner processes were stopped.
Source and restored ordered journal digests match for all 10 actions, four
receipts and four modes. The private retained bundle is
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-09-29-proposed-baseline`.
Its v3 manifest independently verifies five files: the journal dump, two SQLite
databases, proposed-policy bytes and approved signed-route snapshot. Private
permissions and exact configuration equality passed, as did public route
signature checks with the actual pinned nak.

The disposable restore passed exact v1 and v2 journal audits and the installed
legacy consumer under revision
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`.
Both copied SQLite databases passed integrity/version checks and reopened
through `Spool`/`Outbox` with all six business tables empty. Owned Docker and
temporary SQLite resources were removed. The qualification receipt explicitly
records `policy_reviewed`, `sending_policy`, `signed_trial_verified`,
`operational_ready` and `collector_activated` as false, with zero production
writes and no off-host copy. All 96 affected tests pass, including a real
PostgreSQL full-bundle regression; its synthetic route verifier is explicitly
a fixture double, unlike the household run.

This closes the inactive household baseline recovery rehearsal. A reviewed,
truthful, unexpired sending policy, exact authorized production journal cutover,
genuine operator-signed confirmation and subsequent bounded user-service
qualification remain open. The accepted thermal model and its timers were not
changed. Off-host recovery remains explicitly deferred by the operator.

## September 30 current-runtime coexistence refresh

The installed consumer has since advanced to
`0864f4d6e231be78ae554e94634c161f5d927e185a94a908893f58b87bd31c68`.
After verifying that both thermal services were inactive, the same disposable
household-copy qualification was rerun under that exact pin through transient
user unit `thermal-journal-coexistence-20260930-current`. Invocation ID:
`b25b3dcabbc8437fbf678801317f0983`.

It exited zero in 2.408 seconds with `status=qualified_disposable_restore` and
**zero production writes**. The original 10 action, 4 receipt and 4 mode rows
restored with identical ordered digests; exact v1 and disposable v2 postimage
audits passed. The installed consumer verified its read-only connection and
runtime role, retained all six independent synthetic fixture observations,
left legacy samples unchanged and counted one supported bucket. Fixture sample
digest remained
`9297230d3cf6cd0e9b704527418d795cb1292ded0a35a7a7fda1c3c29308405a`.

The script removed its owned container and temporary archive; independent
container-list and collected-unit checks confirmed no remaining restore
resource. No new recovery bundle was retained; the earlier private baseline
remains the rollback anchor and still needs a fresh digest comparison before
any authorized apply. This refresh qualifies current-runtime coexistence only.
Production migration, reviewed sending policy, genuine signed confirmation and
collector/service release gates remain separate and unchanged.

## Proposed attended production journal cutover

The next requested authorization is **only** the journal vocabulary cutover,
not collector activation or approval of the staged question. The existing
private `/home/sat/.config/hex/thermal-admin.env` provides working owner access
through a user-level transient unit; passwordless PostgreSQL peer sudo is not
available and is not required. A fresh read-only check verified the exact
v1 fingerprint, the owner identity and zero window/skylight rows. Two non-owner
roles can insert, so the configured runtime role must be bound explicitly (or
uniquely by the exact audited fingerprint), not inferred from a single-writer
assumption. No credential or database diagnostic was printed.

For an explicitly authorized attended apply:

1. Recheck the installed consumer revision and all collector release gates;
   do not run while a thermal job or independent journal writer is active.
   Verify the retained full baseline and compare its ordered journal digests
   with a fresh read-only source snapshot. If source rows changed, retain and
   rehearse a new uniquely named baseline first; never overwrite this one.
2. Use the existing owner connection, distinct restricted runtime role and
   tested `airflow_migration.migrate_v2` in one owner transaction. Authorize
   only that adapter's process-local migration gate; leave persistent source
   flags and all collector/model gates unchanged. The adapter requires the
   exact v1 preimage, uses a three-second lock timeout and 15-second statement
   timeout, and replaces only `action_events_action_check` with the qualified
   v2 vocabulary. A failed postimage audit rolls back the transaction.
3. Require exact v2 postimage fingerprint
   `f3e09cdd6cbd82bcd34475485bbf326bbc4789f4bcb1f4e050d9fba213378790`,
   unchanged ordered digests of all existing rows, unchanged grants and the
   pinned installed consumer. The accepted artifact, Items, timers and
   hardware controls must remain untouched. Retain a sanitized private receipt.
4. If post-commit verification fails, keep collection off. Before reverting
   only the action constraint in an owner transaction, require no new
   window/skylight rows, unchanged original row digests and the exact v2
   preimage; audit the exact v1 postimage before commit. Do not restore a whole
   dump over newer observations or delete v2 labels to force rollback. If any
   new data exists, stop and preserve it for an explicit recovery decision.

At this proposed checkpoint, the exact journal-only apply still needed operator
approval. It has since been approved and completed as recorded below. After it passes,
truthful question review, qualified sender/ingress deployment and a genuine
operator-signed reply/acknowledgement remain separate steps. No unattended
poller or automatic hardware action is included in this plan.

## September 30 four-stream-reader consumer refresh

The installed weather readers' four-stream follow-through changes the consumer
pin to `5e69e9410a7aa5d5ff41dd7339467d33d9add3b6a7b949bcc6e1052d229aa87b`.
The earlier `0864f4d6...` consumer receipt is historical. The household-copy
rehearsal was rerun under that exact new pin using transient user unit
`earthship-thermal-reader-recovery-20260930`; invocation ID
`7ff3c9fba3dd49539d5150b8f07fcc71`.

It exited zero in 3.906 seconds, reporting `qualified_disposable_restore`,
matching ordered row digests and zero production writes. The original
10 action/4 receipt/4 mode rows restored exactly; v1 and disposable v2 audits
passed. The installed consumer verified its read-only runtime role, retained
six explicitly synthetic independent observations, left legacy samples
unchanged and counted one supported bucket. Fixture digest remains
`9297230d3cf6cd0e9b704527418d795cb1292ded0a35a7a7fda1c3c29308405a`.

The owned `thermal-live-restore-*` container and temporary files were removed;
a fresh container lookup is empty and the transient unit is collected
(`LoadState=not-found`). This remains a disposable journal-only coexistence
check, not a new full rollback anchor, production DDL or signed action truth.
The existing private baseline must be compared with current digests before
any apply. Journal-only approval has now been requested; all six source release
flags remain false. No listener, question, model or control was activated.

## September 30 approved production journal-only migration

The operator explicitly approved the journal-only action-vocabulary change.
The guarded `scripts/apply-thermal-journal-v2.py` adapter validates the retained
full five-component baseline, the exact installed consumer pin and inactive
training/shadow jobs, and compares every ordered journal-table digest with the
retained qualification. A transaction guard locks only the three journal tables
and checks their digests both before the DDL and after the exact postimage audit,
**before commit**. A mismatch or guard failure rolls back the same transaction.
No Item, policy, credential, collector code pointer or protected rule is changed.

The initial read-only preflight conservatively counted all ten unrelated
`postgres` sessions as potential writers because superusers can write every
table. No DDL occurred. The corrected preflight requires dedicated journal
runtime/owner sessions and active journal queries to be quiescent; journal
table locks and exact in-transaction digests protect against concurrent writes
without interrupting unrelated JDBC persistence. The qualified preflight at
`2026-09-30T23:52:16.760602Z` found exact v1 and unchanged baseline rows.

Fourteen disposable PostgreSQL tests pass, including the new locked guard,
refusal of changed baseline rows, and a deliberate post-DDL guard failure that
restores exact v1 atomically. All owned test containers were removed.

The approved apply ran through user transient unit
`thermal-journal-v2-approved-apply-20260930`, invocation
`e254a82adebe47dcb03bfa428c583431`, at `2026-09-30T23:53:52.489437Z`.
It exited zero in 609 ms with `status=migrated_v2`. Exact postimage:
`f3e09cdd6cbd82bcd34475485bbf326bbc4789f4bcb1f4e050d9fba213378790`.
The only production DDL replaced `action_events_action_check` to include
`window` and `skylight`; the fingerprint covers unchanged owners, ACLs and
other schema objects.

Unchanged original table proofs:

| Table | Rows | Ordered SHA-256 |
| --- | ---: | --- |
| action_events | 10 | `7006a6beab68bca825a0cc787119b709a137198d4e9fd1be0f5c6f0bf46a0ad3` |
| message_receipts | 4 | `056d846d36b18745fe9da23d3552322af2301ffe3097c078690d39ebfc4a3309` |
| mode_events | 4 | `73f4a3a3445d91047886524f3a1a8cf040d526bac94af025c86a340c0642d966` |

Independent fresh post-commit readback confirms exact v2, all three matching
digests, **zero window/skylight rows**, unchanged installed consumer pin and
all six source release flags still false. A real installed-runtime read-only
`ActionJournal` call successfully reads the current effective history (two
action events and one mode event). Its first verification attempt supplied an
unsupported source-candidate `as_of` argument to the older installed API; the
correct installed signature passed without any runtime or data modification.
The legacy standalone v1 `schema-audit` command is not a v2 audit; use the exact
v2 audit adapter for this postimage rather than weakening its old fingerprint.

The retained v1 baseline remains intact at
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-09-29-proposed-baseline`.
If rollback becomes necessary, require exact v2, no added airflow rows and
unchanged original digests before restoring only the old CHECK in an owner
transaction. Never restore the entire dump over newer records or delete labels.
The transient apply/verification units are collected and no test containers
remain. No credential, DSN or row contents were printed or committed.

**This closes production journal vocabulary migration only.** The collector
is still off. A reviewed truthful question, qualified sender/ingress trial,
genuine operator-signed reply/acknowledgement and bounded service activation
remain. Model graduation and hardware automation are separate evidence gates.

## September 30 post-v2 recovery under the current runtime

The journal recovery checker now takes an explicit `--source-schema v2` after
the approved cutover. Its default remains exact v1 for older pre-cutover
workflows. There is no automatic schema detection, relaxed fingerprint or
production re-migration. The selected source fingerprint is checked inside
the same read-only repeatable-read transaction as export, under ACCESS SHARE
table locks that prevent concurrent DDL but permit ordinary inserts. The
disposable restore must match that selected schema exactly; a restored v2
journal is audited directly, not passed through the v1 constraint change.

The full five-component **inactive baseline** checker accepts the same explicit
selection, retains its closed-gate/empty-state/proposed-policy checks and records
the actual exported schema in its qualification receipt. Both source tools
retain default-v1 behavior for their existing callers. The future reviewed
trial bundle must use v2; the old retained v1 bundle is not overwritten or
relabelled. Disposable PostgreSQL containers are now capped at one CPU / 512
MiB, with no swap allowance beyond that memory limit.

**47 affected tests pass**, including real v1/v2 journal exports/restores,
both wrong-version refusals before constraint DDL, non-disposable-target
refusal before running `pg_restore`, and complete five-file restores from both
vocabularies with window observations preserved. These full-bundle regression
tests use synthetic routes and a verifier double, not an operator-signed trial.

The actual household **journal-only** replay ran through transient user unit
`earthship-journal-post-v2-recovery-20260930`, invocation
`9d42928234a9418d8e57592f0a0faed4`. The exported source snapshot was observed at
`2026-10-01T00:25:09.954209Z` (September 30 18:25 MDT). It exited zero in 2.054
seconds, restoring exact v2 with identical ordered digests for all original
10 actions / 4 receipts / 4 modes and **zero production writes**.

The real installed consumer
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`
verified its restricted read-only connection, retained all six independently
named disposable observations and left legacy samples/support unchanged.
Fixture sample digest remains
`9297230d3cf6cd0e9b704527418d795cb1292ded0a35a7a7fda1c3c29308405a`.
Those fixture rows exist only in the removed disposable database, not in the
household journal or training truth.

The new intentional same-host recovery anchor is
`/home/sat/.local/state/thermal-intel/journal-recovery/2026-09-30-post-v2-7f57eb3f`.
Its 37,924-byte custom archive SHA-256 is
`1fafec190a7200c213603b531e8e8082dfc6e689dbdbe86d547d5bd4ea36fe06`.
The owned 0700 directory contains only the owned 0600 journal dump/manifest;
the manifest explicitly identifies v2, current consumer, journal-only scope,
`full_collector_bundle: false` and no off-host copy. A separate fresh source
read independently verified permissions, archive structure/digest and all
three table proofs against both this anchor and the original v1 baseline.
Owned test/restore containers, temporary exports and transient units were
removed. Both journal-only v1/v2 anchors and the earlier full baseline are
intentionally retained.

This closes the **current-pin post-v2 journal recovery/coexistence check**, not
the truthful-policy or signed collection trial. The full household v3 baseline
is still the prior, explicitly unsent v1 proposal. Before collection, rehearse
the full v2 bundle with the reviewed question/configuration that will actually
be used. No operational policy, collector, model, hardware control, training
job or timer was activated by these checks.
