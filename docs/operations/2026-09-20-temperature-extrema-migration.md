# Temperature extrema Item migration preflight

The four Items below remain managed. The source in
`openhab/file-config/drafts/temperature-extrema.items` is prepared, not deployed.
Do not bulk-copy drafts into the watched configuration tree.

| Item | JDBC mapping | Semantic parent |
| --- | --- | --- |
| IndoorTemp_24h_Low | 178 / item0178 | Shelly_HT1 |
| IndoorTemp_24h_High | 179 / item0179 | Shelly_HT1 |
| OutdoorTemp_24h_Low | 180 / item0180 | AmbientWeatherWS2902A |
| OutdoorTemp_24h_High | 181 / item0181 | AmbientWeatherWS2902A |

Read-only September20 preflight verifies Number:Temperature, category temperature,
Point/Temperature tags, the existing labels, generated semantics metadata,
`%.0f %unit%` formatting and no channel links. Both parent Groups are tagged
Equipment; plain untagged Groups are not equivalent for generated `isPointOf`.
The closed renderer rejects definition, metadata, formatting or link drift.
Ten renderer tests pass. The installed 5.2.1 grammar accepts the exact four
identities and rejects malformed Item syntax.

`scripts/qualify-extrema-file-provider.py` subsequently booted the pinned official
5.2.1 image in a non-root, network-none, read-only-root container with capabilities
dropped and default AppArmor/seccomp. No ports, devices, host mounts, credentials,
production states or rules were copied. All four definitions registered as
noneditable with NULL state; labels, types, category, groups, tags, generated
metadata and display formats matched production exactly. Installed Item bytes
matched the draft. This qualifies the file provider, not persisted state recovery.

The first fixture omitted Equipment tags on parent Groups and correctly failed
metadata comparison; the fixture now verifies and reproduces those live tags.
A second attempt encountered transient REST withdrawal during startup. The
successful run includes stabilization and bounded endpoint retries. All three
owned containers and disposable filesystems were removed, including failed runs.
No host security profile or production service was changed.

The sole exact-name reference in the live rule registry is `temp-highlow-24h`,
IDLE/NONE, with its existing quarter-hour cron. It computes minimumSince and
maximumSince(now minus24hours) from the Ambient indoor/outdoor temperature Items.
This is a provider-only migration: preserve these rolling24-hour semantics.
Home and the temperature chart modal obtain current-day extrema independently;
Weather/Earthship secondary displays still consume the rolling24-hour Items.
Exact-name registry search alone does not prove absence of dynamically built
references, so preserve all stable identities and do not rename consumers.

## Remaining attended transfer

Capture a private receipt containing all four original definitions/states,
the writer definition/status, all rule definitions, links and each JDBC mapping,
latest value and historical-prefix fingerprint. Pause only `temp-highlow-24h`
and confirm it is disabled before removing any Item. Recheck configuration drift
after pausing. Never alter JDBC tables or inject telemetry to make recovery pass.

Remove the old provider before installing the exact reviewed file. Require all
four Items to become noneditable, exact metadata/format/group equivalence and
numeric state recovery **with the same temperature unit**, before resuming the
writer. Rehearse file-to-managed-to-file rollback with no duplicate providers.
If any leg fails, restore all original managed definitions and verify recovery;
do not reenable the writer with missing or mismatched resources. Restore its
original enable state, verify a natural scheduled run and unchanged historical
prefixes, other rule definitions and links.

Only then move the draft to canonical `items/`, declare ownership and publish a
completion receipt. No production restart, hardware command, manual rule run,
notification or persistence-strategy change is part of this transfer.
