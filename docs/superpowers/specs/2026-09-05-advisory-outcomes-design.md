# Advisory outcome evidence and completed-night scoring

## Approval and scope

Sat approved this observational-first scope on September 5, 2026: record
advisory decisions and measured outcomes, and repair premature overnight SoC
scoring. This is the written design for review before implementation planning.
It advances tasks 16 and 18 but does not claim either entire ML task complete.
Task 82 remains on hold.

Threshold values, advisory selection, DM eligibility/deduplication/content,
the 06:40 forecast schedule, household controls, BMS counters, and thermal
model authority remain unchanged. No Thompson sampling, exploratory advice,
conformal interval publication, new notification, or automatic actuation is
introduced. Production migrations and activation require an attended release
approval after tests and review; this design is not that deployment approval.

## Verified problem

The installed and tracked forecast_intel.py match. Its per-day prediction map
overwrites previous runs and retains 30 dates. Advisory category alone does not
identify the inputs, thresholds, successful publication, human action, or outcome
of a particular decision. The current thermal action journal contains ten events
ending in May 2026, not confirmed current warm-season action evidence.

The existing trough measurement window is 20:00 on prediction day through
11:00 the following local day. The September 5 live service finalized that
night's score at 06:40:29 and marked it consumed. Later actuals therefore cannot
correct that score. Seven retained absolute errors are not a trustworthy new
calibration set. The low-temperature error Item measures raw forecast error;
it cannot establish corrected-forecast performance.

## Approach and ownership

Use immutable decision records plus versioned measured-outcome records in the
existing PostgreSQL quantitative platform. OpenHAB remains the source of sensor
history and existing publication surface. Reuse the thermal action journal as
read-only action evidence; never duplicate its ingestion or rewrite its labels.
Hexmem receives compact verified conclusions, not telemetry or raw messages.

Extending only the mutable daily JSON was rejected because overwritten origins
cannot be reconstructed reliably. Treating thermal shadow predictions as rewards
was rejected because predictions do not prove observed benefit.

Earthship-ui owns the forecast script's capture integration and pure record
builders. Solar_PV owns new energy_analytics tables, migrations, bounded reads,
outcome assessment, and report generation. The implementation plan must spell
out the installed Python import boundary and deployment order; do not assume
either checkout is automatically on the other's import path.

OpenHAB-backed sensor persistence is reused. Dedicated relational records are
needed for immutable IDs, publication attempts, uniqueness, corrections and
atomic outcome commits; a single changing OpenHAB Item cannot preserve those
semantics. No additional database server or parallel telemetry collector is needed.

## Decision capture contract

Capture each natural invocation's decision, including a `none` advisory and
suppressed DM eligibility, without changing which side effects that invocation
would otherwise attempt. Each record has a UUID decision ID, schema version,
UTC issued time, site timezone, source revision, policy version and bank epoch.
Record the exact finite inputs actually used: raw and corrected temperatures,
the applied biases, tomorrow and three-day temperature summaries, PV/trough
predictions, thresholds and selected advisory category. Preserve per-quantity
target windows; today's PV and tomorrow's temperature are not the same target.

Persist intent before existing publication where available, then record the
observed result separately. Capture per-Item publication results for the advisory
and the trough prediction: accepted, failed, or unknown. HTTP acceptance does not
prove display or human acknowledgement. A diagnostic candidate requires a
recorded accepted trough publication, not merely accepted advisory publication.
Notification states distinguish not eligible, suppressed by the existing daily
marker, attempted with reported success, failed, and unknown. Existing notifier
output proves only its reported send result, not delivery, reading, or compliance.
Do not persist message bodies, recipients, secrets or raw subprocess output.

A retry of a storage operation uses the same decision ID and exact payload;
conflicting content for that ID fails explicitly. A new natural forecast run is
a new decision, even when inputs happen to match. Never replay notifications or
advisory writes to repair an observational record. A crash between a side effect
and its result record leaves an unknown result, never inferred success.

Capture uses bounded timeouts and reports failure without preventing existing
forecast/advisory/DM behavior. If storage is unavailable, retain an explicit
capture-gap diagnostic in the existing operational log; do not manufacture a
historical decision later. No unbounded retry queue or new local telemetry store.

## Measured outcomes and attribution

Assess records only after their entire target window has elapsed. Use UTC
instants derived from the recorded IANA timezone, with half-open windows:

- Trough: prediction-day 20:00 to next-day 11:00.
- Thermal: next local calendar day for hallway maximum/minimum; retain the
  preceding evening-to-11:00 window for relevant vent/shade transitions.
- Weather low/high: the exact local target day of the recorded temperature.
- PV: the recorded local production day, not the issue date by assumption.

Keep raw and corrected temperature residuals separately using correction values
frozen at issue time. Do not apply today's filter retrospectively. Store signed
SoC residuals in percentage points and PV residuals in kWh; retain the existing
percentage-error diagnostic separately and mark it undefined on zero-PV days.

Record extrema, measurement bounds, sample counts and coverage diagnostics,
source names, assessment version, decision ID and assessment time. Return
pending before window completion; measured only when evidence passes validation;
otherwise insufficient_data with explicit reasons. Invalid, nonfinite, stale,
out-of-window and implausible SoC values cannot become valid observations.

