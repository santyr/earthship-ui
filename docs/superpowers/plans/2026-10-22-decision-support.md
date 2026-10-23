# Earthship Decision Support and Recommendations — Implementation Plan

> **For the coding agent:** Adopt this goal at the next safe checkpoint. Preserve verified work and the existing execution method. Use `superpowers:executing-plans` or the already chosen subagent workflow when available; the checkbox tasks below are the execution contract. This document requests implementation and verification, not another planning-only pass.

**Goal:** Make Earthship UI explicitly and practically help the household decide **what to do, when, and why** about shades, ventilation, and discretionary electricity use, using existing measurements and forecasts to compare alternatives. Remove greywater from recommendation and optimization scope without changing its adequate existing OpenHAB automation.

**Architecture:** Reuse the canonical household snapshot, source-bound numerical models, existing recommendation presentation, and operational safeguards. Add or complete a small, deterministic advisory path that compares explicitly described alternatives and publishes evidence-bound human recommendations. Make per-shade position and movement history a first-class input, ready for motorized shades expected within a month. Keep advisory output separate from equipment commands and do not require automated-control commissioning for manually actionable advice.

**Tech stack:** Existing Python household/thermal/energy model code; Svelte/Vite frontend; OpenHAB observations and existing owner rules; current persistence, replay, and test infrastructure. No SubQ Snap, hosted decision model, new inference API, or new weather provider is required.

**Spec:** The product specification and acceptance contract are Sections 1–5 of this document. The executing agent should retain this document under `docs/superpowers/plans/2026-10-22-decision-support.md`, or link it from the repository's existing canonical plan location rather than create a competing tracker.

**Operator clarification (2026-10-23):** Nightly override and its device-policy scheduling are also excluded from ML planning/recommendations; existing OpenHAB rules already cover them. Preserve those rules and manual controls. Standalone discretionary-task advice requires explicit approval and remains separate.

**Prepared:** October 22, 2026.  
**New hardware commitment:** The user expects motorized shades within approximately one month and expects to observe when and how far each shade is manually opened. Build observation, history, and recommendation integration now; verify each actual device at commissioning. This is a known near-term integration requirement, not a reason to defer the shade work or to enable automatic movement.  
**Repository:** `santyr/earthship-ui`.  
**Source baseline checked for this handoff:** `3124361f86c76052aeea7bb6f0821b54af727bf3`. Reconcile a newer revision before editing.  
**Evidence boundary:** This handoff uses the user's explicit scope decision and targeted repository inspection. It does not establish the current deployed configuration, private data coverage, effect-model accuracy, or physical commissioning. Proposed file names and interfaces below are implementation decisions, not claims that those modules already exist.

---

## 1. Authoritative product purpose

Put the following purpose near the beginning of the README, in the current architecture overview, and at the top of the active work tracker:

> **Earthship UI exists to help the household make timely, informed decisions about solar heat gain, ventilation, and electricity use. It combines current measurements, weather forecasts, and models of the house and energy system to compare practical alternatives—including leaving things unchanged—and recommend what to do, when, and why. Recommendations explain the expected benefit, trade-offs, uncertainty, and relevant constraints. Forecasting is a supporting capability, not the final product. Automatic execution is separate and is not required for useful decision support.**

The three primary questions are:

1. **Shades:** Should we open, close, or leave particular shades unchanged now, and when should we reconsider?
2. **Ventilation:** Should we ventilate now or later, for what bounded window, and when should we close or reassess?
3. **Discretionary electricity:** Should we run, postpone, reduce, or resume an explicitly flexible load, while protecting essential services and battery reserve?

Every active forecasting, modeling, and UI task must identify which question it serves. A new plot, extra predictor, more accurate forecast, or stronger provenance check is not by itself delivery of decision support. The project also retains monitoring, manual controls, and operational diagnostics; they support this purpose rather than replacing it.

### What success looks like

On the existing console, the user can see the highest-priority current suggestion, its relevant time window, and a short explanation. Opening details reveals the baseline, at least one considered alternative when available, assumptions, evidence quality, and why other alternatives were not recommended. The user can dismiss or snooze advice and can record that an action was taken **without issuing an equipment command**. Once shade telemetry is commissioned, independently reported position changes update the baseline and mark supported recommendation targets as reached without requiring duplicate manual logging. Reaching a position proves neither the occupant's motivation nor the predicted thermal benefit.

The system can also state **“No change recommended”**, **“Check these conditions before deciding”**, or **“Insufficient evidence”**. Those are different outcomes. Missing input must never masquerade as a confident recommendation to do nothing.

---

## 2. Scope decisions and non-negotiable constraints

### 2.1 Greywater: remove recommendations, preserve existing operation

The user has explicitly stated that existing OpenHAB logic and scripts adequately cover the greywater pumps. Therefore:

- Do not generate, rank, recommend, optimize, defer, reschedule, curtail, or qualify greywater pump actions in the household decision engine.
- Remove greywater recommendation cards, proposal groups, planner objectives, active qualification requirements, and implicit prerequisite checks. Filtering the visible card alone is not sufficient.
- Preserve greywater rules, scripts, schedules, pump alternation, cooldowns, owner/request-result contracts, manual controls, telemetry, alarms, and operational status. Do not refactor or retune them as part of this goal.
- Greywater's actual consumption may remain in measured household load. Its existing schedule may be modeled as an **external, non-discretionary input** where already available. Do not remove that energy from the baseline, double-count it, or treat it as a source of discretionary savings.
- A broad load-shedding recommendation or policy toggle must not indirectly stop greywater. Inspect the actual affected-device set; exclude any proposal with prohibited collateral effects.
- Preserve immutable old plans and exact replay through their historical producer. Legacy greywater proposals may be inspectable as historical diagnostics, labeled outside current scope, but must not reappear as current actionable advice.

### 2.2 Other exclusions and authority boundaries

Feeder operations remain manual or Lightning-payment driven and excluded from household recommendations and optimization. No Snap integration, distillation, hosted decision engine, or external language model is part of this work. Do not introduce a dependency on one to generate explanations; deterministic templates are sufficient.

Keep automatic planner actuation disabled. Do not add recommendation-to-command wiring, unsolicited messages, or changes to owner-rule permissions. Read-only integration and commissioned observation of the incoming motorized shades are in scope; installing or changing their physical command path is a separate authorized operation. Existing manual controls continue through their established safety path. Advice acknowledgement is never a control request, and human-readable text must never be reparsed into a command.

