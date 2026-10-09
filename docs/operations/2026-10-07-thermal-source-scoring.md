# Source-bound thermal scoring

`score_qualified_origin` reads an owned immutable origin-capture archive and
requires its output to match the original persisted `Thermal_Model_JSON`
publication. The native outcome must match the selected actual trajectory target,
have original receipt/storage/expiry metadata, be mature, and retain the original
indoor sensor epoch.

The recent-cycle comparison is recomputed from seven earlier qualified native
cycles using the original issue clock and the existing local-clock policy.
Future, duplicate, missing, late-stored or epoch-incompatible receipts refuse.
Revised weather, later origin values and supplied error summaries are not used.

The versioned source-scored pair binds the original capture, publication,
outcome receipt, comparator grid and comparator evidence hashes. It preserves
artifact identity, publication-runtime identity, sensor epochs and as-issued
thermal regime. These raw source references must remain available; the scored
summary is a derived cache.

Unknown actions remain null. Missing action labels do not invalidate an otherwise
qualified temperature forecast pair, but this scorer claims no causal action
response qualification or release authority. It cannot activate forecasts,
recommend actions, change Items, write journal labels or fit a model.

Twelve source-boundary tests passed in 11.50 seconds under the strict local
CPU/memory limits. They include changed persisted output, future publication,
wrong target, late-stored outcome, epoch changes, incomplete/duplicate/future
comparator receipts and forecast evidence with no action labels. Full suites run
remotely in CI. No production writer, service or model was changed.

Immutable policy registration and the combined source/fit/statistical release
assessment remain subsequent work. Legacy v2 captures are not upgraded by this
scorer; only the explicit new original-input contract is accepted.

## Retained raw native query packets

`weather_temperature_sources` provides `fetch_temperature_source`,
`write_temperature_source`, `read_temperature_source` and
`replay_temperature_source`. A versioned
`earthship-native-temperature-query-sources/v1` packet retains the explicit
stream/policy/hardware phase, original target and assessment clocks, bounded
query window and unchanged timestamped raw JDBC snapshots, including NULL
barriers and the original carry row. Receipt selection is recomputed by the
existing native-v2 reader. Selected receipt summaries are not accepted as packet
inputs. No credential, error scalar or release authorization is stored.

The fetch validates the request before connecting, then uses one bounded
read-only repeatable-read transaction. Archive files are immutable, canonical,
digest-addressed, owned private files in a private directory. Packet bounds are
289 targets over at most one elapsed day, 10000 original rows and 8 MiB.

The candidate `ScoreReader.native` now retains each bounded query packet,
reads it back from its immutable archive and returns only replayed selection.
It verifies source configuration before querying, after querying and after
readback. Comparator requests are split into endpoint queries: each retains
its policy-validity window and the original carry row rather than snapshots
across the interval between endpoints. Each query still uses a dedicated
read-only stable transaction and the same original assessment/phase.
Identical endpoint/assessment/phase requests within one reader invocation reuse
the first immutable packet path, with fresh readback and selection replay.
Missing or changed cached source bytes refuse; no database fallback replaces
that original. `native_source_paths` records the retained files for the caller.
Seven complete cycles plus the outcome need at most 15 distinct endpoint
queries and two publication reads, within the existing 24-request budget.
The collector now writes a separate versioned
`earthship-installed-shade-score-sources/v2` packet when its backend retains raw
queries. It binds the unchanged original score inputs to the exact query paths,
original issue clock, phase and assessment. Each comparator query must use the
original issue assessment; the later outcome must be mature. Every selected
receipt must equal independent selection from the raw packet. The approved air
identity, range and expiry policy are required. Repeated identical endpoints
across adjacent 24-hour cycles are allowed; conflicting selections refuse.

`read_raw_score_sources(path, assessed_at=...)` validates private ownership,
outer digest, original publication capture and every raw query binding, then
recomputes the score. Missing or changed raw files refuse even when the scalar
score cache remains. At most 24 query paths and 64 MB of cumulative raw packet
bytes may be consumed per binding. The source binding grants no release
permission. Existing v1 diagnostic source packets remain distinct.

