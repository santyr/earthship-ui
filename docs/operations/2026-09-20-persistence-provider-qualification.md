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

The [version-matched REST implementation](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.rest.core/src/main/java/org/openhab/core/io/rest/core/internal/persistence/PersistenceResource.java#L176-L257)
reports provider editability separately and refuses edits to non-managed
configuration. It does not provide an atomic managed-to-file handoff. Do not
install an overlapping file while the managed provider is still authoritative.

Before production transfer, exercise actual JDBC write/restore behavior during
managed/file rollback against a disconnected disposable database. Preserve
the explicit immutable power path, forecast behavior and historical mappings.
Account for the live collection boundary: an interval without strategy listeners
cannot be presented as uninterrupted sensor history or qualified learning
coverage. The migration procedure needs a tested gap/recovery policy before
changing the production provider. Do not introduce periodic persistence or
synthetic telemetry to conceal missing events. Preserve private recovery material
and compare the exact strategy DTO and historical prefixes after each leg.

This qualification does not authorize or claim production persistence migration,
whole-host recovery or protected-control restart safety.