Keep WeatherNext as the active external weather provider and preserve existing no-billing restrictions. Reuse approved resource profiles, immutable archives, numerical producer identities, private configuration, and bounded scheduled jobs. Keep essential services and operator overrides out of discretionary load optimization by default.

### 2.3 Reprioritize earlier goals without undoing their work

This goal supersedes earlier scope statements that make greywater a planning candidate and earlier completion language that treats forecasting infrastructure alone as the end product. It does not undo completed audits, delete working WeatherNext capabilities, relax source/quality checks, or authorize a wholesale rewrite.

Finish an in-flight bounded repair or deployment transaction before switching workstreams. Then move this end-to-end decision-support work ahead of optional forecasting expansion. A broader forecast improvement remains a prerequisite only when a reproduced limitation prevents a named decision use case. Record its smallest necessary repair, rather than blocking advice until every previous research task is complete.

### 2.4 Incoming motorized shades: a required staged deliverable

Prepare for the user's motorized shades within approximately one month of October 22, 2026. Do not turn that expectation into a claim of present commissioning or a guaranteed delivery date. Do not block all useful advice until the motors arrive, and do not design a permanent manual-entry-only solution when automatic position observation is expected soon.

**Before installation:** deliver the closed observation contract, device/zone mapping structure, simulated adapter fixtures, durable movement history, advice integration, and commissioning runbook. Keep current manual declarations usable with explicit provenance; preview positions never become physical truth.

**When hardware is available:** map actual IDs and native position semantics, verify real manual opening/closing and intermediate stops, validate timestamps and offline/reconnect behavior, and connect actual observations to the same advice path. Commissioning movements require the existing attended authorization. If hardware arrives while this goal is being executed, complete these checks rather than automatically consigning them to a later project.

**After observation is reliable:** accumulate actual shade-action/outcome episodes and evaluate the action-response model. Motorization and position feedback alone do not authorize automatic control or prove the thermal effect of an action.

---

## 3. Baseline observations and the changes they imply

The checked source gives specific starting points:

| Existing surface | Observed behavior at the checked revision | Required direction |
|---|---|---|
| `household/pipeline.py::_candidates` | Generates `RUN_GREYWATER_CYCLE` for modeled surplus and even constructs a greywater intent as a preliminary check before building other candidates. Action effects are initialized to unknown. | Remove greywater generation and the hidden prerequisite. Make each retained domain depend only on its own required evidence. |
| `household/planning.py` | Includes greywater in `AUTOMATED_CAPABILITIES`; its existing command-oriented checks require battery evidence and registered owners. | Preserve old command/replay contracts, narrow current scope, and do not force manual shade/ventilation advice through irrelevant actuator-owner or battery gates. |
| `src/lib/household/recommendations.js` | Includes a greywater preview group; has a candidate ventilation path; intentionally does not derive shade advice from baseline trajectory markers. | Preserve the distinction between baseline and candidate actions, remove greywater, and supply genuine shade and ventilation recommendation contracts. |
| `src/lib/ui/RecommendationPreview.svelte` | Presents preview/blocked advice and includes greywater in the group catalog. | Make supported human advice clear and prominent; keep unsupported candidates in diagnostics rather than make every card an automation-blocked placeholder. |
| Household architecture plan | Describes the state→models→planner→owner flow and separates intelligence from authority. | Make the user-facing decision outcome the explicit product objective and give manual advice its own readiness contract. |

Pinned references are in Section 10. These observations are not a fresh whole-repository audit or proof that no other recommendation producer exists. Task 0 must find and reuse any relevant newer or parallel implementation.

---

## 4. Product and decision contract

### 4.1 Separate three capabilities

**Prediction** describes likely conditions under a declared baseline. **Recommendation** compares permissible alternatives and explains a human decision. **Execution** operates equipment through existing authorized owners. This goal completes the first-to-second transition; it does not enable the third.

Absence of a motor, commissioned actuator, or command capability is not by itself a reason to withhold manual advice. Absence of a necessary observation or defensible action-effect basis is a reason to qualify or withhold the specific recommendation. Do not weaken automatic-control gates to solve a manual-advice problem.

Readiness must be per action family and target. A stale battery feed can block energy advice without blocking a well-supported manual shade recommendation. Missing indoor humidity can withhold a moisture benefit claim without erasing an otherwise supportable temperature comparison; any unresolved rain, wind, security, smoke, or occupancy constraint must be represented according to its actual relevance. Do not claim outdoor air is safe or clean when there is no evidence for that claim.

### 4.2 Advisory kinds and scope

Use a closed advisory catalog, distinct from actuator intent names:

- `SHADE_POSITION`: a named zone/group and supported open/closed/partial position.
- `VENTILATION_WINDOW`: a named opening/group, bounded opening window, close/review condition.
- `FLEXIBLE_LOAD_TIMING`: a named operator-approved discretionary load or class, start/defer/resume/reduce alternative, and duration/finish window where known.

A report also has per-domain evaluation outcomes: `recommendation_available`, `no_change_recommended`, `conditional`, `insufficient_evidence`, and `unavailable`. Lifecycle adds `expired` or `superseded`; feedback is separate. Do not put unknown confidence, disabled automation, and missing evidence into one undifferentiated “blocked” state.

A conceptual `DO_NOTHING`/`LEAVE_UNCHANGED` baseline participates in every comparison. “Leave unchanged” means hold the known or explicitly assumed current state while existing independent schedules continue; it does not mean switch all loads off or cancel greywater automation.

### 4.3 Required contents of an issued recommendation

Define a versioned, closed schema, for example `earthship-household-advice/v1`, with:

| Group | Required contents |
|---|---|
| Identity | Recommendation/episode IDs; source snapshot; evaluation and policy versions; model/forecast references; target; action family. |
| Time | Original decision time; recommended start/end window; review time; advice validity deadline; source validity and timezone. A future opportunity is not indefinitely valid advice. |
| Action | Specific physical-language action and target; baseline state or declared assumption; reason this action is currently preferable. No ambiguous override ON/OFF labels. |
| Comparison | Baseline versus candidate trajectories or qualitative rule evidence; relevant alternatives considered; metric units; declared outcome horizon. |
| Benefit and trade-offs | Supported thermal/energy benefit, disruption or delay, adverse outcomes, and reasons alternatives lost. Numeric effects stay null when not supportable. |
| Evidence | `rule_based`, `model_compared`, or `experimental`; current support/limitations; model uncertainty distinct from data freshness. No fabricated confidence percentage. |
| Conditions | Machine-checked constraints, explicitly unresolved user checks, invalidation triggers, relevant missing evidence, and the next information needed. |
| Authority | `human_action_only: true`, `automatic_actuation: false`; no execution token, raw Item command, or hidden schedule write. |

