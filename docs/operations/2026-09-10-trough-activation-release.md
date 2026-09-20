# Attended completed-night scoring release

Status: prepared, not activated. The outcome specification requires an attended
release approval after verification. This document defines the exact production
mutations for that approval; implementation approval is not live qualification.

## Reviewed release boundary

- Solar_PV feature through `814a10a`: migrations 0003/0004, assessment/store,
  worker and exact observational publisher; 523 analytics tests pass.
- Earthship feature through `81f6a03`: capture dependencies already in its base,
  completed-score adapter and retirement of premature legacy scoring;
  795 script tests and 42 subtests pass.
- Real subprocess/disposable PostgreSQL tests prove successful measurement,
  replay uniqueness, exact required reads and denied raw writes. These are not
  production forecast origins or sensor evidence.
- Preserve Task 82 hold, thresholds, DM behavior, controls, BMS counters,
  everyChange persistence, learned parameters and legacy arrays. No new timer,
  full forecast replay, synthetic production origin or test DM is authorized.

## Revalidate and back up before mutation

Require clean intended branches and compare reviewed source hashes again. Verify
the service still executes `/home/sat/openhab/scripts/forecast_intel.py`, its
timer remains 06:40, and installed script hash remains
`6a3d176a9e8e852c8da9890e4c5d8a4731a912124065b8cf8ae7af7f72b23412`.
Verify migrations [1,2] and their checksums, the current Discover bank, unique
`BMS_SOC_Evidence_JSON` mapping (preflight item0613), and absent proposed roles.
Do not adopt an existing role with unknown memberships or privileges.

Create a private timestamped source/service/state backup and an analytics-schema
backup with hash manifest. Restore the database archive into an isolated test
database and verify tables/counts before declaring the backup restore_verified.
Never overwrite forecast state or manufacture decisions from legacy predictions.
Record baseline counts/fingerprints for existing quantitative tables.

## Transaction and installation sequence

1. Record timer active states. Briefly pause the existing forecast-intel,
   forecast-json and energy-* timers during the schema/code transition; wait for
   already active jobs to finish rather than interrupting them. Restore only
   previously active timers, with their original schedules. No manual service
   run is part of activation.
2. With the verified backup gate, apply exactly migrations 0003 and 0004 from
   the pinned Solar branch in the existing transactional migration mechanism.
   Require statement/lock timeouts and checksum readback [1,2,3,4]. The migration
   creates outcome/selection tables and indexes; it does not rewrite telemetry.
3. Merge and push reviewed Solar source to main within the paused interval.
   Old source cannot safely remain scheduled against newer migration versions;
   new source cannot safely run before its pending migrations are applied.
4. Create two fresh login roles with separate generated credentials, no elevated
   attributes, no memberships, and no grant options. Grant CONNECT to this
   database and USAGE on energy_analytics. Exact additional grants:

   | Role | Object | Privileges |
   | --- | --- | --- |
   | advisory_writer | advisory_decisions, advisory_results | SELECT, INSERT |
   | advisory_assessor | advisory_decisions, advisory_results | SELECT |
   | advisory_assessor | advisory_trough_outcomes, advisory_trough_selection | SELECT, INSERT |
   | advisory_assessor | public.items, resolved atomic evidence table | SELECT |

   Qualify advisory tables with energy_analytics. Do not grant raw writes,
   schema creation, ALL TABLES, default future-table privileges, or role
   ownership. Verify effective privileges/read access without inserting test
   production records. Keep credentials out of command arguments, logs and docs.
5. Merge/push reviewed Earthship integration, then install exact source hashes
   for forecast_intel.py, advisory_capture.py, advisory_records.py,
   advisory_windows.py and completed_trough_score.py into the existing script
   directory. Verify imports under `/usr/bin/python3` without invoking main.
   Retain an installed scoring-disabled rollback artifact that never resumes
   premature scoring; restoring the unmodified old script is not safe rollback.
6. Install a private mode-0600 service EnvironmentFile and narrow drop-in with
   `PYTHONPATH=/home/sat/openhab/scripts:/home/sat/Solar_PV/analytics/src`.
   Set both enable flags to 1, both bank IDs to discover_4_module_2026, site
   timezone America/Denver, and a newly recorded UTC assessment cutover instant.
   Use separate explicit loopback DSNs for writer and assessor. The DSNs are
   private configuration, not receipt content. Keep ExecStart/schedule unchanged.
7. Reload the user manager and verify the resolved unit/configuration privately.
   Initialize only Forecast_Trough_Error_7d to UNDEF with authenticated exact
   state PUT and GET readback. This intentionally retires the unverified legacy
   displayed score; no numeric test value or control request is sent.
8. Restore the recorded timers. Read back source hashes, bank/enable/cutover
   settings without secrets, migration checksums, role privileges, timer next
   times and unrelated history fingerprints. Observe the next natural jobs.

The diagnostic publisher uses a five-second socket timeout, not an independent
hard-process deadline. The assessor has its own 40-second hard deadline. Keep
the existing service 180-second deadline and inspect natural runtime duration;
do not expand timeouts or rerun forecasts merely to create a successful receipt.

## Natural qualification, not a synthetic canary

If activated September 10 before the next scheduled forecast, the first natural
origin is September 11 at 06:40. Its trough target is September 11 at 20:00
through September 12 at 11:00 local time. The September 12 06:40 invocation must
not consume it. The September 13 06:40 invocation is the first scheduled scorer
that can qualify that origin. Recompute dates if activation happens later.

Verify immutable decision identity, frozen raw/corrected inputs and accepted
trough-publication result from that natural invocation. Missing capture is an
explicit gap, never a fabricated replacement. After full completion, verify
actual original atomic rows, at least 90% valid coverage, persisted revision,
frozen selected origin, sample count and diagnostic GET readback. A genuinely
insufficient night remains insufficient; do not lower coverage to pass a gate.
Verify natural normal prediction/DM eligibility and deduplication without
sending extra notifications. Retain no causal reward or bandit eligibility.

## Rollback and failure boundaries

Disable capture/assessment first. Restore the reviewed scoring-disabled source
and request diagnostic UNDEF; preserve learned state and all captured outcomes.
Keep migrated schema and compatible Solar source. Do not reverse migrations or
restore an old database archive over accumulated records as routine rollback.
Revoke or disable new roles only after their producers stop. Restore prior
timer states without starting forecast/advisory/notification jobs manually.

If migration fails transactionally, leave prior source/schema matched. If a
later installation step fails, keep affected jobs paused only while completing
a compatible rollback; report any interruption. An ambiguous diagnostic PUT
does not authorize a forecast retry. Record activation/rollback evidence in the
canonical tracker and Hexmem only after actual readback.

Weather/PV/thermal outcome attribution, bandit reward design, broader algorithm
audit and seasonal/data gates remain separate unfinished work after this release.
