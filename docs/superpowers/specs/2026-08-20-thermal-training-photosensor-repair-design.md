# Earthship Thermal Training and Photosensor Repair

**Date:** 2026-08-20
**Status:** Approved in conversation; implementation not started
**Extends:** `2026-08-13-rc-thermal-model-design.md`

## Purpose

Repair the first live RC thermal-model training failures without weakening the
approved physics gates, preserve year-round learning, and begin durable
collection from the newly installed Philips SML003 motion/light sensor. This
change remains observational. It cannot command vents, shades, the Kiva,
`Thermal_Advisory`, or any other household equipment.

## Verified starting point

The production PostgreSQL journal and OpenHAB JDBC history now contain enough
data for identification:

- A 90-day window produced 3,646 thermal samples and 999 fitted pairs, but only
  warm-mode data. Outdoor shades were continuously installed, making the
  `solar_unshaded` design column identically zero. Training correctly refused
  the rank-deficient design.
- The 2025-10-01-to-present window produced 14,217 samples and 4,737 fitted
  pairs across `fall_charge`, `winter`, `spring`, and `warm`. The air and mass
  designs were full rank.
- The all-season air and mass fits satisfied gain ordering, but the auxiliary
  glazing fit was rejected with `shade gain exceeds unshaded gain`. The current
  box-constrained least-squares fit does not encode the coupled ordering later
  required by `validate_physics()`.
- Four operator-approved Kiva inference intervals are present as eight
  `model_inferred` events at confidence 0.15 and are excluded from passive
  fitting.
- No accepted artifact exists. `Thermal_Model_JSON` and all thermal systemd
  units remain absent.

The Philips SML003 Thing
`zigbee:device:a7351eb531:001788011024c307` is online in the hallway. It
represents the living-room/office window area and exposes illuminance,
occupancy, and temperature channels, but those channels are not yet linked to
Items. The active JDBC configuration already persists `*` with `everyChange`
and `restoreOnStartup`, so Item creation requires no persistence-policy write.

## Selected approach

Use exact constrained identification and staged photosensor capture.

Rejected alternatives are:

- Omitting the glazing observation whenever its fitted gains are unphysical.
  This needlessly discards a useful auxiliary validation signal.
- Clamping gains after an unconstrained fit. Clamping is not the constrained
  least-squares optimum and would hide identification failures.
- Immediately inferring shade state from an uncalibrated photosensor. With no
  persisted history or confirmed shade transitions, this would represent
  guesses as measurements.

## Training-window contract

The default and scheduled training window is exactly 400 days ending at the
training origin. OpenHAB retains older history; the fitting window rolls so the
model adapts while retaining at least one complete seasonal cycle.

Samples before the earliest evidence-backed mode remain unknown and cannot
enter a fitted pair. The fitter continues to require known vent, indoor-shade,
and outdoor-shade inputs. A 400-day window does not relax rank, coverage,
provenance, chronology, or promotion requirements.

The data manifest adds exact nonnegative `sample_counts_by_mode` entries for
`unknown`, `fall_charge`, `winter`, `spring`, and `warm`. Artifact validation
rejects missing or unknown mode keys and a mode count sum that does not equal
the manifest sample count. A year-round promotion requires nonzero counts for
each of the four evidence-backed seasonal modes; `unknown` remains reportable
but cannot enter a fitted pair. This is evidence about the fitted dataset, not
a new shadow-output field.

## Constrained dynamics fitting

Air, mass, and glazing regressions retain their existing equations, row
selection, end-of-step alignment, square-root confidence weights, and
coefficient bounds. Their solar gains gain two coupled inequalities:

```text
solar_unshaded - solar_indoor_closed >= 0
solar_unshaded - solar_outdoor >= 0
```

All three solar coefficients remain nonnegative. The solver minimizes the same
weighted sum of squared residuals subject to the existing box bounds and these
linear inequalities. The implementation must use a deterministic constrained
optimizer with an explicit feasible starting point and must reject non-finite,
unsuccessful, infeasible, or rank-deficient fits.

`validate_physics()` remains an independent post-fit gate. No coefficient is
clamped, substituted from a prior artifact, or invented when a design is rank
deficient. Existing exchange-sign, transition-stability, output-range, and
72-hour simulation checks remain unchanged.

## Philips OpenHAB resources

Create exactly these observational Items:

