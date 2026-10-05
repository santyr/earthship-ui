# Battery charging-status Item — isolated file candidate

`BatteryChargingStatus` remains the original managed, unlinked Switch. The
prepared file is **not installed** and no ownership declaration is added.
This continues the approved file-first migration pattern without changing the
display writer, Item name/type/label, charging semantics or persistence.

## Exact scope and live preflight

The candidate declares only:

```text
Switch BatteryChargingStatus "BatteryChargingStatus"
```

The original Item has no tags, groups, metadata or channel links. Its sole
inspected writer is the already file-owned `UpdateBatteryIcon` display rule;
the Home battery-direction display consumes it. The original writer source
matches `/etc/openhab/automation/js/battery-icon.js` exactly, SHA-256
`bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45`,
with sole file ownership and IDLE/NONE status. This preserves its existing
current-based hysteresis; it does not supply source-freshness authority.

Read-only native SQL confirms JDBC identity **154** and **97,347** original
rows at the fixed preflight cutoff. A recoverable ordered CSV/gzip prefix and
exact original Item/writer descriptors are retained privately. These are
preparation evidence; a later transfer must take a fresh guarded backup and
compare the fixed prefix rather than expecting unchanged total row counts.

The October 5 18:26Z live inventory has zero structural issues. Of its 17
unlinked/ungrouped/literal-unmentioned review candidates, 16 belong to Goat and
remain outside this task. The literal census is a review prompt, not a proof
that dynamic/external consumers are absent or permission for a bulk transfer.

## Qualification

`scripts/qualify-battery-charging-status-provider.py` reuses the existing
OpenHAB 5.2.1 networkless provider harness with exactly this Item and Switch
type. It passed exact descriptor/state-description comparison, sole file
ownership and unchanged source bytes. Fresh first-boot state is NULL, correctly
distinguished from JDBC restoration. Its owned container/tmpfs were removed.

`scripts/qualify-battery-charging-status-jdbc.py` reuses the existing disposable
OpenHAB/PostgreSQL harness. Separate ON and OFF rehearsals both passed:

- Original Switch state persisted through the unchanged file JDBC strategy.
- File withdrawal and original managed restoration, with exact history prefix.
- Managed withdrawal and forward file transfer, with state/history restoration.
- Hot file loading and full-JVM restart, with state and original history intact.
- Owned OpenHAB/PostgreSQL cleanup and zero production writes.

Neither exercise contains the production charging writer, channel links or hardware.
Synthetic values are confined to disposable isolation.

Independent review of commit `0c7d121` against `d0dbf0d` is clear of
Important/Critical findings. It confirms the exact Switch descriptor, absent
production target, unchanged ownership manifest, isolated ON/OFF transport,
native recovery/cleanup logs and all 15 retained capsule hashes. The recovered
original compressed history contains exactly 97,347 rows.

Reproduction:

```bash
python3 scripts/qualify-battery-charging-status-provider.py
python3 scripts/qualify-battery-charging-status-jdbc.py --state ON
python3 scripts/qualify-battery-charging-status-jdbc.py --state OFF
```

Candidate source SHA-256:
`546d5498d3392b6ea041850d7a869783b7a3f29a56a49e5cfdbdb97a6200802a`.
Private mode-0700 capsule:
`/home/sat/.local/state/openhab-config-migration/battery-charging-status-candidate-20261005-t3wlwuh_/`.
Mode-0600 native history, preimages, source, qualifier pins, logs and manifest
are retained. Original CSV/history identities are never committed to Git.

## Remaining live gates

Isolated qualification and independent review are complete. Prepare the closed,
exact one-Item attended transport and its recovery path. Revalidate
the existing writer, target absence, current provider/descriptor, original
history and protected definitions/PID at the actual handoff boundary. Pause
only this display writer if needed; preserve its original enabled state and
never stop the forecast publisher or another owner. Perform an actual original
managed rollback before final file ownership and verify a natural writer/JDBC
receipt. Never restore through synthetic production Item updates.

The already approved production restart remains blocked by host
authentication. This candidate is staged while that qualification is pending;
its isolated restart does not close the household restart gate. No production
service, rule, Item, link, control or notification changed in this preparation.