Human wording comes from these structured fields using deterministic templates. Full source payloads, private identifiers, credentials, or raw archives do not belong in the public recommendation report.

### 4.4 Preferences and actual household state

Reuse existing verified preferences. Keep a compact, versioned operator policy for comfort bands and occupied periods, privacy/night-shade preferences, allowed ventilation periods, rain/wind limits where applicable, essential versus discretionary loads, load deadlines, battery reserve, and advice frequency. Do not silently invent preferred temperatures, convenient operating times, safe wind thresholds, or appliance power values.

Where the current system lacks a needed preference, document the exact missing field and provide a safe disabled/conditional state for that branch while finishing other work. Optional manual declarations can fill states the user actually knows, such as “living-room shades half open” or “windows closed,” with provenance and an explicit validity policy. Preview slider state is not measured hardware state. Self-reported observations are not silently promoted to sensor-qualified evidence.

### 4.5 Per-shade observation and movement contract

Treat the upcoming position feedback as an input to the decision engine and to future action-effect learning, not merely a cosmetic upgrade to the Shades screen. Reuse existing observation contracts and shade history where possible; do not create a second general sensor platform.

The schema and adapter must distinguish:

- Stable logical shade ID, its actual room/zone/group, device mapping, installation/calibration epoch, and source identity. Reconcile the existing preview roster with the installed hardware; no device is commissioned simply because a preview slot exists.
- Canonical `position_open_pct`: **0 = fully closed, 100 = fully open**. Retain the native value/convention and a versioned mapping; some providers use the opposite convention. Do not round away the device's actual precision or claim more precision than it reports.
- Actual reported position, requested/commanded target (if available), movement state, and feedback basis. A controller's travel-time estimate is not independently measured position. A target command, successful transport, or UI preview cannot confirm a position.
- Source-observed, received, and available times; last valid acquisition; quality; sequence or event ID; and freshness. A motionless shade can remain freshly observed; old held values cannot become fresh through browser arrival or an unrelated packet.
- Action origin: manual, existing automation, another identified source, or unknown **only when supported by evidence**. A known position change with unknown origin is still useful state evidence, but not proof of manual preference.

Record movement episodes with starting position, intermediate reports where available, ending position, movement/start/stop times or explicitly bounded timing uncertainty, source quality, and links to the original events. Preserve duplicate/out-of-order/reconnect and hardware-replacement semantics. Unknown periods remain gaps; do not invent the continuous path between sparse reports.

Freeze this state into each decision snapshot. Live observations drive the next decision, not retroactive edits to old decisions. Resolve hardware versus operator-report conflicts through an explicit quality/availability policy rather than an unconditional preference for whichever arrived last. Keep unresolved disagreement visible.

Use per-shade state even if the thermal model supports only zone/group effects. Aggregate positions only with declared geometry/weighting and uncertainty; percent-open is not automatically a linear solar-transmission coefficient. An accurate position map does not identify a separate temperature-response model for every shade.

Manual movements immediately trigger bounded re-evaluation. Respect the person's choice: do not issue a contradictory follow-up automatically or repeatedly urge reversal. Apply the configured manual-hold/review policy unless materially changed conditions justify an explained new recommendation. Feedback satisfaction requires the appropriate final position evidence and configured tolerance/settling policy, not a moving shade passing through a target percentage.

### 4.6 Minimal architecture, not another framework

Reuse existing source capture and forecast projections. Keep the decision calculation pure and replayable:

```text
existing frozen household state + actual shade/opening state + forecasts + operator policy
                                  ↓
               domain-specific readiness and scope checks
                                  ↓
                bounded alternatives including unchanged
                                  ↓
          comparable consequences / explicit rule-based evidence
                                  ↓
         constraints, preference ranking, interaction checks
                                  ↓
          recommendation lifecycle + curated public projection
                                  ↓
      Home / Earthship / Energy / Shades + feedback/outcome record
```

Do not rebuild weather acquisition, model training, the snapshot system, or OpenHAB owners. Reuse an existing equivalent advisory module when discovered. If no suitable layer exists, proposed module boundaries are `household/advice/contracts.py`, `policy.py`, `energy.py`, `shades.py`, `ventilation.py`, `evaluate.py`, and `lifecycle.py`. Add these incrementally as their vertical slice needs them, not as an up-front platform project.

Proposed pure interface: `evaluate_advice(*, snapshot, projections, policy, action_state, now) -> AdviceReport`. It consumes a single bound snapshot and known model outputs, not mutable Item reads. Proposed lifecycle interface: `reconcile_advice(previous, evaluated, feedback, now) -> AdviceReport`; persistence/publication wraps it. Keep Python and JavaScript schema fixtures shared. Treat any new API names as proposed contracts, adapting to actual equivalent repository interfaces during Task 0.

---

## 5. Decision-quality rules

### Alternatives must correspond to real choices

Use the resolution supported by the data and models. If only house-level thermal behavior is modeled, do not invent 26 independent shade-zone temperature responses. If partial openness is unsupported, begin with open/closed/unchanged at the validated grouping. For loads, require an allowlisted flexible load and a measured or explicit declared power/duration profile before estimating kWh or SoC effects.

Use a bounded candidate set and deterministic tie-breaking. Do not construct the unrestricted product of every shade, vent, load, and time slot. Start with a small, explicit set of useful schedules and evaluate their interactions only where the model supports them.

### Rank benefits without trading away constraints

Eliminate forbidden or unsupported alternatives first. Rank the remaining alternatives against the same baseline, horizon, sources, and declared preferences. Prefer leaving things unchanged when expected improvement is negligible or the comparison is unresolved. Keep infeasible, unknown, and no-benefit cases distinguishable.

Useful comparison measures include time or degree-hours outside the stated comfort band, minimum modeled SoC, reserve-shortfall magnitude/duration, load-completion deadline, and number of requested user interventions. Use explicit units and a small declared preference policy; no opaque universal score or arbitrary weights hidden in code. Essential services, excluded devices, and hard limits must not become soft penalties.

### Avoid false precision and unsupported causal claims

Keep actual observations, modeled candidate outcomes, and unobserved alternatives separate. An accurate baseline forecast does not by itself validate the effect of changing shades or opening a vent. Never obtain an alternative trajectory merely by relabeling baseline markers.

