# October 5 Moon display and temperature-evidence file migration

## Result and scope

The attended live transfers are complete. Exactly 25 remaining Moon display
Items, their 25 original channel links, and `http:url:weatherTemperatureEvidence`
now have one verified file provider. Each transfer exercised file ownership,
restoration of the original managed provider, and final return to file ownership.
All 26 original JDBC mappings and historical prefixes survived every phase.
Production OpenHAB was not restarted; PID **1696** remained unchanged.

This continues the operator-approved file-first migration. It preserves names,
IDs, labels, semantic membership, units, profiles and existing behavior. The
Moon phase/illumination pair and parent Astro Things were already file-owned and
were not transferred again. The temperature evidence Item and its existing link
remain managed and unchanged; only their read-only HTTP Thing moved to files.
No household command, production rule execution, fabricated state, training,
publisher run or active JSONDB edit was used.

Live literal consumer checks found no rule mentions of these 25 Moon names;
this is a bounded consumer census, not closure of arbitrary dynamic/external
consumers. The HTTP snapshot continues feeding the existing file-owned Office
Hallway temperature observer and passive UI, with its source policy intact.

## Qualification and review

Baseline was clean commit `59b3500`; the 40 existing Moon migration/provider tests
passed. New guards were exercised RED then GREEN for exact definitions, closed
mutation scope, source/spec hashes, release gates, exclusive file installation,
both failed file-verification recovery paths and repeated source withdrawal.

An owned, networkless OpenHAB 5.2.1 restore rehearsal with the exact installed
Astro/HTTP binding versions verified all 25 Items/links and the HTTP Thing on
first load and full JVM restart, then restored the original managed definitions.
There were **zero descriptor/metadata deviations**. The first isolated Thing
rollback used an incorrect recreation method; correcting the harness to the
original `/things` POST contract, omitting binding-generated channels, passed
repeated rollback. Failed and successful owned containers/volumes were removed.

A separate owned OpenHAB/PostgreSQL rehearsal persisted all 25 synthetic values
only inside isolation, then verified hot reload, full JVM restart and original
managed state/history recovery. Initial fixture errors exposed the need to
match the live US measurement context and the native JDBC REST DTO's unitless
quantity representation. The final comparison retains exact decimal values in
each frozen original Item unit; explicitly wrong units and nonfinite values are
rejected. Both owned containers were removed. No production values were posted.

Fresh independent review found two recovery issues: surviving Items can lose
binding-derived metadata after partial link withdrawal, and backup directory
entries needed syncing before deletion. Both were fixed with failing/passing
tests. Recovery now checks intrinsic Item identity before repairing exact links,
then requires complete original metadata and history. Backup files and directory
entries are synced before the first destructive stage. Withdrawal uses unique
private names and syncs both directories. Final review reports no remaining
Important/Critical findings; its independent three-module run passed 36 tests.
The final affected suite, including existing Moon and registry inventory tests,
passed **90 tests**; all four new scripts compile.

## Live execution and independent readback

| Resource batch | First file phase | Original managed rollback | Final file phase |
| --- | --- | --- | --- |
| 25 Moon Items and 25 links | 2026-10-05 16:25:29.654074Z | 2026-10-05 16:25:31.544286Z | 2026-10-05 16:25:34.867291Z |
| Temperature evidence HTTP Thing | 2026-10-05 16:29:30.213625Z | 2026-10-05 16:29:32.500498Z | 2026-10-05 16:29:35.026920Z |

Each phase checked exact definitions, sole provider, populated states, original
JDBC prefixes and protected configuration/process signatures. Independent
16:35:27Z readback again verified the installed source hashes, final definitions,
all 26 history prefixes and all 25 current Moon states against their latest
native JDBC values. Native quantity columns omit units; comparison uses the
unchanged original Item unit. DateTime values are compared at JDBC's native
millisecond precision; higher-resolution REST timestamps are retained privately.
The temperature JSON state matched its latest JDBC value byte-for-byte.

