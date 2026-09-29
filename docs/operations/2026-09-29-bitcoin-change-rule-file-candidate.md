# Bitcoin 24-hour change rule: file-provider candidate

The live `hex_btc_24h_change` is one healthy managed DSL rule with a single
`BTC_USD_Price` update trigger. Its 1,737-byte action has SHA-256
`9e15eb8e7f4e3d3118f12295d7b09f82525ab52f41b951f8809097c98fc369bb`.
It reads that Number Item's 24-hour held `persistedState` and posts only
`BTC_Price_24h_PercentChange`. A redacted live-rule reference census found no
other rule mentioning either Bitcoin Item; the Home card and ticker consume the
percentage for display. This is a manual known-consumer review, not proof
about uninspected external clients.

The staged JS file preserves the same UID and every-update trigger. It uses
OpenHAB's default persistence service and the Java `persistedState` extension
at now minus 24 hours. It posts `UNDEF` for unavailable/non-numeric current or
historic states, preserves the managed rule's zero-prior behavior, and changes
no Bitcoin price Item, Thing, link, or JDBC strategy. Three VM tests pass.

An owned networkless OpenHAB 5.2.1 rehearsal loaded the exact file rule as
`editable=false` with the expected UID/trigger, then withdrew it and restored
the managed rule. Its container and volumes were removed. The generic guarded
handoff/rollback adapter now includes this candidate with the release gate
**off**; ten offline transaction tests pass. Because the natural price poll
continues every 30 seconds, the Bitcoin path tolerates a legitimate output
change during provider transfer; it still requires one unique healthy rule,
the pinned source, a private managed-rule backup, and guarded rollback.

Before any live apply, rerun the exact managed-rule/source/Item preflight and
verify a fresh natural Bitcoin price receipt. After transfer, require a new
natural price update followed by the file-attributed percentage calculation
and an independent 24-hour carry/value check. Keep ownership managed until
that receipt, and keep the private backup until later restart verification.
No OpenHAB restart, test price, synthetic update, or protected control change
is authorized by this candidate.