A conservative, reviewed rule can supply useful human advice when it has a defensible directional basis, fresh relevant inputs, and explicit limitations. It must not manufacture a numeric temperature or SoC improvement. Experimental model comparisons remain labeled experimental, not disguised as established recommendations.

An acknowledgement does not prove the action occurred. A qualified device position report can establish a supported physical state, but a temperature change after shade movement or ventilation does not, by itself, prove the action's thermal effect. People often move shades because the room is already changing; their actions are not automatically labels of optimal behavior. Do not train on the system's own recommendations as though they were observed optimal actions or outcomes.

Use actual shade position trajectories to estimate or evaluate action-response parameters with the current thermal framework, conditioning on weather, solar geometry, starting air/mass temperatures, ventilation state, other concurrent changes, and sensor epochs where available. Start with the identifiable group-level effects; preserve per-shade evidence for finer modeling only when later data supports it. If multiple shades always move together, do not claim their separate effects are identifiable from those episodes. Daily refitting or finer telemetry is not a substitute for independent intervention coverage. No experimental household actuation is authorized by this learning requirement.

### Advice must be stable and remain valid

Separate opportunity start/end, source validity, recommendation validity, and feedback time. Recompute on material state/forecast/policy changes and at a bounded periodic cadence. Reuse existing resource coordination; do not retrain on every browser refresh.

Use configurable minimum useful change, hysteresis, and a minimum episode hold period to suppress reversals. Stale evidence, hard-condition changes, and operator changes invalidate advice immediately; hysteresis cannot preserve a newly unsuitable suggestion. Coalesce equivalent advice and keep dismiss/snooze state stable across numerical refreshes. Expiry must advance on a quiet stream and after browser wake-up, without requiring a new SSE event.

---

## 6. Ordered implementation tasks

For every code task: first add or extend a normal-harness regression; observe its meaningful failure; implement the root change; run focused and adjacent tests; review the change; and commit a cohesive unit. Preserve the existing deployment authorization boundary. Independent reviews may run in parallel, but shared schema/policy changes must be coordinated.

### Task 0 — Reconcile current work and establish a short decision backlog

**Depends on:** nothing.  
**Inspect:** current branch/worktrees and repository instructions; `README.md`; the architecture plan; active progress/audit records; `household/pipeline.py`, `planning.py`, `intents.py`, `capabilities.py`; existing thermal candidate/schedule and energy-trajectory modules; all recommendation UI consumers and scheduled producers.

- [ ] Record the current source revision, in-flight changes, installed source families, original schemas, and relevant tests. Preserve completed audit fixes and compatibility packages.
- [ ] Trace each of the three desired recommendations from observation to model to comparison to UI. Identify existing candidate generation, action-effect support, manual state inputs, and missing links.
- [ ] Record the incoming motorized-shade requirement, actual known device/binding details, and the existing logical shade/zone roster. Do not require the user to repeat the delivery expectation; device-specific gaps should block only actual device commissioning, not the observation contract or fixtures.
- [ ] Create one `decision-use-cases.md` or extend the current tracker with decision, user outcome, required input, current readiness, exact gap, test, and disposition. Do not build a separate status bureaucracy.
- [ ] Map outstanding forecast work to a named decision. Move unrelated or merely incremental improvements behind the first complete advice slices.

**Exit:** a current gap map and minimal change set. Documentation claiming a historical implementation is pending is not evidence that it remains absent. Do not rerun the old whole-project audit as a prerequisite.

### Task 1 — Make the objective authoritative and enforce greywater exclusion

**Depends on:** Task 0.  
**Modify as needed:** `README.md`; current architecture/work tracker; `household/pipeline.py`, `planning.py`, current proposal/qualification/public-projection code; `src/lib/household/recommendations.js`; `RecommendationPreview.svelte` and its callers.  
**Preserve:** existing greywater scripts/rules, manual contracts, registry entries needed by those contracts, telemetry, schedules, historical producers.

- [ ] Add the product purpose and a dated greywater scope decision. Supersede conflicting current planning text without rewriting historical records.
- [ ] Add backend tests: no greywater candidate for surplus, no stop/defer greywater suggestion, no greywater prerequisite for energy advice, and no greywater selection when an old or adversarial candidate is injected.
- [ ] Remove greywater from current recommendation generation, optimization, active qualification requirements, and current report projection. Keep the legacy identity catalog only where required for manual use or historical replay.
- [ ] Add frontend tests that old cached greywater proposals do not become current advice. Preserve status/history and manual-control views; remove only their recommendation treatment.
- [ ] Assert no changes to protected pump sources, schedules, runtime settings, or existing command behavior. Verify pump load remains in the energy baseline and cannot be cut by a collateral macro.

**Exit:** zero current greywater or feeder recommendations anywhere, while existing independent operation and observation remain intact. Removing `RUN_GREYWATER_CYCLE` from a catalog must not delete its valid manual owner contract.

### Task 2 — Implement the advisory contract and shade-observation foundation

**Depends on:** Task 1.  
**Reuse or create:** advisory contract/policy module; existing household observation publisher and recommendation parser; a minimal reusable recommendation card; shade-position observation/history adapter and feedback/manual-state storage using existing private persistence patterns.  
**Proposed new tests:** `openhab/scripts/test_household_advice_contract.py`, `openhab/scripts/test_shade_position_observations.py`, `tests/household-advice-contract.test.js`. Proposed modules, only if no equivalent exists: `household/advice/shade_state.py` for normalization/history and `household/advice/shade_adapter.py` for read-only binding to retained OpenHAB evidence.

- [ ] Define the schema from Section 4, units, per-domain readiness, nullable effects, advisory validity, and compatibility/version rules. Write shared valid/invalid fixtures for Python and JavaScript.
- [ ] Keep advisory eligibility distinct from automated capability/owner checks. Do not require a battery reading or actuator registration for an action that does not need it.
- [ ] Implement Section 4.5's per-shade position/event contract, read-only adapter boundary, bounded durable movement history, and snapshot attachment. Preserve native raw values and canonical 0-closed/100-open semantics.
- [ ] Supply fixtures for full/partial/manual movements, in-motion reports, target-versus-position differences, offline/reconnect, duplicate/out-of-order reports, stale acquisition, and a new calibration epoch. Do not invent a production binding for an unknown motor model.
- [ ] Implement explicit operator-reported action state where necessary before installation or for an unobserved opening, with target, state, time, source, validity, correction/supersession, and unknown-state behavior. Device reports, operator declarations, and shade-preview values remain distinct.
- [ ] Write the device commissioning checklist now: actual mapping, native direction/scale, intermediate-stop reporting, timestamp accuracy, actual feedback basis, manual-origin support, offline detection, and position-history-to-advice trace. Do not enable movement to test this without applicable authorization.
- [ ] Implement a minimal data-to-card path displaying an action, time window, reason, evidence status, and baseline/alternative detail. No appliance commands or schedule writes.
- [ ] Test unknown kinds, excluded devices, stale/future inputs, invalid numeric effects, source mismatch, absent policy, and no-change versus insufficient-evidence outcomes.

