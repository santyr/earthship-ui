# Decision support: installation and incoming shade observations

The [implementation contract](../superpowers/plans/2026-10-22-decision-support.md) is authoritative. The [decision coverage](decision-use-cases.md) records current acceptance. Advice is human-only; feedback and observations never operate equipment. Greywater and feeder retain their existing independent behavior and are excluded from advice and optimization. WeatherNext remains the external weather provider. No Snap, new inference API, external messaging, or billing path is introduced.

## Source and installation boundary

Implementation is on `feature/decision-support-20261023`, based on repaired source `09363f1`, in `.worktrees/decision-support-20261023`. Do not replace the root checkout's unrelated overlays. The observed installed UI is the pinned `sensitivity-release-f17f9dc` family; this new branch has not been activated. Follow the existing stage/verify/activate process in `household-native` and UI release records. This document grants no selector replacement, service restart, rule modification, or physical movement authorization.

Stage compatible readers first: advice/shade parsers, fixed GET routes, and cards; then the updated household producer. Preserve pinned historical producers and receipt originals. Version 7 model plans and version 6 nested plan receipts have current scope; older receipts replay through retained historical producers. The existing model-plan-v6 filename convention stays stable for downstream archive lookup; its internal schema identifies the producer. New trajectory shadow receipts are version 2. Rollback restores the prior staged source/service selection; new private advice files can remain historical, and their original deadlines still expire. Never rewrite archived plans or ask old producers to execute new schemas.

Advice publication runs after the existing canonical household cycle, with failure isolated from forecast publication. It uses the existing private `household-intel` directory (0700), files (0600), immutable originals and atomic publication pattern. No browser model execution, training, new timer, or raised resource profile is required. Feedback uses same-origin JSON requests, closed fields, bounded storage and idempotent IDs. Feedback is separate from the protected `/rest` proxy and all device owners.

## Exact operator inputs

The private `advice-policy.json` must follow `household/advice/policy.py::validate_policy`. It declares a version, validity, timezone, actual comfort bounds, review/advice intervals, temperature deadband, manual hold, named shade members/privacy, a bounded ventilation window and required rain/wind/security/smoke checks, and approved flexible loads/reserve. Null domain policy disables only that domain. Do not fill missing preferences with plausible temperatures, appliance power or convenient hours. There is deliberately no production example with invented household preferences. Maintained test factories in `test_household_advice_contract.py` and `test_household_advice_energy.py` provide clearly synthetic schema examples.

Use **Record an observed shade or window state** in the console after configuring logical targets. The separate `advice-operator-state.json` retains declarations, time, validity and revision; corrections are new declarations rather than rewritten observations. The UI clearly declares 30-minute validity. Operator declarations never become independent sensor observations. The private state also accepts bounded, source-referenced environmental checks; the console does not infer clear wind, rain, smoke or security from temperature. Unresolved checks yield conditional advice. Preview sliders are never read by this path.

Actual energy comparison additionally requires `advice-energy-baseline.json`: a snapshot-bound original profile/steps, nominal bank, source reference/availability/expiry and explicit embedded task attribution. `household/advice/energy.py` defines the closed fields. Use the existing profiled storage model and original PV steps. A generic learned household profile does not prove that an individual task is already included. Do not fabricate that attribution. The current implementation compares a single useful approved task against unchanged behavior and bounded start windows. Multiple useful tasks require an operator choice; essential loads, pumps, feeder and uninspected broad macros cannot become discretionary savings.

## Before hardware arrival

The operator expects motors approximately one month after October 22, 2026. This is an expectation, not a guaranteed date or a claim of commissioning. `openhab/shade-observation-inventory.json` reuses the 26-slot roster: Kitchen 1–8, Living 9–17, Bathroom 18–21, Bedroom 22–26. Every device mapping is intentionally null. Reconcile physical names and zones before filling mappings. No RF ID, binding or installation epoch is guessed.

