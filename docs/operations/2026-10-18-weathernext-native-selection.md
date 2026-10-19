# Native Google configuration and execution selection

Observed October 18, 2026. This completes another Task 8 preparation increment; production provider selection and the full migration remain unfinished.

**Current source update (October 19):** both obsolete standalone publisher families and their uninstalled schedule templates are removed. Current native observation/receipt tests use the native Google publisher. The old thermal weather commands and their provider import are also removed; journal/schema commands and generic helpers remain. Shared Google/local acquisition classes remain. The base model source binding contains 81 files; the raw shared binding contains 76. The owner-approved 84-path source retirement is applied in `2f02e38`; installed provider/binding/state retirement still awaits coordinated cutover. The prepared production worker now consumes source-qualified native Astro, with [220-test and actual read-only evidence](2026-10-19-weathernext-native-astro-serving.json). Final source freeze, fresh release fitting and qualification remain required. Production has not cut over. Earlier sections below retain their historical audit status.

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


### Shared worker and tool import closure

The remaining six shared workers and four capture/qualification/deployment tools
now import the existing serial verifier directly. Astro collector identity and
thermal capture revision pin that verifier's actual source path. Every changed
production/tool AST matches its preimage after only the resource-import and
manifest-path substitutions. Resource thresholds, supervision and numerical
functions are unchanged. Only the three obsolete provisional entry points still
import the old publisher CLI; those entry points remain pending removal.

Two new regressions failed before this change and now prove cold worker imports,
collection admission and source closure without the old publisher. Relevant test
fixtures inject the verifier at its new boundary. The raw runtime source count
assertion is 77, accounting for the two helpers already added in the preceding
increment; the full native base remains 85. Forecast ML CI now explicitly selects
the operational import/source-closure regression module.

Final verification: **745 tests across 67 modules passed in 135.76 seconds**,
with two existing tests requiring a selected capped scope skipped. The pinned
WeatherNext package passed **211 tests in 8.808 seconds**. Every changed Python
source/test matches isolated export 7db29600ed1859703bb0d6e79a8d6282ea124825.
The first expanded run found the stale raw source-count assertion (710 passed,
one failed, two skipped); its expected count now matches the declared inventory.
No production resource safeguard or numerical assertion was relaxed. Live
services, installed sources, models, ownership and actuator authority were not
changed. This closes the shared CLI resource dependency, not the entire provider
retirement or production cutover.


### Provisional standalone family retired — October 19

Removed provisional_thermal.py, thermal_model/provisional_live.py,
thermal_model/provisional_monitor.py and household_score_queue.py, plus their
four uninstalled forecast/score service and timer templates. All production
imports were confined to this closed obsolete family before deletion; none
remain. Current source binding excludes its three fitted-runtime entries,
reducing the native base from 85 to 82 files. The raw shared binding remains 77.
Required mathematical fit/forecast/score validators remain available to native
execution. Installed model receipts and weights were not rewritten.

Twenty-nine observer, actual-receipt and cache-boundary tests now invoke the
current native Google publisher with genuine fresh synthetic fourteen-parameter
fit evidence. They passed before deletion and remain in the affected suite.
The native-query packet fixture moved unchanged to native_cycle_test_support.py;
its function AST matches the original, preserving native gap/absence tests.
Four test modules exclusively exercising the removed family leave with it.
Importability and obsolete-schedule regressions failed before retirement and
pass after it. Forecast ML CI selects the replacement observer tests and no
longer names the deleted test modules.

The complete affected **70-module suite passed 784 tests in 151.84 seconds**,
with two existing selected-capped-scope smoke tests skipped, from isolated export
13ab3c361641ff4f45b91d38e0587ae23882b342. The pinned WeatherNext package passed
**211 tests in 8.404 seconds**. The first wide run exposed a fixture still treating
the removed provisional worker as protected current model code; its tampering
case now targets the actual native helper. The full 24-case deployment module
then passed before the final wide run. Source-integrity checks remain strict.

The published predecessor's Forecast ML CI also found one stale raw source-count
assertion. Correcting that fixture for the two previously extracted helpers
passed its isolated registration test in **0.62 seconds**. Final export
be7cab1caa1019d770d5126ef0788e36ac388f2e adds only that test correction after the
wide run; numerical/operational source bytes are unchanged. Full new-head CI
remains separate evidence.

Closed historical handoff metadata and its fixtures still identify the original
worker/unit preimages; they cannot load or execute a removed producer. Installed
services and frozen runtime sources were unchanged. The installed-shade operator,
its legacy loaders/renderer and the remaining provider/worker/tool graph still
need retirement before final fresh fitting, qualification and attended cutover.
No actuator, resource-policy or recovery workflow changed.


### Installed standalone family retired — October 19

Removed thermal_installed_intel.py, installed_shade_schedule.py and
scripts/stage-installed-monitoring.py, their two uninstalled service/timer
templates and four exclusive old-operator test modules. Removed the six old
configuration loaders and WithdrawalBackend from installed_shade_live_inputs.
Mixed mathematical, registration, withdrawal and telemetry tests remain.

TelemetryTransport, SourceLiveBackend, CompressedSourceLiveBackend and the local
clock retain identical function/class ASTs. LiveBackend changes only its protected
source-set declaration to the same five values: release inputs, token, journal
DSN, native database configuration and native policy. The retired forecast DSN
is still explicitly refused before private reads. The closed Google configuration
field set and mandatory Google reader are unchanged. The optional old-CLI scorer
hook is removed; current serial/native resource verification remains. Native base
binding is 81 files and raw shared binding is 76. Installed weights and receipts
were not relabelled or changed.

