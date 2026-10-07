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
