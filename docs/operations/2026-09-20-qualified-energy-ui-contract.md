# Qualified energy UI v3: reader-first contract

The frontend accepts exact v1/v2 unchanged and adds `earthship-energy-ui/v3`.
The live publisher remains v2; no synthetic Item state was published. The
running Vite service serves the new validator/component, and the unchanged live
v2 payload parses successfully. All1536unit tests and the production build pass.

V3 retains the v2 sections and adds an exact `accounting` object:

- `policy`: `qualified_power_evidence_v1`.
- `basis`: `observed_qualified_throughput_in_requested_window`.
- `cutover`: actual aware collection activation timestamp.
- `windowStart`, `windowEndExclusive`: canonical local dates, one to366days;
  the exclusive end cannot follow today's site-local date.
- `daysPresent`, `missingDays`: nonnegative integer counts summing to the window.
- `latestBatteryCoverage`, `latestPvCoverage`:0–1 or null for an empty series.
- `latestRevision`: null for an empty series, otherwise exact
  `{id, sha256, computedAt}`. ID is a positive safe integer; digest is64lowercase
  hexadecimal characters. Computed time must be no later than generatedAt, no
  earlier than cutover, and after the latest represented local day completed.
- `loadStatus`: `ac_load_evidence_unqualified`.

The latest date must lie in the selected window and not precede collection's
local date. The selected latest revision is not replaced by an older
better-quality day. Missing days forbid overall `ok`; latest coverage below0.9
forbids `ok` for the corresponding battery/energy section. Existing15-minute
freshness and16KiB limits apply to all three versions.

V3 `lifecycle.periodEfc` is observed-window throughput. Both
`endingCumulativeEfc` fields must be null: this bounded series must not masquerade
as lifetime accounting. `energy.latest.loadKwh` and winter deficit must be null
until independent AC-load evidence is qualified. Empty series have no latest
revision, date, energy row, coverage, daily EFC or period throughput totals.
Negative throughput is rejected. Original v1/v2 numeric-load requirements remain.

The compact display says **observed EFC**; details identify the window, missing
days, latest coverage, policy, cutover and revision. Legacy estimates are excluded
and the distinction from lifetime use is explicit. No control is added.

## Remaining producer work

Implement matching Python v3 validation/projection and publisher policy routing,
selecting latest revisions before quality interpretation. Carry qualified daily
source quality into health without reading stale legacy rows. Share fixtures
across producer/consumer tests, then rehearse the database release and deploy
the producer only after this reader. Do not activate the accounting writer while
other consumers still require legacy-only products. Existing monthly/lifecycle/
winter reports and feature exports still need explicit policy treatment.

Rollback order: return the publisher to v2 first and verify its live payload,
then remove v3 reader support if necessary. Do not delete qualified evidence.