**Exit:** real source-bound advice objects can reach the UI; the same pipeline accepts recorded/manual state now and device observations at commissioning. Synthetic fixtures are visibly test-only. The adapter contract, history, and commissioning procedure are ready before installation. This task is not complete if it only creates schemas that no producer or screen uses.

### Task 3 — Deliver the first end-to-end energy decision slice

**Depends on:** Task 2.  
**Reuse:** existing PV/captured-energy distinction, household demand profiles, nominal-storage simulator, trajectory-energy projections, energy policy, and the Energy/Home displays.  
**Proposed test:** `openhab/scripts/test_household_advice_energy.py`.

- [ ] Inventory actual operator-approved discretionary loads, power/duration evidence, interruptibility, deadlines, and essential services. Do not assume a controllable device is discretionary.
- [ ] Compare a declared unchanged baseline against running now, delaying to an available solar window, and reducing/deferring only interruptible discretionary use. Preserve existing fixed schedules.
- [ ] Compute changes to minimum modeled SoC, reserve exposure, completion time, and modeled unaccepted PV where supported. Remove/replace a task's baseline contribution before rescheduling it; never count the same appliance twice.
- [ ] Explain physical outcomes rather than raw policy flags: for example, “Delay this discretionary task until the forecast solar window,” with its evidence and limitations. Verify night-load override semantics and all affected devices before exposing any suggestion involving that macro.
- [ ] Test cloudy low-reserve periods, adequate reserve, essential-only loads, high-SoC surplus with no useful flexible task, load deadlines, unknown duration, and infeasible completion.
- [ ] Replay retained decision inputs locally and publish at least one supported real recommendation or a precise real-data blocker. Do not simulate a successful live recommendation using fabricated appliance data.

**Exit:** energy advice works from frozen inputs through display. No greywater rescheduling, pump interruption, essential-service loss, or change to battery protection. Nominal capacity and forecast uncertainty remain labeled.

### Task 4 — Deliver shade timing and position advice

**Depends on:** Task 2; can proceed alongside Task 3 after shared contracts stabilize.  
**Reuse:** actual thermal model and candidate schedules, shade-state history, zone registry, original solar geometry/horizon, and the Shades/Earthship/Home presentation.  
**Proposed test:** `openhab/scripts/test_household_advice_shades.py`.

- [ ] Establish actual modeled zones/groups and action-state evidence. Respect the existing sensor/zone mappings; no unsupported per-window precision or invented independent zone temperatures.
- [ ] Compare unchanged, supported opening now, opening later, and closing/partial closure before forecast overheating. Include later comfort and thermal-mass implications within the available horizon.
- [ ] Use actual action-conditioned model evaluations where supported. Otherwise implement a reviewed directional rule with explicit limitations; leave quantitative benefit null. Unvalidated model scenarios belong in scenario details, not high-confidence advice.
- [ ] Use the actual per-shade state from Task 2 when available, with exact target IDs and an explicitly declared mapping to model-supported zones/groups. Before installation, retain supported manual advice using declared state; unknown position yields a state-confirmation condition or unavailable alternative, not an invented baseline.
- [ ] Support intermediate position recommendations to the degree justified by the effect model or a reviewed rule. Position telemetry is retained at native precision even when advice is initially coarser; do not pretend 50% open necessarily admits 50% of full-open solar heat.
- [ ] Recompute on observed manual movement, cancel already-achieved or obsolete advice, and respect the occupant's new setting. Group completion must use each required shade's evidence, not one average that conceals an unchanged or offline shade.
- [ ] Test a cool clear morning, a warm interior before solar gain, a cloudy low-benefit day, the terrain sunrise boundary, partial-position unsupported by the model, privacy/night policy, stale room/outdoor evidence, and already-achieved target position.
- [ ] Deliver action, target group/shade, current reported position, recommended position/range when supported, timing, reason, comparison, review trigger, and evidence level to the same visible advice path as energy.
- [ ] When motors are installed and observation commissioning is authorized, demonstrate the actual manual movement → retained position event → updated snapshot → revised advice path. No simulated proof substitutes for that installed observation milestone.

**Exit:** at least one defensible shade action family works end to end, and unsupported cases fail truthfully. The software is ready for incoming per-shade telemetry; actual observation commissioning is closed separately when available. Rendering the shade panel, forecasting temperature alone, or publishing a preview percentage does not satisfy this task.

### Task 5 — Deliver ventilation windows and closing/reassessment advice

**Depends on:** Task 2; coordinate with Task 4 where actions interact.  
**Reuse:** existing thermal schedule/candidate functionality, qualified indoor/outdoor observations, action history, available moisture/wind/rain inputs, and retained manual opening-state evidence.  
**Proposed test:** `openhab/scripts/test_household_advice_ventilation.py`.

- [ ] Compare keep closed/current state, open now for a supported bounded window, wait for a later window, and close/reassess. Make the assumed state during the forecast explicit.
- [ ] Apply relevant rain, wind, moisture, security/occupancy, and comfort constraints from known policy/evidence. Missing critical conditions withhold the recommendation or create an explicit user-check condition; missing optional fields must not trigger unrelated global rejection.
- [ ] Do not confuse lower outdoor relative humidity with a drying benefit. Use a documented, unit-consistent moisture comparison only when the necessary inputs exist; otherwise do not claim drying or condensation avoidance.
- [ ] Do not infer safe outdoor air, adequate ventilation for health, or a CO2 benefit from temperature alone. This is household thermal/moisture decision support, not a new air-quality safety system.
- [ ] Test favorable cooling, outside air warmer than inside, impending rain/wind, nighttime overcooling risk, unknown opening state, stale input, already-open conditions, and a closing/review reminder after the proposed window.
- [ ] Publish supportable advice through the common path; show whether the benefit is a model comparison or a qualitative rule. User acknowledgement must not falsely mark a vent physically closed.

