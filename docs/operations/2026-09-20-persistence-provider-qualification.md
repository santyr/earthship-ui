# JDBC persistence file-provider qualification

The prepared `openhab/file-config/persistence/jdbc.persist` now loads in an
isolated OpenHAB5.2.1 runtime and yields exactly the live managed strategy DTO,
except for the expected `editable:false`. Production remains managed; no
connection settings, strategy, collection or database content was changed.

Verified exact entries:

- All Items except Power_Evidence_JSON: everyChange and restoreOnStartup.
- gForecast group members: forecast and everyChange.
- Power_Evidence_JSON: restoreOnStartup only; its explicit immutable writer
  must remain the sole ongoing persistence path.

Aliases, custom cron strategies and all filter collections are empty in both
DTOs. The full-object comparison did not normalize away selectors, strategy
names, order or additional fields. This is provider/configuration readback,
not proof that an installed JDBC service executes every strategy correctly.

`scripts/qualify-persistence-file-provider.py` reproduces the test using the
pinned official image already retained on this host. The instance is non-root,
network-none, read-only-root, capability-dropped and uses default AppArmor and
seccomp. It has no published ports, devices or host bind mounts. Disposable
tmpfs holds all writable files. Only the secret-free strategy file was staged;
no production credentials, Item data, rules, Things or database were copied.
An ephemeral isolated administrator/token enabled the authenticated REST read;
neither was printed or retained. The successful client invocation uses explicit
loopback, the image's console login, attached stdin and a newline. Two earlier
console-connection attempts failed before qualification; all three containers,
their test identities and disposable filesystems were removed.

The installed offline grammar check also still passes; the renderer suite passes
three tests and ten parameterized subtests. Production strategy readback matches
the same prepared bytes after testing. OpenHAB's production service remains active
with MainPID4060018. No production restart, API mutation, hardware command, test
telemetry, notification or collection-policy change was performed.

## Remaining cutover requirements

Follow-up: the isolated5.2.1 test now passes two file-to-managed-to-file
roundtrips. Each leg observes HTTP404 before installing the other provider,
then compares the full strategy DTO including editability. File-owned REST
deletion is refused405; managed creation returns201 and deletion200. Exact
strategy selectors, filters and aliases survive both cycles. The first attempt
stopped on a test assertion expecting200 instead of the documented201 creation
response; cleanup completed, the assertion was corrected, and a fresh isolated
run passed. Both owned containers and their tmpfs/test identities were removed.
This qualifies configuration-provider rollback only, not JDBC data operations.

### Actual JDBC follow-up

`scripts/qualify-persistence-jdbc.py` now passes with the cached JDBC5.2.1
bundle and PostgreSQL42.7.11 driver, both reported Active by the isolated
runtime. A fresh disposable PostgreSQL16 container has no network interface
beyond loopback; OpenHAB shares only that container's network namespace. Neither
has published ports, host mounts, production data or production database
credentials. Ephemeral database credentials exist only in disposable resources.

Five successive values (10–14) written to a synthetic Number Item persisted:
initial file ownership, managed1, file1, managed2 and file2. Each checkpoint
verified exactly one added history row and byte-equivalent parsed prior rows,
including their timestamps. Both exact configuration-provider roundtrips passed.
Deleting and recreating the synthetic Item restored its last persisted value.
This verifies Item-recreation restore behavior, **not a full runtime restart**.

Two preliminary runs timed out reading initial history; the first lacked numeric
normalization and the second returned404. An instrumented run passed, followed
by another successful run with explicit JDBC mapping-table readiness before the
first update. The fixture does not conceal startup loss by replaying test state
updates until something sticks. Numeric representation is compared by value;
historical prefix records remain compared exactly.

All four owned OpenHAB/PostgreSQL pairs, tmpfs databases and identities were
removed. The production provider remains managed. Remaining qualification:
full isolated restart, forecast-group behavior, immutable-power exclusion and
explicit handling of events during the provider-free gap. The synthetic probe
does not establish uninterrupted production collection or hardware safety.

