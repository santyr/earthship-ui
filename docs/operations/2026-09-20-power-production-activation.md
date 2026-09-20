# Qualified power accounting enabled in production

Activation: **2026-09-20T17:10:31.538073Z**. Solar_PV code `d4151a1` activated;
monitor deadline correction `d3361d1` subsequently deployed and pushed to main.
All702analytics tests and1537UI tests pass; UI production build passes.

## Verified live state

- Existing daily aggregate, five-minute UI publisher and hourly data-quality
  jobs now use explicit qualified policy and restricted credentials. Their
  original timers were restored; no competing schedule was created.
- `energy_power_writer` and `energy_power_reader` have SELECT on38explicit
  required tables. Only the writer has INSERT on `daily_power_snapshots` plus
  identity-sequence usage. Neither has reference-table mutation, schema creation,
  database creation, superuser, role creation or bypass-RLS authority. Private
  credential files are0600 and were not committed or printed.
- Actual restricted daily dry-run succeeds; read-only reference checks match
  all21sources/3epochs. Restricted v3 projection and monitor reads succeed.
- Actual `Energy_Analytics_JSON` is v3 and passes the frontend parser. Initial
  publication17:10:31.652998Z succeeded, followed by the natural17:15:24.382623Z
  timer publication. No synthetic forecast, daily record, DM or actuator action.
- The new daily table remains empty before the first scheduled completed-day
  write. Null totals are intentional, not zero use. The UI exposes a validated
  **WAITING / No daily data** state with provenance details; malformed payloads
  remain unavailable without a details action.

The first normal daily write is approximately00:21MDT onSeptember21, covering
September20. It will necessarily be partial because collection began that morning.
The monitor waits until00:30before requiring the newly completed day, avoiding
a false alert from its00:20run before the existing writer. Present partial
coverage is distinguished from a missing daily record. Lifetime/legacy EFC and
unqualified AC-load balances are not blended into this series.

## Receipts and rollback

Private role/readback receipt: `/tmp/power-role-release-huyo69bt`.
Private service activation before/after: `/tmp/power-activation-release-_1o7jxr8`.
The source/schema and restore rehearsal receipts remain linked from
[release preflight](2026-09-20-power-release-preflight.md).
Drop-ins are exactly `qualified-power.conf` under the existing three service
directories. Credential files are under `/home/sat/.config/hex/energy-power-*.jdbc`.

If rollback is necessary, pause those existing timers, let active jobs finish,
restore the captured service definitions/drop-ins, daemon-reload, and restore
their prior timer states. Verify the resulting publisher contract before any UI
reader rollback. Preserve migration5 and all recorded evidence; do not delete
history or reset learned state. Restricted accounts can be disabled separately
after confirming no remaining consumers.

## Still unproven / remaining

The first natural completed-day insert and full-day acquisition/persistence
coverage require future evidence. Independent AC-load qualification and remaining
legacy report/feature-export policy work are still outstanding. Neither this
activation nor passing tests prove long-term accuracy, lifetime battery use,
physical-source failure recovery, or full-openHAB restart behavior. Task82 remains
held. File-first configuration migration remains a separate approved workstream.
