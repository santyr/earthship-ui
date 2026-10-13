# Household capture within the forecast cycle

> Execute inline under the approved full PR3 architecture. One final immutable review and one Important/Critical correction pass. This stage must deliver an operational source/model/cache feed, not stop at an adapter or fixture.

Goal: capture household originals under the existing forecast lock shortly before its actual issue, combine them with that cycle's verified original thermal/weather publication, and update the private observation cache without renewing source timestamps or granting action authority.

Architecture: use the existing injected backend interface of unchanged provisional_live.publish_cycle. A delegating backend collects household inputs after the parent's original collection and before issue minus a safety margin. An outside-producer driver owns the same SharedScoreLock, invokes the unchanged pinned forecast implementation, then derives/replays the full source/model/plan artifact and curated cache only after verified delivery. Observer failures remain explicit and cannot fabricate a forecast or qualified input. Preserve existing forecast numerical output, source versions and the original candidate runtime. No training or equipment requests.

Files:
- openhab/scripts/household_cycle.py: bounded backend adapter and coordinator/CLI.
- openhab/scripts/household_cycle_sources.py: owned configuration and reusable restricted source collector, outside the household producer directory.
- openhab/scripts/test_household_cycle.py and test_household_cycle_sources.py.
- deploy definitions/guarded installer, operations evidence and canonical program tracker.

Task1: injected collection boundary
- RED integrated actual publisher tests: post-parent/pre-issue collection, original output and delivery parity, bounded remaining time/guard, late-window skip, collector error isolation and parent error propagation.
- Implement adapter and GREEN, with no changes to any of the72 original predictive-runtime files.
- Verify parent provisional tests and source hashes.

Task2: complete source/model/cache coordinator
- RED owned config/read-only source collection under one external issue deadline, independently pinned epochs before/after, byte/runtime/config/registry stability and missing/expired sources remaining unknown.
- Implement measured weather + bank/topology + base/power collection using existing restricted readers and fixed paths. Preserve original records and clocks.
- RED coordinator only accepts exact verified same-cycle original delivery, derives the measured v6 snapshot and model/shadow plan using existing retained parameters, replays exact originals, then publishes the curated cache. Withhold mismatched/late/runtime-changed artifacts and preserve source/intent expiry.
- Implement full private CLI; retain diagnostic originals0600/0700. No source payload stdout, no action/owner request or model execution from HTTP.

Task3: qualification and operational feed
- One final independent immutable review; one Important/Critical TDD correction pass.
- Actual bounded source+model+cache proof against a natural cycle; do not force/restart OpenHAB or original workers.
- Guarded source-pinned service/driver deployment using current credentials, unchanged original forecast numerical/runtime sources and existing limits. Observe natural publication and real UI freshness/expiry, then all exact-head checks/merge/canonical evidence.
- Full PR3 stays active: trajectories, calibration/effects, authority/policy/owners, outcomes and graduation/integration remain required.

Limits: scientific tests and workers CPU20%,memory256MiB,swap0,tasks24,IOWeight10,nice15,idleI/O,BLAS/OMP/MKL1. Browser-only proof may use96 tasks with identical CPU/memory/swap caps and one renderer/CPU affinity. Serialize local numerical jobs. Preserve root thermal UI overlay and all original private artifacts.

Follow-up: timely snapshot composition and owned-stage upgrade
- Remove repeated intermediate snapshot construction while retaining original source replay, prepared-context validation, exact complete-document identity checks and source expiry.
- Verify every original layer still rejects corruption and lookalike context types; compare retained original production replay numerically and by receipt identity. Retained parity is not operational source qualification.
- Verify weather, energy-source and measured-weather pipelines serially under the existing limits.
- An upgrade requires explicit previous-stage identity, both stages verified against the same original forecast/candidate/parameters/base service, the same cache and exact installed previous override/entry point. Qualify the new production runtime, recheck inactivity and originals, then atomically replace only the owned override and reload units. On failure restore only the exact new override; preserve concurrent edits. Never restart services.
- Independently review the immutable performance/upgrade patch, then observe a natural cycle before claiming current-input planning is qualified. Keep TTL and action authority unchanged.
- The active thermal fit is fixed to October10 data; automatic capped training and candidate promotion remain separate unfinished ML work, not satisfied by an observer upgrade.

Follow-up: distinguish publication headroom from fitting headroom
- The read-only original input probe reproduced refusal at the training monitor when global swap-out/OOM counters changed. Preserve current publication resource/RAM/PSI/single-thread preflight and refuse new host OOM or worker memory-limit events. Ordinary host swap counters do not by themselves disqualify a capped inference worker.
- Keep all fitted-runtime files and training policy unchanged. Add an outside-driver PublicationHeadroom monitor and pin it in the driver source guard. Verify unknown/regressed counters, new OOM/worker-limit events, original resource refusals and bounded quiet preflight.
- Verify the actual read-only original collector under the new guard, then guarded source-pinned deployment and a natural publication/observation cycle; no action authority or source TTL change.

Collector deadline inspection is separate from source-access preflight: keep explicit source guards and adapter entry/return/post-serialization guards, while the deadline callback only measures the unchanged hard six-second budget. Profiling found 79 source checks recursively executing 158 expensive resource checks before refusal. Verify drift refusal and original publication parity before deploying this optimization; neither source TTL nor the connection minimum budget changes.

