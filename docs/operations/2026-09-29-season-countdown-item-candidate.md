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

At the initial cutover checkpoint, ownership remained **provisional** until the next natural `Sun_TimeLeft`
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

## September 30 natural file-owned writer and JDBC qualification

At 14:51:32.753 MDT the Astro source naturally changed `Sun_TimeLeft` from
7,084,800 to 6,998,400 seconds. At 14:51:32.757 the event log identified the
file writer `org.openhab.automation.jsscripting$file:update_days_until_season.js`
as the source of `DaysUntilNextSeason` changing from 82 to 81 days until Winter.
No forced rule execution, synthetic Item update or OpenHAB restart was used.

Independent readback verified the Item and rule remain file-owned, the rule
IDLE/NONE with its single `Sun_TimeLeft` change trigger, and both installed
Item/writer files still match their pinned source SHA-256 values. JDBC uniquely
maps the display to Item 176. A read-only repeatable-read database inspection
found 218 rows and verified that its first 217 rows and exported CSV bytes
exactly preserve the retained cutover backup prefix. The one new row is
`2026-09-30 20:51:32.762562+00`, `81 days until Winter ❄️`.

Retained prefix CSV SHA-256:
`e0bb2630eee9df6689ddf81f25a62b7ba19225b2a7011050ad86efe1c65a387a`.
Current 218-row CSV SHA-256:
`05da75f1178d7d97a92d9f380a8b41fd99551c278d51818ab206a9c5a6879203`.
These are the adapter's ordered CSV representation, not a different history
digest encoding.

This closes the natural file-owned writer/JDBC gate. The production restart
gate remains open, so the manifest's provisional migration status and private
rollback backup are retained. The one-shot apply gate remains false.