The new `earthship-installed-shade-qualification-report/v4` contract requires
these raw-source packets. `qualify_raw_published_installed_shade_candidate`
accepts original pairs only as `{"raw_score_sources_path": "/absolute/private/path"}`
references. It independently reads and replays the v2 archives, compares frozen
candidate/runtime/phase identity, rejects duplicate windows, and includes both
native binding and outer source-packet digests in the report. Its mandatory
`raw_native_score_sources` gate stays closed without those original pairs.
Numerical thresholds, independent support and uncertainty gates are unchanged.
Before numerical replay, v4 checks the complete reference inventory: at most
256 distinct original captures / 64 MB of capture bytes, 64 MB of score-header
bytes, and 8192 distinct raw query files / 128 MiB of raw packet bytes. Raw
packets are streamed rather than retained together in memory. A shared
60-second monotonic budget covers preflight, raw-query replay and scoring;
exceeding a limit refuses qualification. The enclosing process must still run
under the approved CPU, memory, swap, process and wall-time limits. Large
corpora need bounded query acquisition/reuse within these limits; supplied
cached scores cannot replace the raw replay to make a release pass.
Earlier report readers reject v4 instead of interpreting its new semantics.

Use `validate_raw_published_installed_shade_qualification_report`,
`render_raw_published_installed_shade_qualification_report` and
`write_raw_published_installed_shade_qualification_report` for this version.
Reports remain derived caches and cannot substitute for fresh source replay.
The new private reference schema `earthship-installed-shade-release-inputs/v2`
selects qualification v4 in the publisher's fresh preparation on each cycle.
Its fields remain `registration_path`, `candidate_path`, `runtime_bundle_path`
and `original_pairs_path`; the pair index contains raw archive references.
The runtime bundle must include the complete 63-file raw-profile closure and
match the executing code. A prepared raw profile rejects older reports before
reading a current origin. The live path writes a v4 report cache and rechecks
source, runtime and delivery freshness through the existing send guards.

The reference schema and qualification schema are versioned independently from
the public output. Mode, confidence, freshness, uncertainty and action authority
retain the existing publication-v4 meanings and validation. Reference v1 remains
an explicit earlier qualification path for compatibility; use reference v2 for
the new deployment. Neither profile accepts a supplied cached report or active
switch. The new profile has not been commissioned with a genuine frozen
candidate. Production activation and natural receipts remain unproven.
Existing selected-receipt score archives cannot
be retroactively described as retaining raw snapshots. Legacy v4 diagnostic
origins remain outside the candidate graduation contract.

## Shadow bootstrap before calibration

An uncalibrated candidate v1 can supply original shadow forecasts for calibration
when its native training fit gates pass and registration is explicitly absent.
This path does not require a calibration record. It still requires a verified
candidate, compatible executing runtime, qualified current inputs, and honest
shadow publication. A configured invalid registration is not equivalent to
absence and refuses bootstrap. Failed native fit gates refuse source preparation.

Freeze the valid uncalibrated candidate first, retain its exact as-issued shadow
forecasts, then collect naturally mature source-bound outcomes for calibration.
Freeze the calibrated candidate separately and preregister its release policy
before inspecting its untouched chronological holdout. Only fresh replay of the
qualified calibrated candidate's own evidence can authorize forecast-active mode.
Bootstrap fixtures and legacy diagnostic origins are not release evidence.

## One operational scoring job

`openhab/systemd/user/thermal-installed-score.service` is an inert template for
one explicit original publication and one horizon (1, 6, 12, or 24 hours). Render
its source/config/capture/horizon operands from reviewed private staging before
installation. The shared-lock operand must identify the existing owned private
lock used by the other input consumers. Never use a different lock to bypass a
busy worker. The service shares the input slice, caps CPU/memory/swap/tasks, and
has a hard process lifetime. Collection now requires the explicit `--shared-lock`
argument. The scorer opens an existing owned mode-600, single-link file with
no-follow flags, holds its descriptor, and checks path/inode identity before
source reads, including after request pacing. Missing, symlinked or replaced locks
refuse collection. Exit 75 indicates lock contention, not an outcome.

A successful collection still requires `status=scored` and the retained raw
score-source packet. Pending, busy and withheld results do not satisfy an outcome
gate. A timer and bounded job-selection/completion mechanism are not provided by
this one-job template. Those integrations must retain the first qualified original
sources and avoid treating repeated attempts or overlapping horizons as independent
evidence. No service is enabled merely by adding this template to the repository.

## Queued prospective scoring

The scorer also accepts `--batch --queue /absolute/private/jobs.json
--shared-lock /absolute/private/existing.lock`. Default invocation still checks
configuration only. Batch and explicit-origin collection are mutually exclusive.
The owned mode-600 queue in an owned private directory has this closed schema:

```json
{
  "schema": "earthship-installed-score-jobs/v1",
  "jobs": [
    {"origin_path": "/absolute/private/original.installed-shade-origin-v3.json", "horizon_hours": 24}
  ]
}
```

