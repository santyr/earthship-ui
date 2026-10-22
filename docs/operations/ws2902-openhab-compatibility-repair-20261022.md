# WS-2902 rain display and OpenHAB compatibility repair

The 22 October station adapter stopped populating the existing rain and pressure aliases while the native OpenHAB overview still consumed them. The replacement HTTP numeric channels also declared quantity Item types instead of the binding's generic Number channel type. A first UI follow-up exposed only the latest receiver session's rain and removed the harvesting estimate. That did not preserve the requested behavior.

The repair restores the existing OpenHAB Items from accepted measurements, keeps the station pressure explicitly absolute, formats numeric rain/pressure to hundredths, and restores Home's inches / estimated gallons for today and the Sunday-based week. The harvesting estimate remains 3,500 sq ft × 0.623 gal per sq ft-inch × 80% efficiency. It estimates collection from recorded rain; it does not measure cistern contents.

Recorded calendar counts accumulate only accepted continuous counter increments. Restarts, source faults, gaps and increments straddling an unobserved period boundary do not supply rain. A private atomic ledger preserves these counts across worker reloads; it never restores measurement freshness. Initial recovery replays original persisted OpenHAB rain-counter receipts through the same validation and counter transition code. The separate complete-coverage calendar values, native evidence and forecast-learning qualification retain their existing rules. The tooltip describes recorded counts and excluded gaps; Home has no visible partial label.

A saved ledger error cannot interrupt other radio measurements. A stale writer cannot overwrite a newer ledger. The supported deployment has one Gunicorn worker. The ledger's private sidecar lock must remain beside it. Set WEATHER_STATION_RAIN_TOTALS to override the release entry point's /home/sat/.config/hex/weather-station-rain-totals.json path.

## Verification and rollout

- Reproduce against actual REST Items and the rendered native overview, including its state-event subscription. Reject item commands and state writes during browser inspection.
- Replay literal OpenHAB receipt fixtures: at the saved observation time they support 0.08 inches today and 0.22 inches this week, approximately 140 and 384 estimated gallons. These are time-specific observations.
- Verify restart recovery, stale-data withdrawal, source-fault barriers, midnight/DST, persistence failure, concurrency, display precision, and current legacy Item values.
- Check the exact scoped release with backend tests, all frontend unit tests, build and station browser cases. Review before merge/deployment.
- Before deployment, preserve exact source originals and REST definitions, prepare the bounded read-only history recovery and rehearse apply/rollback. Install consumers and metadata before activating the receiver. Reload only the HTTP worker; the RF listener needs no restart.
- Observe real receiver packets, then verify actual OpenHAB Item values against the receiver and inspect both the native overview and Home. Keep measured amounts and test evidence in the deployment receipt.

Rollback restores exact saved files and only owned REST definitions/metadata, followed by one HTTP worker reload. Preserve the ledger and all original rain-counter evidence; do not write fabricated readings or rewrite persistence history.
