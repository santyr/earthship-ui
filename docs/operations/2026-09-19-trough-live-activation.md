# Completed-night capture and assessment: live activation

Operator approval: all pending work and live learning preapproved. Existing
held/deferred tasks, control authority, thresholds and notification policy remain
unchanged. This receipt supersedes the staged status in the September10 release
plan and September19 preflight; it does not claim natural outcome qualification.

## Installed release

Assessment cutover: **2026-09-20T00:48:40+00:00** (September19,18:48:40MDT).
Existing `forecast-intel.service` still executes the same script path at06:40
daily, with its180-second limit. Capture and assessment are both enabled through
owned0600 `/home/sat/.config/hex/advisory-outcomes.env` and the narrow
`advisory-outcomes.conf` service drop-in (0644). PYTHONPATH includes the installed
helpers and Solar analytics source. Bank is discover_4_module_2026; timezone is
America/Denver. Credentials are never in this repository or command arguments.

Installed forecast SHA256:
`7d14bbef3982ea33faf58b4b2dc2cbca182144af105f868d818e6f719d174cd7`.
Installed capture/record/window/completed-score helpers all match repository
source. Imports under /usr/bin/python3 passed without running main.
Solar main advanced from008f856 to tested compatible9ab7461.

The preexisting qualified-hourly scorer and runtime wrapper were preserved.
Its separate environment/cutover2026-09-20T00:30:09Z remain resolved by systemd.
No temperature collector restart or persistence-policy change was needed.

## Migration, grants and scheduling

The verified16-table backup and isolated3/4migration rehearsal were checked
before production mutation. Eight existing timers were briefly paused, with
their active states saved; associated jobs were checked terminal rather than
interrupted. Exactly migrations3/4 were applied through the existing transaction
helper, with20-second statement and2-second lock bounds. Ledger/checksums1–4
and no pending migration were verified against compatible Solar source.

Created only two previously absent roles, each with generated independent
credentials, no elevated attributes, no membership or schema-creation authority:

| Role | Effective table grants |
| --- | --- |
| advisory_writer | SELECT, INSERT on advisory_decisions and advisory_results |
| advisory_assessor | SELECT on decisions/results, public.items and public.item0613; SELECT, INSERT on advisory_trough_outcomes and advisory_trough_selection |

Advisory tables are in energy_analytics. Neither role has raw-history writes,
UPDATE/DELETE/TRUNCATE, grant options, or future-table grants. Config validation,
actual read access and effective table permissions were verified. The initial
post-creation verifier stopped with InsufficientPrivilege while resolving an
unrelated schema's table by name. No grants were broadened: verification was
corrected to inspect catalog object IDs and then passed against both roles.
Role creation was not replayed. The create-only provisioning tool now preserves
that distinction and has seven collision/preflight refusal tests.

The only OpenHAB write was an exact state PUT of Forecast_Trough_Error_7d to
UNDEF, confirmed by GET, retiring its premature legacy score. No numeric canary,
control command, rule runnow, forecast replay, test DM or synthetic origin was
used. Capture does not assert delivery/compliance; outcome rewards remain
observational and explicitly bandit-ineligible.

All eight timer active states were restored with original schedules/units.
Normal systemd random delay may produce different next-trigger seconds; no timer
definition was edited. The naturally scheduled18:50:14MDT energy-ui publication
exited0 and published its normal1706-byte observational payload. No service was
manually started. New forecast capture has not yet run naturally.

## Preservation and verification

All15pre-existing data-table fingerprints matched the frozen pre-release
snapshot, including363,630forecast snapshot rows. Migration ledger was the only
pre-existing table intentionally changed. Learned state hash matched its private
backup. Decisions, results, outcomes and selections were all empty after release.

- Reconciled and deployed Earthship suite:1014passed,42subtests,1expected
  disposable-PostgreSQL skip,139.25seconds. That database test was separately
  qualified before this release; the full backup/migration rehearsal also passed.
- Deployed Solar main:523passed,19.12seconds.
- Focused forecast/adapter/hourly suite:153passed.
- New role-provisioning refusal tests:7passed separately after the full run.

Private source/unit/model/timer-state backup:
`/tmp/trough-live-release-k9o5vg_a` (0700).
Verified analytics archive/manifest:
`/tmp/trough-activation-backup-x4d0_p5m` (0700 directory,0600 files).
These are same-host recovery artifacts, not offhost disaster recovery.

## Rollback and next natural evidence

Prepared `forecast_intel.scoring-disabled.py` in the private release backup has
SHA256`08f540e5bbabc718b4ffb20526eee2bb7697795780aa2530eb4d11eff32e6485`.
It hard-disables only advisory capture/assessment at process entry, retains
qualified hourly learning and morning forecast behavior, and never restores the
premature legacy trough scorer. Pause only affected forecast jobs before an
attended rollback; preserve captured records/model state, migrated schema and
compatible Solar source. Restore prior timer states afterward. Do not roll an
old database archive over subsequently accumulated evidence.

Expected first natural origin: September20 at06:40MDT. Its target is
September20 20:00–September21 11:00 local. September21 06:40 must NOT score that
incomplete window; September22 06:40 is the first normal scorer able to qualify
it. Actual capture, accepted trough publication, original atomic SoC rows,
90percent coverage, frozen origin and persisted revision must all be verified.
Missing or insufficient evidence remains explicit; no lowering the coverage gate.

The pump rule was not edited. Its concurrent15-minute configuration and hash
e28f2616dcd830cd41bf7433f4f0ee6e36de7d6e32d2a3d00c5a6913eec8b375
remain intact. A natural South start at18:53:03.334MDT was observed; a bounded
read-only monitor is checking completion separately. This release does not
claim a completed pump cycle, thermal outcome attribution, conformal intervals,
threshold tuning, or completion of the broader algorithm audit.
