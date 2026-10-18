# WeatherNext comparison publication activation

Observed 2026-10-18. This extends the [private backend activation](2026-10-18-weathernext-shadow-activation.md); it does not select WeatherNext as the production provider or qualify predictive skill.

## Installed state

The immutable private backend remains at `f5775f8132a35b177ba503d6fc605e1b9d94df47`, including separately retained precipitation products. Existing collection, inference and weekly training timers remain enabled under shared resource admission. Only the owned local-recording override that omitted `--publish` was removed, restoring the canonical shadow service's `--publish --include-incumbent` arguments. The previous override is retained privately. No credential, grant, resource policy, incumbent forecast unit or actuator authority changed.

Exactly three previously absent String Items were added through `/etc/openhab/items/forecast-provider-shadow.items`: `Forecast_Provider_Status_JSON`, `Forecast_Comparison_JSON` and `Forecast_Local_Shadow_JSON`. Installed file SHA256: `0d1b7607446e5707425a59178283999ed79f8eecba07b057631c0360d45a73d8`. Readback at 18:59:47Z verified `editable=false`, no groups, no links and initial NULL states. The live rule inventory had no references or generic wildcard Item triggers for these additions. OpenHAB hot-loaded the file; its PID remained 3693697. Ownership rows were appended only after actual file-provider/state verification. Here `migration=verified` records that narrow ownership/publication check, not whole-JVM restart or recovery qualification.

The first explicit publication completed at 19:00:51Z with all three Item states identical and READY, 337 future-hour targets, and an explicitly untrained local candidate. Status is published last; consumers refuse unequal generations. Subsequent publication at 19:12:57Z carried generation `7bf8ff3362c55814514dacb4329a2c1f5fd846fac81ed6f607ed538d86796951`, again identical across all three Items, with automatic actuation false.

## First candidate and UI

An explicit run of the already staged training service completed at 19:04:45.057621Z after the first retained prospective target elapsed. It fitted a fresh Google/local candidate from **one qualified pair on one target date**, through 19:00Z, with model SHA256 `1bc9df70ca8a90bacfa5303b8323edc48198b0b1162a57f057c86ff61c138101`. Status remains SHADOW_ONLY and validation is null. One pair is not a complete qualified training day, a holdout score, demonstrated skill or promotion evidence. No incumbent learning state was imported.

The live Weather page now exposes **WeatherNext comparison · shadow** in the ten-day forecast tile. Its read-only dialog separates incumbent corrected temperatures, raw WeatherNext and the local candidate, with training support, source clocks and an explicit unqualified warning. Only this feature was added to the live root UI; its existing Astro, AQI and other overlays were preserved. A private preimage and exact reverse comparison verify preservation. No UI service restart was required.

Real browser inspection found the comparison button positioned against the page because its forecast-cell ancestor lacked positioning. The narrow fix adds `position: relative` to `.daily-cell`, preserving grid dimensions. Geometry tests failed before the fix and passed afterward. Live unmocked rendering passed at 1440×900 and 1024×768, with 24 forecast rows, contained dialog bounds, functioning close, no console errors and no mutating REST requests. Screenshots and extracted forecast data remain private.

## Verification and limits

- Full migration-branch frontend suite: 2,585 tests passed in 42.24 seconds.
- Focused live-root parser/component/Weather integration: 20 tests passed.
- Fixture browser geometry/click/focus: two tests passed at 1340×800 and 1280×720.
- Live-root production build passed in 1.49 seconds; existing chunk-size warning remains.
- Full live-root UI suite: 2,217 passed and 11 failed in five files. An isolated copy with only this feature removed reproduced exactly the same 11 failure names; no additional failure names were introduced. Those failures concern `alert-staleness`, `home-card-state` (six Astro/season/daylight expectations), `Earthship` thermal-card order, `SeasonCountdown` and `ThermalModelCard` (two presentation expectations). This is not a green full-root suite and is not a production-cutover qualification claim.

Natural collector execution was already verified at 18:35Z. The 18:40Z shadow trigger still used local-only recording. The first **natural published** shadow trigger is now verified: timer 19:40:31Z, service success/exit 19:40:32Z. Its retained original issue `f4a0bbbe5ba05e2cf877a701a609dce16580e0022e41434a865b9a075560b1d7` exactly matches all three live Item states, READY with 337 targets and the one-pair SHADOW_ONLY candidate. Source snapshot `ad52a362ec0b4952b5d8550a9a75671443b3d267c4decc9ba70c2215eea45247` came from the 19:35:37Z natural collector trigger and completed at 19:35:48.221224Z; all 4,320 normalized points rederive from the originals, including 360 hours for each rain product. This proves natural matching publication, not additional acquisition days or model skill. Existing 30-day acquisition, 14-day normal local-model shadow and training/holdout/required-variable gates remain incomplete. Household production forecasts still use the incumbent. Complete Open-Meteo removal remains part of the attended production cutover, not this comparison rollout. Recovery/restart rehearsals remain deferred.


The 11 live-root failures reproduced on the isolated pre-feature baseline were:

- `alert-staleness`: subscribes only to two update topics and never renders their duplicate values.
- `home-card-state`: counts browser-local calendar days to the 2026 autumn equinox.
- `home-card-state`: uses singular and event-day seasonal wording.
- `home-card-state`: counts local calendar days across daylight-saving changes.
- `home-card-state`: rolls from the December solstice to the next spring equinox.
- `home-card-state`: declines dates outside the supported astronomical approximation.
- `home-card-state`: rounds daylight to whole minutes before carrying into hours.
- `Earthship`: adds the shadow model beside existing displays without changing advisory or zone order.
- `SeasonCountdown`: advances its local-date label after midnight without a reload.
- `ThermalModelCard`: labels modeled values, candidate timing, confidence, and age without promising action.
- `ThermalModelCard`: renders unavailable without exposing forecast or candidate copy as advice.
