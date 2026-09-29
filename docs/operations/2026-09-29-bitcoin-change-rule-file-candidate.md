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

## Guarded live handoff and natural writer — September 29

After the exact read-only preflight passed, the reviewed release flag was
briefly opened in commit `2c60247` and the guarded adapter saved the managed
rule privately at `/home/sat/.local/state/bitcoin-rule-fzvzhmq5/managed-rule.json`.
It withdrew the managed provider, installed the exact Git file (SHA-256
`41893bdbd9eeefb60fab2ffa5bbe12c49ebc1c0f09e91176d285c02d9d719391`),
and found one file-owned `IDLE/NONE` rule with the original UID and trigger.
No OpenHAB restart or price-writer pause occurred.

At 06:22:44 MDT the next natural Exec price update posted 84,187, followed
four milliseconds later by a file-attributed 24-hour change of
1.0284411376455058%. The calculation matches the held 83,330 price returned
by OpenHAB's persistence extension: `(84187-83330)/83330*100`. Read-only
JDBC readback showed seven percentage rows from 06:22:14 through 06:25:14,
crossing the provider handoff without loss of the existing Item history.
The exact later prior-day 06:22:44.024 sample was 83,321, but both the old
DSL and new JS paths selected the preceding 83,330 sample at this same-second
cutoff. This preserves the live OpenHAB `persistedState` behavior; it does
**not** establish sub-second 24-hour precision. The file rule continued to
produce naturally changed values through 06:25:14, and OpenHAB stayed active.

Ownership is `file`/`provisional` pending a later restart check. The private
managed backup remains; the one-time Bitcoin release flag was re-locked.
