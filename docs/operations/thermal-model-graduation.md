# Thermal model graduation: active goal

Owner: Hex. Hexmem task99. Operator explicitly added completion of the requisite
work to move the model out of shadow on September20,2026. This is part of the
broad Earthship/OpenHAB goal, not an indefinite optional follow-up. Do not rush
the evidence gates or equate a working shadow publisher with completion.

## Current evidence, September20

The scheduled trainer uses the400-day default, bounded physical fitting and
chronological walk-forward evaluation. Today's accepted artifact is in use.
Live Thermal_Model_JSON at23:29:48Z reports low confidence, reconstructed action
labels, no physically valid bounded candidate and no alternate schedule.
Forecast temperatures already appear in the UI. Advisory graduation is distinct
from training-artifact acceptance and from automatic actuation.

## Required work and evidence

The [September20 baseline audit](2026-09-20-thermal-graduation-baseline.md)
records errors, interval coverage and absent confirmed action evidence. It also
identifies evaluation-only persistence blending: resolve forecast-output parity
before tuning or using those metrics to qualify the displayed trajectory.

Source-only parity repair now removes evaluation-only blending and advances the
model/backtest schemas to v5/v3. Daily extrema, horizon errors, candidate scoring
and published states use raw physical simulation. Legacy v4/v2 evidence is
explicitly rejected by the new validators; it must not be relabeled or used to
seed a new accepted registry. Production still runs the previous runtime and
accepted model. Before cutover, run the new trainer with a separate candidate
state directory, verify recalculated residual intervals and unchanged acceptance
gates, and retain the old runtime/model pair for rollback. If the candidate
fails, continue tuning rather than deploying this incompatible runtime alone.
Historical weather/action provenance and live no-candidate replay remain open.

An [isolated qualification run](2026-09-20-thermal-v5-qualification.md) now uses
the frozen parity revision and original historical window. Its source audit
confirms conditional hindcast inputs, not operational forecast replay; retain
that distinction when interpreting any successful training result.

1. Audit the current accepted backtest: errors by horizon, season/regime and
   temperature state; compare persistence, recent/seasonal trajectories and
   existing advisory baselines. Separate legacy history from receipt-qualified
   evidence. Investigate absent candidates rather than assuming time fixes them.
2. Use historical data for bounded tuning of physical parameters and fitting
   choices. Keep chronological train/validation splits and an untouched final
   test period. Preserve physical stability constraints, provenance, budgeted
   computation and reproducible reports; never optimize against the final test
   set or leak future weather/actions into operational forecast claims.
3. Audit and complete confirmed ventilation/shade-action and outcome collection.
   Score comparable nights and uncertainty. Reconstructed actions can support
   exploratory fitting but must not count as confirmed causal benefit evidence.
4. Derive explicit numerical graduation thresholds from baseline evidence:
   accuracy versus baselines, bias, interval coverage, data support and modeled
   benefit. Review thresholds and representative advice before cutover; do not
   fabricate a minimum day count or announce a release date without evidence.
5. Implement repeatable graduation assessment with explicit failure reasons and
   next evidence checkpoint. Implement validated advisory status/schema/UI and
   consumer integration with honest stale/no-candidate fallback and rollback.
   Preserve existing alert codes and controls until their reviewed transition.
6. Deploy eligible advice in stages and verify natural publication plus operator
   review of examples. Retain seasonal scope: warm-season success does not
   qualify winter recommendations. Automatic actuation requires its separate
   authority, reconciliation/manual-override and fail-safe review.

Revisit this task at subsequent thermal work checkpoints and after relevant
completed outcome windows. When a gate is waiting on observations, record the
specific missing evidence and next review opportunity; continue implementable
work in parallel. Do not mark task99 or the overall goal complete merely because
collection is active or the UI badge was changed.
