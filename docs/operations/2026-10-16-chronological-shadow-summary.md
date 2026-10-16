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

## Deployment

Reviewed source `36aed88fd706cb07281c29f3445ed441736a77c8` is deployed as generation `c87ec63d4d61355699409bc24c0786b75f290e67784a9a2ca7168fc2b6576fc1`, activated at **2026-10-16 16:41:52 UTC**. The complete thermal candidate remains `284139ee4ab464adca22e79eae741f740ee62ffcda9a1f86b1be550e8180fe9f`, trained through 06:00 UTC. All five owned definitions, three active timers, both scoring calendars, shared resource pool and public UI/model/forecast passed readback at16:42:22 UTC. The clean idle daily checkout advanced to the same source; its unit bytes are unchanged and no training was started.

Three earlier handoff refusals are retained privately: a shared-lock collision, a resource-preflight refusal with rollback, and reuse of a retained private handoff output. The private helper now acquires the original lock in its idle check and uses a distinct output per attempt. Its idle window retains at least165seconds before forecast acquisition. Read-only family/handoff verification passed before the successful retry. No resource thresholds, job limits or production numerical sources were changed to make deployment pass. The precise transient resource-preflight cause was not retained in the first refusal; resource-only diagnostics were added to subsequent attempts.

Concurrent sensor/main-history merges were preserved. The UI installer used immutable reviewed file blobs and exact live preimages, installing only four files and preserving143 unrelated modified files. No explicit UI or worker restart, manual forecast, production fit or qualification probe was invoked.

Private evidence: `.superpowers/sdd/2026-10-12-household-common-cycle/chronological-summary-20261016/`.

The first normal scheduled issue produced decision `30eb4fc3dae399f8324e2e2d9a7aad6fd1c630eeb2334e18b8cac311daf711d4` at **16:45:27 UTC**, summarized at16:45:33 UTC and observed through the fixed GET at16:45:42 UTC. It reports **one decision, one Denver origin day, one non-overlapping window**, two proposals, two unknown-input blocks, zero selections and one exact matching greywater block. One decision has unavailable source evidence; model availability at original issue is observed, not qualification. There is one software/model version group.

File-only verification through the exact deployed summarizer at16:46:05 UTC reproduced the public report identically and verified original document/runtime/config/registry/snapshot bindings. Both retained admission and original plan were unchanged. No model or forecast ran during this proof. Laptop1280×800 and tablet1340×800 browser checks passed with no page errors, mutation requests or outer overflow; the panel remains beneath the existing Earthship content.

After preserving the concurrent sensor/main-history merges, combined source `112c6717d60ed6ab04debffc5b48ce81d9792096` passed the full **2,557-test frontend suite** and production build. These checks are separate from the85 affected backend tests on the reviewed feature. Gitleaks8.30.1 default rules reported zero findings for feature range1f1a85c..36aed88 with no suppression. Full PR#3 qualification remains open.