The queue is limited to 64 KiB and 256 unique jobs. Horizons are 1, 6, 12 or 24
hours. Populate it from the declared sampling plan and original publications
before inspecting their outcomes; do not select jobs by prediction error or
replace an original with a reconstructed forecast. Queue entries do not declare
independence: the qualification layer still derives independent windows from the
original issued clocks, stratifies revisions and checks regime support.

Each tick attempts at most one mature collection. An owned atomic cursor rotates
past unsuccessful or malformed original sources, and limits a scan to eight
uncompleted origins before resuming later. A changed queue during work refuses
completion. Source inventory and replay have a 55-second shared check budget; the
service retains its hard 90-second process limit and existing resource guards.

A completion reference is written only after replaying the actual raw score
packet and matching its original path, horizon and digest. Its scheduling metadata
can suppress repeated acquisition, but supplies no support count or release pass.
New work does not replay the entire completed prefix first. An idle tick instead
replays one retained completion, rotating that audit between ticks. Missing or
changed raw sources refuse that audit without reacquiring or rewriting its original
completion. Qualification always replays the underlying sources independently.
`completion_verified` describes one audit, not qualification of the whole queue.

`thermal-installed-score-queue.service` and `.timer` are inert templates. Render
reviewed private paths and a pinned worker containing the queue module before
installation. The timer runs every ten minutes without catch-up; the existing
shared lock serializes it with input consumers. Do not enable it until genuine
candidate publications and their declared queue exist. Adding these templates
is not evidence of live scoring, a qualified candidate, or production cutover.

## Reproduce the current raw-source qualification report

The current publisher uses qualification-report/v4. The standalone command now
exposes that profile explicitly with `--contract-version 4`; earlier profiles
1/2/3 remain available for their original diagnostic contracts. They do not
substitute for the current raw-source report.

Run the v4 command with the existing global input-consumer lock, the original
registered policy, frozen calibrated candidate/runtime bundle, and a private
original-pairs JSON file. Each list entry is a closed reference to an immutable
raw score packet:

```json
[{"raw_score_sources_path": "/absolute/private/original.raw-score-sources.json"}]
```

Use actual digest-addressed packet paths retained by the collector; this is a
schema example, not a qualified input. Raw packet replay, candidate identity,
independent window selection, statistical gates and freshness remain enforced.
No error scalar, completion marker or cached qualification result can replace
those originals.

The following is one shell command. Replace absolute operands with reviewed
private paths and execute from the pinned repository generation:

```sh
systemd-run --user --scope -p CPUQuota=20% -p MemoryMax=256M -p MemorySwapMax=0 -p TasksMax=24 -p IOWeight=10 nice -n 15 ionice -c 3 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 timeout 90s python3 /absolute/pinned/repo/scripts/qualify-installed-shade.py --contract-version 4 --shared-lock /absolute/private/existing.lock --registration /absolute/private/original.registration.json --candidate /absolute/private/original.installed-shade-candidate-v2.json --runtime-bundle /absolute/private/original-runtime-bundle --original-pairs /absolute/private/original-pairs.json --output-dir /absolute/private/qualification-reports
```

The worker checks resource limits before numerical imports or original reads,
holds the shared lock across replay and report writing, and disables fitting for
this invocation. It restores the prior fitting environment on exit. The output
root must already be owned mode 0700; original files retain their existing
private immutable contracts. Replay keeps the library's aggregate/time limits
and the outer command retains its hard process lifetime.

Exit 75 means lock contention and produces no accepted report. Exit 1 means a
sanitized invocation failure. Exit 0 means a report was written, including when
its decision is unavailable: require the actual `forecast_qualified` value and
every gate, exact candidate/runtime/policy identities, and current expiry. An
unavailable report with absent evidence is honest refusal, not qualification.
The command writes private machine/human reports and cannot enable a publisher,
change telemetry Items, fit a model or activate forecasts.


## Raw development calibration

`installed_shade_calibration.build_raw_calibration` produces the distinct
`earthship-installed-shade-calibration/v2` contract. Its inputs are explicit
`raw_score_sources_path` references to original score-sources/v2 archives.
It replays the retained native query files before computing development residual
bands. Changing a cached receipt, even with rehashed containers, or removing a
query file prevents calibration. `write_raw_calibration` and
`read_raw_calibration` retain and replay these original source references; the
source archives must remain available at their recorded private paths.

The older calibration/v1 APIs remain receipt-only diagnostics. Their readers
refuse v2 records. Both profiles retain the independent support requirements and
provide no release authority. The new calibration API alone does not upgrade
the current calibrated candidate, issuance, or production qualification path;
those consumers still need an explicit stronger versioned integration before
this provenance gap can be considered closed.


