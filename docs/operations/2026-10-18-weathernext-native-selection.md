# Native Google configuration and execution selection

Observed October 18, 2026. This completes another Task 8 preparation increment; production provider selection and the full migration remain unfinished.

## Explicit source selection

Two closed configurations select Google native inputs:

- `earthship-weathernext-thermal-live-config/v1` uses complete candidate validation.
- `earthship-weathernext-thermal-live-config/v2` uses the existing externally pinned model-verification receipt.

Both replace `forecast_dsn_file` with `weather_source`. This source has exactly `schema=earthship-weathernext-native-source/v1`, `archive_directory` and `site` (latitude, longitude, IANA timezone). Extra fields, incumbent forecast credentials, malformed sites and archive aliases refuse. Existing token, local measurement/journal configuration, shared lock, model/runtime identity, evidence directory, geometry and native measurement cutover fields keep their validation. Receipt serving still requires its pinned receipt and externally selected deployment stage.

The native publisher and household lazy collector now construct the archive-only backend for either Google profile. Preparation, current and retained scoring, monitoring and deployment staging recognize the same profiles. A Google publisher refuses incumbent weather inputs before any telemetry write. Missing Google data never selects the old forecast database. Current operational scoring retains support for older immutable native archives that have only their original schema constants; archived numerical functions and hashes remain unchanged.

Inference opens the existing archive and SQLite index read-only. It cannot create directories/schema, chmod the collector's index or store snapshots; a missing archive refuses without initialization. Unit tests verify that even a direct SQLite delete fails and opening/reading preserves the original index bytes, modification time and mode. The collector remains the writer. Withdrawal configuration remains loadable without an archive, candidate or prepared geometry.

## Staging and fitting boundaries

Immutable deployment staging recognizes both Google profiles and retains receipt/dispatch pins. It permits replacing the forecast credential with the explicit archive source, while unrelated credentials, lock and base URL remain pinned. Google release preparation may have a new committed numerical source closure, as required by fresh fitting and retirement; an ordinary incumbent model switch still requires the exact original base runtime. All new committed source bytes, original dependencies and candidate/runtime identities remain checked. Staging is separate from model qualification and service handoff.

These package/routing tests use synthetic model metadata where stated. They do not establish predictive skill, reuse permission for incumbent weights, or release authority. Actual fresh fitting must use the final Google-only source closure. Preserve the installed newer irradiance/shade model family when porting the release; an older checkout fixture is not a replacement model.

## Actual private source check

A copy of the actual installed private configuration was translated to the Google receipt-serving profile and loaded from a private preparation directory. The installed configuration and all existing model/receipt files were left unchanged. Backend construction and forecast selection used actual private local-source configuration paths and a real retained Google snapshot. SQL connections and network connection creation were forbidden during this check. No model admission, collection of new household telemetry, API request, forecast publication or service change occurred.

Preparation began **2026-10-18T22:46:44.730458+00:00** and completed **2026-10-18T22:46:45.443919+00:00**, using cutoff 2026-10-18T22:46:44.730458+00:00 and target origin 2026-10-18T22:50:15+00:00. It selected **26 bracket rows** in **0.713 seconds / 96360 KiB peak RSS**. This is `SOURCE_SELECTION_PREPARATION_ONLY`, not an as-issued production forecast.

Private immutable receipt: `658f9d2049c0db2688de0e6da9181c4dba9603bdc482a4cc584bdb03765c727f`. Retained Google snapshot: `8cc3a3d8a7267f441c2ed828bf641e8b8630a6077f383f0521ce65427cca9ece`. Originals and translated private configuration remain outside Git and browser assets. The old model was deliberately not admitted under the changed source/configuration.

## Verification and remaining work

Fifteen focused Google configuration/routing/source tests cover both profiles, field/path damage, read-only SQLite access, lazy collection, original Google publication, owned receipt preparation/driver/score routing, older archived scoring, and differing-source Google staging with an incumbent negative control. The complete relevant native preparation/publication/deployment/scoring set passed **115 tests in 18.89 seconds**. The pinned WeatherNext suite passed **175 tests in 6.142 seconds**. Native input/runtime/household weather/physical energy regressions passed **140 tests in 55.87 seconds**. The final staging-only fix was followed by the complete 115-test relevant set; no numerical/model code changed. Tests run in an immutable Git export, without changing live or working source permissions.