**Exit:** ventilation advice includes both when to consider opening and when to stop/reassess, without new actuator authority or fabricated environmental safety claims.

### Task 6 — Coordinate decisions and prevent recommendation churn

**Depends on:** Tasks 3–5 for the implemented candidate families.  
**Reuse or create:** pure advice evaluation/ranking and lifecycle modules; existing time/source validation and private report persistence.  
**Proposed test:** `openhab/scripts/test_household_advice_lifecycle.py`.

- [ ] Integrate a bounded candidate set with an explicit baseline and deterministic tie-breaking. Retain separate readiness and failure reasons for each domain.
- [ ] Check physical interactions: do not simultaneously advise incompatible shade positions, vent to cool while recommending heat capture for the same context without an explained trade-off, or spend the same discretionary energy headroom twice.
- [ ] Simulate combined schedules only when action effects and the model support it. Otherwise resolve conflicts conservatively, expose the limitation, and avoid claiming a jointly optimal plan.
- [ ] Add stable episode IDs, supersession, hysteresis, meaningful-change criteria, review times, and bounded periodic/material-change refresh. Separate rule/source/policy versions from episode identity so a small refresh does not resurrect dismissed advice.
- [ ] On manual shade movement, use fresh reported state, invalidate the old baseline, and honor the manual-hold policy. Do not mark a recommendation completed during transient motion through its target, infer motive from position, or let an average group position hide a member mismatch.
- [ ] Withdraw unsuitable or expired advice immediately. Preserve unrelated valid advice when one model/data domain fails. Do not keep stale suggestions visible as actionable during outages.
- [ ] Bound candidate evaluations, memory, publication size, and job time under existing approved profiles. On timeout, publish a truthful limited/unavailable result instead of an asserted optimum from an unfinished search.

**Exit:** a coordinated shortlist that is stable in ordinary noise and responsive to material changes. Automation remains disabled regardless of advisory confidence.

### Task 7 — Make decisions prominent and record human feedback safely

**Depends on:** Task 2 for the first slice; complete after Task 6.  
**Modify:** Home/Earthship/Energy/Shades and existing reusable recommendation components/parsers. Do not restore retired routes or add a separate assistant chat.  
**Proposed tests:** `tests/ui/DecisionRecommendations.test.js`, `tests/e2e/decision-support.spec.js`.

- [ ] Put a concise **Recommended now / Later today / Review needed** area in the existing console. Show up to three prioritized actionable cards by default, with other relevant entries in details. Keep current status/forecasts readily accessible.
- [ ] Each visible card answers what, where, when, why, and what would change the recommendation. Details show the baseline and alternatives, source age, evidence basis, limitations, and trade-offs. A small “Manual advice” label replaces repeatedly leading with automation-disabled warnings.
- [ ] Preserve distinctions among no change, unsupported effect, stale source, insufficient data, and rejected constraints. Do not fill space with perpetual generic “Model advice unavailable” cards when a specific explanation is known.
- [ ] Provide `dismiss`, `snooze`, `acknowledge`, and `report_action_taken` as feedback events, using existing approval/access patterns. Acknowledge means seen; action reported means self-reported. Neither is a command or sensor-confirmed event.
- [ ] Show actual shade positions and feedback quality separately from preview/desired targets. When qualified device observations establish the advised physical target, record `target_observed` with evidence without forcing redundant user entry. Keep user attribution/intent and thermal-benefit verification separate from that physical observation.
- [ ] Version and retain feedback correction/undo. Bound storage and text; avoid accepting arbitrary command-like payloads. Keep physical controls on their existing route and ownership path.
- [ ] Test 1340×800 and 1280×720, long reasons, focus/touch, quiet-stream expiry, reconnect, browser wake-up, duplicate feedback, old cached excluded proposals, and absence of unexpected device mutation requests.

**Exit:** a household user can act on the advice without reading diagnostic hashes or interpreting raw override semantics. Every feedback test proves zero physical command/schedule changes.

### Task 8 — Verify decision usefulness and close only the necessary evidence gaps

**Depends on:** the relevant vertical slices and Task 6.  
**Reuse:** existing retained-source replay, action/observation histories, chronological evaluation and immutable report patterns.  
**Proposed test:** `openhab/scripts/test_household_advice_evaluation.py`.

- [ ] Retain each original recommendation, its candidate set, baseline, alternatives, assumptions, input/model/policy identities, user feedback, and later observations where available. Do not regenerate an old recommendation using today's model and call it as-issued evidence.
- [ ] Evaluate decision coverage by domain, unsupported/withheld reasons, timeliness, stale/invalid advice rate, contradictory advice, unwanted reversals, operator burden, and useful-versus-dismissed feedback. Track sample counts and evidence limitations.
- [ ] Compare against unchanged behavior and a small transparent rule baseline. Separately evaluate forecast error under known actual actions, modeled alternative benefits, and observed household outcomes. Unchosen alternatives remain unobserved, not factual labels.
- [ ] Use later chronological periods and meaningful independent windows. Do not tune on and then claim success on the same evaluation set. If few actual interventions exist, report the effect as unqualified rather than infer causal savings.
- [ ] Use newly commissioned shade events to build as-of action/outcome episodes including from/to/intermediate positions, timing, initial thermal state, weather, solar geometry, ventilation, relevant concurrent changes, and evidence gaps. Retain unadvised/manual moves too; the model must not learn only from episodes in which its own suggestion was followed.
- [ ] Evaluate whether observed position history improves the existing model's action-conditioned forecasts. Compare a coarse group-state baseline with the position-aware path, and separate better prediction under known actions from evidence that a suggested change is beneficial. Do not build an unrelated new ML platform or require a separate fitted model for every shade.
- [ ] Identify the minimum next measurement needed for each blocked decision: a known shade state, a load profile, a wind constraint, or a suitably observed action/outcome episode. The motors are already planned; prepare and use that telemetry instead of proposing redundant sensors or treating their absence as a permanent limitation. No unapproved experimental movements.
- [ ] Route further WeatherNext/model work through the decision-to-feature matrix below. Complete only improvements that remedy a concrete blocker or materially improve a scored decision; leave optional research clearly separate.

**Exit:** evidence about the actual decision product, not just forecast accuracy. Software readiness, installed advice, user-reported use, statistical usefulness, and physical/action-effect qualification are separately recorded.

### Task 9 — Integrated verification, scoped delivery, and final handoff

**Depends on:** Tasks 1–8 for implementable work; precise external evidence blockers may remain.

