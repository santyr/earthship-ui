# Window/skylight journal vocabulary: isolated v2 candidate

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
