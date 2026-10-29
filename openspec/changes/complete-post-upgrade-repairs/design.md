# Design

## Context

See `proposal.md` for scope. The main checkout contains unrelated work; canonical
native code is in `.worktrees/post-upgrade-runtime-20261024`. Existing immutable
artifacts remain under `artifacts/post-upgrade-repairs-20261024.local`.

Verified evidence carried forward:

- Signed runtime commit `a14b6e3f18db9d6cee3bd41601aa35749b5a0098`
  corrects the retained-coordinator pin; 78 covering tests passed. It is not
  deployed. Native 19-file, fitted 81-file, and codec identities were unchanged.
- The actual dense private capture retained 8,638 rows and replayed all three
  289-target grids. That does not prove full scoring or publication.
- The historical 198-score run reached two actual PostgreSQL read-only sessions
  and closed both without commits, then timed out at 119.003 seconds during final
  verification. Full qualification failed.
- That fixture used stage/script/operational-file/config depths 11/15/12/11.
  Inspection of the active unit confirms its executing coordinator is in the
  staged archive at depth 14; the earlier depth-10 operational-source note named
  a release copy, not the executed file. The retained historical model's actual
  stage/script/config depths are 9/13/9; the current model's are 10/14/10.
  Repeated source checks consumed 36.89 seconds. Fixture fidelity must match the
  selected model and actual execution path, not the earlier assumed location.
- The Oct27 ten-minute radio watch passed 600 samples, including Bedroom. The
  clock layout passed 11 focused live views. These are bounded historical checks.
- The Oct28 OpenHAB diagnostic ended with launcher defer 75, no thread-dump
  signal, and no test bodies completed. Both terminal verifiers passed: seven
  private IDs removed, production and volumes preserved, guardian collected,
  original admission lock free. The exact historical pressure sample is absent.
- The dense synthetic design lacks an explicit extra 05:55 capture/delivery;
  its proposed reader adapter cannot supply that missing origin.

## Goals / Non-Goals

**Goals:** Finish the existing recovery contracts, preserve evidence, and verify
the deployed data paths. Use OpenSpec as the active checklist and decision record.

**Non-Goals:** Security scans or hardening; equipment actuation; retired
Lightningd work; resetting retained databases; rewriting evidence or timestamps;
raising resource or freshness limits to obtain a pass.

## Decisions

1. **Keep workflow metadata in the canonical project.** OpenSpec lives in the
   main project; current immutable runtime archives stay untouched. Existing
   `.superpowers` documents supply historical facts only. Superpowers skills,
   mandatory delegation rules, and fix-round ceremonies are not used.

2. **Correct fixture fidelity before optimizing production.** Prepare a fresh
   historical case with measured production-equivalent path depths, preserving
   all 197 retained records, the genuine extra job, actual read-only acquisition,
   complete reports, final checks, and the original 119/120/50-second limits.
   Arbitrarily shortening paths or extending time would obscure the result.

3. **Preserve full dense numerical coverage.** Retain 64 cohorts and four
   horizons, ten distinct seed contexts, all original query and cache pressure,
   and an additional complete origin/delivery for the extra job. Generate the
   eleventh context through the same full builders. Use natural complete raw
   envelopes; do not pad data to an invented byte floor. A minimal explicit
   in-memory reader factory is acceptable only if needed for the full synthetic
   coordinator, with unchanged production defaults and original guard behavior.
   Synthetic transport/SQL evidence earns no actual acquisition/publication credit.

