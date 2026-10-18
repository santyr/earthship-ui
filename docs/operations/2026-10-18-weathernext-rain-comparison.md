# WeatherNext precipitation comparison foundation

Observed 2026-10-18. Task 7 increment; no precipitation product is qualified or selected, and household production remains unchanged.

## Source and comparison contract

`weather_learning.energy_shadow` now compares the three separately retained Google rain products with the existing source-qualified local counter-day reader. It does not accept a bare numeric daily Item as a label. The native JDBC reader has an optional source-capture callback, invoked only after its existing complete-day qualification succeeds; the default return and SQL/role/timeout/transaction behavior remain unchanged. Capture failure refuses the read and still closes its connection. No callback runs on invalid evidence.

Each private rain-source capsule retains exact original receipt strings and persistence timestamps, sensor policy, source activation cutover, timezone, native summary and original availability. Its source hash excludes only the later assessment clock, so rereading the same original receipts does not manufacture another outcome. The comparison replays the existing native daily validator and requires the complete summary/hash to reproduce. Invalid packets, gaps, counter faults, incomplete/activation days and excessive boundary uncertainty remain refusals. Hashes bind retained bytes; they are not sensor signatures or proof of physical gauge calibration.

The shared prospective-source check was extracted from the temperature feature builder. Both temperature and rain rederive normalized points from the original Google rows and validate source/run/availability clocks; numerical temperature behavior is preserved. A daily rain forecast must both start and finish its household issue before the local day begins. Original snapshot identity, decision/completion clocks, native grid and each product's complete trailing-hour total are retained. Later completion cannot be backdated into a day-ahead forecast.

The fixed operational comparison rule is **the latest retained issue strictly before local day start**, selected before looking at product missingness or local outcomes. Equal-time conflicting originals refuse. If any of the three products lacks an hour, that day is withheld for all three; an older, easier issue is not substituted. All products therefore use identical days. Compare paired complete-day MAE in millimetres, with RMSE, signed bias, p95 absolute error and MAE bounds from the native midnight uncertainty. Wet, dry and boundary-uncertain observed cases and forecast horizons are reported separately. Native grid, sensor policy, activation cutover and receiver epoch define independent cohorts; there is no pooled cross-epoch skill number.

Reports remain SHADOW_ONLY, `diagnostic_comparison_only`, with `selected_product=null` and automatic actuation false. They do not select a product on an opened final holdout, claim an untouched holdout exists, or authorize production. Chronological selection/frozen-choice later assessment and adequate actual precipitation events remain unfinished requirements from the [capture/qualification contract](2026-10-18-weathernext-rain-candidates.md). No new numeric event gate was added.

## Actual integration evidence

A bounded, read-only audit at **19:35:15Z** revalidated six retained original household issues and their exact Google source snapshots, producing one current prospective October 19 comparison decision. Native rain history qualified October 15 and 16 from **2,876 and 2,868 original receipts**, respectively, in the same receiver epoch; October 17 was withheld. Exact private source capsules were retained with mode 0600. These earlier local days cannot be paired with the first October 18 Google decisions.

The report correctly contains **zero paired days** and withholds October 19 as `NO_QUALIFIED_OUTCOME`; it does not reconstruct older forecasts or treat future rain as measured. Report SHA256: `bb3c9007ea29f45cba3222b974cf4ce2c09e6b5e01ec5b74b76e9d84e47066c9`. No cloud request, production publication, model fit, IAM change or actuator call occurred. This was a one-shot research audit, not a newly scheduled rain-scoring service.

## Verification and remaining work

Test-first checks cover qualified-source replay, forged summaries/normalized values, native capture/refusal/connection closure, incomplete and invalid source days, missing common products without issue substitution, late issue completion, historical source refusal, same-epoch aggregation and separate-epoch partitioning, duplicate reassessment, conflicting source bytes, and wet/dry/uncertain-boundary treatment.

- Full pinned WeatherNext Python suite: **139 passed in 4.482 seconds**.
- Existing forecast intelligence plus native rain history/day regressions: **148 passed in 1.64 seconds**.
- Actual original-source/native-reader integration audit: passed with zero eligible paired days, as required by current timing.

The scorer is committed research code; the installed collector/inference/training release remains f5775f8. Task 7 is incomplete: actual paired precipitation outcomes, chronological selection/assessment, irradiance timing/energy comparison, fixed-artifact PV/storage/thermal forcing attribution, fresh downstream Google/local fitting and required-variable qualification still need completion. Existing cutover gates remain unchanged.
