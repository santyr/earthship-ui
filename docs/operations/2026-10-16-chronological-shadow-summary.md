# Chronological shadow summary — 2026-10-16

Approved scope: retain source-bound summaries after the existing scheduled original-plan replay, report per-intent proposals/blocks and exact original policy comparisons, and distinguish decision volume from chronological coverage. No fitting, extra forecasts, resource policy changes, owner changes or actuator requests.

The observer retains one immutable private admission per original receipt. It pins the original document, replayed snapshot, normalized as-issued observation, original decision/expiry, forecast horizon, software runtime, registry, configuration and model identities. Normalizing verification time and presentation expiry prevents later verification from creating another decision or renewing its original clocks. A conflicting or corrupt retained admission refuses the new report; the previous report expires normally.

The rolling report covers seven elapsed days, with Denver origin dates. Bucket dates derive from the exact UTC window endpoints, with at most nine Denver dates across spring-forward; a maximum of 4,096 admissions, 16 distinct version groups and 32 KiB public output prevents unbounded work per cycle. Admissions remain private retained evidence; the rolling report is bounded independently. The report counts:

- distinct original replayed decisions;
- distinct Denver origin days;
- a maximum set of non-overlapping original forecast intervals, selected by earliest forecast end;
- planner availability **at original issue**, plus decisions with unavailable source evidence;
- proposals, hard blocks, unknown-input blocks and shadow selections for each intent family;
- original greywater `matching_block`, `different_gate_result` and `unknown` comparisons.

A family without a proposal receives zero exposure. Versions remain separate, including each group's per-family counts. Totals across groups describe collection volume. Origin days and non-overlapping windows do not establish statistical independence, model skill, physical eligibility, action benefits or release authority. Objective decomposition, baseline performance and other missing evidence remain explicit. The existing twelve-gate qualification report is unchanged.

The fixed GET endpoint `/api/household-chronological-summary` serves only the curated private cache under existing ownership, mode, symlink, size and read-race checks. Query parameters, other methods, duplicate JSON keys, unknown nested fields, promoted authority and inconsistent counts are refused. The Earthship page displays the summary under its existing content and marks it stale after fifteen minutes. No action control is added.

Collection and reporting occur after the existing verified observation is successfully published. No second model replay or historical backfill is performed. Optional reporting failure leaves that observation intact and allows the remaining scheduled reporting flow to continue. The existing scheduler, shared resource allocator and production limits are unchanged. Source verification runs at bounded directory/publication boundaries rather than once for every historical row.

## Verification

Initial backend feature and adjacent observer/qualification/cycle tests: 68 passed; driver compatibility: 15 passed. Initial full frontend suite: 2,550 passed. These include duplicate receipt identity, original expiry, empty families, mixed horizons, version separation, retained corruption, malformed history, unsafe directory aliases, exact policy comparisons, strict public parsing and fixed GET transport. The build passed with the existing large-chunk warning. A synthetic 2,016-admission cost check took 0.316 seconds, 12 source-boundary checks and 3,651 public bytes; this is resource evidence, not outcome qualification. The single final review identified two Important issues: spring-forward can span nine local dates, and deeply nested malformed JSON can raise `RecursionError`. Both were reproduced with failing tests and corrected in one pass; reporting recursion now remains an optional refusal. No second review was requested. Final affected backend tests: **85 passed**. Full frontend suite after corrections: **2,551 passed**. Final build passed. Deployment evidence follows below.

Full PR#3 remains incomplete; counts alone do not satisfy its chronological qualification or release gates.