4. **Diagnose OpenHAB from observed behavior.** Preserve the consumed diagnostic
   case. Determine the launcher defer path and record host pressure at relevant
   boundaries before selecting another measurement. Keep the complete seven-
   service workload and existing aggregate caps; do not guess pool settings, retry blindly,
   or claim topology evidence from a case where Java never reached the trigger.
   The provisional per-process split may be revised only from measured peaks,
   with a declared source change and independent budget arithmetic. The balanced
   candidate moves sixteen controller slots to OpenHAB (32/48 controller,
   144 OpenHAB); Python and post-retirement browser totals both remain 248 under
   the original 256 aggregate with eight spare. No credit transfers from the
   failed 128-task candidate: rerun the complete workload, resource-event and
   guardian8 recovery gates for the new split.
   Actual browser startup also exhausts the provisional512MiB controller scope.
   Use the established1024MiB UI allocation within the unchanged6144MiB pool,
   retaining all2112MiB external reservations,256MiB uncertainty and3072MiB host
   reserve. Commitment is3136MiB; initial host availability must be6208MiB and
   residual must remain at most2752MiB. Do not transfer passing Python results
   into a browser-capacity claim. Observe positively stopped, empty retirement
   cgroups separately; running service caps remain strict.

5. **Deploy a coherent current family.** Reconcile each legitimate scheduled model
   transition, preserve original fit/admission provenance, and avoid reverting a
   newer selected fit to an older private test candidate. Update the required
   source routes and five family files together through the existing bounded
   activation path. Observe fresh household publication, analytics, sensitivity,
   and the subsequent scheduled fit before closing their tasks.

## Risks / Trade-offs

- [Timed fixture still fails] → Preserve the failure and measure the remaining
  cost; do not infer production success from path correction alone.
- [Host pressure changes during a private case] → Retain actual pressure and
  event deltas, honor the existing defer behavior, and verify cleanup.
- [Scheduled fits alter legitimate selections] → Verify the actual transition
  and record an explicit before/after chain rather than changing old baselines.
- [Planning completion is mistaken for recovery] → Track source, tests,
  deployment, publication, and natural operation separately in `tasks.md`.

## Migration Plan

1. Preserve the current source/evidence inventory and finish missing qualification.
2. Prepare the exact deployment delta and restoration material.
3. Activate through the existing lifecycle, preserving timer and owner state.
4. Verify actual APIs, analytics, all UI routes, radio delivery, and scheduled jobs.
5. Integrate only the qualified changes into the dirty main checkout and retain
   rollback material. Archive this OpenSpec change only when all tasks are proven.

## Evidence References

All paths below are relative to the project root:

- `artifacts/post-upgrade-repairs-20261024.local/repair-tracker.json`
- `.worktrees/post-upgrade-runtime-20261024/.superpowers/sdd/2026-10-26-native-temperature-source-density/task-3-retained-coordinator-pin-correction-report.md`
- `artifacts/post-upgrade-repairs-20261024.local/native-temperature-density-20261026/preparation/phase-h3-a14b6e3-historical198-prep/parent-historical198-terminal-failure.json`
- `artifacts/post-upgrade-repairs-20261024.local/sensor-topology-witness-v1-a01/topology-terminal-supplement.json`
- `.worktrees/post-upgrade-runtime-20261024/.superpowers/sdd/2026-10-26-native-temperature-source-density/task-3-phase-h-synthetic-design-review.md`

## Demonstrated post-publication budget mismatch

The deployed segmented runtime produces confirmed as-issued thermal deliveries
(the 01:35 UTC delivery and 01:45 UTC UI-proxy values are retained), while the
whole ninety-second service times out during household derivation. A 20-second
nonblocking stack-only sample contains 353 valid samples and 146 failed samples;
310 valid samples are in `complete_cycle/load_cycle_delivery`, 309 in original
segmented source replay and 291 in the original expensive guard. Sampling does
not mutate source, inputs, worker clocks or caps and contains no locals.

The post-publication guard returns None, so the unchanged segmented adapter must
call it on every raw row. Its existing numeric contract supports local expiry
checks between full 64-call/5-ms checkpoints. Give the whole coordinator one
fixed 85-second work deadline from entry (the existing native publication work
bound), expose its positive remaining time from both forecast/observer guards,
and retain all their full lock/resource/config/source checks, terminal checks
and the original 90-second outer service. Observation never gets a renewed
budget after publication. Unknown/invalid clocks or any original refusal remain
terminal. No cache, source thinning, timeout extension or model change is needed.
Implement/test this in the isolated `post-publication-budget-20261029` worktree;
the currently selected clean runtime and immutable deployed archive remain intact.

