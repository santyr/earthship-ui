# Trough miss and diagnostic-only origin components

Read-only comparison of immutable morning decisions against completed-night
atomic SoC outcomes and each day's maximum `MPPT60_EnergyFromPV_Today` Item:

| Issued day | PV forecast / Item max (kWh) | Trough forecast / qualified minimum | Signed trough error |
| --- | ---: | ---: | ---: |
| Sep 20 | 8.16 / 7.389 | 84% / 85% | -1 pp |
| Sep 21 | 7.35 / 7.237 | 77% / 84% | -7 pp |
| Sep 22 | 7.10 / 7.285 | 76% / 83% | -7 pp |
| Sep 23 | 3.42 / 6.557 | 59% / 83% | -24 pp |

The first three completed-night outcomes are already stored. The Sep 23
origin was assessed read-only after its 20:00–11:00 MDT target window:
890 atomic evidence rows, 99.8454% coverage, status `measured`, minimum
83% and signed residual -24 percentage points. That fourth outcome was not
stored or used for learning in this check; the ordinary Sep 25 06:40
assessment remains the persistence gate. The PV maxima are Item-level
production values, not independent qualified-PV receipts.

The Sep 23 model started near 85% SoC and, from its 3.42 kWh PV forecast and
5.49 kWh direct-demand coefficient, implied roughly 75% at dusk. The
observed change-only SoC Item was about 97% at 20:00. Under the model's
20.48 kWh bank and 0.95 efficiency assumptions, the 3.137 kWh PV miss
corresponds to about 14.6 SoC points; the remaining daytime difference
cannot be assigned to PV alone. Earlier nearly accurate PV forecasts still
preceded 7-point-low troughs. Demand, battery charge response, curtailment,
and overnight-drop assumptions need origin-linked validation. These are
diagnostic inferences, not causal decomposition or grounds to adjust a
safety-related alert from four nights.

Commit `85b1d83` adds only as-issued diagnostic fields to the local forecast
state: SoC reference, PV resource, dusk estimate, dated overnight-drop
samples/base/cloud penalty/final drop. The numerical forecast, advisory,
notification threshold and immutable advisory decision schema are unchanged.
All 143 focused forecast/advisory/qualified-SoC tests passed. Source and
installed producer SHA-256 both equal
`2b15a617a65022336055f6c8bac7840d59d9096d8f87efa97d2cae7ff90ed4ae`.
The exact prior installed source is privately recoverable at
`/home/sat/backups/earthship-energy/forecast-diagnostics-uJv7c2pD/forecast_intel.py.previous`.
No early service run or DM was made. Verify the new fields from the next
natural Sep 25 06:40 run before using them for calibration; do not alter
live trough advice until a separate prequential accuracy and safety review.