`installed_shade_calibrated_artifact.build_raw_calibrated_candidate` creates
`earthship-installed-shade-candidate/v3` with calibration/v2 metadata and its raw
source contract. Build, validation, private storage, and readback replay the raw
calibration sources. The aggregate retains the original base physics and
learning cutoff and requires the complete raw replay/publication runtime source
closure. Candidate/v2 APIs refuse v3 records. Candidate/v3 alone provides no
release authority: issuance, preregistration, qualification, and publication
still require their corresponding stronger contract integration.


Raw candidate/v3 issuance uses the distinct origin/v4 capture, forecast/v3
numeric output, and scored-pair/v4 contracts. Origin/v3 and scored-pair/v3 remain
reserved for the earlier publication-capture contracts. Public
`prepare_raw_calibrated_candidate` replays the raw candidate proof;
`build_raw_calibrated_capture` requires its separate prepared type and refuses
insufficient calibrated bands. Storage and scoring use explicit raw-calibrated
APIs; older issuance readers refuse these schemas. Numerical captures remain
shadow observations with no release or actuation authority. Production
publication and release qualification still need the matching stronger profile.


Raw-calibrated receipt capture uses origin/v5 around the unchanged numeric
origin/v4 and both persisted Item receipts. Its main output shape is
publication/v2 (version 5), release/v2, and forecast/v3. The explicit raw
publication-capture APIs validate original numeric equality, native expiry at
main delivery, chronology, and immutable typed storage. Their scored pairs use
v5. The older publication and capture readers refuse these versions.

`collect_raw_published_score` requires whole native query archives and emits
score-sources/v3. `read_calibrated_raw_score_sources` replays those original
queries before accepting outcome or recent-cycle receipts; it refuses rehashed
cached temperature changes and missing query files. Older score-sources/v2
readers refuse v3. Derived scalar results still confer no release authority.
These APIs do not yet provide the stronger qualification/publisher/queue/UI
integration or authorize any production cutover.


`register_raw_calibrated_installed_shade_policy` creates the distinct
policy-registration/v3 seal for candidate/v3. Its development references point
to original score-sources/v2 query archives from before the final freeze.
Persistence/recent-cycle baselines are replayed exactly in the same hardware
phase; the seal retains raw source bindings and the unchanged numerical policy.
Readback replays the original archives. Development baseline evidence is separate
from later release scoring of the final candidate.

The actual registration clock must precede both untouched and prospective
release intervals. Chronology is checked after replay and immediately before
atomic receipt publication, including time spent writing the private file.
Original source locators remain unchanged and must stay available. Old seal
readers refuse v3. Registration provides no release permission; matching
qualification and production publisher integration remain required.


Qualification-report/v5 explicitly requires all three raw evidence phases:
registration/v3 development sources, candidate/v3 with replayed calibration/v2,
and later score-sources/v3 release pairs around actual publication captures/v5.
Its raw development and calibration gates cannot be supplied by weaker schema
metadata. Development bindings cover every declared baseline row. Original
candidate/runtime/phase matching and statistical/support gates stay unchanged;
older qualification validators refuse v5. JSON and human reports retain the
original phase bindings and remain diagnostic caches.

Use the guarded `scripts/qualify-installed-shade.py --contract-version 5` profile
with the same existing `--shared-lock` and resource scope as v4, supplying the
v3 registration and candidate paths and a private index of v3 raw release
references. Without those sources it emits an honest unavailable report. Exit
zero means report creation, not graduation. V5 adds no fitting or activation;
the production publisher, UI, and scoring queue still need matching integration.


`prepare_raw_installed_qualification` accepts only release-inputs/v3 and freshly
loads candidate/v3 and qualification/v5 under the complete executing runtime
closure. It requires the source-verified fit and complete calibrated bands.
Its separate prepared type is consumed by `build_raw_installed_publication`,
which produces publication/v2 (version 5) and release/v2 around the unchanged
forecast/v3. Active output requires every v5 gate, current qualification expiry,
the same candidate/runtime/hardware phase, fresh native inputs, and qualified
interval widths. Invalid source preparation yields a versioned unavailable
output. Cached reports, older references/prepared types, and manual active flags
cannot replace these checks.

Explicitly absent registration permits shadow collection only. Seal the
threshold policy independently before its untouched/prospective intervals, and
retain that immutable seal while collecting the frozen candidate's as-issued
shadow receipts. Reference the seal and original release sources for the later
qualification/cutover. A configured invalid registration never falls back to
bootstrap. Action advice and actuation remain withheld. The live worker, UI,
and scoring queue still require matching integration before deployment.
