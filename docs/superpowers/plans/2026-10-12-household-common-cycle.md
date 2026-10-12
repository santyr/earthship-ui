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
