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
publisher still use the v1 journal/runtime contract. After a production v2
schema change, their old exact schema-audit command would reject the journal.
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
Supported vent confirmations still count. This source correction has not been
copied into the installed v4 runtime or enabled any v2 collector gate.

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
