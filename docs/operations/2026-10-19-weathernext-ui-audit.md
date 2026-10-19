# WeatherNext UI audit and live repair — October 19

The fixes are deployed to the live UI. The [verification record](2026-10-19-weathernext-ui-audit.json) covers Weather, Home, Energy, Earthship and Today/Tomorrow detail at 1340×800 and 1280×720. Before/after screenshots and original readbacks are retained privately; household screenshots and credentials are not published in Git.

| Finding | Result |
|---|---|
| Google cloud cover was retained in original forecasts but discarded from UI payloads; all source weather codes are null. | Carry cloud cover into hourly and daily presentation. Render labeled display estimates from cloud cover and precipitation, with native Astro day/night for hourly icons. Do not invent WMO codes, precipitation types, rain probabilities or moon phases. |
| Trace mean precipitation made every day look rainy and displayed positive amounts as `0.00″`. | Trace amounts show `<0.01″`; condition glyphs use separate hourly/daily depth thresholds (0.1/1 mm). These are display heuristics, not calibrated categorical forecasts. Actual totals remain visible. |
| Both charts still plotted unavailable precipitation probabilities. | Plot forecast depth in inches when probabilities are absent, with a practical 0.01-inch minimum axis range. Preserve percentages when actually supplied. |
| Today's full-day extrema were null because the latest issue cannot supply the elapsed part of the day. | Show the available future temperature range explicitly labeled **remaining**; do not claim complete-day extrema or fill incomplete future days. |
| Daily rows and detail contained repeated unsupported probability/PV placeholders. | Display available precipitation totals and supported metrics. Local correction is explicitly labeled **shadow**, separate from the live WeatherNext forecast. |
| Home/Energy read retired daily PV fields while a fresh sealed PV view already existed. | Read the existing expiring, read-only energy observation. Show remaining-today potential and an eight-period, 24-hour potential outlook. Keep modeled capture separate and conditional; estimates remain uncalibrated. No new forecast, fitting or seven-day PV model was added. |
| Earthship reported forecast unavailable because its advisory depended on the retired prediction receipt. | Use the current validated thermal publication for status and fresh normalized Google data for tomorrow's outdoor temperatures. Do not revive old advice or turn an unqualified forecast into permission to act. |
| Compact history margins compressed the PV and laptop SoC plots; the outlook footer overlapped values. | Use compact chart margins and overlap suppression for Energy's single-series charts; fix outlook flex sizing. Keep the existing 44-pixel touch controls. |

The current conditions icon was also traced to a fresh local station/Astro radiation-ratio calculation. It remains separate from forecast-derived icons.

## Verification

- 158 affected frontend tests across 15 files passed; 221 WeatherNext tests and 147 subtests passed. The production bundle builds successfully.
- Twelve final live page/detail checks passed: all forecast glyphs present, PV data visible, thermal status ready, no page errors, no attempted state writes, no page overflow, and no PV footer/value overlap at either size. Screenshots were visually inspected.
- The cloud-only publisher delta preserves the original numerical forecasts, Item ownership, shared lock and source/resource admission. It changes one of 28 pinned publisher files, outside the native model's runtime binding.
- Applying exact patches preserved unrelated live checkout overlays. No model retraining, OpenHAB/host restart, actuator change or production resource-limit change was made.

The full local frontend runner encountered IPC failures and is not reported as passing. Hosted CI runs on the pushed source. Temporary development jobs were reduced and serialized after shared resource deferrals; the native forecast recovered with its existing safeguards and final live checks verified the fresh publication. Unsupported Google fields and genuinely unavailable source-dependent estimates remain unavailable rather than being fabricated.
