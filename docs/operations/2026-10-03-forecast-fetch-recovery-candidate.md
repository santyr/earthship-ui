# Bounded morning forecast-fetch recovery — source candidate

## October 3 natural morning publication verified

The original scheduled worker ran 06:40:56–06:40:59 MDT and exited zero;
the helper has never run in production. Restricted read-only checks at
`2026-10-03T13:06:52.482946Z` verify exactly one original morning receipt,
matching persisted public values, private issue components and atomic native
SoC source. The weather issue is `12:40:58.396244Z`; the separately preserved
SoC assessment is `12:40:58.411Z`, at 87%. Neither clock is substituted for
the other. The raw weather archive completed at `12:40:58.391135Z`, before
the issue, and its exact digest matches the public/private references:
`e32239c47921c3a7285b4768be06116dba0b628474d2721c5d6c1d1fc6e786ea`.

The receipt persisted at `12:40:58.553Z`: PV 7.13 kWh, morning trough 69%,
diagnostic dusk estimate 95.010%. These remain unscored predictions, not
actual charge or overnight outcomes. Learned state naturally advanced to SHA
`e60f26adb4ff14d2cb3a5994c13576cbbf5acb60705009ef881151f4c9c73fc7`;
the failure marker is absent and October 2 has not been backfilled.

The scheduled 06:45 snapshot job also exited zero. All **1,458** normalized
facts exactly match the original detailed forecast by issue, target, metric,
value, unit and provenance, with no duplicates/missing/extra rows. The detail
issued at `06:40:56-06:00`, persisted at `12:40:58.584Z`, and has UTF-8 SHA
`14903e72a8d5e23eea8a57b8dccb0e9e83b72f42e4056cabb9b99beaca460775`.
Its analytics capture is `12:45:56.964878Z`, not retroactively available at
the earlier producer issue. Verification wrote no SQL/Item/state or controls.
This closes normal post-install issue/source/snapshot continuity, **not** a
natural failed-fetch recovery event or forecast accuracy/calibration release.

## Cause and scope

October 2's DNS outage prevented the original 06:40 forecast-intelligence issue.
The subsequent recovery restarted the weather JSON and thermal shadow jobs,
not `forecast-intel.service`. There is therefore no original October 2 morning
charge/PV issue to score or reconstruct as if it existed.

The new candidate retains the normal 06:40 schedule and original service plus
its four existing policy drop-ins. It records typed weather-fetch failure
metadata, without storing exception messages or URLs. Existing daily/hourly
consumption markers are saved before the fetch; retrying does not reset those
learning markers. A successful fetch clears recovery authority before later
publication stages. This is not a general partial-publication repair.

An `OnFailure` timer waits 15 minutes, then a separate bounded helper may request
the **original** service. Eligibility requires all of:

- Current Mountain day, 06:40 inclusive through 09:00 exclusive.
- No prediction record already present for that day.
- A typed, current weather-fetch failure less than 30 minutes old, identified
  as DNS, timeout or HTTP 5xx; no unknown errors or HTTP 4xx.
- The same failed systemd invocation, rechecked before requesting a start.
- Fewer than eight fetch failures that day, with state/time checked again.

The reader accepts existing group-write permissions only when the owning
primary group contains exclusively the owner and has no access ACL. Shared
groups, world writes, symlinks, hardlinks, oversized/changing state, duplicate
JSON keys and nonfinite constants refuse. No live permissions were changed.

## Qualification — October 3, 08:48Z

All **158** focused recovery and existing forecast-intelligence tests passed.
Installed `systemd-analyze --user verify` accepted the candidate units. An actual
isolated user-systemd fixture used the candidate implementation, a synthetic
morning clock and an owned temporary state directory. Its source callback
raised two simulated DNS failures, then returned a fixture-only result:

1. First real failed invocation authorized exactly one fixture-service retry.
2. The timer rearmed after the second failed invocation and authorized another.
3. Attempt three succeeded; the failure marker disappeared and its fixture
   prediction was retained. Both retry helpers and the timer became inactive.

Only the fixture used a process-local release override and two-second delay.
It had no production fetch, Item, credential, DM or household-control callback.
The production candidate remains default-off and retains its 15-minute delay.
The three exact temporary unit files and owned test directories were removed;
systemd subsequently reported all three fixture units not-found/inactive.

The actual production-state **read-only** check reported `eligible=false`,
`release_ready=false`, `start_requested=false`. This is a valid negative check,
not proof of a successful live recovery. OpenHAB remained active, PID 1696.

## Initial source checkpoint

No production script, unit, timer, state or source release flag was changed.
Candidate forecast SHA-256:
`1b902853bc155b404bc18dc352545ea214632de4053ff295f8683e31574c5d1b`.
Recovery helper SHA-256:
`5006637dee86001e4d5c484ad9573f155bcde3a86855b4c7d62385363d84c82c`.
Installed forecast still has SHA-256:
`943c09d414c6265d5a9527bb1901c3e8aa7355fc190f261a61cf58d02fbed58e`.

Next: qualify exact installed-source/unit handoff and interrupted rollback with
the current policy drop-ins preserved, then deploy reversibly and observe the
next natural original issue. Rebuild supporting-Energy source/consumer pins if
this forecast source changes. Do not run an early issue, backfill October 2,
change prediction coefficients, activate notifications or label a fixture as
live forecast evidence to close this gate.

