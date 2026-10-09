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
readback. `native_source_paths` records the retained files for the caller.
The next collector integration must bind these paths into versioned collected
score sources, validate every outcome/comparator against independent raw
packet replay, and keep incomplete attempts explicit. Collector result and
release-consumer schemas do not yet establish this raw-source binding. Existing selected-receipt score archives cannot
be retroactively described as retaining raw snapshots. Legacy v4 diagnostic
origins remain outside the candidate graduation contract.
