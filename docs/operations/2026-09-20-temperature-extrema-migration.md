# Temperature extrema Item migration

## Verified provider transfer, September20 at17:23 MDT

The four Items below are now file-owned. Canonical source is
`openhab/file-config/items/temperature-extrema.items`, installed at the matching
`/etc/openhab/items/temperature-extrema.items` destination and declared in
`ownership.json`. Both SHA256 values are
`9d732df108e6bf5bf8a5f6c483e6af97390e99658c2e420231451afe226ba3e3`.

The attended transfer restored all four numeric values in Fahrenheit before
reenabling their writer. Actual file-to-managed-to-file rollback restored the
same states on both legs. JDBC mappings and historical prefix counts, maximum
timestamps and ordered time/value fingerprints remained unchanged. All rule
definitions and links matched their before snapshots. Live REST confirms exact
labels, groups, tags, generated metadata, format and `editable:false`; the writer
returned IDLE/NONE. Registry inventory reports422managed plus7file Items with no
ownership issues. OpenHAB remains active with original MainPID4060018.
Natural quarter-hour execution at17:30:00.025/.032 MDT successfully published
both indoor and outdoor extrema with no manual run. Post-run values remain
60.8/78.98°F indoors and38.3/80.42°F outdoors. The bounded read-only log monitor
exited after both expected messages; no watcher remains running.

Private receipt: `/tmp/temperature-extrema-transfer-9k7w12zt/` (0700), containing
before/paused snapshots and successful verification. This local receipt is not
an off-host backup. No hardware command, manual calculation trigger, telemetry
injection, history change, persistence-policy edit or production restart occurred.

An earlier attempt read metadata before the provider settled, rejected it and
restored all original managed definitions and Fahrenheit states; the writer was
reenabled. The bounded verifier now allows settling but never accepts mismatched
metadata or units. Eleven migration guard tests pass, including transient
metadata and wrong-unit rejection; eleven closed-renderer tests also pass.
The superseded failed-attempt receipt was removed after verifying its successful
recovery and the retained successful transfer receipt; no useful rollback
material from the successful transfer was deleted.

The following sections retain the reviewed preflight and transfer requirements.

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

## Reviewed transfer procedure

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
