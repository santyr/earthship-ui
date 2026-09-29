# Season countdown Item: staged file-provider candidate

`DaysUntilNextSeason` remains a REST-managed, unlinked, ungrouped String Item
with label “Days Until Next Season,” category `calendar`, no tags or metadata,
and JDBC Item ID 176. Its file-owned display rule has now produced a natural
Astro-triggered update, but that does not transfer Item ownership.

The prepared source is
`openhab/file-config/items/days-until-next-season.items` (SHA-256
`56b31562a03c03f8a95e0190ef3caf80fc6c12b61c3ab45d96bbd189461906e9`).
The existing networkless OpenHAB 5.2.1 provider harness matched its exact
live Item definition and removed its owned container. A separate isolated
OpenHAB/PostgreSQL rehearsal persisted a synthetic String value, withdrew the
file Item, restored managed ownership, transferred it forward again, and
preserved the JDBC history prefix through hot reload and full JVM restart.
Both owned containers and the disposable database were removed; production
writes were zero.

This is a source-only candidate. Do not install it while the managed Item
exists. A guarded live cutover still needs a private exact Item/JSONDB/history
backup, provider and current-state preflight, one-provider transfer, history
readback, rollback exercise and a later natural display write. Keep the
file-rule's separate restart gate open. No whole-OpenHAB restart is authorized
by this candidate.
