# Provisional thermal production

The operator-approved deployment mode publishes a live, low-confidence thermal
forecast and measures its actual outcome errors. Multi-day coefficient stability,
independent calibration, sealed holdout and prospective baseline superiority are
requirements for later graduation, rather than prerequisites for provisional use.
This mode does not claim calibrated intervals, stable identification or automation.
Qualified publication contracts retain their existing requirements.

The model is a prior-regularized fit of original native-phase development inputs.
Finite coefficients, existing physical bounds, stable transitions, complete causal
weather forcing, known installed shades and fresh phase-matched observations remain
mandatory. Missing data do not become healthy measurements. An unsupported heating
or shade state withholds the forecast. November's operator no-venting default is
preserved through the existing origin-action reader.

`provisional_thermal.py --config CONFIG --train` performs an explicit supervised fit
from a closed `earthship-provisional-thermal-training-config/v1` configuration. It
requires snapshot path/SHA, native epochs, exclusive training interval, explicit
initial coefficients, private output directory and existing shared lock. It creates
an immutable `earthship-provisional-thermal-candidate/v1` artifact with input/runtime
pins and honest rank/support diagnostics. No timer automatically retrains or changes
an active candidate. Each manually selected revision is scored separately.

A closed `earthship-provisional-thermal-live-config/v1` configuration supplies the
candidate path, local OpenHAB base, existing token-file reference, read-only journal
and forecast DSN files, native DB/policy references, private evidence directory,
existing shared lock and original native cutover. `--publish` prepares sources before
an aligned issue and updates only the two existing String thermal telemetry Items.
Both exact persisted receipts must be verified before a delivery record is created.
Version 8 renders as PROVISIONAL with low confidence and uncalibrated uncertainty.
The display includes current-revision MAE/bias and baseline counts when available.

`--score` discovers delivered originals, scores at most two mature jobs under one
50-second budget and checks the original model, delivery, native outcome and source
identity. Horizons are 1, 6, 12 and 24 hours. Reports retain model, persistence and
recent-cycle errors; insufficient recent-cycle history is explicit and never zero
error. A completed record whose original inputs disappear is withheld, without
recollection. Recent reports use at most 256 pairs and keep model revisions separate.
Day-partitioned originals remain private; these files are not disaster backups.

The publisher timer starts 45 seconds before each five-minute issue. The scorer
runs between preparation windows under the same existing nonblocking shared lock.
Both services enforce 20 percent CPU, 256 MiB memory, zero worker swap, 24 tasks,
nice 15, idle I/O and one numerical thread. The pressure watchdog requires a 1.5 GiB
host reserve and low memory PSI; provisional operations allow at most 1 MiB/s host
swap-in, while swap-out/OOM events still refuse execution. Numerical tests stay
serial locally. Full CI runs on hosted runners.

Render the service placeholders to verified private runtime/configuration paths
before installing user units. Disable the legacy shadow publisher before enabling
the provisional publisher. Keep the native input producer and persistence running.
`--withdraw` requires the token and shared lock, and publishes unavailable telemetry
without reading the candidate, fitting, or requiring model qualification. Publication
failures attempt withdrawal; unresolved transport/resource failures remain visible
as failures and the prior payload expires after 15 minutes.

Training loss is development evidence only. Assess actual model quality from later
served-prediction outcomes, bias and error against both baselines. Automatic actuation
and causal action advice remain disabled. PR3 household-planner work and backup or
recovery work remain deferred.