`household/advice/shade_state.py` defines closed versioned mappings and acquisitions. Canonical position is 0 closed / 100 open. Native values, scale, direction, actual precision, requested target, movement, supported origin, original acquisition/received/available times and clock basis remain separate. Old held values never become fresh because they arrive in a browser or an unrelated packet. A travel-time/controller estimate remains an estimate. A moving report passing through the target does not satisfy a recommendation. Every required member must independently report a fresh stopped target; a group average is insufficient.

`shade_adapter.py` reuses `thermal_model.shade_history.fetch_shade_intervals` and the existing joined-row qualifier. JDBC reads remain repeatable-read/read-only with existing row/time bounds. Legacy reports have no native motion/origin evidence, so those fields remain unknown. Their timestamp is labeled adapter-report reception, not a native motor clock. The generic acquisition importer supports richer commissioned feedback without changing any command path:

```bash
PYTHONPATH=openhab/scripts python3 openhab/scripts/shade_observation_ingest.py \
  --mapping /private/commissioned-shade-mapping.json \
  --acquisition /private/captured-motor-acquisition.json \
  --history /private/household-intel/shade-observations.sqlite
```

All input files must be owned/private. This imports a previously captured observation; it does not query or operate a motor. The retained history caps at 8192 events and refuses exhaustion explicitly. Advice archives cap at 4096 reports; feedback caps at 128 human events, declarations at 64. Arrange an explicitly reviewed archive/rotation before exhaustion; nothing silently evicts originals. Gaps, unavailable positions and mapping/calibration epochs remain explicit. Independent state changes create a new baseline; recent movement honors the declared hold and never invokes a reversal command.

## Actual observation commissioning when hardware is available

Use the upstream Dooya repository's commissioning authority and [existing handoff](2026-09-27-dooya-shades-earthship-handoff.md). Its hardware/protocol claims have not been established by this software work. Before any attended movement, obtain the existing applicable movement authorization.

For **each actually installed unit**, retain an acceptance record with:

- Logical shade, physical location/zone, real device/Item mapping, installation/calibration epoch and feedback source; distinguish a preview slot from installed hardware.
- Native scale/direction, end positions, intermediate stops and reported precision; validate 0 closed / 100 open normalization against physical observation.
- Independently measured versus estimated feedback; target/transport acknowledgement never confirms position. Identify whether movement/stop and manual-origin data are actually observable. Leave unsupported origin unknown.
- Source timestamp basis/accuracy, adapter receipt, persistence availability, duplicate/order behavior, genuine same-valued acquisitions, stale retained reconnect, offline/loss and a new installation epoch. An unavailable member prevents group completion.
- Naturally occurring or explicitly attended manual movement → retained original event → movement episode → as-of baseline → revised advice/hold → supported target-observed record. Record each member; a mean or synthetic fixture does not close acceptance.
- Console readback of actual position/quality separately from preview/desired targets, and no recommendation-driven command, rule or schedule writes.

Hardware presence alone does not authorize automation. Unmapped units and incomplete feedback retain exact blockers while other domains continue.

## Action-response evaluation after reliable feedback

Retain unadvised/manual/unknown-origin moves as well as advised moves. The advice cycle retains as-issued reports/inputs and assembles private `shade-action-episodes.json` from real movements and only contexts available before the action. It includes native/intermediate from/to positions, timing uncertainty, original references and available air/mass/outdoor, weather/solar, ventilation and sensor epochs. Missing concurrent-change/model-training information remains a confounder gap; later observations do not become earlier features.

The existing thermal framework remains the numerical producer. Feed matched coarse-group and position-aware predictions into `compare_known_action_forecasts` using later target windows, strict pre-decision training cutoffs and retained real outcomes. It reports sample count, independent days and matched errors, with qualification collecting. Better forecast error under known actions does not prove that a recommendation helped, identify separate effects of shades that always move together, or label an unchosen alternative optimal. No numeric thermal savings or causal qualification is currently established. No experimental movements are authorized to manufacture a dataset.

Report five independent evidence dimensions at every acceptance: **software verification**, **installation/readback**, **real-input advice availability**, **device-observation commissioning**, and **action-effect evidence**. A synthetic fixture closes only its software regression.