| Item | Type | Label | Channel |
| --- | --- | --- | --- |
| `LivingOffice_Shade_Illuminance` | `Number` | Living room / office shade illuminance | `zigbee:device:a7351eb531:001788011024c307:001788011024C307_2_illuminance` |
| `LivingOffice_Shade_Occupancy` | `Switch` | Living room / office shade-area occupancy | `zigbee:device:a7351eb531:001788011024c307:001788011024C307_2_occupancy` |
| `LivingOffice_Shade_Temperature` | `Number:Temperature` | Living room / office shade-area temperature | `zigbee:device:a7351eb531:001788011024c307:001788011024C307_2_temperature` |

A dedicated configuration tool owns only these three Item paths and three
Item-channel-link paths. It implements checksum-bound snapshot, plan, offline
rehearsal, exact apply/readback, close, drift refusal, recovery, and rollback.
It must never mutate a Thing, channel, persistence policy, rule, metadata,
unrelated Item, or Item state.

Before apply, the tool verifies all of the following read-only facts:

- The exact Thing is online.
- The exact three channels exist with the expected Item types.
- None of the desired Items or links conflicts with a different live resource.
- JDBC remains editable and has wildcard `*` coverage with `everyChange` and
  `restoreOnStartup`.

After apply, exact Item and link readback must match the desired resources.
JDBC history is allowed to be initially empty; once a channel emits, the first
persisted point must be readable through the explicit `jdbc` service. A newly
linked Item that remains `UNDEF` is reported as pending first acquisition; it
does not weaken exact Item/link verification and it cannot supply model input.

## Photosensor learning boundary

This change starts collection but does not emit photosensor-derived shade
events. Current training continues to use journal evidence and approved
historical reconstruction.

A later calibrated classifier may consume illuminance relative to outdoor
radiation, solar elevation, cloud state, south-glazing temperature, occupancy,
and the auxiliary Philips temperature. Until it has sufficient daylight
history and operator-confirmed shade transitions, its only permitted output is
`uncertain`; it cannot override confirmed, reconstructed, or inferred journal
evidence. Artificial light, darkness, saturation, and fast cloud transients
remain explicit abstention conditions.

## Failure behavior

Training fails closed on any rank-deficient matrix, infeasible constrained
solution, invalid physics, chronological leakage, weak promotion evidence,
missing mode, stale input, invalid forecast, or artifact validation failure.
The accepted-artifact registry retains the previous verified generation.

Photosensor configuration fails before its first write on schema, channel,
Thing, JDBC, receipt, or live-state mismatch. An interrupted write remains
receipt-recoverable; rollback restores exact captured Items and links without
touching unrelated resources.

An unavailable local shadow is never published. No stage in this repair writes
`Thermal_Advisory`, changes household rules, or invokes an actuator.

## Testing

Test-driven implementation must include:

- A synthetic full-rank dataset whose unconstrained optimum violates solar
  gain ordering and whose constrained optimum is finite, ordered, and accepted.
- Recovery of known constrained synthetic 2R2C and glazing coefficients within
  existing tolerances.
- Continued refusal of rank-deficient, infeasible, unstable, non-finite, and
  out-of-range models.
- An exact 400-day default-date-range test, including timezone-aware endpoints.
- Exact per-mode manifest counts and artifact-schema rejection of missing,
  unknown, negative, boolean, or sum-mismatched counts.
- Exact Philips Item/channel manifests, closed request allowlists, body/type
  validation, receipt integrity, rehearsal, drift refusal, recovery, rollback,
  and concurrency tests.
- A test proving wildcard JDBC coverage is verified but never written.
- A test proving no photosensor shade label is emitted by this change.
- Focused Python and JavaScript suites, full thermal/forecast pytest, full
  Vitest, production build, Playwright viewports, offline systemd verification,
  syntax/static checks, and clean-diff checks.

## Attended deployment gates

1. Install the reviewed runtime atomically and verify its complete manifest.
2. Snapshot, plan, rehearse, apply, verify, and close the three-Item/three-link
   photosensor receipt. Report initial live channel states and verify JDBC
   history when available; otherwise record pending first acquisition.
3. Run private Gate A schema audit, 400-day training, chronological backtest,
   and local shadow generation.
4. Require an accepted artifact covering all four seasonal modes, explicit
   Kiva exclusions, valid physics, at least two folds, finite metrics, a
   24-hour hallway-air result better than persistence, exact runtime revision,
   and a valid shadow payload below 16 KiB.
5. Stop and present this evidence before Gate B creates or publishes
   `Thermal_Model_JSON`.
6. Gate C systemd installation and timer activation remains separately
   authorized only after manual publication/readback, UI, log, advisory, and
   actuator invariants are green.

Timer activation authorizes future daily private 400-day training/backtest and
accepted-artifact replacement plus two-hour observational shadow publication.
It never authorizes physical automation.
