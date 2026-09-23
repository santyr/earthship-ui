# Qualified power: two natural full-day persistence checks

Read-only PostgreSQL and production-parser audit on September 23, 2026.
No rule, Item, persistence policy, accounting total, retention setting, or
hardware control was changed. Both windows are completed America/Denver days
after the explicit immutable-writer cutover.

| Local day | Persisted rows | First–last sequence | Invalid strict-parser records | Sequence gaps/reversals | Duplicate persistence timestamps |
| --- | ---: | --- | ---: | ---: | ---: |
| September 21 | 50,528 | 28,675–79,202 | 0 | 0 | 0 |
| September 22 | 50,530 | 79,203–129,732 | 0 | 0 | 0 |

Each day has one continuous stream epoch. The sequence boundary between the
two days is also contiguous. SQL validated every persisted JSON envelope and
sequence in the two windows; Solar_PV main at `1f50bdc` supplied the
`parse_power_evidence(raw, persisted_at)` additionally accepted all 101,058
original timestamp/value pairs. The September 22 rows span
06:00:02.038Z–05:59:59.978Z and contain 24,102,486 payload bytes. A natural
25-hour window starting September 22 06:00Z contained 52,640 rows, below the
consumer's 60,000-row bound. At audit time the whole `item0648` table held
158,254 rows and occupied 86 MiB including its index.

This closes the previously open **natural full-day sequence/durability and
bounded-volume check for these two days**. It does not establish delivery under
all future restarts, DST windows, physical source faults, or indefinite
retention. It does not independently validate raw register physics or qualify
AC-load evidence. Legacy pre-repair sequence gaps remain unqualified and are
not rewritten. The qualified accounting reader must continue respecting
invalid/expired intervals and its original cutover boundary.
