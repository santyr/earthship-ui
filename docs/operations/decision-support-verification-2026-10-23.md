# Decision-support verification and delivery — 2026-10-23

This record closes source verification for the [adopted decision-support goal](../superpowers/plans/2026-10-22-decision-support.md). The [current decision coverage](decision-use-cases.md) remains the product tracker. It does not establish installation, commissioned observations, or useful causal effects.

## Candidate and preservation

Branch `feature/decision-support-20261023`, isolated worktree `.worktrees/decision-support-20261023`, repaired baseline `09363f102d70b38e379d235b54241d3f805f39cd`. Frozen production source `9a8bad5`; the final follow-up changes only a tooling test fixture and this acceptance documentation. The unrelated dirty root checkout is untouched. Protected `openhab/rules`, `openhab/items`, `openhab/things`, `src/lib/controls`, and `src/lib/openhab/proxyPolicy.js` have no changes against the repaired baseline. No installed release selectors, services, rules or devices were changed.

Decisions and recommendations are the objective. Shade, ventilation and explicitly approved flexible-task advice use existing numerical/transport infrastructure. Current command-planner capabilities are empty. Greywater, feeder and nightly override/device-policy scheduling are excluded; historical receipt producers remain available for exact replay. Existing independent demand remains in the energy baseline. No Snap or automatic actuation is introduced.

## Software evidence

All listed local checks returned zero. Verification profiles: Python 3.12.3 in disposable `/tmp/earthship-decision-clean-testenv`, requirements-test installed; Node 22.22.0; actionlint 1.7.7 in `/tmp/earthship-decision-test-tools`. No host dependency changes. The CI-required provisional thermal UI contract passed all 12 checks, and actionlint validated the workflows. Local raw logs are retained under `artifacts/decision-support-20261023.local/verification/`. Numerical partitions use the existing SHA256(path)%3 split with a fresh pytest process per partition and single-thread BLAS. Partition 2 ran independently while partition 1 finished; the sequential coordinator stopped only after partitions 0/1 returned zero, avoiding duplicate partition 2 execution. Its interrupted duplicate is not used as evidence. BMS auxiliary tests use their separate companion PYTHONPATH. Extracted companions were verified against git blobs, not parent-directory git rev-parse: primary `24d2e8984810cb596fe9792768510a356786f709` (105 source/test files), auxiliary `7b70117bcfb9599a12d0325771ed1103f083fa5c` (122), zero differences.

