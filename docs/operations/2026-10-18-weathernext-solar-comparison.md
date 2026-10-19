# WeatherNext solar exposure and timing comparison

Observed 2026-10-18. Task 7 increment; this does not select the production provider, fit PV coefficients or qualify direct-component/calibrated irradiance skill.

## Source and interval contract

Google documents surface downward radiation as hourly SSRD/GHI energy and total-sky direct radiation as hourly FDIR/direct-beam energy, both in J/m². The comparison retains the two native mean products separately and converts each trailing-hour energy to Wh/m². It does not reinterpret FDIR as measured local DNI, interpolate fractional-hour targets or sum marginal quantiles.

The local source remains the existing source-qualified lux proxy, including its fixed 126.7 conversion. It is not a calibrated pyranometer and cannot independently observe direct versus diffuse radiation. Reports therefore keep `calibrated_ghi_skill_qualified=false` and `direct_component_skill_qualified=false`; direct-versus-total-proxy numbers are explicitly diagnostic. These are statements of observability, not a new hardware purchase, numeric threshold or release gate. Existing qualification must account for proxy limitations without inventing calibrated physical ground truth.

The existing restricted JDBC window/day reader now offers an optional callback only after its native clean-window check passes. Default results, SQL, roles, timeouts and transaction/connection behavior are preserved. Partial windows emit no qualified capsule; callback errors are sanitized. Exact original receipt strings/timestamps, source policy/cutover, history digest, receiver epoch, original availability and native summary remain in private source capsules. Reassessment alone does not change source identity. Every comparison rederives the capsule through the native validator; a rehashed invented summary is refused.

`weather_learning/solar_shadow.py` isolates this responsibility from rain comparison and future PV/storage attribution. Its hourly exposure profile comes from native accumulated sample-and-hold windows, never an instantaneous numeric fallback. The Google original-source check is shared with temperature/rain. Household issue completion must precede or equal window start. The latest retained original decision is selected before source outcome or missingness checks; incomplete GHI/direct coverage withholds the common window without substituting an older/easier issue.

Receiver epoch, policy/cutover and native grid define separate cohorts. Paired overlap cannot inflate support; different window lengths have separate summaries. Exposure MAE/RMSE/bias/p95 and energy ratios remain distinct from hourly energy-centroid displacement and normalized shape error. Zero exposure is valid but has no invented ratio/timing. Timing/shape diagnostics require at least two hourly bins; one bin cannot demonstrate a timing match. This is research reporting, with no automatic product selection, fitting, publication or actuation authority.

## Exact coverage correction found with real data

The first source audit found an otherwise clean October 15 day whose 10–11Z hourly slice reported 3599.9999999999995 covered seconds. Floating addition made the native exact-equality check invent a coverage gap. The pure reader now accumulates covered elapsed duration in integer microseconds and compares it with the exact integer window duration. Radiation integration order and all source/expiry/fault/closing-receipt requirements are unchanged. There is no epsilon or tolerated missing interval: a one-microsecond genuine gap remains partial with no qualified total.

Synthetic fractional persistence alone initially did not reproduce the bug; a test with distinct allowed receiver/decoder/persistence microsecond clocks reproduced it before the correction. The actual October 15 source and all 24 hourly slices then passed. This corrects measurement arithmetic in the isolated research source; it does not change resource safeguards or install a new production reader.

## Actual integration evidence

A bounded read-only audit at **20:01:10Z** revalidated four original Google household decisions completed before the **19–20Z / 1–2 PM MDT** target interval. It selected the latest original decision before outcomes and paired that now-elapsed hour with **126 original qualified radiation receipts**. Its source epoch remains separate from the earlier days. The one-bin timing/shape metrics are correctly unavailable, and no calibrated/direct-component skill is claimed.

Two earlier local days, October 15 and 16, qualified from **2,883 and 2,873 receipts**, each with 24 native hourly exposure intervals in the same earlier receiver epoch. October 17 remains partial for actual coverage gaps and restart. These historical local days have no original prospective Google decision at their origins; they are source integration checks and cannot be scored as reconstructed old Google forecasts.

The resulting report contains **one prospective hourly pair**, no withheld target, and SHA256 `58a61e32434c83ddf554ff8760dab8be665881308d867a0f0c1738d99d9788c8`. Original extracts, capsules and code-file hashes remain private outside Git/browser assets; source files are unchanged between that audit and this committed increment. It made no cloud request, fit, database grant, production Item write or actuator call. It is a one-shot audit, not a new scheduled source owner.

## Verification and remaining work

- Full pinned WeatherNext Python suite: **152 passed in 4.711 seconds**.
- Native radiation evidence/config/history/window and thermal-source regressions: **164 passed in 1.30 seconds**.
- Tests cover source replay/forged summaries, partial/legacy/faulted/closing evidence, exact microsecond coverage and real-gap refusal, preserved default JDBC behavior, common-product missingness, original completion clocks, zero exposure, timing/energy separation, tails, epoch partitioning and overlap/duplicate rejection.

The installed collector/shadow/training release remains f5775f8; this increment was exercised from the isolated migration worktree. Required full-day/seasonal/weather-regime and incumbent paired comparisons, fixed-artifact PV/storage/thermal forcing attribution, fresh Google/local downstream fitting, existing release gates and full Open-Meteo cutover/removal remain unfinished. Neither a single hour nor the two unpaired historical source days satisfy those requirements.

Official references:

- [Google model variables and native solar units](https://developers.google.com/weathernext/guides/models).
- [Google 0.1-degree band catalogue](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p1deg).
- [Approved variable/qualification design](../superpowers/specs/2026-10-05-weathernext-exclusive-forecast-design.md).
