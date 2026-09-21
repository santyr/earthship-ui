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

This qualification does not authorize or claim production persistence migration,
whole-host recovery or protected-control restart safety.