Real installation, final Google-only code/configuration removal, fresh weather-dependent Google/local fitting, variable/regime/outcome and prospective interval qualification, production release ownership and retained publication attempts, natural publication and final whole-branch review remain required. The existing production service still selects its incumbent configuration. No resource policy, actuator/notification authority or recovery scope changed.

## Operational caller and score-dispatch retirement

The prepared household publisher, score coordinator and deployment/runtime verifier
now select only the two Google configuration profiles. They no longer construct
the provisional producer, translate its forecast credential, refresh its metric
report or run a non-native archived scorer. Literal Google profile checks also
prevent an archived module's schema aliases from re-enabling an old factory.

Score dispatch is now earthship-native-score-dispatch/v2, with exactly schema,
current and historical. A fresh Google cohort starts with an empty historical
list. Retained entries must be independently pinned Google receipt-serving stages
and configurations. The family writer, scheduled training package, dispatch reader,
handoff and installer use this contract together. Version-1 dispatch records are
not accepted or rewritten in place. The unused legacy executor is removed.
The existing 63-stage inventory bound, 31-model process envelope, rotating native
slots, shared lock, source checks and deadlines are unchanged.

A separate verify_handoff_baseline verifies prior stage/preimage bytes for
ownership transfer only. Active verify_stage rejects the retired deployment
profile and validates the new candidate. The metadata reader does not construct
an old producer or initialize the fresh model from old weights. Initial cutover
can retain original service/configuration preimages without retaining an active
legacy scorer. Later Google upgrades retain their explicit Google score history.

Verification: **256 tests passed across 30 affected modules in 72.16 seconds**,
using shared host admission and a committed isolated export
f85dff5d8f1b40811e68b0b71f3138a896bfd255. All 23 changed Python/test files matched
that clean export. Coverage includes the thirteen new retirement regressions,
genuine fourteen-parameter fit evidence, native score/report reconstruction,
historical selection, source/candidate identity, staged handoff/installation
integrity, daily training and real memory-event protection. These are development
tests, not site skill or a production qualification report.

The published predecessor's Forecast ML run found two stale source-closure test
parameters for removed capture helpers. They now exercise the actual neutral
weather_source_files.py and openhab_runtime_io.py dependencies; the focused
43-case verification passed before the complete affected suite. The old helpers
were not restored to satisfy those assertions.

## Shared native helpers separated

Current native artifact, publication, household, score and deployment callers now
import their operational helpers from thermal_model/native_operational_io.py,
without loading the old provisional publisher or monitor. The unchanged serial
resource verifier moves to thermal_model/serial_publication_caps.py, which the
old CLI temporarily reexports. Cold-start coverage blocks all four old standalone
publisher/monitor imports while current native execution and the scoring-policy
context initialize.

Seven helper function ASTs and the serial resource verifier exactly match their
originals. Receipt verification accepts the issuing native clock explicitly;
actual persisted receipts, two attempts, retry pacing and guard checks remain.
The complete base source binding now contains 85 files, including both new
helpers. This is source separation, not permission to reuse old fitted weights.

Verification: **336 tests across 41 modules passed in 94.64 seconds**, with one
explicitly capped-scope resource smoke test skipped. A further **27 pressure and
forecast-budget tests passed in 0.50 seconds**. All changed Python/test bytes match
committed isolated export f2ee3817aa75823d940a7126080c3399abed4a79, using the pinned
Solar_PV companion. The 211-test pinned WeatherNext package also passed in
8.602 seconds. A diagnostic run exposed a fixture importing the native resource
alias while its dependency was mocked; initializing the original module first
fixed isolation without weakening the source-location guard. No numerical
assertion or resource threshold was relaxed.

Standalone obsolete CLIs/loaders and the remaining provider/worker source graph
still need retirement before the final source freeze, fresh release fitting and
attended cutover. Their files remain present; no broad source deletion occurred.
Installed services, models, credentials, binding/links, root UI overlays and
actuator authority were unchanged. No recovery rehearsal ran.
