# Earthship UI: post-remediation audit and completion plan

> **For the coding agent:** Adopt this goal at the next safe checkpoint. Preserve completed, verified repairs and unrelated local work. Execute the ordered tasks using the repository's established development, testing and review process. When the installed Superpowers workflow is used, use its executing-plans or subagent-driven-development workflow; the required outcome is the verified work, not creation of a parallel management system.

**Goal:** Repair the remaining demonstrated source-level defects, verify the interactions introduced by the recent remediation and deployment work, and close all newly discovered in-scope implementation gaps with reproducible evidence—without repeating the previous audit or expanding forecast/control authority.

**Repository:** `santyr/earthship-ui`
**Freshly reviewed baseline:** `87a70336fa52a19a282941af1bcd80b2f63ded52` (`main`, merge of PR #42, October 20, 2026).
**Plan date:** October 21, 2026.
**Suggested repository destination:** `docs/superpowers/plans/2026-10-21-post-remediation-audit.md`.
**Architecture:** Existing Svelte/Vite dashboard, OpenHAB REST/SSE and managed control owners, Python weather/thermal/PV pipelines, retained source-bound numerical producers, PostgreSQL observations, durable weather-scoring queues, and observation-service integrations. Preserve these boundaries; make focused repairs.
**Specification:** This goal plus current repository requirements and the established October 20 audit/operational records. Earlier handoffs supply historical evidence, not an instruction to repeat their work.

## 1. Evidence boundary and changed starting point

This plan is based on fresh GitHub source and deployment-record inspection at the pinned revision, current hosted CI inspection, and three local synthetic diagnostic probes. No private household measurements, installed service state, credentials, live devices or operational model artifacts were accessed. A full repository checkout/test run was not available in the remote analysis environment; the attached probes use copied source-function excerpts with explicit in-memory/fault-injection dependencies. Their successful assertions demonstrate the diagnosed behavior, **not repaired software or a production incident**.

The current source is materially different from the previous `65ee7e9` audit baseline. Current CI run **39509322468** completed successfully, including the frontend/build job, browser-fixtures, all three OpenHAB shards, WeatherNext foundation and `nak` authentication. Job success is not a claim that every environment-dependent test ran. There were no open pull requests returned when checked. Recheck both facts when beginning execution. [S01][S02][S03]

Source inspection confirms important previous repair mechanisms now exist:

| Area | Current mechanism to preserve | New audit treatment |
|---|---|---|
| Night-load owner | Capacity-aware retention of still-admissible identities; request-conflict handling; JDBC policy readback | Keep prior findings closed absent a current reproduction; test only affected boundaries and real-cycle evidence. |
| Browser state | Authoritative collection replacement, request deadlines, delta preservation, resync retries and session teardown | Preserve these changes; investigate the residual temperature value/evidence mismatch below. |
| Sensor history | Intersection of contact validity, packet communication intervals and quality barriers | Preserve the correction; audit epoch/policy boundaries and load behavior rather than reimplementing it. |
| Weather scoring | Durable pending work independent of the seven-day report window; matched comparisons; separate artifact and procedure cohorts | Preserve corrected semantics; audit fault isolation, lifecycle, capacity and actual scheduling. |
| PV support | Explicit local-calendar support and v3 target-weighted gains with a target-based prior | Do not reinstate UTC-prefix counting or raw forecast-pair weighting. |
| Browser verification | Maintained fixture project and repaired `test:geometry` command | Extend real gates rather than adding another disconnected test runner. |
| Thermal admission | Explicit original-fit/inference compatibility proof, separate candidate/serving selectors, bounded daily post-step | Preserve the repaired A22 path; verify outcome reporting and the next full scheduled producer/consumer cycle. |

The repository records A22 as source-verified, installed, and exercised by a natural conditioned forecast. Its next genuine morning candidate/post cycle is separately listed as an operational observation. Do not reclassify A22 as unfixed merely because that later cycle was not in the retained record; inspect what has actually happened since. [S04][S05][S09][S12][S19][S20][S21]

## 2. Global constraints

WeatherNext remains the sole active external weather provider. Retired providers may remain available to original historical replay, never as silent active fallback. Preserve the no-billing policy and explicit unsupported probability/weather-field states.

Planner translation and automatic actuation remain disabled. Existing OpenHAB owners and hardware protections keep their authority. No new actuator family, household message, listener activation, device enrollment or live physical test is authorized by this audit plan. Preserve manual/Lightning-payment feeder operation; exclude feeders from automated planning and recommendations.

Keep original source bytes, observations, forecasts, fitted models, issue clocks, admissions and published scores immutable. New computation or corrected scoring must have the appropriate new identity and compatible readers. Retaining an incumbent does not authorize retaining a defective future selection path.

Preserve the intentionally modified live checkout, private configuration, original producer packages, compatibility branches and unrelated services. Do not replace the live checkout wholesale with `main`. A source merge, an installed pin, a successful process exit and a verified domain output are four different claims.

Retain effective approved CPU, memory, IO, task, timeout, lock and no-swap controls. Do not use stale documentation to impose or relax resource limits. A bounded staging probe does not establish production container limits.

Keep missing observations, unknown water inventory, nominal storage capacity, uncommissioned radio devices and unqualified statistical or physical effects explicit. Complete all implementable work; do not fabricate evidence or wait indefinitely for long-lead/rare-event outcomes as a substitute for a precise handoff.

Novel predictive model families remain a separate experiment program. Existing-family refitting made necessary by a correctness repair belongs in scope. Do not automatically implement every challenger in the existing research brief.

## 3. Execution discipline and artifacts

Use one isolated worktree/branch and the existing audit ledger. Give the new findings a distinct namespace such as `R20261021-01`; do not renumber the older A/C findings. A previously closed finding may be reopened only with a reproduction at the actual execution revision.

For each change: establish the failing behavior in a maintained repository test; record RED; repair the root cause; run the new test and related existing gates; review the diff; commit a focused change. Do not weaken assertions, privacy validation, time guards or resource admission to obtain a green run.

Extend existing records with a compact current delta, rather than copying entire historical logs. Required outputs are a current requirement/finding cross-reference, verification evidence, an actual per-surface runtime compatibility map, and a concise release/handoff summary. Keep private paths and payloads out of public reports. Full private local evidence may stay in existing protected storage; public evidence should contain only curated identities, counts, statuses and limitations.

### Review focus

Five cross-boundary cases must be owned by tests: newer source evidence paired with an older displayed value; an optional weather-domain failure suppressing unrelated work; a child failure after a durable selector write; a scheduled producer changing an artifact used by a different immutable consumer; and a matured long-horizon target encountering restart/backlog or observation-policy change. Tasks 1–5 explicitly own these cases.

## 4. Ordered work

### Task 0 — Reconcile the actual branch, runtime and completed work

**Depends on:** nothing. **Produces:** an execution baseline and ownership map for every later task.

Read applicable `AGENTS.md` files, current main and local branch, outstanding reviews, dirty worktrees and the current audit records. Record both the source SHA and relevant non-documentation/runtime identities. If main advanced beyond the reviewed revision, inspect the intervening diff before applying any findings.

Read the current versions of:

- `docs/audits/2026-10-20/findings.json`, `requirements.md`, `verification.md`, `qualification.md`, `deployment.md` and the new thermal-admission proof records;
- `docs/operations/2026-10-20-thermal-admission-compatibility.md` and `2026-10-20-weather-day-icons.md`;
- current workflows, service/managed-resource manifests and the separate published compatibility manifests.

Build a per-surface map of **source → installed package/pin → effective command/environment → selected artifact/admission → consumer → actual last successful output**. Include browser, control owners, sensor ingester, weather acquisition/writer/trainer/evaluator, native thermal learning/preparation/forecast/scoring, daily PV learner/writer/scorer, calibrated storage and household planner/replay.

Where available, use authorized read-only local inspection to establish current versions. A document from October 20 is historical evidence, not a substitute for current readback. Do not assume that every service uses the newest main source; intentional immutable compatibility producers are part of the architecture. Record the reason, provenance and permitted operations for each such producer.

**Gate 0:** Every active surface has an owner and known verification status. Missing local access is an explicit blocker only for that readback, not permission to infer state or abandon source work. Closed A00–A22/C findings are mapped without duplicate repair tasks.

### Task 1 — Make temperature values and freshness evidence coherent

**Finding R20261021-01 — confirmed source-excerpt reproduction; P2.**
**Inspect/modify:** `src/lib/openhab/store.js`, `src/lib/openhab/sse.js`, `src/lib/openhab/timestamp.js`, `src/lib/alerts/staleness.js`.
**Tests:** extend maintained store/SSE/freshness suites; add a browser fixture to the existing Home runtime suite where practical.
**Consumes:** source timestamps, item snapshots, SSE state/evidence events and the existing reconciliation sequence.
**Produces:** coherent displayed source state with truthful freshness; no new freshness clock based on browser arrival.

`applyUpdateEvidence()` rejects an older source timestamp for both curated temperature and Astro Items. `applySnapshot()` respects that rejection when choosing the **value** only for Astro Items. A rejected older temperature value is therefore installed while the newer freshness evidence remains. Temperature `stateupdated` parsing also carries the timestamp without its value, unlike Astro; examine the complete event/state association rather than patching only a label. [S05][S13][S14]

The attached probe sets temperature to 70 with evidence at 12:05 UTC, then applies a snapshot containing 40 with evidence at 11:00 UTC. At 12:06, the current source displays **40** but retains evidence age **60 seconds**; the replacement's own timestamp is **3,960 seconds old**. The analogous Astro value remains at its newer value. These are arbitrary fixture values, not household measurements.

- [ ] Reproduce this case against the imported production module in the normal test harness, asserting the desired coherent outcome; record the failure.
- [ ] Define and implement a single value/evidence ordering rule for the curated temperature Items. Reject or explicitly withhold stale/conflicting state rather than attaching a newer timestamp to an older value. Preserve authoritative withdrawal when an Item genuinely disappears.
- [ ] Test older/newer/equal timestamps, equal-time conflicting values, malformed/missing/future clocks, same-valued updates, statechanged/stateupdated ordering, evidence received during snapshot reconciliation, resource removal, and session/source reinitialization. Legitimate timestamp/epoch reset must require a declared source reset, not silent clock mixing.
- [ ] Preserve first-open resync, bounded retry, cancellation and removed-provider handling. A malformed snapshot must become a bounded unavailable/retry state rather than an unhandled rejection.
- [ ] Run focused tests and a Home browser check showing that value and age agree through the failure/recovery sequence.

**Gate 1:** The original mismatch no longer reproduces, temperature freshness is tied to the accepted state, Astro protections still pass, and recovery sends no commands.

### Task 2 — Isolate optional weather-domain failures

**Finding R20261021-02 — confirmed fault-injection path; P2.**
**Inspect/modify:** `openhab/scripts/weather_learning/monitoring.py`, `solar_shadow.py`, `energy_shadow.py`, the existing monitor worker/public projection consumers as needed.
**Proposed new test file:** `openhab/scripts/test_weather_monitor_fault_isolation.py`, unless a maintained equivalent already exists.
**Consumes:** retained issue/snapshot originals, domain-specific forecast derivation and outcome readers, durable pending queues, approved work/time budgets.
**Produces:** independently truthful temperature/solar/rain/correction results with explicit per-domain failures.

The current monitor catches issue-loading errors and local outcome-read errors, but calls `solar_window_forecast()` and `rain_day_forecast()` outside those isolation boundaries. Those calls occur **before** temperature queue bootstrap/scoring. A solar derivation failure propagates out and prevents temperature work from being reached. End-of-run domain aggregation also needs an explicit error-boundary review. [S06]

The attached probe injects `ValueError('one original solar grid required')` at the real solar-derivation boundary and demonstrates that the temperature stage is not reached. It proves the failure propagation, not that a malformed solar source currently exists in the live archive.

- [ ] Add normal-harness tests for a temperature-valid issue whose solar derivation fails, whose rain derivation fails, and whose local solar/rain evidence is unavailable. Assert valid temperature/correction work proceeds and the failed domain is explicit.
- [ ] Add tests for one bad issue among valid issues and a domain aggregation error after valid temperature scores have committed. No committed score may be lost or recomputed under a different identity.
- [ ] Introduce narrow per-issue/per-domain boundaries around derivation and aggregation. Preserve errors from global deadline/resource admission: optional failure handling must not swallow a global stop condition or continue past the approved budget.
- [ ] Retain raw originals, original clocks, queue identity and matched scoring. Do not synthesize missing products, turn unknowns into zero, or widen acquisition scope.
- [ ] Keep the public report schema closed and compatible. Where representing a domain failure requires a new version, ship consumers and tests with the producer. Valid reports from unaffected domains remain publishable; logs and public reasons stay bounded and non-sensitive.

**Gate 2:** The injected optional-domain failure no longer suppresses valid unrelated work. Global stop guards still stop the run. Partial reports are explicit, distinguish failed from pending, and pass the browser/parser contract.

### Task 3 — Report selector outcomes from durable evidence, not child exit status

**Finding R20261021-03 — confirmed parent-function fault injection; P2.**
**Inspect/modify:** `openhab/scripts/thermal_weather_readmit_post.py`, `thermal_weather_readmit.py`, and the existing private-file/selection validators.
**Tests:** extend `openhab/scripts/test_historical_weather_daily.py` and the existing thermal admission/replay tests.
**Consumes:** original candidate/serving selectors, the bounded child operation, exact proof/admission validators and immutable source references.
**Produces:** an accurate verified-new / unchanged / uncertain outcome without unsafe retries or rollback.

The post-step returns `thermal_readmit_unavailable_previous_preserved` for every nonzero child exit. Its CLI exception handler also uses that status. It never compares the selector before and after execution. The worker writes the new selector near the end of `readmit()`, then returns; process failure can occur after publication but before successful termination. Therefore a failed exit is not proof that the old selection survived. The existing test checks a nonzero exit but does not simulate a child that published first. [S15][S16][S17]

The attached fault-injection probe writes a different temporary selector and returns child exit 1. The unchanged parent still reports **previous preserved**. This is a result-reporting/transaction-boundary defect, not proof that the child bypassed its model validators or that a live selector was corrupted.

- [ ] Add repository-native regressions for failure before any write, success, failure after atomic publication, timeout after publication, unreadable selector, and a concurrent independent selector update.
- [ ] Capture bounded original selector identity before execution and inspect it afterward using the established safe readers. Validate any observed new admission/proof under the actual consumer/runtime contract before describing it as usable.
- [ ] Represent at least unchanged, verified newly selected, and changed/uncertain outcomes. A failed child with verified output may report publication with execution failure; it must not be silently labelled an ordinary successful run.
- [ ] Do not automatically repeat the operation, reinstall the previous selector, or undo another writer's change. Any rollback must use established ownership and compare-before-write protections.
- [ ] Reserve readback/cleanup time **within** the existing owner deadline. Cover readback failure and cancellation without expanding the shared resource limits.
- [ ] Review selector publication durability and result-receipt ordering in the worker. If a crash-safety change is needed, test it on disposable copies and keep all original admissions/proofs intact.

**Gate 3:** Every preservation or publication claim is supported by actual readback, or is explicitly uncertain. The post-step retains its deadline, private diagnostics and no-repost behavior.

### Task 4 — Verify the complete scheduled producer/consumer lifecycle

**Depends on:** Task 0; Task 3 for modified post-step release. Tasks 1/2 may be developed independently after the baseline is established.
**Status:** required follow-through and integration audit, not a claim that the previously repaired A22 is still broken.

Current deployment records describe multiple intentional source families: an incumbent-compatible weather writer/trainer, corrected evaluator, incumbent-compatible PV serving, corrected PV candidate generation with `--retain-selection`, and a separately bound thermal consumer/admission. They also record the earlier A20 future-selection and A22 admission-compatibility defects. Preserve their fixes and use those incidents to audit complete lifecycle transitions, not only today's successful forecast. [S08][S12][S18]

Create executable integration cases for:

1. No-op refresh with unchanged eligible data: model clocks, identity and expiry are not renewed merely to appear fresh.
2. Genuine new fit: a candidate is produced with correct source and training-policy identities; selection follows its explicit policy, including incumbent retention where configured.
3. Compatible admission transition: exact consumer source closure, candidate/serving separation and prepared geometry remain valid together.
4. Incompatible/expired/missing candidate: retain a still-valid prior admission or report declared fallback/unavailability. Never extend an expired artifact without evidence.
5. Failure between fit, proof, immutable output, selector replacement and the first consumer issue: recover deterministically and preserve historical replay.
6. Consumer source upgrade and rollback: compatibility must be established against the actual installed package, not assumed from main's SHA or a matching filename.

Use the actual scheduled entry points in disposable orchestration tests. Validate effective environment composition, including EnvironmentFile values, private path modes, source roots, selected-pointer ownership, companion profiles and producer dispatch.

For the household host, first read available natural-cycle logs and retained receipts. The October 20 record names later daily, six-hour and night-load transitions; some may already have happened by the agent's current clock. Inspect existing evidence rather than waiting for an already elapsed time or manually triggering an unapproved publication. The first natural conditioned delivery is already documented; the distinct morning candidate→post→consumer cycle still requires its own evidence unless later records close it.

**Gate 4:** Each installed procedure is tied to verified effective entry points and outputs. Every remaining operational observation has a named cycle, latest known evidence and exact acceptance test. Do not merge compatibility overlays wholesale into main or activate a previously retained challenger to simplify the map.

### Task 5 — Stress durable scoring and publication under real bounds

**Inspect:** `weather_learning/pending_scores.py`, `monitoring.py`, `performance.py`, current correction-queue/worker modules, `ShadowStore` issue indexing and the report server/consumers. Discover exact current correction-module names before changing them.

The pending queue and matched/cohort evaluator are already implemented; the goal is to verify their completeness, failure isolation and bounded progression—not rebuild them. [S06][S07][S09]

Use synthetic and disposable original-bound records to test a full 336-hour target lifecycle across restarts, seven-day report-window changes and the declared observation-arrival allowance. Mature predictions must be scored from their original issued values, never regenerated by current weights. Exercise late observation availability and late discovery separately; clarify which clock each deadline constrains.

Verify durable commit, duplicate suppression, source-index replacement, earlier same-day issue supersession, missing/corrupt original dependencies, observation policy/sensor epoch changes, and evaluation-version changes. Historical scores must remain retrievable under their own identities. Every new scope requires explicit compatible discovery rather than accidentally qualifying new hardware from an old epoch.

Test backlog fairness and throughput with representative issue frequency and source history, including permanently missing early dependencies and successful later work. Progress must fit current per-cycle quotas and deadlines. Report backlog age, pending/matured/expired/withheld counts and bounded retry reasons; do not hide starvation behind exit code zero. Determine queue/archive capacity and retention behavior, including low disk, failed transaction and interrupted report publication. Preserve original evidence and avoid a new archive-recovery project.

Exercise report byte bounds and cohort growth. If an otherwise valid report exceeds its cap, provide an explicitly bounded/paginated or summarized compatible representation rather than dropping domains, relaxing the cap arbitrarily, or silently omitting samples from qualification. A sampled display must disclose its scope.

Verify immutable score receipts and report schemas through the fixed GET endpoints and browser consumers. Cross-cohort diagnostics remain distinct from current-artifact or stable-procedure qualification. Maintain matched raw/candidate populations, fallback-inclusive policy evaluation and source-quality distinctions.

**Gate 5:** Long-horizon work survives and progresses under the approved resource profile; permanent bad inputs do not starve healthy work; scoring and public coverage remain truthful across restart, growth and scope changes.

### Task 6 — Audit new solar presentation and all corrected-model consumers

**Inspect:** `openhab/scripts/site_daylight.py`, shared terrain and native geometry modules, the fixed `/api/terrain-daylight` route, its parser/store, Home/Weather icon and detail presentation, thermal conditioning and PV/storage consumers. Use current source inventory to resolve frontend filenames instead of guessing them.

The new terrain-daylight projection deliberately reuses retained five-minute native geometry and the declared horizon, produces an unvalidated map estimate, and expires at the end of the local day. It does not acquire new astronomy, establish measured light, or authorize controls. Preserve those semantics. [S10]

Test the 23/24/25-hour local-day cases, midnight rollover, complete-day geometry coverage, no sun, multiple disjoint direct-sun windows, missing/future/corrupt geometry, changed horizon/source runtime, and concurrent cache publication. Confirm duration is the sum of declared visible bins, not simply last-sun minus first-sun when terrain creates intervening gaps. Preserve the five-minute approximation and distinction between astronomical daylight, terrain direct sun and actual cloud-modulated light.

Audit cache selection and scan cost at realistic retained sizes, including one unrelated corrupt/private-mode-mismatched file. Decide explicitly which faults invalidate one candidate and which invalidate the entire trusted directory. Do not casually weaken safe-file ownership, no-symlink or original-hash requirements. Resolve any unnecessary domain-wide outage with a test and documented policy.

Test daily weather icons and current-day summaries against their actual time population: full day versus remaining day, daylight versus darkness, missing hours and source expiry. Each representation must disclose what it summarizes and must not silently substitute one forecast issue for another in scored originals.

Confirm PV baseline parity, overlap-preserving raw/corrected thermal radiation, local-day support and target weighting remain in place across all active entry points, not just pure helpers. Keep GHI, local lux-proxy exposure, direct-beam terrain effects, controller PV input, available array output, captured energy, AC demand and nominal storage distinct. Do not double-apply proxy and electrical corrections.

If any new numerical change is necessary, version it and perform local original-bound reassessment against the existing corrected incumbent as well as raw physics/WeatherNext. Preserve older numerical producers and published scores. A successful refit or lower development MAE is not, by itself, permission to promote a model.

**Gate 6:** Display and downstream model semantics agree about source, time, terrain and target; performance claims are no broader than the verified measurement support.

### Task 7 — Complete the cross-system delta audit

Use the existing requirements and test-ownership inventories as a map, not proof. Trace every current route and active producer/consumer boundary, including auxiliary routes added since the earlier review. Review code changed since the original audit and unchanged high-risk interfaces it touches. Test any resulting defect before changing it.

**Controls:** Regress bounded idempotency, capacity exhaustion, exact policy persistence, request conflict, restart uncertainty, provider confirmation, cooldown, pump alternation/overlap, stale Astro/SoC and timer ownership. Verify server release modes and frontend eligibility agree. No automatic command reposts or test stimulation of real hardware. Existing failed/offline device providers are operational dependencies, not software success.

**Sensors:** Regress supervised duration, communication-only updates, gaps, frame counters, rejoins, disabled/missing devices, epoch replacement, registry policy changes, duplicate packets, MQTT retention and database recovery. Ensure service-online/empty-registry does not become device-online. The deployment record explicitly says production ingester resource settings were unbounded while staging was bounded; inspect current effective limits and assess the risk. Do not claim staging caps protect production, and do not change operational limits without the applicable scoped authority. Actual radio commissioning stays separate.

**Nostr:** Preserve exact-binary cryptographic qualification, sender/recipient identity, replay/idempotency and durable outbox behavior. Relay acceptance is not operator receipt. Keep default authority gates, household keys and real message delivery out of unapproved tests.

**Household architecture:** Regress immutable snapshot→model→typed intent→arbiter→report/replay, explicit unsupported domains, original-plan authority and rejection reasons. No new sensor, corrected forecast or successfully parsed v2 contract may grant action authority. Feeder proposals remain excluded without breaking manual/payment flows.

**Access and operations:** Verify closed public projections, fixed file routes, origin/host restrictions, encoded-path handling, no credential exposure, private source/archive readers, effective service environments and immutable package permissions. Test dependency failure, cancellation, shared-lock contention and cleanup using disposable environments. Backup/restore and migrations are limited to existing changed contracts.

**UI:** Check Home, Weather, Energy, Earthship, Controls, Shades, Ventilation and actual auxiliary routes at 1340×800 and 1280×720. Test stale/missing/malformed/future evidence, reconnect, expired corrections, inaccessible providers, touch/hold/focus behavior, modal dismissal, chart resize and measured-versus-predicted overlays. Assert no browser errors, unintended mutation requests or misleading zero/fresh/qualified states. Keep existing visual style and avoid unrelated redesign.

**Gate 7:** Every current approved capability has a disposition; all newly found in-scope defects are repaired and tested. Genuine hardware/access/measurement blockers have narrow acceptance criteria and do not conceal unfinished software.

### Task 8 — Verify one integrated release candidate

Run the current repository's maintained workflow matrix with its exact lockfiles, Node/Python/Go profiles, native dependencies and Solar_PV companion pins. Do not replace declared profiles with whichever versions happen to be installed. The audit's remote Node/Python probes are not replacements for these gates.

Minimum advertised frontend commands, verified to exist at the reviewed baseline:

```bash
npm ci
npm run test:unit
npm run build
npm run test:geometry
npm run test:e2e
```

Run `npm run test:e2e:sensors` only with its required isolated sensor environment, and report whether that integration actually ran. The general fixtures and sensor project are separate on purpose. Do not manufacture a combined count from overlapping suites. [S11]

For targeted repairs, use maintained tests, including the existing store/SSE suites and `openhab/scripts/test_historical_weather_daily.py`. Add the new fault-isolation tests to the normal discovered Python partition. Run all three OpenHAB shards and relevant completion/operational, ML hardening, receipt-integrity, sensor, encrypted-delivery, WeatherNext and browser/native profiles. Keep opt-in/native/cloud/hardware qualifications distinct.

Review required-check triggers and test ownership for every changed source and test. Confirm a representative intentional failure is detected by its owning gate in a disposable test, not by weakening production code. Account for skips by environment and dependency; a job that is green because relevant tests never ran does not close the affected requirement.

Freeze the tested source and artifacts, then perform final independent review if available. Reviewers must check the actual code, fixtures, changed output contracts, release identities and authority boundaries—not only counts or prose. Any source change after the freeze requires appropriate renewed checks; documentation-only descendants must be demonstrated to preserve the relevant source digest.

**Gate 8:** The final release candidate has complete, current evidence. The three new failure conditions are repository-native regressions with expected correct behavior, not standalone scripts asserting the old bug.

### Task 9 — Scoped delivery and operational handoff

Follow the owner's current established authorization for commit/PR/merge and deployment. This plan creates no new blanket authorization to replace selectors, publish forecasts, restart household services, change database permissions, send messages or operate equipment. Complete unaffected source work while a genuinely external authorization remains pending.

Prepare per-surface compatible handoffs with before/after identities, effective command/environment, original artifact retention, output/readback checks, and scoped rollback. Do not treat a new main commit as the deployment identity of every service. For numerical/admission changes, establish source→artifact→selector→consumer compatibility before any switch; retain the last valid serving path when the transaction refuses.

Verify authorized changed surfaces after installation. Prefer existing natural-cycle evidence for runtime closure. Do not manually trigger a household operation merely to obtain a green screenshot or satisfy an expired scheduled window. Preserve producer dispatch so old receipts continue to replay correctly after rollback or forward recovery.

Publish a concise current status with four independent dimensions: **source-fixed**, **installed**, **runtime-observed**, and **statistically/physically qualified**. Historical pending prose may remain as history, but current status must have one unambiguous machine-readable authority and explicit supersession. Do not overwrite previous source freezes or old scientific results.

**Gate 9:** The deliverable identifies exactly what changed, what was tested, what is installed, which natural paths were observed, what remains unqualified and what evidence would close each dependency. No promise of later background work substitutes for this handoff.

## 5. Definition of done

The executable goal is complete when all three newly demonstrated source-level behaviors are repaired and verified in the normal harness; the current producer/consumer and runtime compatibility map is complete; the scheduled lifecycle and durable scoring stress cases pass; all additional discovered in-scope defects have verified root-cause repairs; and the integrated release/handoff evidence is accurate for the actual revision and authorized installed surfaces.

Previous fixes remain closed unless current evidence contradicts them. Global safety/resource/privacy guards are intact. No new external provider, billing, feeder automation, planner action authority, unapproved live message or hardware qualification has been introduced. Every known unresolved item is labelled either unfinished implementable work, blocked deployment verification, or a concrete external/statistical/physical dependency—never a vague “future improvement” used to hide a required fix.

Do not claim proof that no undiscovered defects exist. Do not stop at another report or backlog when authorized implementation remains possible. Conversely, do not hold source completion indefinitely for future rain, a fourteen-day forecast, new hardware or causal action evidence; retain their bounded monitoring and exact acceptance tests.

## 6. Out of scope unless a new correctness finding requires a narrow change

Do not replace the small correction models with new neural/adaptive/distributional families, alter approved sampling/selection policy to make results look better, smooth the PV gain merely for appearance, or add humidity/pressure predictors without a separately predeclared experiment. Maintain the existing challenger-comparison brief as the subsequent research stage. Correctness-driven refits and reports needed for current repairs remain in scope.

Do not start a new whole-house backup/migration platform, generalized deployment framework or redundant evidence database. Add only the minimal current-state, lifecycle and regression coverage required by actual gaps.

## 7. How to use the attached evidence

The bundle contains three standalone reproductions and their captured outputs:

```bash
node evidence/temperature-snapshot-probe.mjs
python evidence/monitor-isolation-probe.py
python evidence/post-selector-status-probe.py
```

They require only Node and the Python standard library and perform no network/device access. They intentionally assert the currently diagnosed behavior. The temperature probe uses unchanged source functions with in-memory stores; the monitor probe uses the unchanged orchestration prefix and an injected optional-domain failure; the post-step probe uses unchanged parent functions with a temporary selector and injected failure after publication. Build the final regression tests against the actual imported repository modules and complete code paths. Do not mistake these limited probes for a full-source test suite or a claim of household incidents.

## 8. Source references

All code references are pinned to `87a70336fa52a19a282941af1bcd80b2f63ded52`. The branch and pull-request collection reads establish the point-in-time repository state and must be refreshed locally before implementation.

[S01]: https://github.com/santyr/earthship-ui/commit/87a70336fa52a19a282941af1bcd80b2f63ded52
[S02]: https://github.com/santyr/earthship-ui/actions/runs/39509322468
[S03]: https://api.github.com/repos/santyr/earthship-ui/pulls?state=open&per_page=10
[S04]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/rules/night-load-owner.js
[S05]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/src/lib/openhab/store.js
[S06]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/weather_learning/monitoring.py
[S07]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/weather_learning/pending_scores.py
[S08]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/docs/audits/2026-10-20/deployment.md
[S09]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/weather_learning/performance.py
[S10]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/site_daylight.py
[S11]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/package.json
[S12]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/docs/audits/2026-10-20/findings.json
[S13]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/src/lib/openhab/sse.js
[S14]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/src/lib/alerts/staleness.js
[S15]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/thermal_weather_readmit_post.py
[S16]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/thermal_weather_readmit.py
[S17]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/test_historical_weather_daily.py
[S18]: https://github.com/santyr/earthship-ui/pull/41
[S19]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/weather_learning/pv_directional_calibration.py
[S20]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/openhab/scripts/weather_learning/weights.py
[S21]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/services/lorawan/history.py
[S22]: https://github.com/santyr/earthship-ui/blob/87a70336fa52a19a282941af1bcd80b2f63ded52/src/lib/openhab/timestamp.js
