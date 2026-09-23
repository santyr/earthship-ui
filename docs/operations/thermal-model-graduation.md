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

An [isolated qualification run](2026-09-20-thermal-v5-qualification.md) used
the frozen parity revision and original historical window. Its source audit
confirms conditional hindcast inputs, not operational forecast replay; retain
that distinction when interpreting any successful training result.
The run was refused on 24-hour error. An
[exploratory chronological blend audit](2026-09-23-thermal-historical-blend-audit.md)
found a possible 24-hour ensemble improvement in a later warm-only segment;
it is a tuning hypothesis, not graduation evidence or a winter result.

### Confirmed-action collection audit, September20

Read-only aggregate journal queries still find ten action events: eight
`model_inferred` Kiva events (December2025–January2026), one reconstructed
outdoor-shade event (October2025), and one `manual_dm` outdoor-shade event
(May22,2026). There are no ventilation or indoor-shade events. Mode history has
three reconstructed entries and one May22 manual entry. No message bodies,
notes or credentials were exported and no journal entries were fabricated.

This explains a substantive collection gap, not merely insufficient elapsed
time. The dataset only marks confirmed-source event timestamps which survive
sample construction. Evaluation additionally classifies joined action confidence;
one confirmed outdoor-shade state does not make reconstructed ventilation or
indoor-shade states confirmed. Do not relabel those fields to raise gate counts.

The existing CLI `thermal_intel.py journal` accepts structured `THERMAL` messages
with an explicit receipt/idempotency key and optional aware effective timestamp.
It is a trusted ingestion primitive, not proof of authenticated live transport.
Inspection found the legacy user `nostr-inbox.service` disabled/inactive, pointing
to missing `/home/sat/clawd/scripts/nostr-inbox-listener.sh`. No active thermal
confirmation route was established by the inspected repository/service paths;
this is not proof that every host messaging path was exhaustively checked.
Do not enable that obsolete unit or commandeer unrelated messaging projects.

Next implementable collection work: establish a scoped authenticated operator
confirmation route to the existing append-only journal, with immutable original
receipt identity/time, duplicate handling, explicit effective time, correction
semantics, and acknowledgement only after verified storage. Keep planned future
actions distinct from confirmation of completed actions. Test transport and
journal failure/retry behavior in isolation; only genuine operator reports may
be recorded as production confirmations. Then verify natural ventilation/shade
transitions and associate later qualified outcomes without assuming compliance.

Source-only confirmation hardening now requires full action/mode readback equality
before the journal CLI emits success, including duplicate retries. Missing,
changed, duplicate, unexpected or unavailable stored records produce no success
receipt. This is a tested ingestion prerequisite, not an authenticated collector
or deployed collection path. The approved design specifically chooses scoped
Nostr replies; the shared household proxy token is not individual operator
authentication and should not be repurposed as confirmation identity.

The source-only CLI also refuses receipt timestamps later than processing time
and effective action/mode timestamps later than their original receipt, before
constructing a journal connection. Future interval endpoints remain parseable
as plans but cannot enter this confirmed-action write path. Report actual
transitions separately with explicit aware timestamps; do not manufacture a
later receipt date to turn a plan into evidence. Tests cover current and past
confirmations, duplicate retries, future receipts, modes and overnight intervals.
Production ingestion/runtime remains unchanged pending coordinated deployment.

Broader regression verification at source revision `e7af4f2`: all633 local
thermal tests passed in137.87seconds with single-thread numerical libraries.
This includes every `test_thermal*.py` suite except container-backed
`test_thermal_journal.py`, plus the graduation-audit tests. Deployment/systemd
tests use temporary files or mocked services; this result is not a new live
database, inbound-transport, restart or production-deployment qualification.

Subsequent isolated PostgreSQL16 journal verification passed all32 tests
(4.01seconds final run). Actual CLI/database checks now use a completed same-day
ventilation interval: first write stores three records, replay stores zero new
records with the same IDs, and future overnight plans leave no receipt, action
or mode rows. The prior integration fixture represented a future plan and was
updated for the stricter confirmation contract. Fixture DSNs are excluded from
dataclass representations. All owned `thermal-journal-test-*` containers were
removed and absence verified; no production database writes occurred. This
closes isolated storage/replay testing, not Nostr authentication or deployment.

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
