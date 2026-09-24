# Forecast quality Item file-provider handoff

Scope: seven directly published, observational Number Items written by the
existing `forecast-intel.service`: PV, precipitation, high/low and day-3
rolling errors, plus high-temperature bias. Their exact file definitions are
in `openhab/file-config/items/forecast-quality.items`; no channel link, rule,
Thing, Group, learned state or control changes are part of this handoff.

Before release, the read-only production preflight found all seven managed,
non-NULL Items, no links, active daily timer, idle service and unchanged
JDBC identities 583 and 600–605. Histories held 28–69 rows and their last
values matched the live Items. Two source/adapter tests passed. A disposable
networkless OpenHAB 5.2.1 provider accepted all seven exact definitions and
removed its owned container/tmpfs. A separate disconnected OpenHAB/PostgreSQL
rehearsal persisted seven synthetic states, passed managed rollback and
forward file transfer, preserved the JDBC prefix through hot reload and full
restart, and removed both owned test systems. Production writes: zero.

The operator's file-first migration policy and prior authorization to deploy
in-scope work release one attended observational handoff. Immediately before
`--apply`, rerun `--check`. The generic adapter takes a private JSONDB and
managed-definition/history-digest backup, pauses only `forecast-intel.timer`,
withdraws the managed Items, installs the exact reviewed file, verifies their
states and JDBC histories, exercises actual managed rollback, returns to file
ownership, and resumes the timer. Any failure must report whether rollback
and timer recovery succeeded; do not describe a partial handoff as deployed.
The new file-owned resources must be declared in the ownership manifest only
after live verification. Preserve the private recovery directory until a
separate retention decision. The next natural daily writer is an additional
publication gate, not replaceable by synthetic production updates.
