# Attended Moon display Item/link handoff

Status: **release gate off; exact-plan approval and attended execution pending**.
The prepared adapter is `scripts/migrate-moon-phase-readings.py`. Its `--check`
path is read-only, while `--apply` refuses before database/REST access unless
the one-shot `RELEASE_READY` gate is deliberately opened for this plan.

## Exact scope

Transfer only `Moon_MoonPhaseName` (JDBC Item 59) and
`Moon_MoonIllumination` (JDBC Item 41), plus their two existing Astro links, to
`/etc/openhab/items/moon-phase-readings.items`. The canonical source SHA-256 is
`fc96f70a65e8de45479cda6b8c2c97840ae78eaedc5334111036013143e3941e`.
Keep the Moon Group, Astro Thing, read-only phase options, Point semantics,
fractional unit `one`, and exact legacy link profiles unchanged.

No OpenHAB restart, Thing configuration change, command to any Item, synthetic
state update, SQL write, privilege change, model/collector activation or DM.
The Moon label may temporarily disappear while providers are withdrawn.
Do not substitute another resource, shared source file or channel.

## Qualification and fresh preflight

The [candidate receipt](2026-09-30-moon-phase-readings-candidate.md) records
actual isolated file loading, restart, managed rollback and JDBC state/history
recovery, including the corrected version-matched Astro fixture. Seventy-one
focused/adjacent tests pass for the adapter and existing provider/JDBC paths.
Fault tests cover partial link/Item withdrawal, failed file readback, unknown
target preservation, protected-definition drift and overlapping execution.
They are real filesystem/state-machine tests with REST/PostgreSQL doubles,
not proof of the still-unperformed production rollback.

The actual read-only check passes with 998 phase and 136,382 illumination rows
under identities 59 and 41. Those counts are a checkpoint, not fixed release
requirements: natural illumination updates may add rows. Exact prior history
must remain intact and live state must match current JDBC, not an old held
planning snapshot. Re-run immediately before the attended apply:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/migrate-moon-phase-readings.py --check
```

## Ordered attended transaction

1. Acquire the private process-owned resource lock. Refuse another active
   handoff; an existing empty lock file does not imply a live process.
2. Check the exact source, absent file target, managed definitions/profiles,
   units/state descriptions, online Astro channels and healthy protected rules.
   Capture immutable definitions of the Moon Group/Thing and five protected
   rules as a digest; raw private configuration stays out of diagnostics.
3. Privately retain managed Item/link DTOs, exact current JDBC prefix snapshots,
   streaming CSV history copies and JSONDB recovery preimages under a new
   `~/.local/state/openhab-config-migration/moon-readings-<UTC timestamp>`
   directory (0700; files 0600). Verify copied histories before withdrawal.
   JSONDB copies are recovery preimages, not an atomic whole-install backup;
   never write JSONDB behind the running registry.
4. Recheck definitions/state/history/protected digests. Withdraw just the two
   managed links, then Items, and verify their absence.
5. Publish the complete pinned file atomically using exclusive creation. An
   existing target or symlink is never overwritten. Verify sole file ownership,
   exact definitions/links, current natural/restored state and unchanged prior
   JDBC prefix.
6. Exercise the actual managed rollback, retaining the withdrawn source privately.
   Verify original definitions/links/state/history and protected digests. Then
   repeat the guarded transfer back to the file provider and verify again.
7. Re-close the one-shot apply gate. Independently verify source bytes, private
   backup permissions/history copies, sole provider, history identities/prefix,
   parent/Thing/protected-rule definitions and active OpenHAB. Only then add exact
   **provisional** ownership declarations for the two Items and links.
8. Qualify a later natural Astro update from logs/state/JDBC as appropriate.
   A phase held unchanged for days is not stale; do not fabricate a phase change
   to produce an everyChange row. Preserve the backup until restart recovery is
   separately qualified. Production restart qualification is not included.

## Failure and recovery boundary

After any withdrawal, the adapter attempts exact managed Item/link restoration
and verifies recovered state and the original JDBC prefix. It never repairs or
rewrites history. If the target/source/provider has changed unexpectedly, it
refuses to overwrite or delete unknown data and requires attended manual review.
Retain the private receipt; do not report success from a partial rollback or
delete backups to make a failure look clean. No general protected-control
restart authority follows from this display-only plan.