The final affected **73-module suite passed 806 tests in 174.09 seconds**, with
two existing selected-capped-scope smoke tests skipped, using isolated export
693bee0326406aaaeefb6e2958805983a5cf4d09. The pinned WeatherNext package passed
**211 tests in 8.701 seconds** with the same production bytes. The last change
was confined to a test fixture and its regression. All new retirement regressions
were observed failing before source removal and passing afterward.

Predecessor Forecast ML CI failed eighteen observation tests because its toolcache
interpreter failed the immutable-source guard. A writable-interpreter reproduction
failed at the same guard. The fresh synthetic fit fixture now uses the existing
private_interpreter helper: an owned, non-writable copy with identical executable
bytes. The regression first proves that the original writable binary is refused,
then verifies the fitted candidate pins the original executable hash. The
regression and all observer/receipt cases passed (41 tests in 19.92 seconds)
before the final wide suite. No production guard or host interpreter permission
was changed. New-head repository CI remains separate evidence.

Remaining provider/worker/tool source retirement, final fresh fits, prospective
qualification and coordinated live ownership/cutover are unfinished. No live
unit, model, source release, resource policy or actuator changed.


### Old thermal weather commands retired — October 19

thermal_intel now exposes only journal and schema-audit. Its old train, backtest,
shadow, observe-candidate and release commands and their weather factories are
removed, including the implicit forecast-provider reader and payload adapter.
The retained module does not import forecast_intel. Its revision manifest drops
that source (26 to 25 entries); the current native/raw bindings remain 81/76.
This changes source identities and still requires final fresh release fitting.
No installed artifact or receipt was relabelled.

Sixteen retained helper function ASTs are unchanged, including schema auditing,
exact journal readback, vent/mode projection and original receipt archival. The
November no-vent default keeps the America/Denver timezone. JDBC parsing, current
measurement assembly and generic validated publication helpers retain their
logic but require explicit caller-supplied I/O callbacks. They cannot acquire
weather or select an implicit provider transport. Timestamped invalid-state
barrier and quantity parsing tests remain at the actual explicit reader boundary.
All mathematical model, fitting, outcome, sensor-identity and source guards remain.

Three exclusive old-operator test modules and old-command-only cases in mixed
modules leave with the removed functions. Mixed physical, fitting-proof, release,
measurement and journal tests remain. New cold-start and command-refusal tests
failed against the original implementation, then all seven passed. After updating
two integrity fixtures to tamper a retained pipeline helper, 61 focused cases
passed in 0.52 seconds. The complete 211-test pinned WeatherNext package passed
in 8.807 seconds.

The wider 160-module run passed 2,720 tests and skipped seven, with 24 fixture
failures in two modules (714.87 seconds, export
189aafcb43b3dd67b31505a2eefc7561c0c8aaac). Twenty-three failures came from a
historical replay fixture trying to classify the current, changed manifest as an
old replay runtime. It now constructs the original supported historical fixture
explicitly. One legacy installer test redundantly compared its already exact,
literal source list with today's changed module; it now keeps those independent
historical assertions. No archive reader, installer, acceptance rule or production
source changed to accommodate the fixtures. Both complete affected modules then
passed **111 tests in 1.66 seconds**.

After the independent tool/template removal, the complete native operational and
retirement modules passed **25 tests in 1.79 seconds**, including all thirteen new
retirement checks. Final export e906bb6598168b2cb140d1529193f25695e0e39b differs
from the wide-run export only by those closed tool/test/template removals and
localized test changes. All nineteen present and eleven deleted changed Python
paths match it; retained production native/model bytes match the wide-run export.
The full 160-module suite was not repeated after the test-only corrections.
New-head repository CI remains separate evidence; this is not site qualification.

The obsolete sunset-SoC experiment and household-energy installer are also
removed, together with the old daily/weather lock-patch tools, their four
exclusive test modules and two repository drop-in templates. No production
caller imported or invoked these tools. All six source-availability regressions
failed before removal and passed afterward. The installed definitions remain
untouched. There are now no external production Python imports of the old
forecast-worker family. This proves import closure only; remaining deployment
tools, unit templates and dynamic references still need closure before worker
removal. Live services, source
releases, model receipts, resource policy and actuator authority were unchanged.


### Google publication no longer enters the incumbent worker — October 19

The unused ProviderSnapshot overload in forecast_intel.build_forecast_payloads
is removed. The remaining dictionary worker refuses a Google snapshot before its
old model selector can run; all original dictionary calculation statements have
identical ASTs. No current native source binding or model receipt changed.

All Google provider tests now exercise the actual forecast_payloads and
publication_states APIs, retaining nullable fields, original source/decision
identity, complete local/DST days, maximum-horizon byte limits and unavailable
withdrawal checks. Serialized or incumbent dictionaries cannot impersonate the
immutable provider object. The Google package no longer imports the old worker
to verify those contracts.

Verification: **all 211 pinned WeatherNext tests passed in 8.561 seconds**, in a
fresh process whose import hook rejects all fourteen old worker/evidence modules
throughout discovery and execution. **168 legacy-worker/native boundary tests
passed in 3.05 seconds** from export fa3401bdf719347e4635e380ba704d9776ff02c0.
The new incumbent refusal test failed before the edit, then passed. Existing
native cold-start coverage now blocks the same fourteen modules in addition to
the four retired standalone publishers. These are development tests, not site
qualification.

At this earlier boundary-check stage the separate operator/recovery/template
proposal was still unapplied pending the owner decision; the later approval and
source application are recorded above. This independent boundary change did not
apply that proposal or alter recovery functions, templates, installed
services, resource policy, model state or actuator authority.
