# Sky-condition icon: attended one-Item file handoff

Scope is only the passive `SkyConditionIcon` String Item. Its live managed
definition has label `Sky Condition Icon`, category `sun_clouds`, `Status` tag,
no Group or channel link, and unique JDBC Item 173. The live
`sky-condition-calculator` rule posts this icon only when it changes; its
separate `SkyCondition` output is a greywater eligibility input and must not
be paused or edited. The icon is not a pump or equipment command.

The staged source is `openhab/file-config/items/sky-condition-icon.items`
(SHA-256 `3a6d7f386c6a2b2461ea0b3b7caa52da7001a0ac9ac4233efe137e697437272c`).
Its exact DTO matched a networkless OpenHAB 5.2.1 file provider. A separate
disposable OpenHAB/PostgreSQL run preserved synthetic state/history across
file withdrawal, managed rollback, return to file ownership and JVM restart;
both owned containers and their database were removed. Four focused adapter
tests cover the closed gate, exact preflight, provisional success and managed
rollback. The production read-only `--check` found 21,175 Item 173 rows,
matching current/persisted state and an idle writer with pinned script hash
`d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
A read-only production history-copy rehearsal produced a 1,227,764-byte
mode-0600 CSV and removed its disposable directory.

The guarded `--apply` takes a private mode-0600 managed-registry receipt and
Item 173 CSV copy before mutation. It rechecks Item state/history, source and
writer identity, removes only the managed icon, installs the exact file Item,
requires the same state/metadata and unchanged JDBC history, and refuses any
new link. On failure it withdraws only its exact installed file and restores
the managed Item from the saved definition, verifying state/history. No
synthetic production update, rule run, OpenHAB restart, control or unrelated
Item change is part of this transaction.

An `--apply` success is **provisional**. Before changing the ownership manifest
to file/verified, independently read back the Item, Item 173 history prefix,
the unchanged `SkyCondition` control input and rule status, then observe a
natural icon change from the existing writer with a new JDBC row. If the
natural writer gate is not yet due, retain the private rollback receipt and
leave the manifest managed/pending; do not create an artificial icon update
to close it.
