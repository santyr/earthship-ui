# Post-upgrade repairs: deployed state and rollback

OpenSpec change: `complete-post-upgrade-repairs`. OpenSpec is the active workflow;
historical Superpowers files are retained evidence only.

The RTL-SDR weather receiver uses the retained 25.02 compatibility release built
against current librtlsdr. Receiver and OpenHAB freshness passed a600-sample,
ten-minute watch for indoor235, Bedroom223, north193 and outdoor206. Bedroom is
physically in the bedroom; its historical Hallway JDBC identity is preserved.
This is bounded observation, not a guarantee against future RF interference.
Rollback and original receiver bytes are under
`/home/sat/system-repair-20261024/rtl-weather-dropouts/ACTIVE-RADIO-RECOVERY.md`.

The UI verification below originally used
`ui-release-forecast-readable-20261029-3bbf7d6caca1-a02`. Its deployed successor is
`ui-release-suggestions-20261029-a03`, which preserves those layout/model-consumer
bytes and adds the verified suggestion-refresh changes described in
`suggestion-refresh-cadence.md`.
Date is first-row left before Suggestions. Time is64px, left of energy on the
second row; Today occupies its own unbroken energy row. Original energy labels
are restored. Forecast labels and zones fit the landscape tablet. Full3404 UI
tests,167 final focused checks, a fresh build, and18 post-fit live route/viewport
views passed. The relative OpenHAB connection and private proxy settings remain.
UI selector backup: `openspec-runtime-20261028/ui-forecast-selector-before.conf`.

Production native models use signed39b0070b5ea1f1546f2513482f4a2824f3535c07,
separate from the publication checkout. The following fit/artifact observations
are the recorded repair verification window; later scheduled fits may advance
the live selection. The actual06:50 scheduled fit completed06:57:47;
training extends through2026-10-29 06:00UTC. The selected artifact is
b21275bfabeb5fbfb8033295deeabfcf512229b406c579efee96abd1eb0ac101.
Natural publication completed at07:00 and the current artifact obtained its
first mature H1 score at08:11. Longer horizons are not claimed from that score.
All original numerical guards and freshness limits remain. Point/source reuse
fixes fit/publication costs without substituting inputs or extending deadlines.
Activation/rollback receipts and the prior selection are retained under
`openspec-runtime-20261028/production-point-reuse-*`. The six-hour fit timer and
forecast/score/geometry timers remain enabled. Equipment actuation stays off.

Sensitivity uses signed0075a1d791598b86b7097c11c0bb06eba221c530 and its segmented
origin reader; actual hourly publication and the UI API were verified. Optional
experimental rain-shadow/marginal products remain unavailable; these are not the
production range/sensitivity panel. Do not fabricate their artifacts or turn
unavailability into current weather data.

The energy readers use `analytics-reader-release-2fd49d818476`;53 reader tests
and a natural UI publication confirm the health correction. Forecast is healthy;
independent daily-source degradation is retained truthfully. Exact two-selector
backups are in `openspec-runtime-20261028/analytics-reader-health-backup-20261029`.
Reader deployment does not replace the writer, credentials or historical data.

The private seven-service sensor stack passed all original11 Python and2 browser
bodies in `sensor-final-budget-20261029-a01`. Its fixed worker supervisor
recovers unacknowledged packets after a database outage. The isolated browser
uses bounded worker pools; assertions, SSE/state transitions and both viewports
remain. Provisional private allocation: OpenHAB144tasks, controller32 Python /
60 browser, private PostgreSQL20, guardian8;1GiB controller. The original6GiB/256task/8CPU/no-swap total,
3GiB host reserve, deadlines and uncertainty reserve remain. No container memory reservation is released. The completed simulator task
reservation is released only after all11 Python bodies and its stopped-ID proof. The separate interrupted guardian recovery is
`sensor-guardian-recovery-20261029-a07`; it is not an uninterrupted browser pass.
Both cases retain original and supplementary terminal checks for exact7 IDs,
production preservation, retained volumes, unit collection and free real lock.
These test-stack corrections do not alter production radio capture or actuators.

Source integration has its own exact before/after manifest and scoped backups in
`final-source-integration-20261029`. Use its guarded rollback only while installed
source identities still match. Both original Git indexes and unrelated edits
remain protected. Native runtime source is deliberately kept in its separately
deployed worktree; copying the entire worktree into main is not a rollback.

All relative evidence paths above are under
`artifacts/post-upgrade-repairs-20261024.local/`. Original failures, including
OOM/process-limit refusals and incomplete observers, remain retained separately.
Fresh post-integration runtime observations and maintained main tests are recorded
in OpenSpec evidence and the final operator receipt; do not infer them from this
source manifest alone. LNbits/custom Strike remains outside this repair scope.


## Final main verification and operational readback

All73 scoped source targets are integrated with exact reversible backups across
`final-source-integration-20261029`, `final-source-dependencies-20261029` and
`final-source-native-interval-20261029`. Final main validation passes2398 UI,
544 helper and53 analytics tests; fresh build passes866modules. Existing chart
precipitation/time labels, unrelated modules and both original indexes are
preserved. These checks use byte-verified writable copies, with all original
failed copies retained. The deployed immutable UI remains separately qualified.

The final11:40UTC issue matches the current model binding, all five installed
family files and all three unexpired exact-cache UI energy APIs. Production
weather and sensitivity are available. All four temperature roles are fresh at
receiver and OpenHAB, including Bedroom. A120-sample two-minute under-load watch
has no observed drops/expired readings/resets; maximum receipt lag2.568s.
The original longer watch remains separately recorded.

The same-source guardian recovery uses one fault only. A positive automatic
restart and lock-preservation event is retained before an observer's redundant
READY read races normal descriptor release. Its original error remains; a separate
read-only parent adjudication verifies exact cleanup and original terminal proofs.
No second fault is used. The independent topology observer's earlier timeout is
also retained without complete-monitor credit. Original controller resource and
per-start cap checks prove the uninterrupted13-body result with zero new events.

Both formerly deferred read-only scorers are actually rerun and exit0. No failed
system/user units remain. Sudoers/package checks pass; Wi-Fi is up. Independent
historical daily-source/AC-load qualification warnings remain; they are not
rewritten to healthy or substituted with forecast data. Final receipts and the
OpenSpec evidence file provide actual timestamps, limitations and rollback paths.
