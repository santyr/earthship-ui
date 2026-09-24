# Curtailment prediction Item: file-provider staging

`Predicted_Curtailment_Hours` is an observational Number Item directly written
by the existing `forecast-intel.service`. The Home and Energy screens display
it; a read-only search of current live Rule actions found no control consumer.
At the September 24 preflight it remained REST-managed, unlinked, with no
group or extra metadata, label `Predicted Curtailment Hours Today`, one
`forecast-intel` tag, current state `0.0`, and JDBC ID 574 with eight historical
rows. The latest JDBC value is numeric `0`; exact text equality would
incorrectly reject the equivalent current Number state `0.0`.

The staged Git definition is
`openhab/file-config/items/predicted-curtailment.items`, SHA-256
`ef89bc9f0a704713d13c8eba04d3f1429f9a5861b493cfdb15266a92d5ce989e`.
The existing disconnected 5.2.1 file-provider qualifier was generalized only
to accept an explicit Item type. It confirmed exact live-definition parity for
this Number Item; its owned networkless container and tmpfs were removed.
An isolated OpenHAB/PostgreSQL rehearsal then used one synthetic `2.0` value
only inside disposable network-none containers. It verified the JDBC write,
managed rollback and forward transfer, hot file reload, and full JVM restart
with the state and historical prefix preserved. Both owned containers and the
test database were removed; production writes were zero. Three focused tests
cover numeric-only state equivalence and the staged source.

The new live adapter is read-only by default and hard-gated with
`RELEASE_READY=False`. Its September 24 `--check` passed with the stable Item
ID and eight-row history; an `--apply` probe refused before mutation. The
source file is **not installed**, the managed provider and timer are unchanged,
and no forecast was manually run. Keep the gate off until after the upcoming
natural 06:40 MDT qualified-SoC forecast publication is verified. Before any
attended transfer, repeat the live preflight, inspect the exact source/state
and timer, preserve a private rollback copy, then require an actual natural
post-transfer writer and unchanged JDBC identity/history. This staging alone
does not qualify provider ownership, forecast learning, or curtailment advice.