Audit integration (2026-10-12): A01–A11 are additional requirements of the full PR3 goal.
Source: docs/operations/2026-10-12-astro-binding-efficiency-audit.md and exact adjacent inventory CSV. Every task/acceptance is in the canonical tracker with complete=false.
- A01: finish withheld diagnostics/native/consumer/daily-refresh acceptance of deployed minimum stable5.2.3.
- A02/A05/A06: user chose native whole-day season (zero less than1day), native rise-end→set-start daylight, shared household Denver formatting. Test typed units, invalid/stale/current-day qualification, update ordering and rollover; preserve Item identity/history. Remove browser polynomial after coverage.
- A03/A04: current Home/Weather native moon through existing store/SSE; retain date-specific future SunCalc, provider day flags and weather-condition distinctions.
- A07/A08: exact-instant bounded native geometry cache/offline replay; version/refit/compare before promotion. Preserve elevation<=0 thermal-night policy, measured weather/irradiance calibration; no per-row synchronous RPC or guessed altitude.
- A09: native circadian evaluation stays observational; preserve existing curve/brightness/manual-OFF owner until explicit qualified policy choice.
- A10: qualify isolated native pre-dusk scheduling with retries/catch-up/idempotency/windows; shared sunset stays unshifted.
- A11: protected pump freshness/bounds review/harness separately; retain BMS/voltage/hydrology/alternation/manual/fail-closed gates. Recovery deferred; no live control migration implied.
Interfaces: A02/A05/A06 share typed quantity/site-time/daily provenance. A03 uses original store/SSE evidence; A04 separate future instants. A07/A08 require pinned historical geometry/versioned artifacts, not ten civil-noon points. Full household ML and bounded collector work remain active.

Bounded collector window follow-up: raise the outside-driver maximum from6 to10seconds, still min(maximum, original issue minus3seconds minus actual current time). Share that maximum across adapter, source-budget validation and exclusive hard alarm. Preserve source TTL, RAM/PSI/OOM guards, transport minimum1second, forecast source/runtime/numerical output and caps. Verify an8second source window, total-budget renewal refusal, issue-margin refusal and original publication parity before any guarded live upgrade. This does not qualify stale inputs or fit a model.

Publication metadata efficiency follow-up: actual capped coupled probe measured originalcollection13.105seconds andhouseholdbudget3.735seconds inside the original20second acquisition window; standalone full-driver-guard collection8.891seconds succeeds. Preserve original publisher/timer/72fitted files and20second source cadence. The original cap helper launches /usr/bin/ionice on every check where io.weight is absent. Outside the fitted runtime, implement identical or stricter live metadata checks using current-process Linuxx86_64 ioprio_get (syscall252 verified installed ABI header) for that fallback. No cached freshness, no relaxedcaps or pressure/OOM guards, no monkeypatch of original fitted modules. Retain pinned cgroup membership/identity checks before/after. Qualify original ionice/native parity, scientific tests, and an actual coupled capture before guarded deployment. Unknown ABI/metadata refuses.

Collector transport efficiency: measured8repeated SSL/context initializations consumed1.065seconds inside the tiny remainingwindow, despite fixed local HTTP endpoints. Prepare one no-proxy/no-redirect opener in CycleSourceCollector startup and reuse it for original owner and measured-weather GETs; accept optional caller-prepared opener in measured-weather transport. Keep auth perrequest, endpoint identity, byte/timeout/mainthread/alarm constraints, HTTPerror/missing semantics, source epoch/clock andTTL. Standalone measured-weather callers retain existing default. Test actual transport behavior and beforedeploy comparecoupled capture/source replay.

Decision latency follow-up: capped retained-original profile measured thermal preparation10.911s and weather preparation9.801s, both invoking the same complete native-origin replay; derive/replay7.597s and observation replay3.606s. Introduce one frozen capture-to-paired-context entry point that invokes unchanged complete thermal preparation once, then constructs the exact same independently validated immutable weather context from those same originals. Standalone weather preparation retains its full validation contract. Verify byte-identical paired contexts, native archive refusal, resealed numeric corruption refusal and input immutability; keep all72 fitted sources/sourceTTL/action authority unchanged. Use the paired entry point in complete_cycle; profile actual retained originals and observe a natural cycle after reviewed guarded upgrade.

Immutable weather-context reuse: actual current4c1daa cache-replay profile3.493s found7PreparedWeatherContext constructions1.876s,6from one snapshot.weather property. Reuse the independently validated immutable context per frozen snapshot using a cached property, without global caches, cached source reads/metadata or expiry results. Preserve original bytes/identity, independently validate new/restored snapshots, and keep snapshot serialization/equality/hash unchanged. Test full planner context parity, returned-data immutability and stale-source refusal; verify historical complete-receipt replay parity under actual caps, review, then guardedupgrade/natural-cyclecache freshness.

Outcome monitoring follow-up: actualoriginalscore diagnostic passed234guards and failed only original mature outcome unavailable atprovisional_monitor.py142. Completed598scoremarkers exist but originalscore_jobs unlinks current report before attempting the nextpoint, so thisexpectedgap erases measuredperformance. Nativeoldest1h/6h/recent1h probes allqualified; retainedmissingpoint hasvalidreceiptsbut no qualifiedselectedpoint at its exacttarget. Add outside-fitted scorer coordinator: on onlythat exactexpectedmissing-outcome refusal, reconstruct report with originalrefresh_report, revalidating originalcompletion hashes/pairs/sourcefingerprints and currentcandidate/runtime. Never fabricate anoutcome or fallbackafterunexpectederrors/resource/corruption failures. Existingonejob semantics, SharedScoreLock, originalconfig/sourceguard andcaps remain; boundedtotalclock avoids forecast preparation window. Verify missingpoint/pastmeasurements andcorruption refusal, actualguardedrefresh, review, thenownedscore-onlyoverride withno restart. All72fittedsources unchanged; gapqueueadvancement andautomaticrefitting remainunfinished.

Outcome queue follow-up: the original one-job loop stops at the first absent qualified native point. Retain the original fitted 72-file runtime; an outside-fitted queue mirrors discovery/completion persistence and delegates full numerical scoring, native capture/delivery validation, completion fingerprints and report schema to the pinned monitor. Assess only one pending outcome per invocation. A well-shaped native query with no selected point produces an immutable gap receipt with exact delivery/capture/horizon/target identity, assessment and 15-minute retry, retained native paths and complete original fingerprints. A subsequent invocation may skip only a validated, unchanged, not-yet-due gap; later qualified jobs score normally. Missing points contribute no pair, error average or graduation evidence. Completed-original loss, malformed native results, source changes and corrupt gaps refuse. Existing 50-second total budget, shared lock and capped scorer service stay unchanged. Verify RED gap starvation, retry/malformed/corrupt-source refusals, exact supported-pair parity and coordinator integration; review the immutable patch, install only the owned scorer override, observe natural gap then later scoring. Original fitted coefficients/source files and physical authority are unchanged; fresh-data training, promotion, recent-cycle baseline qualification and full PR3 completion remain separate unfinished requirements.

