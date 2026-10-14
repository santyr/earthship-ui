# Retained scorer failure diagnostics

Scheduled legacy and historical scoring failed with only `score_withheld`, while
current-model scoring could complete. The previous log did not establish whether
resource admission, unavailable inputs, or another validation caused the failure.

The score coordinator now reports a fixed, bounded reason category. Raw exception
messages, paths, connection details and traceback text are never added to its
failure output. Unknown validation errors remain `validation_refused`.

Retained legacy and native scorers execute their original `run()` function from
the pinned source archive. The current wrapper formats their failures. Python's
`-P` option and explicit archived PYTHONPATH prevent current dependencies from
replacing archived dependencies. The wrapper checks the deployment digest, source
digest, dependency context and unchanged source/manifest around execution.
Original model validation, resource guards, scoring and report writes remain in
the retained function. Busy responses still return status 75.

Validation: 39 focused tests passed in 1.89 seconds, covering current CLI reason
categories, private-error suppression, original legacy/native function arguments,
source and manifest drift, dependency separation in a real Python child, and both
legacy and native dispatch commands. An existing deadline regression now derives
its expiration from the deployed 120-second constant instead of assuming 50 seconds.

Deployment completed on 2026-10-14. Source `d702d47` is selected through
`fd2aed248b91f97ec2770ac6adf42d0eb1676a8e00d4348f86e6f14e0c96a4e7`.
Model artifact `52dd5d122485f0bdafa0aed4fa7412c0823ce9829ed3d9bdc920e44d88526506`
and the training cutoff of 2026-10-14T06:00:00Z are unchanged. Packaging took
5.5 seconds; activation took 55.7 seconds with 55,746,560 bytes peak memory and
zero memory-limit/OOM events. No fit, qualification probe or actuator command ran.

Independent 20:04:36 UTC readback verified all five owned files, three effective
service deployment pins and resource caps, all three active timers, and HTTP 200
from the UI and both thermal publications. The clean daily production checkout
was advanced to the same source while its worker was idle. Existing schedules
and resource policy remain unchanged.

The next scheduled failure reason is pending. This change does not yet establish
the cause of historical failures or forecast accuracy.


The first scheduled legacy run at 20:06 UTC returned `unexpected_failure`.
Inspection found that the retained v1 `_bytes(path, *, private=False)` helper
predates the `maximum` keyword. A regression reproduced the exact TypeError.
The wrapper now calls the common helper signature and separately enforces the
128 KiB manifest bound. All 40 focused cases pass after the correction.
The initial handoff also left the new geometry directory empty until its next
scheduled preparation; the 20:05 forecast was withheld. Subsequent corrective
handoffs should finish before a normal preparation opportunity.
