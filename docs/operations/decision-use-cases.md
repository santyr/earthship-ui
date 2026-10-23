# Current decision coverage

Authoritative implementation contract: [2026-10-22 decision support](../superpowers/plans/2026-10-22-decision-support.md). Decisions and recommendations are the product objective; forecasts support them. Previous audit repairs remain preserved. Greywater, feeder and nightly override/device-policy actions are outside advice/ML optimization; independent operation and measured demand remain unchanged.

| Decision served | User outcome | Required evidence | Source readiness / exact gap | Acceptance |
|---|---|---|---|---|
| Shade position/timing | Open/close/hold a named group; review time | Declared comfort/privacy policy, fresh indoor and solar state, actual or declared shade state | Existing preview is not truth; 26 unmapped logical slots; observation normalization, movement history, JDBC bridge and rule-based advice implemented; physical mappings absent | Cold sunny / overheating / unknown / partial / privacy / per-member target tests |
| Ventilation window | Bounded opening or close/review | Fresh indoor/outdoor, explicit opening state, environmental/user checks | bounded rule-based opening and close/review paths implemented; real opening state/preferences remain absent | Favorable / adverse / stale / missing constraint / close-window tests |
| Flexible electricity | Run/defer useful approved load | Explicit flexible-load profile/deadline, battery reserve, source-bound storage scenarios | single approved-task comparison implemented with existing storage; actual approved task profile/attribution absent | Energy shift accounting / reserve / excluded or essential loads / deadlines |

No software completion, installation, real-input availability, device commissioning, or action-effect qualification is implied by this adoption record.

Incoming motor expectation: approximately one month from 2026-10-22; no commissioned devices inferred. Prepare software now, commission actual feedback with attended authorization when available, evaluate thermal action-response only with retained real episodes.

Forecast priority: shade position/solar geometry → shade timing; indoor/outdoor bands → robust shade/vent comparison; wind/rain/moisture → specific ventilation conditions; PV/load/storage → approved flexible-load window. Broader predictor/model expansion deferred unless it repairs a reproduced decision blocker.


## Current acceptance dimensions (2026-10-23)

| Domain | Source implementation | Software verification | Installation | Real-input availability | Device observation | Action-effect evidence |
|---|---|---|---|---|---|---|
| Shades | Closed source-bound advice; native precision/epoch/movement history; existing JDBC bridge; actual-state UI | Focused fixtures/producer/browser checks pass; full frozen matrix pending | New branch not activated | Needs actual operator comfort/privacy/declared state or commissioned feedback | No motor Items found in460-Item GET inventory;26 logical slots remain unmapped | Thermal benefit null; retained as-of episodes/evaluation path prepared |
| Ventilation | Bounded cooling window; conditional environmental checks; close/review | Focused available/no-change/conditional/stale/adverse tests pass; full frozen matrix pending | New branch not activated | Needs target/opening state and actual preferences; unresolved rain/wind/security/smoke remain explicit user checks | Physical opening confirmation not inferred from acknowledgement | Directional rule, no drying/clean-air/condensation or numeric thermal benefit claim |
| Flexible electricity | Original-baseline replacement and bounded hourly alternatives using existing nominal storage | Shift/reserve/deadline/essential/collateral/task tests pass; full frozen matrix pending | New branch not activated | No approved useful task/profile and attributed baseline supplied; generic household load is not task attribution | No automatic actuation | Nominal SoC comparison is a model scenario; calibrated/causal savings unqualified |

Current source: isolated branch`feature/decision-support-20261023`, repaired baseline`09363f1`. Existing root overlays and pinned installed releases remain untouched. See [commissioning/installation runbook](decision-support-commissioning.md) for reader-before-writer staging, original replay, exact private input contracts, telemetry acceptance, retention bounds and rollback. Software verification is still in progress; this table does not claim the integrated candidate passes until final evidence is recorded.

Active tasks are now ordered by **decision served; user-visible outcome; acceptance test; evidence limitation**. First close the current advice/telemetry software gates, then provide operator inputs, then authorize/verify installation, then commission actual motor feedback when hardware exists. Further forecasting work must repair a named decision blocker or improve later matched decision evidence. Optional predictor expansion remains behind those tasks.


Operator clarification on 2026-10-23: shades still require connection; use the existing Dooya installation handoff. Nightly override scheduling is already adequately covered by OpenHAB and requires no ML. Current command-oriented planner capabilities are empty; descriptive/manual catalogs and historical numerical producers remain retained. Standalone flexible-task advice is separate, explicitly opt-in, and never inferred from night-control membership. Its modeled baseline still includes independently operated pump/essential demand.

Independent review found implementable source defects in effective evidence expiry, feedback deduplication/correction, packet identity, auxiliary failure isolation, current device scope, episode stability and thermal evaluation wiring. These have focused RED/GREEN regressions. Thermal orchestration now invokes the existing model, retains original model/source pins, binds pre-action context durably, and scores later qualified known-action windows; it is experimental and initially supports complete uniform house endpoint states. Mixed/partial positions remain native observations without a proportional heat-gain assumption. All final integrated gates remain pending until the verification record is updated.
