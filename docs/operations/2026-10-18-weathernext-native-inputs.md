# Google originals in native thermal and energy inputs

Observed October 18, 2026. This is Task 8 source/consumer preparation, not production activation or variable/model qualification.

## Source contract

weather_learning.native_forecast prepares a separately versioned Google-only forecast capsule from the private archive. It preserves the complete original API headers/rows in bounded compressed form and rederives the full original snapshot digest on replay. Selected temperature/GHI/wind rows are reconstructed from those originals; fabricated legacy metric receipts, edited derivatives and unsupported weather codes are refused. Raw originals are retained without storing another full normalized point array.

The capsule keeps initialization, actual archive acquisition, selection cutoff and model origin separate. Selection requires acquisition before the cutoff and cutoff before origin. It uses the existing Google 24-hour initialization-age policy; the legacy six-hour policy remains unchanged for incumbent records. Applying the latter to Google would reject normally delivered runs about eight hours after initialization. The first UTC hourly row is at or before origin and the last brackets the horizon endpoint. Missing bracketing values refuse rather than extrapolate, zero-fill or select another provider.

Temperature converts to Fahrenheit, native trailing-hour solar energy to mean W/m², and wind to mph. The same native five-minute interpolation and physical input bounds are retained. This does not reinterpret hourly energy as measured instantaneous irradiance, refit physical gains or qualify solar accuracy. Weather codes remain null and the household weather-code evidence is explicitly unavailable.

weather_learning.native_backend creates the existing bounded native collector with this source reader. Its private configuration has no forecast-database credential or field; Google failure cannot enter the incumbent PostgreSQL branch. Local temperature/journal readers, source epochs, latent-state observation, retained query evidence, shared-lock guard and fixed telemetry write scope remain intact. The private Google archive still uses its SQLite eligibility index.

## Immutable source and private context changes

The complete native prediction closure is now 83 Python files. Source-inventory metadata capacity increased from 72 to a bounded 96 entries so every new parser/backend dependency can be pinned. Per-file checks, interpreter/dependency hashes, CPU/RAM/swap/pressure/OOM/fitting guards and operational deadlines were not relaxed. An old fitting receipt under a different runtime correctly refuses; a fresh bounded fit on synthetic local data was used to test real-runtime candidate creation/write/read within the unchanged 16,384-byte candidate limit.

Actual installed-context sizing found 244,485 bytes before adding Google originals, including a 131,009-byte prepared thermal model and 14,670-byte incumbent forecast. Retaining the complete Google source requires more than the remaining room. A Google-specific private weather context/projection v4 therefore permits up to 512 KiB; versions 1–3 retain their original 256 KiB limit. v4 requires a verified Google source and native geometry, so relabeling an incumbent context cannot obtain the larger limit. The 2 MiB decoded original-capture limit, prepared thermal bound and public forecast 64 KiB limits remain unchanged.

Native cycle, weather, energy-configuration and measured-weather snapshot consumers now accept that typed v4 envelope. A valid high-volume native-statistics fixture exceeds 256 KiB, passes native/frozen/physical-energy consumers below 512 KiB, and refuses when relabeled as an older schema. No artificial padding or validator bypass establishes that result.

## Evidence and verification

A retained-source replay used the original 20:15:15 UTC reference origin and its retained action context, with a 20:14:45 cutoff. Its Google snapshot ad52a362ec0b4952b5d8550a9a75671443b3d267c4decc9ba70c2215eea45247 was initialized at 06:00 and actually acquired at 19:35:48.221224 UTC. It produced 26 bracket rows (20:00 through the next day's 21:00) and 288 five-minute forcings, preserving the retained shade/vent values. Its capsule is 70,403 bytes and contains 279,214 uncompressed original-source bytes.

Replay was created at **22:25:34.535771 UTC** and completed at **22:25:35.539242 UTC**, in **1.007 seconds / 88,976 KiB peak RSS**. This is explicitly RETAINED_ORIGIN_REPLAY_ONLY: it is not a forecast published at the earlier origin, a fresh action observation, a model fit or a scored outcome. Immutable private receipt: cfdb9f8fcaca0e91636cca1d984bde7bd46f22f8f27c26485db4677262988b51. Raw originals remain private, not repository fixtures or browser assets.

Tests first exposed missing Google source dispatch, unexpected legacy weather SQL, unknown-code evidence incorrectly retained as usable, and legacy private framing rejecting valid larger Google originals. Real runtime binding also exposed the 72-file metadata ceiling. All were diagnosed before the corresponding changes. Test setup was corrected where an old fake fitting environment was appropriately refused and where the candidate writer required a precreated private directory; fitting provenance was not weakened.

Final checks: **175 pinned WeatherNext tests passed in 5.777 seconds** and **140 native/household/runtime/energy regressions passed in 55.78 seconds**, including complete capture, frozen no-I/O replay, physical PV, causal bracket/site/age checks, all original-source tampering cases, real runtime pins and fresh synthetic candidate round-trip. Tests run in an isolated Git export with immutable source modes; no live/working-source chmod bypass was used. Frontend files are unchanged in this increment; the preceding 2,591-case frontend/build results remain applicable.

## Remaining release work

The installed newer irradiance/shade model family must be preserved when porting these interfaces into the final immutable deployment. Current numerical fixtures do not authorize replacing it with an older model. The native live/serving configuration and worker still need deliberate Google selection and removal of their legacy forecast-credential requirement; creating a backend factory alone is not an installed selector.

Prepare the final combined Google-only removal/source closure before fitting real release artifacts, because subsequent code retirement changes the runtime binding again. Preserve the strict fit/runtime checks. Complete fresh Google/local weather-dependent fitting, required variable/regime/outcome evidence, qualification intervals, release/ownership/lock integration, retained publication attempts and final whole-branch review. Apply complete Open-Meteo removal in the attended cutover; no dormant fallback or capture-only integration may remain. Recovery finishing stays deferred.

Production schedules, installed model/artifacts, current UI source, notification behavior and equipment authority are unchanged.
