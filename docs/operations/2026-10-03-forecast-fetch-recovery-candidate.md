# Bounded morning forecast-fetch recovery — source candidate

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
