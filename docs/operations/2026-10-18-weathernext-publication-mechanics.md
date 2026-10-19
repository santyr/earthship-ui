# Google-only publication mechanics and partial failures

Observed October 18, 2026. Task 8 preparation; **no production writer was activated**.

## Publication scope and ordering

The new transport-independent module, weather_learning.production_publish, prepares three existing forecast JSON Items plus eight retained numeric consumers:

| Item | Meaning / output unit |
|---|---|
| Forecast_Temp | First future hourly temperature, °F |
| Forecast_Cloudiness | Same target's cloud cover, % |
| Forecast_Radiation | Same target's native hourly GHI mean, W/m² |
| Forecast_Daily_High / Forecast_Daily_Low | Complete original local-day extrema, °F |
| Forecast_Daily_PrecipSum | Complete original local-day precipitation, mm |
| Forecast_Tomorrow_High / Forecast_Tomorrow_Low | Next local-day extrema, existing plain Fahrenheit numbers |

Unavailable numeric values are UNDEF, never zero. Unsupported AQI/UV/probability/weather-code Items belong to the removal patch. Old correction/error diagnostics belong to namespace reset/new scoring; independent PV/storage/thermal outputs retain their explicit owners. This publisher cannot write those outputs or any actuator.

A caller must explicitly supply its qualified deployment/ownership admission and bounded state writer/readback functions. Missing admission refuses before writes. No permissive production authorizer, live transport, scheduler or activation command is installed. The injected admission is an interface for the attended release worker, not a scientific gate assessment implemented by this module. That worker must verify actual release evidence and exclusive writer ownership under the existing shared lock, including permission to withdraw values when current Google data is missing.

The algorithm first publishes and verifies an unavailable detail marker, then writes/verifies the other ten outputs, then publishes/verifies the final detail. String states must match exactly. Numeric readback accepts equivalent finite values, including Celsius/Kelvin-to-Fahrenheit temperature conversion, inches-to-millimetres and explicit dimensionless quantities (`0.25 one` or `0.25 1` equals `25 %`). Bare unitless fractions and `25 one` are not accepted as `25 %`. Every write/read failure triggers attempts to withdraw all eleven owned outputs; one failed clear cannot stop the others. The result identifies unconfirmed withdrawals without logging private transport exception details. It never claims atomic multi-Item writes or successful clearing when transport prevents confirmation.

Home and Weather now suppress old hourly/daily fallback arrays when a parsed Google detail is unavailable or invalid. Weather displays “Forecast unavailable.” Incumbent missing-detail compatibility is preserved before retirement. Task 9 still removes that obsolete compatibility path from the final active project.

## Complete-day coverage correction

The provider previously computed daily summaries after discarding targets earlier than the current decision. That made today's daily summary unavailable even when the selected original run contained every required local-day hour. Daily aggregation now uses all mean points from that same validated original snapshot; hourly UI rows remain strictly future. No alternate run, observed-weather substitution, quantile pooling or backdated issue is introduced. Genuinely partial source days remain unavailable. Full source coverage is not a claim that an intraday issue was prospectively available before the day began; existing scoring origin gates remain required.

## Evidence

A read-only check verified the types of all eleven installed Items. Success and partial failure were then exercised **only against an in-memory store**, using real retained 12Z Google data and a validated live native Astro input. These were simulated writes and simulated authorization, not live PUTs or production admission.

- Decision: 2026-10-18 **21:17:21.464433 UTC**; completed **21:17:21.720249 UTC**.
- Google original snapshot: 07efc2fb281f344104118d57ac5ef296cc6f491b5f94cb7c38ea8128a3b962e2, acquired at **20:36:52.534100 UTC**.
- Prepared provider: 427a93067a1512a24f6af312c3527cf69b46aa13246cb27178b429d8bdfbb15b.
- Private immutable simulation receipt: e4e9a1671f3386ef45ea3093f6c3166a6ae70fa9915b7672413acd8add9d8ae3.
- Eleven simulated outputs verified; injected radiation write failure produced FAILED and eleven confirmed withdrawals. The actual UI parser accepts the successful detail, rejects the failed detail, and disables legacy fallback.
- Elapsed **0.281 seconds**, peak RSS **47,696 KiB**, unchanged shared admission. Original source hashes match final files; evidence is private mode 0600 and browser HEAD returns 403.

Tests first failed for the missing publication module, and both actual Home/Weather component tests exposed stale legacy fallback. A separate complete-day regression failed with None rather than the supported native daily high before the aggregation fix. Final checks: **167 WeatherNext tests**, **150 existing forecast/clock/Astro tests**, and **2,591 frontend tests / 172 files** passed. Publication tests exercise every one of twelve writes and twelve readbacks failing individually, persistent clear failure, missing source, denied admission, quantity conversion and distinct daily highs/lows. UI build passed in **1.47 seconds**, with the existing large-chunk warning.

The qualified release worker, retained publication-attempt recording, exclusive ownership/consumer lock integration, native energy/thermal input translation and fresh fitted-model serving remain unfinished. Required-variable/regime/outcome evidence, qualification intervals, complete Open-Meteo removal and final whole-branch review also remain required. Production forecasts, installed shadow runtime, notifications, equipment authority and resource safeguards are unchanged.