Fresh provisional refit and selection: diagnosed strict acquisition swap-in-zero refusal, then used the existing provisional 1MiB/s allowance with original reserve/PSI/no-swapout/OOM checks and 256MiB/no-worker-swap caps. Captured and recaptured adjacent source intervals under one collector revision, assembled with a fresh full-window journal, verified10 endpoints/3originDates throughOct12 06UTC, and ran unchanged prior-regularized fitter. Candidateb463 matches the original72-file numerical runtime and remains low/notgraduated. Stage a separate live config that changes only candidate_path; add an optional original service configuration argument to the immutable package builder, binding both config files without changing the base unit. Qualify the new package/runtime before replacing only the owned forecast and score overrides together under the existing shared lock. Preserve both timers, caps, original config and physical authority; recheck source/config/unit fingerprints before/after, and restore only exact new owned override bytes on incomplete handoff. Independent immutable review and natural new-candidate delivery are required. This is provisional model selection, not measured improvement, automatic graduation, owner migration or completion of automatic retraining.

Current-model outcome scheduling: a bounded actual inventory after fresh selection found607 mature unscored outcomes from the previous artifact and zero yet-mature new-artifact outcomes. Prioritize mature jobs for the selected candidate, chronological within each candidate group, then continue older-model work when no active job is assessable. Preserve one pending assessment, all capture/native/delivery/source checks, original numerical scoring and current-artifact report filtering. A reviewed exact b84d000 queue source digest is compatible with the unchanged gap schema/native absence replay; unknown queue versions refuse, and compatible gaps still require every original fingerprint and exact native absent-query replay. Verify mixed valid artifacts, maturity boundaries, completed-current fallback, missing-current gap/fallback, known/unknown old-gap sources and original single-artifact pair parity before a scorer-only guarded handoff. This improves current-model measurement scheduling; it does not supply automatic retraining, graduation or production benefit.

Native geometry A07 execution: use one bounded standalone JVM batch against the installed Astro SunCalc.getPosition library, not synchronous per-row OpenHAB action calls. The qualified 5.2.3 public position actions delegate to the same calculation; their full daily context work is unnecessary for pure positions. Seal exact UTC millisecond instants, configured site/timezone/unknown altitude, original native stdout, source/collector/library hashes and availability. Replay rejects missing/reordered geometry, unexpected units/types, changed runtime/request/native output and unsupported versions; thermal night remains elevation<=0. Cache protocol supports256 points and the acquisition worker128 per batch to stay within the original16KiB supervised-worker result budget; larger datasets require bounded complete coverage across caches. Preserve all72 deployed fitted sources until a separately versioned dataset/artifact, native refit and forecast comparisons pass. Actual88-point historical/future/leap/DST/millisecond cache replay succeeded under originalguards, 113283072-byte peak/zero memorymax/OOM,9.935s;2horizon disagreements establish a real feature-contract change. Native radiation/sky inference remains a separate A08 experiment; no altitude is invented. Versioned model integration/refit/prediction comparisons are still required.

Native geometry review correction: reject unsupported timestamp string precision before datetime parsing, including fractional timezone offsets; parsing may never truncate the requested or returned instant. Five regressions failed before the fix;44 affected cases passed, and the original88-point cache retained identical offline replay under its original collector pins. Current selected model outcome pairs are independently verified; two1h examples have model MAE1.554249F vs persistence0.36F and one independent origin date. Operational scoring is established; improvement/graduation is not.

A07 multi-batch integration: add an immutable native geometry series for up to8192 exact instants (28days at5min) made from ordered128-point acquisition batches. Seal the complete requested timestamp set, original child cache hashes/native outputs, configured site/timezone, availability and one runtime identity. Refuse holes, overlapping/reordered chunks, extra points, runtime/site drift, malformed JSON and changed original pins; offline replay has no provider calls, interpolation or legacy fallback. The fitting adapter must bind the series identity into separately versioned dataset/artifact lineage before any native refit or promotion. Current fitted72-file runtime remains unchanged. Verify coverage spanning at least3batches and use the original88-point cache as actual offline replay evidence where it exactly covers the requested set.

Native worker packaging closure: package committed scripts/java/NativeSolarGeometry.java alongside the Python native worker; refuse missing/symlink sources before creating a stage, and verify retained Java bytes in the sealed source manifest. Original72 fitted sources and existing stages remain unchanged. Three packaging regressions failed before fix;84 affected packaging/cache/worker/series cases pass(8.40s). Native series immutable426b131 review C0/I0/M0. First actual778-point training-window phase captured128points/1of7batches in12.25s,125534208-byte peak and zero memorymax/OOM; remaining batches capture separately under original pressure guards/sharedlock. Dataset/model/refit/promotion remain pending.

Actual native training-window acquisition now complete:778exact5min instants for original snapshot2e2edd36e4b82b29b95c51968ab448c6a0b3d01655116365043ae5ab166f4b4b,October9 13:10 throughOctober12 06:00UTC,7separate128-point phases. Series29a85097f6376320c859a78c0ac2a73eeddfd99067ddc478a173f0b3309034cc replays identically offline under collector e7dd9d5. One horizon classification differs from legacy andmaxsin difference0.00483682. Maximum phase12.25s/125534208bytes;zero memorymax/OOM, original sharedlock/pressure guards preserved. Native dataset reconstruction, model artifact lineage, refit, historical/as-issued prediction comparison and coherent producer promotion remain required. Java packaging reviewe044170 C0/I0/M0; actual sealed209-source stage includeshelper/all72originalfitted files. Staged native execution qualification remains pending.

Sealed staged native worker execution verified under original caps/guards:stagee044170/172a8ec reproduced original128-point native stdout/positions exactly,10.39s/112128000B/zero memorymax orOOM. Initial attempt withheld on hostswapin above unchanged1MiB/s allowance; terminal refusal confirmed before bounded retry. All72 fitted source identities unchanged; no model fit, production-unit handoff or full forecast-stage runtime qualification claimed. The next native model work is versioned dataset reconstruction/lineage, refit and prediction comparisons before consistent producer promotion.

