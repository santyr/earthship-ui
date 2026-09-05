# Energy analytics release — September 5, 2026

Tasks 95 and 96 were implemented, independently reviewed, merged, pushed, and
deployed with operator approval. Task 82 remains explicitly on hold. This
release does not complete the remaining forecast-learning and outcome-verification
work in [the outstanding-work tracker](outstanding-work.md).

## Verified outcome

- The dual-version UI reader was deployed before the v2 publisher. While the
  publisher still emitted v1, the two new values rendered as unavailable.
- The live v2 payload exactly matched the September 4 battery row in epoch
  `discover_4_module_2026`: minimum SoC 84%, daily range 16 percentage points,
  daily estimated EFC 0.1656947462379083, cumulative estimated EFC 7.297289539817,
  and battery quality `ok`.
- The repaired forecast service captured 1,446 rows with genuine issue time
  `2026-09-05T13:45:29Z`, v2 provenance, and no target earlier than its issue.
  Live analytics now reports the forecast as current. Missing historical
  origins were not backfilled or relabeled.
- Both attended service runs exited successfully; the existing capture and
  publication timers were restored active and remained enabled.
- At Lenovo M9 dimensions 1340x800, the live dialog was 1120x542 pixels,
  fully within the viewport with no horizontal overflow. It displayed
  `16.0 pp` and `0.166`, had no form controls, and closed successfully.
- A live check caught inherited capitalization rendering `Pp`. A scoped fix
  and rendered-innerText regression test now preserve the proper `pp` unit.

The independent `daily_source_quality_not_ok` warning remains visible. This
release does not claim all source quality is healthy or change battery
accounting, BMS counters, advisory policy, thermal authority, or household actions.

## Verification and rollback

Merged verification: 203 analytics tests; 1,103 UI unit tests; production build;
five Energy browser tests, including 1340x800 and 1280x720 geometry. The casing
follow-up passed all five Energy tests and another build. Task and final
cross-repository reviews found no remaining issues.

UI implementation: `81c9b38`, with casing correction `aa0d2cc`.
Analytics implementation: `5b60501`; verified-state documentation: `9565f8f`.
Both repositories publish on `origin/main`. The Vite service reads the UI main
checkout, so no UI service restart was needed; analytics services read their
main checkout directly.

Private receipt: `/home/sat/.local/state/earthship-energy/release-20260905.66WS8c`.
It holds before-source archives, exact unit definitions, a forecast-table dump,
the prior observational Item, database/service evidence, and live verification.
Restore publisher v1 before removing the dual-version UI reader. Retain valid
captured history. No credentials or raw payloads belong in this repository.
