# Household original-source capture implementation

Approved basis: PR #3 phases 1–2 and initial milestone. Inline execution with TDD; one stage review after source and tests are complete.

Implement a bounded read-only collector that produces the exact existing `earthship-household-inputs/v1` offline bundle. Fixed roles: BMS SoC, MPPT60 day counter and three native temperatures. Epochs are explicit independent configuration, never inferred from a receipt. Final as-of time follows collection; every original remains subject to its original expiry and the frozen policy.

1. Pure assembly tests: exact bytes/digests/persistence clocks, fixed role/epoch bindings, future/refreshed clocks refused, deadline and size refusal, missing source explicit.
2. Assembly implementation with injected bounded readers and no transport or command path.
3. Fixed read-only JDBC reader for energy receipt Items, stable transactions, query/row/byte/time limits, no older-good fallback across malformed barriers. Reuse native temperature source reader unchanged.
4. Private-config CLI with sanitized errors, exact local PostgreSQL role restrictions, stdout-only bundle, no service installation or automatic publication.
5. Focused serial capped tests and original-source replay proof; update full program tracker; one independent review and hosted validation. This stage does not complete projections, constraints, planning or live qualification.

All local tests: CPU20%, memory256MiB, swap0, tasks24, idle I/O, single numerical thread. No credential values in output or repository. No new grants or owner changes.

Verification:30 collector tests;121 combined household tests passed under the declared caps in6.09seconds. Independent final review approved after connection-budget fix and regression; no unresolved Critical/Important findings. Real native-source capture and identical offline replay completed. Publication and broad hosted CI are next; full architecture remains incomplete.
