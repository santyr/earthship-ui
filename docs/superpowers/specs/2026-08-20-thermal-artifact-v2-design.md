# Thermal Artifact v2 Design

**Status:** Approved by the operator on 2026-08-20.

## Problem

The current two-state thermal model can fit `mass.air_exchange = 0`. With no
other mass-to-environment exchange, the transition matrix then contains a
neutral mass mode with spectral radius exactly 1.0, so the independent physics
gate correctly refuses the artifact. Relaxing that gate, clamping a fitted
coefficient, or adding an unconstrained bias would hide the structural defect.

## Approved model

Retain hallway air and north-wall mass as the only dynamic states and glazing as
an auxiliary observation. Add one bounded nonnegative mass-to-outdoor exchange:

```text
mass_next = mass
  + air_exchange * (air - mass)
  + outside_exchange * (outdoor - mass)
  + solar_unshaded * solar_unshaded_input
  + solar_indoor_closed * solar_indoor_closed_input
  + solar_outdoor * solar_outdoor_input
```

`mass.outside_exchange` is constrained to `[0.0, 0.20]` per five-minute step,
the same conservative ceiling as the existing mass-air exchange. It has no
bias term and is not clamped after fitting. The transition matrix becomes:

```text
[[1-air.outside-air.mass-air.vent*v, air.mass],
 [mass.air, 1-mass.air-mass.outside]]
```

Outdoor temperature remains an exogenous forcing, not a third state.

## Version boundary

The artifact schema becomes `earthship-thermal-model/v2`; dynamics version is
exact integer `2`; the mass coefficient vocabulary adds exact key
`outside_exchange`; and the constraints manifest records the new ordered name
and bounds. The registry fails closed on v1 candidates/accepted artifacts. No
silent migration is allowed because v1 lacks the fitted coefficient and cannot
be faithfully upgraded. Retraining is the migration path.

The public `Thermal_Model_JSON` shadow output remains its existing version-1 UI
contract because it carries forecasts/provenance rather than model coefficient
schema. No UI parser change is required solely by artifact v2.

## Unchanged gates

- Weighted five-minute fitting and action-confidence selection.
- Ordered nonnegative solar-gain constraints.
- Exact coefficient/bounds manifests and finite/rank checks.
- Independent sign, gain-order, spectral-radius, output-range, and 72-hour
  simulation validation.
- Chronological backtests, at least two scored folds, and 24-hour hallway-air
  performance better than persistence.
- All four seasonal modes, Kiva exclusion behavior, exact runtime revision,
  16-KiB shadow bound, accepted-artifact registry safety, and no actuation.

Zero remains a legal fitted value. If both mass exchange paths fit to zero, the
stability gate must still reject the artifact; the model must earn promotion
from evidence.

## Deployment boundary

Run the private Gate A schema audit, 400-day retraining, chronological backtest,
candidate validation/promotion, and local shadow generation. Preserve any prior
accepted artifact through the registry's atomic/quarantine behavior. Stop and
present evidence before Gate B creates or publishes `Thermal_Model_JSON`.
Gate C timer activation remains separately authorized after Gate B validation.