| Check | Result | Local evidence |
|---|---|---|
| Frontend unit/UI | 202 files, 3066 tests passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-vitest.log` |
| Production build | Passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-build.log` |
| Operational/completion tests | 2014 passed, 45 skipped | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-tools-completion-final.log` |
| Pinned WeatherNext SDK profile | 4 passed without cloud access; exact requirements-weathernext pins in a separate clean environment | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-sdk-profile.log` |
| Receiver optional profile | 32 passed; Flask-CORS 6.0.5 under separate disposable target | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-receiver-profile-final.log` |
| Browser fixture suite | 128 passed; full traced run, no retries or increased timeouts, fixture network/mutation guards active | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-browser-traced.log` |
| Numerical partition 0 | 2481 passed, 8 skipped, 68 subtests passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-openhab-shard-0.log` |
| Numerical partition 1 | 2473 passed, 6 skipped, 123 subtests passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-openhab-shard-1.log` |
| Numerical partition 2 | 2676 passed, 8 skipped, 69 subtests passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-final-openhab-shard-2.log` |
| BMS auxiliary profile | 1 passed | `artifacts/decision-support-20261023.local/verification/earthship-reviewed-final-bms-aux-profile.log` |

The three general partitions passed 7630 tests and 260 subtests; the distinct BMS auxiliary profile adds 1 test. Of 22 general-profile skips, 14 receiver cases and 4 SDK cases are covered by the separate passing profiles. Four explicit capped/hosted qualification cases remain unexecuted, along with 45 operational/completion profile skips; those cases are not qualified by this work. Optional receiver cases missing Flask-CORS in the clean general profile were separately executed with that dependency; the Earth Engine SDK contracts were separately executed in their pinned CI profile. Pinned nak/systemd and capped production qualification remain distinct and unqualified by skipped cases. Earlier runs/failed cases were retained and classified: historical producer expectations now explicitly target historical producers; source identity failures during source edits were rerun only after freezing production source; the Docker ownership fixture now asserts the selected explicit port. Browser startup intermittently timed out before mounting different existing screens; the same cases passed unchanged in isolated traced runs, and the full final traced result is reported above without retry flags or increased timeouts. This remains relevant to future test-harness reliability.

The fresh whole-branch review found eight Important issues and two initially graded Minor issues. Both Minor issues were regraded Important for decision-record integrity and fixed. Corrective regressions cover actual source/device identity, expiry, feedback deduplication and later correction, independent auxiliary failure, stable recommendation episodes, retained original thermal orchestration, and baseline/winner comparison visibility. No review finding is intentionally deferred. Fixtures verify source behavior; they do not establish real motor/protocol or thermal-effect claims.

## Installation/readback

Not installed. Read-only service inspection found `earthship-ui.service` active/running from `artifacts/weathernext3-capabilities.local/sensitivity-release-f17f9dc`. Existing publication continues independently. The new source remains committed in its isolated worktree. Use the existing [installation/commissioning runbook](decision-support-commissioning.md), stage compatible readers before writers, and reconcile root-only overlays before selecting a new release. No installation or movement approval is requested by this source handoff.

## Real-input advice availability

Read-only metadata snapshot at approximately 22:41 UTC: retained household observation v4, energy observation v1 and profiled-energy observation v1 exist. Energy status was available with expiry 22:55:15 UTC; profiled energy was conditional. The household observation deadline was 22:40:36 UTC, so existence alone does not qualify all decision inputs as fresh. `advice-policy.json`, `advice-operator-state.json`, `advice.json`, and `shade-observations.sqlite` are absent in the installed private directory. No live advice report was fabricated or published.

Shades need actual comfort/privacy policy plus a valid declaration or commissioned observations. Ventilation needs actual comfort/opening state and the declared environmental constraints; unresolved rain/wind/security/smoke checks remain explicit. Flexible electricity needs an explicitly discretionary useful task, deadline/reserve and source-bound original task attribution. Nightly override membership does not supply that task; the user confirmed it remains adequately handled by existing OpenHAB rules without ML.

## Device-observation commissioning

Not commissioned. The user confirms shades still need connection. A read-only inventory found 460 OpenHAB Items and no motor Items; existing Astro/sensor shade names are unrelated. The 26 logical slots follow the existing Dooya handoff; all mappings remain null. Native position precision, motion/origin, acquisition clocks, offline behavior, calibration epochs and per-member stopped targets must be established for actual hardware. The JDBC bridge labels unsupported motion/origin unknown and uses its actual adapter receipt clock. It cannot alone prove a stopped target. No RF IDs, positions or successful physical movements are invented.

## Action-effect evidence

Not qualified. No actual movement/temperature intervention dataset was collected. The software now retains original as-of inputs, stable episodes and source/model/training identities; it invokes the existing thermal producer and evaluates later qualified known-action windows. Current numerical action support requires independently observed complete uniform house endpoint positions. Mixed/partial positions remain observations without a proportional heat-gain assumption. Paired prediction error under known actions does not establish optimality or causal thermal savings. Energy nominal SoC comparisons are experimental model scenarios; rule-based shade/ventilation advice has no invented numerical benefit.

## Implementation rulings and costs

1. Use an isolated worktree based on the current repaired branch instead of importing the dirty root overlay: preserve prior repairs and reviewability. Cost: root-only features require reconciliation before installation.
2. Compare one approved flexible task at a time with the existing storage model: avoid unqualified joint scheduling/headroom claims. Cost: multiple tasks require an operator choice.
3. Prepare observation software now and leave physical commissioning pending actual connection/mappings and applicable attended authorization. Cost: real-feedback acceptance remains open until hardware exists.
4. Reuse the existing JDBC shade acquisition and preserve unknown motion/origin plus adapter clock basis. Cost: that legacy feed alone cannot confirm stopped targets.
5. Regrade omitted baseline/winner comparisons as Important and always retain them. Cost: a small bounded comparison-selection change.
6. Regrade correction of expired self-reported advice as Important; retain bounded human history and distinguish physical observations. Cost: bounded journal API/UI expansion.

Next acceptance events: supply actual policy/declarations/approved task attribution; authorize and verify a staged installation through the existing process; connect/map each motor and retain read-only commissioning evidence; then accumulate later matched action/outcome evidence. Forecast work is ordered by the specific shade, ventilation or useful-load decision it improves.