- [ ] Run all relevant current tests using the repository's pinned environments, including unit/build, browser fixtures, normal OpenHAB partitions, model/replay/receipt tests, and the new decision suites. Use actual workflow commands rather than inventing a new incompatible environment.
- [ ] Verify old forecast/plan replay; current schema compatibility; source/consumer/admission bindings; future scheduled refresh; no-op updates; missing sources; expiry; feedback persistence; rollback; and new publication failure isolation.
- [ ] Check the diff and runtime surface list for unintended greywater/feeder changes, command wiring, paid access, privacy leaks, and changes to core safety/resource gates. Preserve immutable originals and the live checkout's unrelated overlays.
- [ ] Follow the existing integration and deployment authorization process. Where installation is authorized, stage compatible readers before writers, use exact source readback, and inspect natural cycles already elapsed. Do not manufacture a physical test or wait indefinitely for future weather to call unblocked software work complete.
- [ ] Close the incoming-shade observation milestone when hardware is present: verify all actually mapped units, intermediate position semantics, loss/reconnect, epochs, naturally observed or explicitly attended manual movements, and end-to-end advice readback. Keep automatic movement disabled; hardware presence alone is not command authorization.
- [ ] Update the README and current tracker with what is actually supported in each domain, exact remaining dependencies, and the next acceptance event. Finish with a functioning recommendation product, not another list of forecasting projects. Before hardware arrival, mark software readiness separately from installed observation commissioning and action-effect learning.

**Exit:** source-level work is complete and verified, any authorized installation is evidenced, and remaining data/physical dependencies are explicit. Do not call the overall product complete when a requested domain has only a placeholder; describe any genuinely blocked domain and its precise limitation.

---

## 7. Decision-to-forecast priority matrix

| Supporting work | Decision it must improve | Decision-level acceptance or reason to defer |
|---|---|---|
| Per-shade position and movement history | What shade state to change, when, and how actual changes affect the house | Ship observation/history integration before motor installation; verify real feedback afterward. Separate position knowledge from thermal-effect identifiability. |
| Temperature bands and local uncertainty | Whether shade/vent timing remains preferable under plausible conditions | Demonstrate a meaningful change in recommendation robustness or an honest abstention; a chart band alone is not decision delivery. |
| Native direct plus total solar and terrain | Shade solar-gain timing; discretionary-load solar opportunity | Preserve correct physical units/intervals and test candidate decisions. Do not stack proxy and electrical corrections without a matched comparison. |
| Dew point/moisture context | Whether ventilating is likely to help or worsen moisture conditions | Use available consistent inputs and show missing conditions. Do not block thermal-only advice for unrelated moisture enhancement, or claim condensation safety without surface evidence. |
| Wind components/cloud context | Ventilation exposure and improved thermal decision timing | Add only for a demonstrated consumer and validated benefit; no full-atmosphere feature expansion. |
| Interim versus full-range forecasts | Whether a near-term recommended window remains current | Bind each comparison to actual availability and original source; score the policy users receive. |
| Household uncertainty scenarios | Whether flexible load timing or thermal advice is robust | Stress scenarios stay non-probabilistic unless joint uncertainty is validated. Do not sum hourly quantiles into daily probabilities. |
| Rain product improvements | Whether a proposed ventilation window requires a rain caution | Implement only relevant evidence support; a roof-harvesting or pump-optimization expansion is outside this goal. |
| More general ML research | A named failing or underperforming decision | Defer unless it repairs a blocker or outperforms the simpler existing approach on later decision-level evidence. |

Existing acquired fields and working forecast features remain available. Reprioritization is not deletion or a claim that the earlier work had no value.

---

## 8. Required regression scenarios

The companion acceptance matrix assigns these checks to the tasks above. Implement them in maintained tests, using isolated fixtures and no physical stimulus.

| ID | Scenario and required behavior |
|---|---|
| D01 | Solar surplus never generates a greywater or feeder recommendation. |
| D02 | Injected/cached legacy greywater proposals cannot be ranked or shown as current advice; historical replay remains readable. |
| D03 | Missing greywater metadata does not block an otherwise valid energy recommendation. |
| D04 | Pump rules/scripts/schedules and manual contracts remain unchanged; pump demand remains included once in baseline energy. |
| D05 | A broad curtailment macro affecting greywater or essential services is excluded. |
| D06 | Manual shade advice can be supported without motor registration; motor absence is not action-state evidence. |
| D07 | Stale battery evidence blocks relevant energy advice but not independent supported manual shade advice. |
| D08 | Unknown shade/window state never silently becomes open/closed; declared state retains its source and validity. |
| D09 | A valid evaluation favoring unchanged state is distinguished from missing/invalid evidence. |
| D10 | Same frozen inputs, time, and policy produce the same recommendation/report identity. |
| D11 | A delayed flexible load is removed from its original baseline slot before being added elsewhere; no duplicate energy. |
| D12 | High predicted surplus with no useful discretionary task produces no invitation to waste energy. |
| D13 | Essential-only loads or an infeasible deadline produce a precise limitation, never unsafe load shedding. |
| D14 | A cold sunny shade case and warm overheating case give different supported decisions or honest model limitations. |
| D15 | Terrain boundary and unsupported partial shade position do not create false zone-level precision. |
| D16 | Privacy/night policy can defeat an otherwise attractive shade alternative without being traded away. |
| D17 | Favorable vent cooling has an explicit close/review window; impending adverse conditions invalidate it. |
| D18 | No outdoor-air-quality, drying, or condensation claim is inferred from temperature alone. |
| D19 | Conflicting shade/vent instructions are not simultaneously presented without an explicit resolved schedule/trade-off. |
| D20 | Two proposed loads cannot spend the same reserve/headroom twice. |
| D21 | Small forecast noise does not churn advice; material evidence/constraint changes invalidate it immediately. |
| D22 | Quiet SSE, reconnect, browser sleep, local midnight and DST do not keep advice actionable past its validity. |
| D23 | Snooze/dismiss survives equivalent refreshes; a materially changed episode is traceable and re-evaluated. |
| D24 | Acknowledge, snooze, dismiss, and action-report writes cause zero device commands, rule changes, or schedule writes. |
| D25 | Self-reported action, observed device state, and model-predicted effect remain distinct records. |
| D26 | Model/publication failure in one domain leaves independent valid advice available with accurate status. |
| D27 | Resource exhaustion yields truthful partial/unavailable evaluation, not a falsely optimal plan or raised limits. |
| D28 | Old originals replay through their original producers; new advice schemas and scope do not rewrite history. |
| D29 | A real later observation cannot be used as an earlier feature or evidence that an unchosen alternative worked. |
| D30 | Both supported console sizes show action, timing, reason and uncertainty without unreadable compression, page errors or unintended mutation. |
| D31 | Opposite native position conventions normalize to 0-closed/100-open with explicit versioned calibration and no silent inversion. |
| D32 | A commanded target or preview percentage never confirms actual position; moving through the target does not mark final satisfaction. |
| D33 | Actual manual partial movement produces retained per-shade history and a new as-of baseline; the old advice is reassessed without automatic reversal. |
| D34 | Duplicate/out-of-order reports, stale reconnect state, and same-valued genuine acquisitions obey the declared quality/order/freshness policy. |
| D35 | A device-reported estimate remains identified as such; unknown action origin is not relabeled manual or automation. |
| D36 | Offline, remapped, or recalibrated hardware creates explicit gaps/epochs; old state does not silently become current. |
| D37 | Hardware reports and operator declarations that disagree retain both provenances and resolve or withhold under explicit policy. |
| D38 | A group mean cannot satisfy advice when one required shade is offline or at the wrong position; unsupported zone effects remain unknown. |
| D39 | Original manual shade episodes include actual weather/state confounders; recommendations and later temperatures are not treated as optimal-action/causal labels. |
| D40 | Read-only motor observation commissioning has a distinct acceptance record; hardware readiness never turns on automatic recommendation execution. |

