# Capture-safe thermal replay origin census — September 23

Read-only live census at approximately09:20 MDT. No training, model scoring,
advice, journal write, OpenHAB mutation or synthetic telemetry was performed.

The query tested63 hourly five-minute-aligned 24-hour origins from
**2026-09-20T00:45Z through 2026-09-22T14:45Z**. For each origin it required:

- one complete Open-Meteo hourly bracket from one issuance, with both issue and
  actual capture times no later than the origin;
- three receipt-qualified initial temperatures (indoor air, north-wall mass,
  outdoor), assessed as known at that origin;
- an append-only action/mode snapshot limited by both receipt time and actual
  database creation time; and
- one receipt-qualified indoor-air outcome exactly24 hours later, assessed as
  known at that outcome time.

All **63/63** origins passed these input/outcome availability checks. The
naive indoor persistence baseline (origin air temperature as its 24-hour
prediction) has MAE **2.0314°F** and signed initial-minus-outcome bias
**−1.7914°F** on those63 overlapping samples. They comprise24 origins each
on September20 and21, plus15 on September22. These hourly origins overlap
strongly; this is not63 independent days, a held-out seasonal test, a physical
model score, a calibrated interval test, or evidence of advisory benefit.

Action knowledge remains incomplete: the live origin assembly has Kiva and
outdoor-shade history, but no vent or indoor-shade history. The Kiva source is
model-inferred. As-of availability does not prove compliance with actions or
qualify future action forcing. The next work is a scored operational replay
that uses these origin-time inputs, compares the physical model and frozen
baselines on chronological non-overlapping holdouts, and refuses any origin
whose action/outcome evidence cannot support the particular claim. The current
shadow model remains unpromoted.
