# Moon phase display readings: staged file configuration

Current status: the approved October 1 handoff and natural Astro/JDBC checks
have passed; the two Items/links are file-owned provisionally, with the apply
gate closed and restart recovery still pending. See the
[execution receipt](2026-09-30-moon-phase-readings-cutover-plan.md#october-1-attended-execution-and-natural-source-receipt).
The staging statements below describe the earlier September 30 checkpoint.

The next observational migration slice is the two managed Moon readings,
not the Moon Group or Astro Thing. No production provider or state has changed.

| Item | Type | Exact existing channel | Existing link configuration |
| --- | --- | --- | --- |
| `Moon_MoonPhaseName` | String | `astro:moon:local:phase#name` | `profile=system:default`, `function=astro.map` |
| `Moon_MoonIllumination` | Number:Dimensionless | `astro:moon:local:phase#illumination` | Empty |

Both retain their labels, absent category, `Moon` membership and generated
`Point` semantics. The phase name is consumed by `Home.svelte`; the live
literal-rule census mentions neither reading. This is scoped dependency
evidence, not proof about dynamically constructed names or uninspected external
consumers. The unusual legacy `function` parameter is retained; do not turn
the phase-name link into a MAP transformation as incidental cleanup.
[openHAB's profile syntax](https://www.openhab.org/docs/configuration/items.html#profiles)
supports explicit channel-link parameters.

Canonical staged source is
`openhab/file-config/items/moon-phase-readings.items`, SHA-256
`fc96f70a65e8de45479cda6b8c2c97840ae78eaedc5334111036013143e3941e`.
It is **uninstalled** and has no file-ownership manifest claim. The source guard
rejects changed bytes before any live query or container allocation.

## Current unit and history evidence

A read-only repeatable-read production check at
`2026-10-01T01:37:24.278807Z` uniquely resolved the existing JDBC mappings:

- Phase name: Item 59, 998 rows, ordered digest
  `3b345682dd750919a8469778b684b3929e076d7b332e844d211254fe755507d8`,
  latest change `2026-09-27T00:02:40.741012Z`.
- Illumination: Item 41, 136,376 rows, ordered digest
  `ad3cf18475176c70b7a985ecb80303d583891b14b166cef2711f1ae704a9df13`,
  cutoff `2026-10-01T01:32:40.736142Z`.

Illumination's actual unit is **`one`**, with state expressed as a fraction
between zero and one. No explicit percent metadata should be added during
migration. The phase's older last-change timestamp is not itself stale
telemetry: this JDBC strategy stores changes, and a phase legitimately holds.
These are planning snapshots, not frozen live-cutover backups or proof that
later rows match. A handoff must capture and verify its own current prefix.

## Isolated qualification

`scripts/qualify-moon-phase-provider.py` reuses the established private,
networkless OpenHAB 5.2.1 snapshot harness. Its first run passed exact file
Items/links on boot and after restart, withdrawal and managed rollback. The
two profiles and generated semantics matched; the owned container and volumes
were removed. The strengthened unit/state-description comparison then failed
closed because the offline restored snapshot lacked the Astro binding: both
descriptions lost their channel-derived read-only flag and phase options.
That owned container was also removed. The corrected harness now stages the
actual cached Astro 5.2.1 bundle, SHA-256
`1a3b8207ec49834022706359bff60ff2f4eaa1354d392c48850cb418de63e7db`,
before boot. It rejects bundle drift before allocation and retains the strict
unit/options/read-only comparison. The complete corrected run passed exact
first-boot definitions/links, full restart, file withdrawal and managed rollback
for both readings, including units, state descriptions, phase options and
semantics. Its owned container and volumes were removed. Neither failure was
treated as a production fault or repaired by weakening the expected contract.

`scripts/qualify-moon-phase-jdbc.py` reuses **one** established OpenHAB/PostgreSQL
fixture pair for both Items, rather than starting a separate pair per reading.
Its first attempt incorrectly expected a percent display and failed closed;
both owned containers were removed. After correcting the fixture to the actual
fraction/`one` contract, its complete rerun passed:

- Two synthetic states persisted only inside isolation.
- Managed rollback and forward transfer restored the states and history prefix.
- Hot file reload preserved state and history.
- Full isolated restart restored both states and unchanged history prefixes.
- Both owned containers/databases were removed; production writes were zero.

Forty-three focused/adjacent tests pass, including source/binding/provider/profile/type/
semantic/unit drift, exact fractional quantity checks, existing numeric/string
comparison behavior and setup limited to these two Items plus an isolated Group.
Production inventory still has zero issues and 382 managed / 62 non-managed
Items, 246 / 21 links. No OpenHAB restart, actuator command, configuration
normalization, Item state injection or credential/grant change occurred.

## Remaining live gates

Prepare a guarded exact-target handoff with a private Item/link and current
JDBC-prefix backup, existing unit/state/semantic readback, managed rollback
exercise, original history identities and one provider per resource. Preserve
the `Moon` Group and Astro Thing; do not install the source beside managed
definitions or reuse the historical snapshot as a current backup. Require a
natural source update after transfer, without fabricating a phase change or
mistaking a held phase for stale telemetry. Production restart recovery remains
separate from these isolated results.

The source-only handoff adapter and
[exact attended plan](2026-09-30-moon-phase-readings-cutover-plan.md) are now
prepared. Seventy-one focused/adjacent tests and the actual read-only live
preflight pass (998 phase / 136,382 illumination rows). History verification
streams a bounded digest instead of allocating repeated full row lists; it
permits new natural updates only when the original prefix remains exact and
current Item/JDBC values agree. Atomic exclusive file creation, a private
process lock, complete partial-failure rollback and an explicit successful
managed round trip are covered offline. Apply remains default-off; no backup,
lock, provider transfer or live rollback has yet run. Owned test scratch was
removed. This is readiness evidence, not production ownership.
