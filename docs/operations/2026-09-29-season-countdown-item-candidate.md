# Season countdown Item: attended file-provider cutover

Before cutover, `DaysUntilNextSeason` was a REST-managed, unlinked, ungrouped
String Item with label “Days Until Next Season,” category `calendar`, no tags
or metadata, and JDBC Item ID 176. Its file-owned display rule had already
produced a natural Astro-triggered update.

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

The attended live cutover was approved and completed September 29 at 19:21
MDT. The exact preflight again found the managed Item, idle file-owned rule,
217 JDBC history rows under Item 176, and the unchanged source hash. The
guarded adapter took a private Item/JSONDB/history backup, transferred the
Item to file ownership, exercised actual managed rollback, and transferred it
back to file ownership. It reported `file_provider_provisional` and the same
217-row history. Independent readback found the file-owned Item's current
state equal to the JDBC last state, the rule `IDLE`, no Item link, matching
installed/source hashes, and OpenHAB running. The backup directory is mode
0700 and its contents mode 0600. No OpenHAB restart or synthetic Item update
occurred. The one-shot `--apply` release gate was closed again.

Ownership remains **provisional** until the next natural `Sun_TimeLeft`
*change* makes the file-owned rule post a new `DaysUntilNextSeason` value and
JDBC persists it under Item 176. Unchanged Astro updates and persistence
restoration during provider reload are not that proof. Retain the private
rollback backup; the separate restart gate also remains open.

A post-transfer read-only `config_inventory.py --summary` initially flagged
the file-owned Item as undeclared. The exact installed/source file hash and
file provider were rechecked, then `ownership.json` gained only the
`DaysUntilNextSeason` declaration with `migration: provisional` and the
existing file-owned rule as its writer. The live inventory now reports 382
managed and 60 non-managed Items with zero issues; its 14 focused tests pass.
This manifest repair does not qualify the pending natural-write or restart
gates.

The source `scripts/migrate-season-countdown-item.py` implements an
exact live preflight, private Item/JSONDB/Item-176 history backup, managed
rollback exercise, and fail-closed restoration path. Its `--apply` gate is
again **off**. Before approval, a September 29 17:18 MDT `--check` found the
exact file-owned writer, managed display Item, 217 JDBC history rows and
matching source definition; it made no production write, and `--apply`
refused before opening either live authority. The failure paths were then
tested and live state rechecked before the attended transfer above.
Two offline transaction tests now pass: the success path exercises managed
rollback before returning to file ownership, and a simulated file-provider
failure restores the managed Item. These tests do not substitute for the
next natural writer event.