---

## 9. Completion, acceptance, and drift prevention

### Required deliverables

Deliver the updated product purpose and scope policy; backend greywater exclusion; a source-bound advisory contract; per-shade position/event ingestion and movement history prepared for the incoming motors; functioning energy, shade, and ventilation comparison paths at the level their evidence supports; integrated recommendation cards; stable lifecycle and non-actuating feedback; retained evaluation evidence; and a tested, scoped release/handoff.

Track three shade milestones explicitly: **software/fixtures ready before arrival**, **actual observation commissioning when hardware is present**, and **action-effect evidence accumulating/evaluated afterward**. None implies autonomous shade operation. Hardware waiting must not block energy/ventilation work or the software stage; an installed device must not be ignored merely because the earlier goal was described as manual advice.

For each domain report separately: source implementation, automated verification, actual installed status, real-input recommendation availability, effect-evidence level, and exact remaining blocker. Unsupported numeric savings remain null. No mandatory arbitrary calendar wait is imposed, but missing observations cannot be declared collected.

A fixture can prove that the software behaves correctly; it cannot prove that the household has adopted the advice or that it improved actual comfort/energy outcomes. Conversely, lack of fully causal effect qualification must not become an excuse to leave a defensible, labeled manual rule-based advisory path unimplemented.

### Acceptance gates

1. The README, architecture overview, current tracker, and user-facing UI identify decisions as the goal and forecasts as supporting evidence.
2. No current greywater or feeder advice is generated, optimized, displayed, or implicitly executed. Existing independent operation remains intact.
3. Each in-scope domain has an implemented vertical slice, with recommendation, no-change, conditional, and insufficient-evidence cases as applicable—not merely a placeholder panel.
4. Relevant alternatives and the unchanged baseline are actually compared, or the output explicitly identifies its non-numeric rule basis. No fabricated action effects.
5. Advice can serve a human without registering an actuator; it cannot operate an actuator or weaken an existing owner gate.
6. Recommendation validity, source quality, stability, conflicts, and feedback semantics are covered by tests.
7. Evaluation measures decision usefulness and operator burden, not only forecast MAE. Outcomes and counterfactuals are not conflated.
8. Required integrated checks pass for the actual final candidate, and any deployment claims have source/readback evidence.
9. Remaining external dependencies are specific; new speculative forecasting tasks do not replace the requested implementation.
10. Incoming shade position feedback and manual movement history are implemented as first-class inputs, with device commissioning and action-effect qualification recorded separately. Real manual movements invalidate old assumptions and update advice without hidden control actions.

### Prevent the goal getting lost again

Keep a short, current **decision coverage table** in the main tracker. Every active task/PR adds these fields to its description: **decision served; user-visible outcome; acceptance test; evidence limitation**. Use this as review discipline, not a brittle keyword test or a new management subsystem.

Review work in the order **useful decision → comparison/evidence required → forecast improvement required**, not the reverse. At milestone review, demonstrate a concrete recommendation on a representative source-bound case for each supported family, including a case where the right answer is to refrain. Preserve monitoring and safety work, but do not declare the recommendation goal complete because the data pipeline is sophisticated.

---

## 10. Source map and handoff boundaries

These source references are pinned to the inspected revision. The executing agent must use current corresponding files and preserve historical identities. Source inspection supports the starting observations; proposed architecture, acceptance criteria, and priorities are requirements of this new goal.

- [Household candidate generation and projection](https://github.com/santyr/earthship-ui/blob/3124361f86c76052aeea7bb6f0821b54af727bf3/openhab/scripts/household/pipeline.py)
- [Current planner scope and owner gates](https://github.com/santyr/earthship-ui/blob/3124361f86c76052aeea7bb6f0821b54af727bf3/openhab/scripts/household/planning.py)
- [Recommendation parsing and climate previews](https://github.com/santyr/earthship-ui/blob/3124361f86c76052aeea7bb6f0821b54af727bf3/src/lib/household/recommendations.js)
- [Recommendation presentation](https://github.com/santyr/earthship-ui/blob/3124361f86c76052aeea7bb6f0821b54af727bf3/src/lib/ui/RecommendationPreview.svelte)
- [Existing household architecture](https://github.com/santyr/earthship-ui/blob/3124361f86c76052aeea7bb6f0821b54af727bf3/docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md)

**Instruction for the running agent:** Adopt this goal at the next safe checkpoint. Make decisions and recommendations the explicit product objective. Remove greywater from recommendation/optimization scope without changing its OpenHAB behavior. Preserve prior verified repairs; implement the three human-advice slices and their feedback/evaluation through existing infrastructure. Prepare per-shade position and manual-movement telemetry now for the motors expected within approximately one month; commission actual feedback when available and use it for both updated advice and carefully evaluated action-response learning. Do not add Snap or automatic actuation. Reprioritize remaining WeatherNext/ML work by the decision it improves. Finish implementable work and report source verification, installation, real-input availability, device-observation commissioning, and action-effect qualification separately.
