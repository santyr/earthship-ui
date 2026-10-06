# Weather-health age Item file migration

Two observational Items are now live, verified file-owned:
`WeatherData_WH31E_AgeSeconds` (JDBC 532) and
`WeatherData_WH32B_AgeSeconds` (JDBC 534). Their canonical source is
`openhab/file-config/items/weather-health-ages.items`, SHA-256
`c1cba28d41c685d40eb61628d866b488365543d7f7bbff45a139a81aad3768e4`.

Both remain plain Number Items, with the same labels, empty category/tags,
`gWeatherHealth` membership, native channel identity and empty link
configuration. The state-description metadata keeps its single-space value
and `%.0f s` pattern; this preserves seconds as a display format without
adding Number:Time or unit conversion semantics. The Group remains managed.
Health-status and outdoor-age Items used by SkyCondition and protected control
remain managed and unchanged.

## Native qualification

The guarded qualifier supports owned isolation only. Its five phases are
managed baseline, hot file handoff, full cold-JVM restart, original managed
rollback and final file handoff. It verifies both Item/link providers, metadata
ownership, restored numeric states, all six Group members and original JDBC
prefixes. The final capsule is
`/home/sat/.local/state/openhab-config-migration/weather-health-ages-20261005-krgv72lu/`.
All **1,671,736** original rows across the six histories remain byte-exact through
every phase and the final SELECT-only production check. Both owned containers
and anonymous volumes are removed. The 28 focused guards pass; independent
source review is clear after correcting post-restart catalog readiness.

The earlier HTTP 400 was a fixture error: it lacked the target Thing/channels.
An owned minimal comparison proves the same link request returns 400 without
a channel and 200 with an inert native channel record. This matches the
[OpenHAB link API implementation](https://github.com/openhab/openhab-core/blob/main/bundles/org.openhab.core.io.rest.core/src/main/java/org/openhab/core/io/rest/core/internal/link/ItemChannelLinkResource.java#L200).
The final fixture seeds exactly two native channels with no endpoints or
transformations, no HTTP binding, no executable rules and no hardware links.
After its internal seeding restart it waits for all three native catalogs.
Binding fetching is not qualified by this fixture.

Docker's packaged client cannot read the private host path directly. Native
stopped-fixture registry copies therefore use an archive on standard input;
production JSONDB is never edited. Private credentials stay outside Git, and
the existing Hex token is reused.

## Attended handoff preparation

The mode-0700 recovery directory is
`/home/sat/.local/state/openhab-config-migration/weather-health-age-handoff-20261005-612g9ts4/`.
It retains original Item/metadata/link and full registry snapshots, all 56
existing installed-source pins, the current configuration archive, private
users and six recoverable original CSV histories totaling **1,671,800 rows**.
The one-shot installer is limited to the two exact Item/link/metadata contracts.
It waits for managed withdrawal before publishing the file, and verifies
providers, state recovery, history, protected definitions and source pins.
Its rollback removes only its own source inode, waits for file withdrawal,
restores original managed definitions and verifies complete recovery. Backup
and one-shot marker directory entries are synced before destructive entry;
watched-source unlink is synced before managed rollback.

The attended hot handoff passed: both Items, both links and both metadata
entries are file-owned, with live numeric states. All six original prefixes
(**1,671,800 rows**) and unrelated Item/rule/link definitions remain intact.
Thing definitions match except two explicitly recorded Open-Meteo binding
`last-updated` advances to 01:27:48Z, both already present before the first
mutation. All 56
previous installed-source hashes match; the new file makes 57 unique declared
source paths. PID **1696** is unchanged. Source updates never write Item states
or execute a household rule.
No state/command/rule-execution RPC or production service restart is part of
this migration. Production whole-JVM recovery remains a separate gate.

## Frozen verification

The full repository run passes **4,161 tests**, with 52 skips and 91 subtests.
The 42 optional signer cases lacked their explicit test-only pin in that run.
A subsequent isolated, pinned signer run passes **48 tests**: those 42 revived
cases and six repeated policy cases. This covers **4,203 unique passing tests**,
with ten standard skips remaining. The four source hashes match the frozen
review snapshot before and after these terminal runs. The follow-up clears
inherited household identities and uses disposable keys and loopback fixtures.
It sends no external relay messages. No production messaging job is rerun.

The corrected installer has independent final review with no remaining
Critical/Important findings. Its preflight regression proves an intervening
foreign regular file or dangling symlink is refused before any DELETE; the
previous artifact's destructive prefix reproduces six mocked DELETEs before
discovering the foreign file. The applied source, prior installer revisions,
review/coverage receipts and natural-source recovery evidence are private.

## Natural writer recovery and restart baseline

At **01:40:03Z October 6** (19:40 MDT October 5), live file-owned age states
are 9 and 34 seconds. Each original JDBC table has three natural post-handoff
rows: WH31E 11/41/10 and indoor console 35/4/34, at 01:37:38–01:38:38Z.
No synthetic production state is posted. Persisted managed Item, link and
metadata records for both names are absent; the live inventory has zero issues,
with 352 managed/93 non-managed Items and 217 managed/51 non-managed links.
No new ERROR/Exception line appears after the handoff.

The refreshed private restart capsule is
`/home/sat/.local/state/openhab-config-migration/restart-20261005-weather-health-ages-zqc4ttzi/`.
It retains all 40 prior prefixes plus the two age prefixes, 57 current source
pins and fresh sparse-preserving archives totaling **1,801,768,960 bytes**.
All 57 source files match the configuration archive; 95 JSONDB documents parse,
and the archived managed age Item/link/metadata entries are absent. Its 53
mode-600 evidence files are hashed by its manifest, inside a mode-700 directory.
The capture is live and non-atomic; production restore/restart remain unqualified.
`/tmp/openhab-restart-directory` selects this capsule, and its retained qualifier
uses the age worktree and all 42 original prefixes. The previous capsule remains
retained. Host authentication is still required for the approved service restart.
