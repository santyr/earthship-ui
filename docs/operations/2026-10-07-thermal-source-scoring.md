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
