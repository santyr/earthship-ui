# Hourly AC-demand model and separate storage scenario

The approved design learns a local hourly AC-demand profile in the existing
scheduled morning job, retains original source and coverage evidence, compares
against the load measured at forecast issue, and issues a separately versioned
PV/storage scenario. Existing forecasts and pending outcomes remain intact.
This implementation is in progress and has not been deployed.

The target is **inverter AC-output energy**, measured by
`Inverter_AC_Evidence_JSON`. Historic DC household scope is not inferred from the
operator declaration made on October 15. Future household-load interpretation
continues to require the current declared topology.

The learner uses the fourteen completed America/Denver calendar days before the
training cutoff. Original bounded daily query packets are retained privately,
including invalid rows and NULL barriers. Strict companion interval accounting
preserves expiry, publication gaps and sequence ambiguity. Ambiguous days are
retained with an explicit exclusion; unobserved intervals supply no zero values.

Each clock-hour estimate is the median of the observed hourly mean AC output
from independent days, with at least three days and at least 99% coverage in each
included hour. The repeated autumn clock hour contributes one independent day;
spring days retain their actual 23 elapsed hours. Projection integrates local
clock-hour estimates over partial hours, then holds each resulting elapsed-hour
mean within its forecast hour. Training min/max values describe the retained
sample spread, not calibrated prediction intervals.

A compact model artifact pins the original day documents, accounting, runtime,
Python executable/version and Denver timezone rules. Daily preparation validates
these originals once. Every serving cycle freshly verifies the admitted original
compressed file bytes, model/admission selection and runtime, then replays the
compact hourly arithmetic. It does not rebuild historic interval accounting.
Source freshness uses the latest actually qualified training hour, with a 36-hour
model age; advancing a requested cutoff cannot make missing data fresh.

The existing morning job prepares this domain independently before checking
whether thermal training is already current. A separate sanitized status survives
a later thermal failure. A load-domain failure preserves the thermal refresh and
previous selected model. No agent-triggered production fitting is used.

Original v1 PV/constant-AC storage code is kept byte-for-byte unchanged. A new
profiled-energy receipt refers to the external original energy receipt and plan,
and retains the admitted load-model payload. It uses the original PV intervals,
bank, starting SoC and fixed provisional conversion assumptions. It remains a
conditional nominal scenario without physical calibration or actuation rights.

Matched load outcomes compare the **hour ending at** 1, 6, 12 and 24 hours, rather
than calling an incompletely observed cumulative horizon a full energy outcome.
Both frozen predicted hourly means are integrated over the identical qualified
observed duration. Hours below 99% coverage are excluded from accuracy metrics.
Matched atomic SoC endpoints compare the profiled scenario, original constant-AC
PV scenario, original constant-battery-power baseline and held SoC.

Daily trained versions have individual receipt/model pins. Their chronological
outcomes can be summarized together under the same algorithm, source, geometry
and bank cohort. Reports explicitly describe rolling as-issued versions and
count model versions and independent origin days; they do not claim that every
sample qualifies the latest fixed artifact. The owned scorer retains full
original scores and externally pins compact verified samples so report refreshes
do not repeatedly parse historical electrical receipts.

Completed synthetic checks include source/query boundaries, invalid barriers,
sequence ambiguity, DST, source freshness, original/runtime changes, immutable
write interruption, independent daily failure handling, numerical parity with
the original constant-load integrator, observer isolation and matched outcome
arithmetic. Scheduled score/publication integration and fixed GET/UI contracts
are implemented. The full frontend suite passes 2,462 cases and builds successfully. A serial
3 GiB development run passes 1,624 backend cases with two explicit resource-scope
smoke skips; those actual scope tests passed separately with opt-in. The complete load-feature run passes 131 cases. After tightening runtime-change
revalidation to require all original byte pins, 39 affected source/store/daily
cases pass, including refusal of resealed original data. The cross-day model-
version comparison also passes. The single immutable feature review identified
two outcome-collection issues: lost progress when all mature source reads exceed
the slot, and an unavailable newest origin blocking older valid outcomes. The
correction limits each opportunity to two source acquisitions, caps readers at
four seconds with a five-second publication reserve, and continues eligible
retained outcomes independently of the newest origin. Final correction checks pass 31 affected outcome/state/scheduler cases. Deployment
will use the unchanged existing thermal artifact; load fitting remains on the
normal morning schedule.