The numeric-guard source `506d09d` passes 185 cycle cases and a genuine retained
delivery replay in 7.485 seconds (4,117 full original checks). It is deployed
through the unchanged reserved lifecycle with the exact existing model/admission.
The natural 02:20 UTC cycle completes, writes energy/calibrated products and
restores the analytics snapshot consumer. Its whole cycle still takes about
86 seconds; short-lived original inputs can expire before household derivation.
Some independent inputs also report missing-source; preserve those truthful
unavailable states and diagnose them separately instead of inventing readings.

Use the already qualified pure-temperature helper inside the SAME held-lock,
85-second publication worker, from acquisition through final observation. Admit
the helper's exact existing coordinator pin from the same release, and recheck
it on successful exit. Delegate to its existing job-local 16/8 MiB LRUs and
original fresh-byte/file-identity checks. This avoids repeated complete decoding
of the same retained source; original first decoding, all external I/O/pacing,
50-second acquisition limits, model/capture validation and final source checks
remain unchanged. All entries clear at exit/cancellation; no new capacity,
cross-worker reuse, expiry extension or model change. Test publication-to-
observation hits, next-worker isolation, refusal and cancellation restoration,
covering cycle/helper suites and actual retained replay before deployment.

### Remaining publication latency (measured Oct29 03:55 UTC)

The nonblocking stack-only profile retains 347 samples (69 sampling errors). Repeated full production-temperature confirmation decoding (`production_thermal_source._points`, `read_emission`, `read_issue`) appears in 107 samples. The proposed publication-only reuse keeps the original decoder mandatory on the first exact request, rereads all three immutable view/emission/issue documents on every reuse, checks the complete arguments and stable file/parent inventory, returns detached results, and retains all existing runtime/source/deadline guards. Its fixed 8 MiB/16-entry bound falls back to full decoding for large inputs. It never caches across completed jobs or worker threads, modifies originals, advances a clock, extends expiry, grants admission, or changes a fitted/scoring source. Source tests, real current-original replay, activation and natural post-deployment freshness must be recorded separately.

### Private OpenHAB diagnostic follow-up, 2026-10-29

The consumed Oct28 case created seven exact private containers, armed the guardian and started MQTT, then the outer original launcher exited 75 before the Python child files were created. The controller's only return-75 branch precedes container creation and cannot explain that observed sequence. In the original launcher, the post-start polling loop raises AdmissionDeferred through check_host_pressure: some avg10 >5%, full avg10 >1%, or MemAvailable below 1536 MiB. The exact original readings were not retained; their values and which condition fired remain unknown. Do not infer them from a later healthy snapshot.

A fresh case sensor-pressure-witness-20261029-a01, nonce b7000000000000000000000000001202, records the exact pressure text and available-memory value consumed by that original callback, including its original exception reason. The existing launcher retains its unchanged admission, startup, stop and wait paths, original 512 MiB/64 admitted task/1800 second controller allocation and 48-task Python phase, seven-service composition, guardian8, eleven Python and two browser selection. Every existing threshold remains unchanged. The prior bounded observer is reused with only fresh path/nonce bindings; its single private-Java SIGQUIT requires the same actual first PID-limit event, identity, armed guardian and startup interval. Production containers, private inputs, immutable original case and all retained volumes remain protected. No deployment or equipment command is added.

The observed launcher instrumentation passes healthy, some-pressure, full-pressure and emergency-reserve checks against the actual unchanged health function. It records the exact text and preserves original return/refusal behavior; no real job, container, or test fixture was launched by those checks. Root preflight, a naturally drained resource window, a fresh consumed approval receipt and both original/supplemental terminal checks remain required for the one new case. No blind retry or guessed Java pool configuration is authorized by this note.


