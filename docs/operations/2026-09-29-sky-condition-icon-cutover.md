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

An `--apply` success is **provisional**. Declare the observed provider as
file/provisional in the ownership manifest, then independently read back the
Item, Item 173 history prefix,
the unchanged `SkyCondition` control input and rule status, then observe a
natural icon change from the existing writer with a new JDBC row. If the
natural writer gate is not yet due, retain the private rollback receipt and
leave the manifest file/provisional; do not create an artificial icon update
to close it.

## Live handoff — September 29, 02:35 MDT

The immediate `--check` passed unchanged: managed Item 173 and 21,175 JDBC
rows, matching current/persisted icon state, exact staged source and idle
pinned writer. `--apply` created a private mode-0700 rollback directory at
`/home/sat/.local/state/openhab-config-migration/sky-condition-icon-20260929T083504Z`
with the managed registry receipt and a mode-0600 Item 173 CSV copy. The
guarded transfer returned `file_provider_provisional`; it did not invoke or
pause the writer or restart OpenHAB. Independent readback found the icon
file-owned with its original label, category, `Status` semantics and
`iconify:mdi:moon-waning-gibbous` state. Installed/Git source SHA-256 match.
The live Item 173 history still has exactly 21,175 rows and its pre/post
SHA-256 prefix digest matches
`f30fdb4bc734a9089596fab493fb52a8688eb2859e9fbd66ea3f2cc329787d4a`.
The writer remained IDLE and `SkyCondition` remained `NIGHT`. The ownership
manifest now declares file/provisional, and the live registry inventory has
zero issues. A later natural icon change plus new Item 173 row is still
required before upgrading that declaration to verified. The private backup
is retained; no synthetic icon update was sent.

## Natural icon writer gate — September 29, 05:30 MDT

After the 02:35 Item-only transfer, the managed sky writer naturally changed
`SkyConditionIcon` from `iconify:mdi:moon-waning-gibbous` to
`iconify:mdi:weather-sunset-up` at 05:30:08 MDT as dawn began. The event log
attributes the change to `sky-condition-calculator`; OpenHAB JDBC Item 173
contains the matching new value at `2026-09-29T11:30:08.159873Z`. Readback
still shows one file-owned icon Item, the same installed/Git source SHA-256,
and the current matching state. This closes the planned natural writer/JDBC
gate, so the Item ownership manifest is now `file/verified`.

The separate sky *rule* was briefly moved to a JS file afterward, then
restored to its original managed provider when its `SkyCondition` output was
identified as a greywater control input. That later rule rollback did not
recreate or withdraw the icon Item or remove its Item 173 row. The private
Item rollback receipt is retained. No artificial icon update was used.