Eight dynamic Moon readings had two new native JDBC rows each after final
handoff: azimuth, distance timestamp/distance, phase age/degree/percent, elevation
and shade-length ratio. The natural 16:31:17Z Astro events include their original
channel source identities and match the persisted readings. The other 17 stable
calendar/sign readings retain populated state and exact history; their next
natural changes are a separate future check.

Temperature evidence had **11 new native rows** after final handoff by
16:35:04.760362Z. The original sole HTTP link, schema and native sensor stream
epoch are preserved. Complete multiline String events include the original
HTTP snapshot channel source identity. A private natural-event receipt captures
58 post-transfer source-attributed changes; all eight dynamic Moon readings and
the temperature snapshot match their captured Item and latest JDBC state.
Moon, Sun and the temperature HTTP Thing remain ONLINE.

Comparing the earlier Moon checkpoint to the later readback exposed exactly two
natural OpenMeteo property updates at 16:27:35/36Z. Only their `last-updated`
properties advanced. Reconstructing those two properties reproduces the original
full Thing fingerprint; every other field matches. The weather checkpoint,
taken after that scheduled refresh, matches the later fingerprint directly.
This is recorded as a natural subsequent property change, not a migration
exception or relaxed live handoff check.

Final registry inventory at 16:34:34Z has **zero structural issues**:

| Kind | Managed | Non-managed |
| --- | ---: | ---: |
| Items | 355 | 90 |
| Things | 78 | 8 |
| Rules | 35 | 7 |
| Links | 219 | 49 |
| Persistence | 0 | 1 |

All 42 rule definitions are unchanged. The manifest adds exactly 51 verified
ownership declarations. Non-managed census counts alone do not establish file
ownership for undeclared resources.

## Sources, recovery points and remaining gates

| Canonical source | SHA-256 |
| --- | --- |
| `openhab/file-config/items/moon-display-readings.items` | `b6fa17b86928912e20c693859621438fc0198042efc7eb70d5ffbcf9e42c03bc` |
| `openhab/file-config/things/weather-temperature-evidence.things` | `b6291324a043559e6d47896ca240f62fdf30e3252c4102a9b9da8aa48b847806` |
| `openhab/file-config/moon-weather-migration.json` | `3d1397e8ea4f90cd4072ed1c5de52da951d10e85ca1bd1630d7e5b7257d4f59d` |

Private recoverable original definitions, exact gzip CSV history exports and
three live phase receipts are retained at:

- `/home/sat/.local/state/openhab-config-migration/moon-file-20261005-td7h7m2a/`
- `/home/sat/.local/state/openhab-config-migration/weather-file-20261005-cw1a5zen/`

Durable qualification proofs, logs, before/after inventories, independent
readbacks, natural-event proof, source/tool copies and the evidence hash manifest
are retained under
`/home/sat/.local/state/openhab-config-migration/moon-weather-qualification-20261005/`.
Directories are private and evidence files mode 0600; original managed rollback
was actually exercised, not merely described. Keep these recovery points. For
any later recovery, withdraw the exact owned file from the watched tree before
restoring its saved managed definition; verify provider absence and every
original link/metadata/history guard. Never install both providers together.

The tracked adapter's `LIVE_RELEASE_READY=False` remains locked. The private
attended runner enabled it only in its process after validating the exact owned
provider/JDBC proof pair and fresh live preflight; it is not an unattended
migration interface and rejects already-installed targets.

Isolated full restart qualifies this batch's load/recovery behavior. **Production
whole-JVM restart recovery remains unqualified** for this new batch and awaits
the separately attended restart. Stable Moon readings still await their next
natural calendar changes. Protected controls, Goat-owned resources and the
remaining managed inventory were not migrated or broadly qualified by this
observational batch. No change to the standing November no-venting assumption.