Native installed-shade dataset integration: a separate outside-fitted native_thermal_inputs adapter validates the original native-v2 training snapshot/sensor phases and complete pinned native geometry series. Reuse original measurement bucketing/quality helpers, explicitly discard every legacy inferred night-zero, then reconstruct missing radiation only under native elevation<=0 (new native_solar_night_zero provenance). Recompute daylight-dependent historical action reconstruction using native geometry while delegating confirmed/unknown direct events and heat cooldowns to the original regime-free projection. Preserve genuine endpoint receipts, observed outdoor/weather forcing, exclusions, retroactive-origin barriers and frozen-origin action selection. Seal original snapshot identity, geometry/runtime/site/timezone/availability, resulting sample/weather rows and separately versioned clear-sky fraction formula; offline replay rederives from both original dependencies. This is the installed-shade development dataset, not full thermal release qualification. All72 fitted sources remain byte-identical; separately versioned native fit/artifact/forecast and general thermal adapters remain pending.

Native endpoint compatibility: return distinct NativeDevelopmentEndpoint records carrying originalsource snapshot, native dataset and geometry-series identities; original v1geometry fitter must refuse this type rather than mixing v2dataset/oldsolar features. Actual compatibility regression failed before fix;99affected dataset/source/cache/worker/series cases pass8.80s. Native dataset is development-only and retains observed future weather as such; promotion/as-issued scoring remain separate qualifications.

Native dataset actual qualification:773genuine endpoint sensor rows/765weatherrows and10supported endpoints(3/3/2/2) preserve original support;1historical horizon state changes; originaldatasetf2b7dcc replays identically,8.39s/62025728B/zero memorymaxOOM,72fittedsourcesunchanged. Public constructor lineage bypass found in independentreview;3real RED regressions now102affectedGREEN9.90s by restricting native data construction to independently validating builder/replay. Verify originaldataset undercorrected source before fitting. This closes installed-shade development-data versioning only; native modelartifact/fit/as-issuedcompare/promotion andgeneralthermal adapter remainpending.

Corrected120a0a2 source independently replayed original native datasetf2b7dcc identically from originalsnapshot/series dependencies,773samples/765weatherrows/10endpoints; publicconstructor refused, sourcecode hashes heldstable,4.39s/61288448B/zero memorymaxOOM. Native installed-shade development-data adapter/lineage/legacyfitter isolation now verified. Next implement native-specific clear-sky forcing normalization and dynamic rollout/sensitivities, prior-regularized bounded fitting, versioned native candidate/runtime/artifact validation, paired legacy/native endpoint prediction comparisons, future/as-issued geometry/capture/replay and a coherently staged producer before any selected-model promotion. General thermal dataset/behavior adapters andallother program requirements stayactive.

Native installed-shade model/fitter: use a separately typed immutable numerical model composed with unchanged InstalledShadeDynamics equations/transition, ten-parameter physical bounds/order/stability/72hzero-solar guards. Normalize every complete original forcing row using the exact pinned native series (includingzero radiation; no missing-geometry fallback). Verify same-geometry legacy rollout/sensitivity parity and independent finite-difference derivatives. Native endpoint batches carry dataset/series identities and preserve original frozen origin actions; reuse unchanged numeric _objective/_constraints, physical prior and priorregularization1.0 in a separately versioned bounded provisionalfit. Deadline/resource callbacks remainmandatory and fitted results remainlow/notgraduated/notas-issued. Opt-in, pressurecaps/sharedlock andfit<=85secremain. Actual developmentfit/prediction comparisons must retain original source/native data/runtime lineage andleave productionunchanged until versionedartifact/capture/publisher validation complete.

Actualnative installed-shade developmentrefit isverified:10endpoints/3originDates/rank8,53iterations,loss296.649127->0.424716,15.81s/97456128B/zero memorymaxOOM underoriginal cappedworker/sharedlock/pressureprofile. Immutablee865953reviewC0/I0/M0. Retain0407b146 fitevidence/source/runtime/dataset lineage andlow/notgraduated/noas-issuedclaims. Paired legacy/native trainingendpoint comparison includes4contexts to distinguish geometry-only, coefficients andchangedhistoricalactions; originalfixedcohorttargets required. Firstcomparison withheldonhostswapin; sameguardsboundedretrypending. Fullnativeartifact/producer/as-issued qualification andgeneralthermalrefit remainrequired.

Paired conditional development prediction comparison iscomplete:10identical originalorigin/target pairs; fourexplicit contexts distinguisholdgeometry/currentfit, geometry-only, nativefit/commonoldactions andnativefit/nativeactions. Native predictedstates replay identically. AirMAE oldfit0.516435F versusnativefit0.544922F; geometry-only oldfit0.545880F. Fourorigin actioncontexts change, withnativefittedventgain yieldingidenticalnative predictionsacrossbothactioncontexts. Reusedtrainingendpoints/observedfutureweather areexplicit, noholdout/as-issued/productionimprovement claim. Comparison4fd2321/13.19s/61538304B/zero memorymaxOOM; originalpressureallowance preservedafteronehostswapin refusal. Nativecandidate/runtime/artifact compatibility andfuture/as-issued capture/publisher qualification arethenext requiredsteps; productionmodelunchanged.

Native provisional artifact/runtime: schemaearthship-provisional-thermal-candidate/v2 isdistinctfromv1 andbound to retained originalsnapshot/dataset/geometry/runtime-bound fit evidence. Preserveoriginal72file/runtime/interpreter/dependencybinding asbase; separatelyseal9requirednative repositoryrelative Python/Java sourceidentities plusknown optionalnativeforecast/live/score modules. Candidate validation requires externalartifact/runtime pins, completeprivateoriginalfileSHA/closedJSON contracts, source/sensor/geometry/native rule correspondence anddata-fit-created chronology. Reuse original coefficient/statistical guards then independently rederive native endpoint support, loss, rank/condition andbothinitial/final physicalrollouts; do notrefit duringartifactvalidation. Three resealed statistic regressions failedbeforefix;164affectedcases pass17.91s. Numericaltest idleadmissionwait increased120->240s tospan reservedforecastwindow; CPU/memory/swap/pressureguards,85s numericalworkbudget andpublicationdeadlines unchanged. Actualfit mustcapturefullnative runtime before/after underexisting guardedsharedlock andsealedartifactmustreadback before nativeforecast implementation/promotion.


