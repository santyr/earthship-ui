# Capture-safe operational persistence baseline — September 23

The new read-only `scripts/audit-thermal-operational-baseline.py` uses an
origin-captured, single-issuance Open-Meteo forecast and receipt-qualified
initial indoor, mass and outdoor temperatures. Only after the 24-hour target
has elapsed does it pair a separate qualified indoor outcome. No observed
future weather, action state, model artifact, OpenHAB command, journal write or
advisory publication enters the score. Missing or post-target receipts cannot
be silently substituted.

The restricted `energy_power_reader` queried archived forecasts; the separate
restricted weather-temperature reader queried persisted atomic receipts. A
one-origin smoke check passed. The bounded chronological run used hourly
origins from `2026-09-20T00:45Z` through `2026-09-22T14:45Z`, with the end
exclusive at `2026-09-22T15:45Z` and a 24-hour target. It returned 63 paired
origins, zero unavailable outcomes, and:

| Selection | Pairs | Persistence MAE | Signed bias |
| --- | ---: | ---: | ---: |
| All overlapping hourly origins | 63 | 2.0314°F | −1.7914°F |
| Greedy disjoint 24-hour windows | 3 | 1.32°F | −1.08°F |

The overlapping result exactly reproduces the earlier availability census.
The disjoint result is only three warm-season observations, not an independent
seasonal holdout. The code explicitly reports `model_scored: false` and
`action_benefit_proven: false`. Neither number is a physical-model score or a
graduation threshold. Next: pair frozen candidate forecasts with the same
origin/outcome identities, require action-forcing provenance and reserve
chronological seasonal holdouts before any model or advisory promotion.

Verification: 40 related baseline/origin/archive/temperature tests passed.
The live audit was SELECT-only and made no
production configuration, Item or journal changes.