The new Earthship panel shows learned hourly demand against the original current-
load assumption, and the corresponding nominal SoC trajectories. It reports
matched AC-energy and four-model SoC errors, marks stale data, and withholds
comparisons from another algorithm cohort. Invalid/missing/expired models leave
the original forecast available. Changed runtime bytes refuse serving until a
normal daily refresh revalidates the retained original days; that refusal cannot
permanently block the refresh itself. Previous immutable model/source files remain
retained. Fixed GET routes only read curated private
caches; HTTP requests cannot run fitting, inference or original receipt replay.

File-only replay entry points are `household_profiled_forecast.py --receipt ...
--energy ... --plan ...` and `household_profiled_outcomes.py --receipt ...
--forecast ... --energy ... --plan ...`. The latter accepts the retained compressed
full outcome receipt. Both check external original documents and executing
runtime again after deterministic replay; neither opens a live data reader.

The installed daily unit already launches its real work through the shared pool
with a 512 MiB minimum and 2 GiB preferred allocation. Its outer 256 MiB/20%
service limits apply to the supervising launcher; the managed work scope receives
the admitted dynamic budget. No new timer, off-host requirement, production
pressure threshold or worker swap allowance is introduced.

Deployment on October 15 at 18:51:34 UTC activated source `c71f14e` as
`06feca50c4db28e3c1be5e20becca164aef5de0ca6f5ce21263d0dbef874f8f0`.
The complete thermal model `188a42a8` is unchanged. All five owned definitions,
three timers, both score calendars and shared budgets pass live readback.
The clean daily checkout now selects that source; its service unit is unchanged
and was not started manually. Five owned UI files were installed while protecting
existing thermal/PV files and unrelated live overlays. Actual laptop and tablet
views show the new collecting state alongside the existing solar chart, without
page errors, write attempts or horizontal overflow.

The first load model will be prepared by the existing scheduled morning job on
October 16 at 06:50 MDT. Until then, learned-demand and storage comparisons remain
collecting. This deployment does not establish load forecasting skill, physical
storage calibration or full PR #3 completion. The review corrections pass 31
affected tests; all three new regressions fail against the immutable pre-fix
scorer, and all six scorer tests pass against the final source. Earlier broad
backend/frontend results above remain the pre-correction regression baseline.

The first normal issue at 18:55:15 UTC completed successfully. Its separately
versioned receipt explicitly records `load_model_unavailable`, as expected before
the morning job. The original v1 forecast remains available and its entire
numerical runtime is byte-identical to the earlier deployed original. Both pure
and exact activated CLI replay match the saved new receipt. The public curated
GET returns HTTP 200 and exactly matches its issued receipt projection. This is
verified publication of unavailability, not a trained-load forecast or skill
claim.


The first normal learned-load outcome report at2026-10-16T14:08:33.173872Z
contains one qualified one-hour pair from one origin day/model version. AC
energy absolute error is0.000255102kWh for the hourly profile versus
0.022405726kWh for holding the original AC load constant. Nominal SoC error is
0.281384 percentage points for learned-load PV/storage,0.399484 for constant
AC PV/storage,1.030273 for constant battery power, and0 for hold-SoC.
Therefore this single observation does not show overall dominance or establish
independent-day skill, calibrated usable capacity or action effects. Longer
learned-load horizons are still collecting. These were initially observed in
the existing scheduled scorer's curated report.
At 2026-10-16T14:21:41Z, the exact deployed file-only CLI independently replayed
the complete retained outcome and its original profile, energy forecast and plan
with network access forbidden. The result matches the full saved score exactly;
all five original input/sample files remain byte-identical. Original issue:
2026-10-16T13:00:15Z; outcome receipt:
`9f5ee0690e87ed2f80ca9616358a7253ef1ca4e433b2c9c9f5a6d95e1b9d80c9`.
This upgrades the arithmetic/provenance evidence, without adding observations or
establishing general skill. No fitting, new forecast, live query or publication
ran. Private proof: `native-score-progress-20261016/profiled-outcome-replay-proof.json`
under the common-cycle evidence directory. Captured-PV eligibility/progress is
separate; see [the retained-scoring diagnosis](2026-10-16-retained-scoring-diagnosis.md).