Native candidate actual qualification: independently reviewed34937cb (0 Critical,
0 Important, 0 Minor). Committed2d62e99 source ran a fresh guarded fit with full
native runtime captured before/after; retained v2 fit evidence5c0c45d uses original
snapshot2e2edd, datasetf2b7dcc, geometry29a850. Runtime d1ea3db retains the original
72-source interpreter/dependency closure and nine native sources. Fit17.13s,
111165440-byte peak, zero OOM; original10 endpoints/3 dates/support3/3/2/2,
rank8 and53 iterations. Candidateee0e142 independently rebuilt support/loss/rank
and physical rollouts, persisted/read back identically in18.46s/115576832 bytes.
The sealed213-source stage2d62e99 replayed the same candidate/runtime with the
production interpreter in10.39s/119582720 bytes, zero OOM. CPU20%, memory256MiB,
swap0, tasks24, original pressure monitor and shared lock remained unchanged.
No live unit/model/actuator changes. This qualifies the native artifact and sealed
reader only; future as-issued native geometry/forecast/capture, coherent score
migration/promotion, demonstrated accuracy, and full PR3 requirements remain open.

Native as-issued forecast task (inline execution within approved A07 migration)
- Create openhab/scripts/native_thermal_forecast.py and test_native_thermal_forecast.py.
- build_capture(candidate, inputs, *, geometry, runtime, expected_artifact_sha256,
  expected_geometry_sha256, issue, available, published, check_budget,
  monitoring_report=None) retains the complete original compressed-temperature
  query binding and exact future NativeGeometrySeries. Require the candidate's
  complete native runtime plus native forecast source identity; geometry must
  use the original training geometry's native library/collector/site/timezone
  contract, cover every five-minute forecast forcing exactly, and be computed
  no later than actual input availability. Preserve original weather, phase,
  action, November vent-default, aligned issue and 90-second publication guards.
- validate_capture(value, *, runtime, expected_artifact_sha256,
  expected_capture_sha256, check_budget) independently replays original candidate,
  temperature queries and geometry, then rederives native numerical output and
  monitoring report. Closed origin/forecast/publication v2 schemas distinguish
  geometry semantics from v1. Persist/read private originals with explicit pins.
- TDD: independent scalar recurrence for the first hourly endpoint; exact replay;
  missing/future geometry; native library/site drift; stale/changed temperature,
  weather/action/phase and publication clock refusals; rehashed output tamper;
  external identity mismatch; November operator override; private roundtrip.
- Run original/native forecast, artifact, dynamics, geometry and source-binding
  regressions serially under unchanged caps/actual lock/pressure monitor. Commit
  immutable source and obtain final independent review; real current-source
  geometry acquisition/readback and latency qualification remain required.
- Native outcome-score migration, UI schema handling, producer scheduling,
  household capture compatibility and coherent model selection remain subsequent
  required integration tasks. No native producer is selected by this pure task.

Native capture implementation91a21d2 independent review:0 Critical,2 Important,
0 Minor. One correction pass09c485c:13 actual RED cases (21.69s) then13 GREEN
(16.90s) enforce lossless issue/availability/publication clocks and caller-independent
capture/runtime snapshots before any callbacks. Full corrected affected suite
202 cases passed in two serial groups46/53.30s and156/18.61s. Original72 source
hashes remain unchanged; interval host-pressure refusals were respected, not
relaxed. Preliminary runtime15cea696 for uncorrected91 source is retained only
as private diagnostic state and must not qualify corrected source. Real source,
latency/current wider runtime/stage readback, native scorer/UI/household/producer
integration and coherent selection remain required; no live model/unit changes.

Corrected native forecast runtime qualification: committed5ce2d67 native10 runtime
5699abd and candidate00d694c retain original fit evidence5c0c45d/core9/base72.
Actual build/write/read17.50s/114987008B, zeroOOM; sealed214-source package
2a3d1a2 loads corrected native_thermal_forecast with production interpreter and
reads identical candidate/runtime in10.42s/118874112B, zeroOOM. No optimizer,
live units/model selection or action changes. Actual future/native issued capture,
native scoring and coherent observer/UI/producer handoff remain pending; adding
observer source requires explicit wider runtime/artifact/stage qualification.

Native outcome scoring task (inline, existing approved migration)
- Create native_thermal_score.py and test_native_thermal_score.py outside the72
  fitted files. score(capture, receipts, outcome, *, runtime,
  expected_artifact_sha256, expected_capture_sha256, horizon_hours, assessed_at,
  recent, check_budget) snapshots caller-owned inputs before callbacks, replays
  native capture under external pins, requires native score source in runtime,
  and verifies both exact persisted numeric/main receipts and their causal order.
- Preserve supported1/6/12/24h horizons, original maturity threshold5min, same
  sensor-epoch/qualified receipt rules, physical predictions and explicit missing
  recent-cycle baseline. Reject unsupported clock precision with native parser.
- Version the closed scored pair/v2 with native model rule and geometry lineage.
  validate_pair(pair, *, expected_pair_sha256) preserves explicit root identity,
  clock/alignment and native fields; reuse legacy pure error-arithmetic validation
  through an explicitly restricted statistical view, never v1 forecast replay.
  summarize(pairs, *, artifact_sha256) keeps original bounded256-point MAE/bias,
  missing-baseline and duplicate/mixed-revision behavior; no graduation/actions.
- TDD first: four horizons, delivery corruption/missing/reordered receipts,
  immature/phase-invalid/precision-invalid outcomes, missing/available baseline,
  resealed arithmetic corruption, external identity, duplicate score and frozen
  caller outcome. Verify original/native source/forecast/statistical regressions
  serially under unchanged lock/caps/pressure checks; commit and immutable review.
- Source-bound mature outcome acquisition/completion reconciliation/reporting,
  UI/household/native producer handoff and actual as-issued scoring remain live
  integration requirements. This pure score task selects no model or live units.

