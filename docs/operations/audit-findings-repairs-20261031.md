# October 31 audit repairs

Six findings are fixed. F03 is partially resolved: normal current and historical
scoring have recovered, but the original 256-entry historical-backlog workload
still exceeds its unchanged 120-second limit. No failing performance candidate
was installed or published to main.

## Deployed fixes

| Finding | Result |
| --- | --- |
| F01 | Expired or failed-refresh action text becomes `Awaiting fresh evidence` in the action-only Home header. Retained details and original expiry remain. |
| F02 | Corrected group-write modes on two advisory files without changing their bytes. Normal fitting completed through October 31 12:00 UTC; its retained fit was activated through the original second-and-final retry. |
| F04 | Existing energy schedules remain owned by OpenHAB. Advice reports `energy_scheduling_managed_by_openhab`, with no missing-task approval blocker. No task/profile was invented; no Items or rules were modified. |
| F05 | Presentation assertions match the requested text-only header and independently check advancing expiry and failed reads. |
| F06 | Fixture builds precede Chromium within the same original budget; both release modes, chart/store instances, all geometry assertions and owned socket cleanup are preserved. |
| F07 | Published the selected deployed UI/advisory sources while preserving unrelated remote repairs, the original dirty checkout, HEAD and index. |

The battery chart retains automatic SoC scaling and the next predicted-low footer.
Forecast-led passive-solar advice uses the existing thermal model, glazing azimuth
165 degrees, tilt 64.5 degrees from horizontal and no front overhang. No shade
position history or measured nighttime shade-insulation effect was invented.
Equipment actuation was not enabled.

## Verification and live authority

- Complete reconciled unit suite: **3,454 passed**; production build passed.
- Original full geometry workload: **82 passed**, under the original 1 GiB cap.
- Action-only/advancing-expiry browser checks: **4 passed**, both tablet sizes.
- Deployed scorer/report/advice contracts: **48 passed**.
- Live UI: no page errors or non-read requests; expired header was neutral and
  Energy showed the next predicted low.
- Native current scoring: repeated successful 23-24-second slots after activation.
  Historical slots also completed successfully (recent observations about 10 s).
  A retained current-model report contains two fully source-backed one-hour
  outcomes; this is operational evidence, not model graduation or proven benefit.
- Native advice retains forecast context and OpenHAB ownership with actuation off.
- OpenSpec strict validation passed. Original checkout/index preservation passed.

UI authority:
`artifacts/audit-findings-repair-20261031.local/release-cfccb67`.

Active model artifact:
`d06ef84b592e3e9f1e1633017f6af43110deba349344e8755c432ee3dcebdc5e`.

Native family:
`20261031-5eab4a17b0ea4c688401cb4fbfebaa82-retry-457c36ba2879469aa0ffe982adbd1300`.
The normal training checkout remains at the deployed source revision `0ac41b8`.

## Native ownership recovery

The user explicitly approved clearing the stale systemd failure counter and normal
retraining/activation. The native retry budget was never reset. The successful
retry reused the newly retained fit; it did not refit.

A temporary scorer selector was restored before coherent activation. A subsequent
refusal exposed the separate advisory postprocessor dropin as incompatible with
the family's exact effective-definition contract. The replacement native family
already includes the proactive advice modules, so that redundant dropin was
retired. Exact original-family verification preceded manual timer recovery.
Original refusal requests/status bytes were archived unchanged with evidence of
dead owners, original definitions, lock identity and timer states. The subsequent
retained-fit activation succeeded. All original serving timers are active again.

## F03 remaining workload

The exact old-model scoring workload was reproduced without dropping mature
inputs or increasing timeout, memory, task or cache limits. Config-guard source
repairs are deployed, and normal current/historical execution has recovered.
The old-model maximum-size report still reaches the 120-second deadline.

Further experimental kernel path and immutable-string/cache-priority optimizations
passed 177 covering Python tests (140 scorer/replay cases plus 37 retained-worker
cases), but failed that real workload qualification. They remain on local branch
`fix/audit-findings-20261031` at `f9cd865`, with immutable trial stages retained for
review. They are not the production or published-main authority. F03 stays open;
unit success is not represented as runtime qualification.

Evidence: `artifacts/audit-findings-repair-20261031.local/`, including
`natural-score-observations.json`, `final-native-performance.json`,
`native-advice-live.json`, `live-ui-check.json`, `ui-qualification.json`,
`unit-results.json`, `browser-qualified.log`, `decision-browser.log`,
`permission-repair.json`, `family-recovery.json`, `prearm-reconciliation.json`,
`backlog-kernel-full-result.json`, `coherent-code-cleanup.json` and
`preservation.json`. Failed experiments remain distinguishable from passing checks.

Rollback selectors and prior immutable releases are retained. No equipment,
OpenHAB scheduling configuration, resource limits or historical measurements were
changed by these repairs.
