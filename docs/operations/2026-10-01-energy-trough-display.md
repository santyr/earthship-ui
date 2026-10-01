# Restored Energy estimated trough

The Energy battery-history footer displays one **Estimated trough** using
`Forecast_PreDusk_Trough_Receipt_JSON`. It does not fall back to the retired
morning estimate or held numeric Items. Invalid or absent receipts remain hidden.

The latest valid pre-dusk issue stays displayed until replaced. After its
following-morning 11:00 Mountain target window, the footer explicitly appends
the forecast night (for example, `Sep 24 night`). Its tooltip identifies it as
an estimate, not a measured minimum. This display-only completed-window opt-in
does not relax parser expiry for alerts or backend forecasting/scoring.

The chart retains only measured SoC history, smooth lines and its existing
30-minute history refresh. No extra series, synthetic projection, increased
polling or equipment control was introduced. Footer wrapping accommodates the
Lenovo M9 and laptop widths.

Verification: all 1,985 frontend unit tests, all 15 Energy browser tests
(including 1340x800 Lenovo and 1280x720 laptop layout checks), and the production
build passed. The build retains its existing large-chunk advisory. The new
browser and completed-window regression were first observed failing before
implementation.

Local deployment restarted only the user-level `earthship-ui.service`, which
is active/running and transforms Energy.svelte successfully. A read-only
headless browser at the Lenovo viewport verified one `Estimated trough 64%`
label and a visible battery-history SVG. No OpenHAB restart or control change.