Native score9942a5b implemented with219 affectedcases initiallypassed. Immutable
review C0/I1/M1; timestamp precision regraded Important because lossy parsing can
count future observations at the target. One fix pass946058b: shared strict outcome
clock/complete receipt validation in fresh scoring and saved pair replay. Two
representative cases RED6.99s; new17 regressions GREEN5/12.90s+12/24.98s;
original31 scoring/forecast cases passed42.80s afterfix. Other188 unchanged
forecast/data/geometry cases remain verified from the prior feature runs. Original
72 sources unchanged; host intervalpressure/swapread refusals respected. No new
review pass. Source-bound raw outcome acquisition/completion/report reconciliation,
11-source runtime/artifact/stage, monitor/UI/household/producer coherence and live
selection remain required. No optimizer/live unit/model/actuator changes.

Corrected scorer11 runtime qualification at8c70a73: actual candidate549a9db,
runtime95e7a12, retained fit5c0c45d/core9/base72; original references and full
before/after runtime identical. Build/read18.2908s/115286016B/zeroOOM. Sealed
215-source deploymente05ec73 loads both native forecast and score modules under
production interpreter; identical candidate/runtime readback10.5588s/119263232B,
zeroOOM. No fit, live unit/model selection/writes/actions. Raw source-bound
outcome replay, completion/report, producer/UI/household coherence remain required.

Native raw-score replay task (inline, approved source-bound outcome migration)
- Add cohesive build_source_score / validate_source_score / persist_source_score /
  read_source_score APIs to native_thermal_score.py. Retain a private v1 source
  record containing the native capture path, exact original delivery receipts,
  cached query grid, original compressed query binding and rederived v2 pair.
- Require external artifact/capture/source-record roots and runtime; re-read native
  capture and original raw queries, validate all lossless clocks before legacy
  selection, derive compare_v2 from captured historical targets. Missing query
  coverage refuses; legitimate null selection remains missing history. Preserve
  seven cycles, 31-day search, DST exclusions and original assessment clocks.
- Replay full native score; refuse resealed pair/baseline/cached receipt changes,
  missing/replaced originals, wrong pins and future assessment. Freeze input
  before callbacks. Read back private bounded digest-bound records.
- TDD genuine compressed temperature source packets, available/insufficient
  comparator, missing coverage, forged cached temperature and resealed pair,
  deleted originals, identity mismatch, caller mutation, precision and roundtrip.
- Subsequent native completion/report reconciliation consumes this replay API;
  this task does not select or deploy a native producer or grant action authority.

Ruling: native raw-score binding must allow up to64 original query packets.
The original v2 helper caps24 paths, which cannot represent all31 historical
cycles plus one outcome when history is missing; each source query itself still
has the original24-hour/289-target bound. Implement native closed selection
binding with identical stream/policy/phase/assessment checks, complete cached
selection equality and64MB aggregate bound; do not edit the72 fitted sources.
Cost if wrong: bounded additional private source reads; all guards remain active.

Native source score replay implemented:21 new +17 original scoring behaviors
passed across6/15.40s,9/24.90s,23/43.00s cappedserialbatches. All four horizons,
31-day genuine null history, original compressed reselection, externalpins,
private readback, frozen caller and resealed scalar/baseline/source refusal.
2 missingAPI RED6.31s;3 rawreceiptclock RED16.10s after actual comparator contract
correction. Full81009 terminal swapread refusal; no pressure guards relaxed.
24h fixture corrected to share whole snapshots for overlapping endpoints; no
production duplicate-target relaxation. All72 sourcehashes reverifiedunchanged.
Current observer source runtime/artifact/stage qualification stillrequired;
completion/report reconciliation and producer/UI/household handoff remainpending.
No live units/model/action changes or GitHub writes. All test scopes terminal.

45021ba source replay actual qualification: candidatea1746c3/runtimeeaafda0,
retained fit5c0c45d/core9/base72. Original artifact build/read17.9031s/115662848B,
identical before/after runtime, zeroOOM. Sealed215-source deployment2390fc2 loads
forecast/scorer and all4 source replay exports under production interpreter;
identical candidate/runtime readback9.8885s/119029760B/zeroOOM. All qualifier
handles terminal. No fit/live units/model/writes/actions changes. Source-qualified
completion/report and coherent live native/household/UI producer remainrequired.

# Native completion and report reconciliation task
Base: 45021ba. Approved PR3 source-bound chronological monitoring migration.

Add source completion build/validate/private persist/read and report reconciliation
APIs to native_thermal_score.py. Completion records bind job, artifact, runtime,
capture, native source-score path/root and rederived pair root. Validation takes
external completion/source/capture/artifact roots and current runtime; read/replay
original source score before admitting a completion. Never trust cached scalars,
completion self-hash or an unverified original fingerprint.

Report reconciliation consumes a caller-pinned list (maximum256 entries) of
completion path/root, source-score root and capture root, with current externally
pinned artifact/runtime and lossless assessment clock. Replays every selected
completion, rejects future scores and duplicates, and uses native summarize.
Budgets remain supplied by the caller and must span all replay work. Missing or
changed originals refuse the report. Qualification remains low/not graduated,
no actuator authority. Actual live producer/discovery/cache performance remain
separate required integration; do not select a native live service here.

TDD: private complete roundtrip, original source/capture/query deletion, external
identity mismatch, resealed pair/root tamper, original model/persistence/recent
statistics and explicit missing baseline, empty report, duplicate completion,
future assessment, caller mutation, bounded list, and guarded deadline refusal.
Run serial bounded tests, preserve72/core9, record actual results. Do not write
product implementation before representative new tests are observed failing.

Native completion/report APIs implemented: externally pinned source/capture/model/
completion roots replay original pair and queries; mature completion clock,
duplicate job, bounded256 entries and caller snapshots enforced. Report-wide
original byte inventory verifies after aggregation; compressed/nativeorigin
queries explicitly observed and rechecked. Representative2 RED7.71s ->GREEN
11.69s; late-original change1 RED7.71s ->fixed. Corrected14 completion +21 raw
source cases allpass in4/21.70s,17/48.29s,15/32.61s serial batches (one roundtrip
case appears in two cohorts;35 unique cases). Original72 hashes unchanged.
All test scopes terminal; current source/runtime stage qualification remains
required. No live selection/units/writes/actions or GitHub publication. Whole
branch final review and full native/household/UI coherent producer remainpending.