The [version-matched REST implementation](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.rest.core/src/main/java/org/openhab/core/io/rest/core/internal/persistence/PersistenceResource.java#L176-L257)
reports provider editability separately and refuses edits to non-managed
configuration. It does not provide an atomic managed-to-file handoff. Do not
install an overlapping file while the managed provider is still authoritative.

Before production transfer, finish the remaining restart and policy-branch
checks above against the disconnected disposable database. Preserve
the explicit immutable power path, forecast behavior and historical mappings.
Account for the live collection boundary: an interval without strategy listeners
cannot be presented as uninterrupted sensor history or qualified learning
coverage. The migration procedure needs a tested gap/recovery policy before
changing the production provider. Do not introduce periodic persistence or
synthetic telemetry to conceal missing events. Preserve private recovery material
and compare the exact strategy DTO and historical prefixes after each leg.

### Change-only and power-exclusion follow-up

The real JDBC rehearsal additionally passed both policy checks at all five
ownership checkpoints. After each successful changed-value write, an identical
Number update left the complete history unchanged. A different synthetic JSON
value was applied to an isolated `Power_Evidence_JSON` Item and its current state
was read back; it produced no persistence history. Each negative check sampled
three times at one-second intervals and had the changed-value probe as a
positive service control. These are bounded observations, not proof of all
future timing behavior. No synthetic values were sent to production.

Both exact provider roundtrips, five-row historical-prefix preservation and
Item-recreation restoration still passed in the same run. Its owned container
pair and ephemeral database were removed. The everyChange power exclusion and
unchanged-state suppression branches are now exercised against PostgreSQL;
forecast-group behavior, full runtime restart and collection-gap accounting
remain open. Restore of power history written by its independent immutable
writer is not established by this empty-history exclusion test.

### Full isolated JVM restart follow-up

A new run now passes an actual Java-process stop/start. The disposable launcher
permits exactly two boots while retaining tmpfs configuration/userdata and the
separate disposable PostgreSQL database. The test captures the original Java
PID, requests a clean shutdown, requires a different live Java PID, then checks
restored Number state, the exact five-row historical prefix and full file-owned
strategy DTO. No additional restore-generated history rows were observed.
All earlier provider, change-only and exclusion checks passed in the same run.

An initial attempt using Karaf's reboot command did not prove a new JVM and
correctly failed qualification; its containers were removed. The subsequent
two-boot supervised run passed and its containers were also removed. This is
full isolated JVM restart evidence, not host reboot, production restart,
protected-control recovery or proof of uninterrupted collection. Forecast-group
behavior, independently written power-history restoration and collection-gap
accounting remain required before production persistence migration.

This qualification does not authorize or claim production persistence migration,
whole-host recovery or protected-control restart safety.

### September 23 isolated collection-boundary run

The extended `scripts/qualify-persistence-jdbc.py` completed successfully against
the pinned OpenHAB 5.2.1 image, active JDBC 5.2.1/PostgreSQL 42.7.11 bundles and
a disposable PostgreSQL 16 database. It again verified exact file-provider DTOs,
two file/managed/file roundtrips, five ordered Number history writes with exact
prefixes, change-only suppression, Power_Evidence_JSON exclusion, Item recreation
restore and a different Java PID after full JVM stop/start. The restart restored
the last Number value without adding a history row.

At each of the four provider-free handoffs, the test observed provider absence,
applied one synthetic Item update inside the disposable runtime and verified that
it was **not** persisted. The next positive write succeeded and preserved the
earlier history exactly. Each unqualified synthetic interval was approximately
9–10 seconds. The final boundary report was
`verified_with_collection_gaps`, with four deliberately unpersisted updates.
This establishes an explicit gap policy for the handoff; it does not establish
uninterrupted natural source collection. Both owned containers, the ephemeral
database and credentials were removed; label-based Docker readback found none.

Forecast time-series behavior and restoration of history written by the
independent power writer were still untested at this checkpoint. The next run
below closes these two isolated-runtime gates. Production is still managed.

### September 23 complete isolated JDBC policy-branch run

The final combined run completed successfully against the pinned image and
disposable database. A guarded, temporary OSGi probe published two future Number
states using OpenHAB's real TimeSeries event API. The member of `gForecast`
persisted exactly those future states under initial file ownership and after
each of four file/managed/file handoffs. Repeating the same target with REPLACE
policy yielded the new values rather than retaining old forecast values. An
otherwise identical Number Item outside `gForecast` had no future history. The
last two forecast values (45,46) were present after a full JVM stop/start.
The final confirmation run also required the exact requested future timestamps,
not just two values inside the queried interval; it passed at all five
checkpoints and after restart.

A separate guarded probe used the exact `PersistenceExtensions.persist(item,
timestamp, state, "jdbc")` overload used by the production power observer. It
wrote one synthetic `Power_Evidence_JSON` history row without posting an Item
update. Before restart, Item state differed from the written history; after a
new JVM started, `restoreOnStartup` restored the independently written state.
The power history still had exactly one row. The ordinary change-only exclusion
check had passed at all five checkpoints. This covers the coexistence of the
excluded automatic writer and explicit immutable writer in the isolated runtime.

The run also repeated exact DTO matching, both ownership roundtrips, five-row
Number history prefix preservation, four observed provider-free gaps with one
deliberately unpersisted update each, Item recreation restore, and unchanged
history on JVM restart. The final report marks forecast and independent-power
restore verified; natural source continuity and whole-host recovery remain
untested. Both owned containers, the temporary probe bundles, database and
credentials were removed. Offline boundary/source tests passed:33 tests and10
parameterized subtests. No production provider, source, credential or rule changed.

The remaining production cutover decision must account for a real collection
gap: each isolated handoff took roughly13–15 seconds and dropped its synthetic
update. Record exact live start/end boundaries and propagate them to relevant
learning/coverage readers; do not imply the missing interval was observed.
Verify backup/rollback and live writer readiness immediately before transferring
the single provider. The isolated result does not by itself authorize or prove
that production transfer.
