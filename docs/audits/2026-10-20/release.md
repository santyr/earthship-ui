# Release and handoff

Status: audit and implementation in progress; no deployment or physical qualification claimed. Live dirty checkout, private configuration and immutable source packages remain untouched. Remote main begins at `65ee7e95d58e6a6101700da3eccea67c9fea0ec7`.

Changed surfaces, exact tested/installed hashes, scoped deployment/rollback and next natural owner-cycle evidence will be recorded as work completes. Software fixture success cannot commission radio hardware, qualify unknown water inventory, establish causal action effects or prove forecast skill.

## Night-load owner repair (candidate, not installed)

Ledger v1 remains readable. New entries add an optional exact request identity; legacy entries suppress duplicate reuse conservatively. Keep all pending entries and all terminal identities through at least acceptance/last terminal update + 150 seconds (120-second request age plus 30-second future skew). Reclaim only expired terminal records, oldest first, when needed. Admission enforces 32 entries and 8 KiB with 128 bytes reserved per pending terminal transition. Saturation denies before acceptance, policy changes or commands. Existing same-ID payload mismatch is explicit `request_id_conflict`. This is bounded admission, not a throughput guarantee.

ON order: durable accepted ledger → visible ON → exact durable JDBC ON → existing device OFF matrix → provider verification → durable completion → completed result. OFF retains Shureflo command/provider confirmation before exact durable OFF and completed receipt. A failed OFF commit restores visible conservative ON ownership and fails; no completion is claimed. No automatic device command retry added.

Other ledgers were assessed independently: feeder has a 5-second accepted-start cooldown, so 32 newer accepted requests need at least 160 seconds, beyond even a future-skewed original's 150-second admission span. Greywater has a substantially longer accepted-start cooldown. Their legacy policies were preserved; the final owner suites must verify cooldown and restart guards separately.

Rollback must use the prior exact managed rule action source and manifest/readback workflow; do not roll back new ledger identities by deleting receipts. Previous code accepts optional fields. Install and next natural-cycle verification remain pending independent review and final integration.