34b707d completion actualqualification: candidateffe998e/runtimebb640b8, fit5c0c45d
core9/base72 retained. Actual build/read19.1941s/115453952B/identicalbeforeafter/
zeroOOM. Sealed215-source deploymentf61d3fb production interpreter loads both
forecast/scorer and all9 source/completion/report exports; identicalcandidate/
runtime10.3931s/119025664B/zeroOOM. All numericalhandles terminal. No optimizer,
live model/unit/writes/actions changes. Current source/module qualification done;
actual native issuing/scoring discovery, UI and household coherence remainpending.

Native UI decoder compatibility task (approved observational migration)
- Accept exactly original provisional publication/v1 version8 and native
  provisional publication/v2 version9. Native numeric forecast/v2 must carry
  exact native installed-shade dynamics/v2 rule and a64hex geometry series root.
  Preserve closed schemas, exact hourly targets, source identity agreement,
  physical temperatures, expiry, low/unavailable confidence, withheld advice,
  no graduation/calibration/stability or automatic actuation.
- Route version9 through the provisional decoder and preserve UNAVAILABLE mode
  on invalid/future/expired native publications. Render the existing PROVISIONAL
  state; do not invent action recommendations or expose implementation metadata.
- TDD ready native trajectory and legacy compatibility, explicit native
  unavailable, missing/wrong geometry/rule/schema/version/source root, authority
  escalation, exact expiry and future clocks. Run focused parser/render contracts
  under one worker and256MiB/CPU20/swap0 caps. No live UI file mirror until verified.

Native UI v9/pubv2/numericv2 compatibility implemented preserving v8. Native rule
andgeometry root closedfield checks, lowprovisional/withheld authority, exact
identity/targets/physicalbounds/expiry; invalid/future/expired v9 UNAVAILABLE.
Node24task attempt22568 terminal124; native-loader24task20585 terminal134 startup
abort; live UI active/NRestarts0/no corefile/PSIzero verified. Frontendonly64task
cap with1worker/CPU20/Mem256/swap0/V8pool1/nativeconfig loader:29271 actual3 RED
of18/2.20s; corrected71067 GREEN85parser/4.80s;54572 GREEN15renderer/24.30s.
100currenttests pass. Numeric24task/BLAS1/pressure guards unchanged. All11native
runtime sourcehashes match bb640b8; no new model/artifact required for UIonlychange.
Live rootdecoder mirror and fresh HTTP/browserverification stillpending. No
live unit/model/actuator changes or GitHubpublication. FullPR3 remainsactive.

2c088e2 native UI decoder installed using checked2file gitpatch, preserving
unrelated dirty root overlay. Private originalbytes/patch/pre-after SHA retained.
Actual UI serviceactive/NRestarts0; loopback/LAN/moduleHTTP200. Fresh96task/
CPU20/Mem256/swap0 browser7331 terminal0 renderedHome, liveconnection, nooverlay,
0pageerrors/0failedrequests. Serveddecoder syntheticnativev9 probe ready/
PROVISIONAL/low/withheld/1point; this is not proof of real nativeforecast issuance.
All numerical/UIbrowserhandles terminal; selectedML v1 andunits unchanged. Actual
native as-issued futuregeometry/producer/monitor andhousehold source/model/cycle
compatibility remainrequired. Publicationapproval remains pending; no GitHubwrite.

Native household thermal projection task
- Add prepare_native_projection(capture, *, code_revision, runtime,
  expected_artifact_sha256, expected_capture_sha256, check_budget) to existing
  household/thermal_model.py. Snapshot caller inputs before callbacks, qualify
  current native execution runtime and replay the externally pinned native capture.
- PreparedProjection accepts closed prepared-thermal/v2 only with native model
  rule, complete immutable geometry packet/root and native execution runtime/v2.
  Preserve v1 factory/type/output. Snapshot temperature evidence and operator/
  forcing context use original policies and identical source observations.
- project dispatches native prepared v2 to NativeInstalledShadeDynamics and pure
  geometry packet replay; result projection/v2 preserves original forecast/v2
  output exactly, unknown action effects, low confidence/no action authority.
- Tests first: complete24h output parity/typed descriptor; exact snapshot clocks;
  pure project/restore with all filesystem/SQL reads forbidden; wrong native
  artifact/capture/runtime/geometry and resealed original output; caller mutation;
  v1 cannot consume native context; closed fields and immutable returned values.
- Native weather/source/model/pipeline/cycle support follows this required step;
  no model selection or physical authority is changed by projection preparation.

Native household weather/context integration task
- PreparedWeatherContext accepts closed prepared-weather/v2 only paired with
  prepared-thermal/v2 and original native origin/v2. Pure restore independently
  matches captured candidate/runtime/coefficients, source observations, actions,
  forcing, native geometry packet/root/model rule and exact numerical output.
- Add prepare_native_weather_context with separate native capture validation and
  explicit external runtime/artifact/capture roots; prepare_native_cycle_contexts
  freezes caller capture and prepares both contexts through one native model
  validation boundary. Preserve original v1 APIs and closed schemas.
- project_weather emits projection/v2 with native geometry/root lineage. Current
  measured weather qualification remains not_assessed; computed forecast geometry
  does not become a measured radiation/humidity/wind observation or action evidence.
- TDD native source/model/shared-snapshot/pipeline/private CLI parity; pure restore
  prohibits file/SQL access, resealed original geometry/runtime/model/forcing/source
  tamper and mixed v1/v2 refusal. Run original/native context/pipeline regressions
  in bounded serial cohorts after all code is final; protect72/core9 unchanged.