### Exact cap-mismatch attribution

The prior pressure witness completed all 189 original health checks without refusal (minimum available RAM 7,101,415,424 bytes; maximum some/full avg10 0.42/0.42). Its full original Python selection failed readiness under a demonstrated private OpenHAB PID limit; MQTT BrokerHandler initialization could not create the RxJava purge scheduler thread. Both terminal verifiers pass. No thread dump exists: the external observer stopped first on a generic caps_changed refusal.

This case answers precisely which owned cgroup field differed, with its exact values, identity, event counters and cgroup.procs at refusal. The only observer logic delta writes that metadata before the SAME refusal. It does not accept a mismatch, retry cap reads, raise a cap, alter signal permission, tune a JVM pool, drop a service or modify the unchanged eleven-Python/two-browser test selection. Valid, empty-but-mismatched and populated-but-mismatched fixtures prove original accept/refusal behavior and unchanged source metadata. Original launcher pressure instrumentation remains installed only for this private case. The old case and all private immutable source inputs remain preserved. The new case and nonce are unique and single-use; original and supplemental terminal verification remain mandatory.



## Final measured sensor and source integration disposition, 2026-10-29

The qualified private source is signed9060ef3886e74e370011ece97bf6f3941ca70e12
in .worktrees/sensor-retirement-budget-20261029. OpenHAB144tasks,
PostgreSQL20tasks (observed peak17), controller32 Python /60 browser, guardian8.
All11 unchanged Python bodies must finish successfully and exit before exact
ChirpStack, Redis and completed simulator retirements. Each requires its original
stopped ID/PID0/cgroup-empty proof and irreversible durable acknowledgement.
The browser stimulus publishes directly to MQTT; simulator restart is revoked.
Four acknowledgements precede browser operation. CPU and all container memory
reservations remain conservative. Totals:32+8+204=244 and60+8+180=248, within
the original256task ceiling and at least eight uncertainty slots. Memory remains
3136MiB commitment under6144MiB total/no-swap,3072MiB host reserve,256MiB
uncertainty,2752MiB residual ceiling and6208MiB initial host availability.
No features/test bodies, freshness rules or original workload deadlines changed.

Private ingestion uses the fixed separately sealed worker supervisor. Browser
inspection reuses the immutable admitted rendered Compose document only after
fresh source-byte and lease checks; runtime containers/images/volumes/foreign
consumers remain freshly inspected through the existing bounded Docker API.
This removes repeated CLI processes while keeping the original validations.

The uninterrupted original11+2 workload passes. Its primary controller resource
checks and per-start caps pass with zero new events; both exact terminal checks
pass. The separate external observer times out before browser execution and has
no complete-monitor credit. Eighteen fixtures verify the current observer's
strict running versus positively retired-empty behavior.

A separate same-source witness passes all11 Python bodies and reaches the
four-acknowledgement browser phase before its single planned controller stop and
guardian kill. Actual automatic restart at8tasks/64MiB, retained FDStore/real
admission exclusion, zero observed guardian events and exact terminal cleanup
are proven. The observer wrapper records that positive restart, then races normal
FDStore release in a redundant READY read. Its failed result stays unchanged;
read-only parent adjudication completes the terminal proof without another fault.
Original root receipts remain unchanged; readable private copies carry root-owned
hash attestations. Static replay alone is not counted as recovery evidence.

Main integration uses three chained exact manifests:45 base targets,27 dependency
and stale-contract targets, and one optional native chart interval fragment.
All73 targets are checked against exact original/current signatures; both original
Git indexes,800 other UI paths,10 analytics paths and154 external inputs remain
protected before final workflow publication. Nine existing modules differing from
the live release remain untouched; the chart retains existing precipitation and
time labels. Exact writable validation copies isolate fixture writes from main.
Native runtime39 remains separately deployed; it is not ported into main.