Operator correction, September 5: retain change-only persistence and make the
algorithms aware of its semantics; do not add periodic persistence as a workaround.
Carry the last known state across unchanged intervals, including a valid value
before the window start, without relabeling its change time as an observation.
Coverage must come from independent update/heartbeat and source-health evidence,
not the spacing or number of value changes. A healthy constant SoC may therefore
cover the full window. Conversely, a restored/cached value without corroborating
freshness does not establish coverage. Keep at least 90% validated coverage for
scoring, but apply source-specific freshness expiry to telemetry evidence, not
a generic 20-minute limit to state-change intervals. The implementation plan
must specify verified per-source freshness contracts and boundary handling.
Never forward-fill across a known fault, unknown source epoch, or unsupported
freshness interval. Do not interpolate daily-reset accumulators across midnight.

Associate action-journal events by effective time, action kind and target window,
preserving source, confidence, corrections and event IDs. Distinguish confirmed,
inferred/reconstructed, ambiguous and unknown evidence. An overlapping action is
not proof it responded to this advice. Missing events never mean no action.
Multiple overlapping advisories must not generate independent claims of benefit
from the same observed trajectory.

Report the already approved 82 F warm-season and 60 F winter references only as
evaluation context. No binary success reward, causal benefit, adherence claim or
bandit-eligible sample is assigned in this increment. Winter lows below 60 F are
not automatically policy failures. Later reward design must address confounding,
confirmed action coverage, exposure and operator review explicitly.

Use a unique (decision ID, assessment version, evidence digest) identity for
outcome revisions. Exact replay is a no-op; later evidence or corrected actions
produces an explicit revision, not a second independent sample. Report a
deterministic current revision per decision. Retain original records.

## Completed-night scoring repair

Keep the 06:40 invocation. Process a bounded backlog of completed target windows
instead of assuming yesterday's prediction can always be scored immediately.
For example, September 5 at 06:40 cannot score September 4's night ending
September 5 at 11:00; September 6 at 06:40 can score it. No extra full forecast
run or new notification schedule is necessary.

For the legacy one-score-per-night diagnostic, select the first successfully
published trough prediction for that local prediction day issued before 20:00.
Freeze that selection. Later same-day forecasts remain separately available for
horizon-aware outcome analysis but do not receive extra weight in the rolling
daily diagnostic. A late prediction has no eligible whole-night diagnostic.

Start verified scoring with post-activation, timestamped records. Preserve the
old arrays and learned Kalman/model state as legacy evidence, never relabel them
as full-window scores or silently reset learned parameters. Maintain a separate
versioned completed-night history. Project Forecast_Trough_Error_7d from up to
seven distinct verified nights, exposing unavailable until the first valid one;
reports include count, dates, coverage and cutover version. Do not imply that
one observed night represents seven days of calibration.

Rebuild the rolling projection deterministically from committed outcomes rather
than append before writing a consumption marker. Retry after process failure,
duplicate invocation, partial publication or delayed persistence must not double
count. A publication failure retries only the observational score Item, not
forecast/advisory/notification actions. Keep current trough prediction equations,
including their existing morning inputs, outside this scoring-only change.

Use at most 30 target days per assessment run, with explicit query limits and
per-run timeouts. Older unfinished evidence remains reported as expired or
unscored, not silently successful. Historical replay is a separate read-only
report mode; it does not mutate learning, resend anything, or forge issue times.

## Operational reporting and Hexmem

Produce a compact private report with capture coverage, publication-result
counts, pending/insufficient/measured outcomes, distinct target dates, residual
summaries, action-evidence classes and the explicit lack of causal reward proof.
No new dashboard card is required. Reports must distinguish raw-weather error,
corrected-weather error and advisory effectiveness.

Hex reviews those reports and records atomic verified summaries with report
identity, date range, source revision, confidence and private sensitivity through
existing Hexmem tools. There is no new automatic Hexmem writer or message sender
in the forecast job. Memory is not the only copy of quantitative evidence and
does not authorize threshold changes.

## Failure, deployment and rollback

New capture/assessment is default-off until its schema, connection privileges,
dependencies and bounded read/write targets are reviewed and deployed. Migration
belongs to an explicit deployment step, never an import-time or startup action.
Back up affected source, forecast state and quantitative schema before activation.
Install the database contract and assessors before enabling the producer adapter.

Use existing schedules where possible. Outcome assessment must have no access
to notification execution or actuator/rule writes. Its only OpenHAB write is
the existing observational trough-error Item. Runtime connection timeout and
SQL transaction boundaries must be covered by integration tests.

On rollback disable new capture/assessment first and restore reviewed source
without deleting evidence. Preserve legacy state and valid outcomes. Never
reenable premature-window scoring as a silent rollback fallback: leave the
diagnostic unavailable until a verified scorer is restored. Leave existing
prediction, advisory and notification behavior intact.

## Completion evidence

1. Regression test fails on the current 06:40/11:00 defect and passes with
   delayed scoring, including January/July and DST transition windows.
2. Frozen origins, corrected inputs, targets, thresholds and result states
   survive persistence and retries without decision or reward duplication.
3. Missing/late telemetry, malformed samples, action corrections, overlapping
   decisions, failed publication and crash boundaries remain explicit.
4. Golden behavior tests show unchanged thresholds, advisory selections,
   notification eligibility/deduplication/content and no new control writes.
5. Read-only integration validates actual persistence cadence and schema
   contracts; isolated database tests validate uniqueness and transactions.
6. After separately approved activation, verify a genuinely completed target
   window against its exact stored decision and real sensor evidence. No
   synthetic or future window counts as live completion.
7. Reports and a verified private Hexmem summary preserve limitations. Mark the
   recording/scoring prerequisite complete only; bandit tuning, conformal
   publication, seasonal verification and deferred rain/wind remain open.