Native household prepared thermal/weather/projection v2 andnative CLI execution
runtime dispatch implemented. Originalnative capture24h output reproduced exactly;
geometry/rule/root, extern artifact/capture/runtime pins,5sourcehousehold manifest,
source sensors/actions/forcing/model retained. Frozenrestore/model/pipeline forbids
file/SQL reads. NativeprivateCLI mathematically declared runtime fixture replay
passes andcurrentruntime driftrefuses; genuinecurrent-source qualificationpending.
Finalnative21GREEN98891/66.79s. Alllegacy237passed: models80/13.71,snapshot7/12.91,
weather20in2/6.69+6/14.99+5/13.90+4/10.19+3/8.90,pipelines115/37.01,weatherwrapper
15in5/22.99+6/34.11+1/21.89+3/14.70. Total258uniqueaffectedcasespass. TDD RED
projection2/5.80,weather2/6.21,CLI1/10.92,sourceclosure2/7.80 beforeimplementation.
Original72/native11 sourcehashes unchanged. Legacypressure/swap refusals respected,
no resultsfromabortedscopes claimed. Traced2/6/5groups peak133615616/167673856/
160600064 bytes, helpinglimit fixturefootprint; smallergroupsstilloccasionally
withheld byglobaltransientpressure. Allprocesshandlesnowterminal. Actualsealed
stage/currentnative source andproducer/delivery/monitor/householdcoherence still
required. No live model/unit/actuator changes or GitHubwrites; wholePR3 remains
active andall13canonicalrequirements remainincomplete. Wholebranchreviewpending.

a62a9ee native household stagequalification89434 terminal0: sealed215sources,
deployment8438a58, unchangedcandidateffe998e/runtimebb640b8/native11/protected72.
Productioninterpreter loads nativeadapter exports, derives actual v2 household
executionclosure from sealed5sources, reads identical originalcandidate with
core9 fit5c0c45d retained. 11.0092s/121016320B/zeroOOM. Artifact originallybuilt
34b707d; no reinterpretation orfit. Actualnativecaptureprojected=false explicitly;
genuine current-source/native futuregeom andliveproducer/monitor/cycle delivery
coherence remainrequired. All processhandles terminal, codeclean afterevidence
commit. No live units/model/writes/actions orGitHubpublish; fullgoalactive.

Native paired score reader task (approved native monitor migration)
- Add NativeScoreReader in optional native_thermal_live.py, outside protected72
  andrequired9. Accept original compressed source score configuration/v4 only,
  require held shared lock guard, and preserve all3 private source fingerprints,
  allowed loopback endpoints, phase binding, existing publication reads and
  dedicated read-only SQL connections. Replace reader/transport budget together
  with50sec/max40requests, preserving1sec pacing andexisting per-call timeouts.
- native(targets, assessed_at, sensor_epoch) accepts1/2 unique ordered aware
  lossless targets over<=24h, assessed<=actualnow andtarget<=assessment. Fetch
  both endpoints in one original whole-snapshot packet/connection; retain/read
  compressed private digest-bound source, replay cache on every use, verify exact
  request/policy/phase, refuse deleted/changed originals, freeze caller targets.
- Cap aggregate original query bytes at64MB, keep max8MB perpacket, andclose
  connections/retain barriers with unchanged native source APIs. No PUT/action,
  nofit, modelselection orlive units changed by this read-only adapter.
- Tests first: paired SQLconnection1, whole snapshot receipt/invalid barrier,
 31 historicalcycles+outcome32queries under50s pacedvirtualclock, cacheprivate
 original replay/deletion, wrongphase/time/span/precision, source drift refusal.
- Adding optional producer module requires fresh12source runtime/artifact/stage
 qualification after final producer behavior; original9/base72 cannot change.

NativeScoreReader paired acquisition implemented inoptional native_thermal_live.py.
Current12native-reader casesGREEN67795/5.99s; original71reader/querybindingcases
GREEN90161/20.21s,83unique cases. Preserves50sec/max40request/1secpacing/read-only
SQL/privatecompressedwhole-snapshot/sourcephase andlosslessclock/barrier checks.
32queriesfor31missinghistoricalcycles+outcome fit31virtualseconds; actualSQL/latency
notyetqualified. Cache reopensoriginals, missingfileandchangedprivateconfig refuse;
64MBaggregate boundenforced before retention. Initial2REDmissingmodule34287/3.00s
followedoriginalguardpreflightrefusal24047; no guardrelaxation. Original72/prior11
sourcehashes unchanged. Newoptional12sourceruntime/artifact/stage pending until
nativeproducerfinal. No live model/units/writes/actions orGitHubpublication.

109a214 actual nativepairqualification70559 terminal0: two actualqualifiedpoints
06:30/06:35UTC assessed06:40:49.275378UTC, one read-onlySQLquery/originalcompressed
packet, identicalprivate cache/readback. 0.2578s/42766336Bpeak/zeroOOM;
sourcee458d51/28641rawbytes. No livewrites/modelchange/actions. This qualifies a
recentpair only, notfull31cycle productionlatency; fullhistoricalwindow/publisher/
monitor/runtime12 andcoherentnativefamilyhandoff remainrequired. Allhandles now
terminal; localcode109a214 plusactualevidence, no GitHubpublishing approval yet.

2026-10-13 native issuer and household-cycle delivery adapter implemented
----------------------------------------------------------------------
Private v2 config requires external artifact/runtime pins and keeps the original
fixed local telemetry endpoint policy. Native geometry preparation is separate
from issuance: three bounded batches cover 288 future five-minute instants,
complete before collection, and retain immutable per-issue private originals.
The native issuer replays the candidate/original inputs and sends only the two
existing telemetry Items, retains versioned origins/deliveries and both persisted
receipts, and withdraws native unavailable states without reading a model.
The household cycle dispatches v1/v2 separately, requires external native capture
pins, replays original archives, prepares native model/weather contexts, and
preserves forecast-first observer isolation and original source stability checks.

87 unique cases pass across bounded cohorts: native archive/cycle13, native
geometry/publication/driver22, original cycle20, original coordinator/driver plus
paired-reader32. The combined suite exceeded the unchanged85s deadline and is
not counted. Java/transport seams in this task are synthetic; actual current
geometry/capture/latency, runtime12 artifact/stage, native monitor and coherent
production selection remain required. No required9 or protected72 source was
changed, no refit/live write/model selection/action/GitHub publish occurred.
All13 full-program requirements and Astro audit still require their own evidence.