## October 3, 09:05Z — disabled production handoff and rollback passed

The subsequent `scripts/forecast-recovery-files.py` adapter uses the existing
secure file engine for the exact two code files and three user unit files.
It requires idle forecast/JSON jobs, unchanged original policies, active original
timers and a 120-second clear timer window. It never starts jobs, enables timers
or overrides the recovery release flag. Private original policy archives and
the exact old script/absent-target preimages precede installation. Changed
sources, policies, modes, archives, targets or effective unit commands refuse.

All **260** recovery/forecast/adapter/file-engine tests pass without skips.
An added effective-unit test initially had a mock argument mismatch; that was
corrected and all positive/negative cases rerun. The actual prepared bundle
passed original/candidate/restored systemd parsing and interrupted code/unit
replacement recovery in temporary targets. Those targets were removed.
The real production sequence then passed:

`disabled install -> exact original rollback -> disabled reinstall`

Readback verifies the original service FragmentPath, effective command and
four original policy drop-ins, plus only the new failure-target drop-in.
Rollback restored original forecast SHA `943c09d4...`, removed both recovery
units/helper and cleared `OnFailure`. Reinstallation matches both candidate
code hashes above. Recovery service/timer are inactive/static, not enabled at
startup. Both original forecast timers remain active; the daily job is still
scheduled for 06:40 MDT. Forecast state stayed byte-identical throughout:
`26987242320a094645ea8c06e223e3d7405aea5a9558aada842777e28d94c23f`.
The installed helper check reports eligibility, release and start all false.
No forecast job, DM, Item write, training or OpenHAB restart was performed.
OpenHAB remains active at PID 1696.

Retained private receipt:
`/home/sat/.local/state/forecast-intel/deploy-receipts/fetch-20261003T090000Z-bd0c92ae`.
Qualification SHA-256:
`3967ea4affe575e4a1bd00f79a47f8ee4cda7740a971ac3d549e8da6c6513fd1`.
Adapter SHA-256:
`6a78b1217fdb7e054a9503f93e77c721c1d01d05f1b826d700ec2c1f2fc3726f`.

This closes actual file/service-manager handoff and rollback, **not** automatic
recovery activation or a natural new forecast issue. Next: bounded release-gate
activation with the policy unchanged, then natural 06:40 publication/state
verification. No further rehearsal of this unchanged bundle is required.
The supporting-Energy prepared receipt correctly refuses its now-changed
canonical input pins; prepare/rehearse a new receipt once its separate
qualification decision is resolved.

## October 3, 09:19Z — bounded recovery activated

Recovery now requires the exact dedicated setting
`EARTHSHIP_FORECAST_FETCH_RECOVERY_ENABLE=1`. It defaults off outside that
service. The qualified `enabled.conf` drop-in supplies only this setting;
the original forecasting job and its learning/data-source settings are not
overridden. The morning window, 15-minute delay, eight-failure limit, current
failed-invocation binding and duplicate-issue refusal are unchanged.

All **278** recovery/forecast/transaction/activation tests pass. New tests cover
exact setting syntax, configuration/backup/source drift, corrupt receipts,
failed readback rollback and later operator-owned edits. Testing caught a
partial-upgrade edge case when an unowned opt-in appeared between prepare and
apply; both original targets are now checked before either phase changes them.
The existing staging adapter also retains explicit support for the previous
closed-generation source pins and private receipts.

The receipt-bound `scripts/activate-forecast-recovery.py` changed only the helper
and new opt-in drop-in, then reloaded the user service manager. Effective
FragmentPath, argv, drop-ins and Environment match exactly. No job or timer was
started/enabled, and no DNS fault or production state was fabricated. A separate
collected, read-only user-systemd check using that setting returned:

```json
{"eligible": false, "release_ready": true, "start_requested": false}
```

The probe is now not-found/inactive. Original daily/JSON timers are active,
recovery units remain inactive/static until an eligible failure, and OpenHAB
remains active at PID 1696. Learned forecast state still has the original
`26987242...` hash above. This verifies activation, not a natural recovery
event or a new prediction. Next is the normal October 3 06:40 MDT original
issue and publication; no early run/backfill or additional unchanged-file
rehearsal is needed.

Private activation receipt:
`/home/sat/.local/state/forecast-intel/deploy-receipts/fetch-20261003T091900Z-fce14280`.
Its qualification SHA-256 is
`7070b852944bc56fd31333dc9077309bcc8b595dacfa44b816ab87724034e9ad`.
Activated helper SHA-256:
`efcaa18f39fcd7c08619f7507ad8c310ad604ce1148e1e9b370017b4f6ba0f33`.
Opt-in SHA-256:
`8e98cdb91652d8fd9c9af0c180f7d4718fbb41774e510c96d7eb164e010629fe`.
Activation adapter SHA-256:
`0c3405aefdde0e939f83689b86b2c2099da1ccf60bd20802e147e91e39549d6e`.

To restore only the activation, during the same idle/clear timer posture:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/activate-forecast-recovery.py restore \
  --allow-apply \
  --receipt /home/sat/.local/state/forecast-intel/deploy-receipts/fetch-20261003T091900Z-fce14280
```

It restores the exact prior helper and absent opt-in, reloads and verifies the
closed gate; it refuses later operator edits. Restore activation **before** any
separate rollback of the parent instrumentation bundle. Both private recovery
points are intentionally retained; task-owned test/probe resources are removed.
