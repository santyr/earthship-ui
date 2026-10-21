# Hourly refresh and near-term correction

Task 6 is in progress. The existing first-original-per-local-day benchmark and
scores remain unchanged. This work introduces a separate population of actual
successful publication decisions and a separately identified near24 correction.
Neither product changes installed model selection or control authority.

`refresh_evaluation.publication_decision` verifies the original attempt/result,
all confirmed Item readbacks, provider/state hashes, exact source metadata and
native forecast reconstruction. It replays the originally selected sources;
re-running today's selector cannot rewrite a recorded publication. The original
near/extended profiles and each composite hourly segment retain their identities.
A modified temperature with fresh, self-consistent report hashes still fails
native-source replay. Publication readback does not prove JDBC delivery or
qualify an outcome observation.

The bounded original-data probe replayed all 49 retained successful publications
from 2026-10-19T22:03:21.481067Z through 2026-10-21T22:47:26.644064Z in 11.31 seconds.
All 98 attempt/result files were checked unchanged and copied byte-for-byte into
private task artifacts. This is the complete retained population at probe start,
not proof of every scheduled cycle. In 48 decisions the near and extended source
differed. Near profiles used 40 distinct originals and extended profiles used 9.
Near-source actual availability lag ranged from 6.69 to 7.71 hours; extended lag
ranged from 7.69 to 9.69 hours. No forecast-improvement claim follows from this
source inventory. The digest-bound public inventory omits private original paths.

`refresh_profiles` independently prepares the latest eligible retained 48-hour
collection and 360-hour collection on identical next24-hour targets. These names
describe collected coverage: a retained 48-hour subset alone cannot establish
Google's nominal full/interim product class. Selection uses actual original
first-seen/completion clocks, verifies the index against its source, requires
all six core fields without internal gaps, and refuses more than 256 candidates.
Initialization age, acquisition lag, native remaining coverage and selected
hours are explicit. A 48-hour source delivered eight hours after initialization
has about 40 native hours left, not 48 hours beyond delivery. The requested24h
profile includes the ceil endpoint when the decision is between native hours.

`near_term_correction.prepare_near_term_correction` uses the same six-field near
source selected for production, independently of the 336-hour extended gate.
It loads the existing original model/selection through unchanged source, epoch,
availability and expiry checks. Both origin-bias interpolation and all future
native temperatures come from that exact source. An exact native origin is
accepted; interpolation needs adjacent one-hour points, with no extrapolation or
borrowing an extended origin. The input origin must have an actual acquisition
clock at or before the decision, within120s, and after its original receipt was
persisted. The existing qualified outdoor receipt policy remains authoritative.
The returned private capture, model/selection hashes and source are retained in
the prepared product. Its independent identity is
`near_term_local_correction_24h_v1`. Missing model or origin yields an explicit raw
fallback, preserving the near forecast. The prepared product declares
`issued=False` and `local_coverage_qualified=False`; it is not a backfilled issued
forecast or an installed extended correction.

The frozen `refresh-evaluation-protocol.json` sets matching, weights, source
classes, publication clocks and support before outcome comparisons. The scoring
sample keeps every native endpoint through ceil(decision+24h), plus offsets48,
72,120,168,240,336 from the first future native hour. Complete extended originals
remain retained. This is a declared bounded score sample, not all-hour scoring.
Only targets strictly later than confirmed publication completion enter scores.
Actual published forecasts and known-at-decision policy replays are identified
separately. Missing comparisons and outcomes never become zeros. Dates have equal
weight, then targets within a date, then forecast origins for that target.

The final offline experiment completed in34.38s, with385 exact production source
files and165 immutable input files retained and verified unchanged. Literal
receipt-source replay yielded375 qualified forecast-target pairs against26
unique measured targets on2local dates. There were570 mature sampled targets
without a retained qualified outcome and574 not-yet-mature targets. These counts
cover1519 declared targets from the frozen49publication population. No fitting,
network connection, child process or installed-state change occurred.

| Same375matched forecast-target pairs | MAE C |
| --- | ---: |
| Latest retained48h collection, next24h | 1.445759 |
| Actual published near/extended serving policy | 1.481400 |
| Latest retained360h collection, next24h | 1.591796 |

These are descriptive results:2local dates do not satisfy the3date gate. Retain
all current serving policies. The collected48h subset is not asserted to prove
Google's nominal product class. Repeated forecasts are not375independent local
observations. Date-block intervals are descriptive with no probability claim.

No new near24 correction was prepared for those original historical decisions.
Its corrected-only matched support is0. The full fallback policy retains all375
original raw predictions, with the explicit reason `NEAR24_NOT_PREPARED`; it does
not acquire apparent skill from invented historical corrections. A selected
model with a missing origin retains its artifact identity for fallback attribution.
Tests distinguish corrected-only matched support from the full raw-fallback
policy, including the case where correction is available on only one target.

The private experiment contains original publication profiles, same-target
revisions, initialization/availability/local issue ages, source grids, exact
observation acquisition clocks, complete group/subgroup diagnostics and source
packages. `refresh-experiment.json` exposes a bounded summary with hashed sensor
phase identity and no original measurement paths or device identifiers.

Remaining Task6 work is the bounded durable profile-decision score queue and
prospective integration. Long-horizon maturity and restart behavior still need
verification. Tasks7–11 remain required for the full capability goal.
