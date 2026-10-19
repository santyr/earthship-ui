# Complete old-provider source-retirement proposal

Status: **owner approved; exact 84-path patch applied to source; scoped verification passed; full repository CI pending**.
This complete proposal supersedes the earlier 47-path operator-only request.
It prepares the source removal required by Task 9 of the approved WeatherNext
migration. Installed services and production ownership are outside this patch.

## Exact review artifact

- Base: `6ba1cfcf41d631d07dd769810703cc9fffd803c4`.
- Private patch: `.superpowers/sdd/2026-10-05-weathernext-exclusive-forecast/proposal-complete-provider-retirement-unapplied.patch`.
- SHA256: `9dc8395861ee7284efcfc19f7890c133a182a968d30f6b6990120a2e54177cdb`.
- Size: 659,083 bytes; **84 paths: 74 removals and 10 modifications**.
- [Complete path/preimage/postimage manifest](2026-10-19-complete-provider-retirement-proposal.json).

Every removal has a tracked Git preimage. The operator explicitly approved the
84-path proposal on October 19. Its hash and all preimages were checked before
application on `4cb8a28`; all 74 removals and ten reviewed postimages matched
exactly afterward. Follow-up verification repaired the workflow shell continuation,
normalized two test EOFs and added a shell regression. Three frontend cases for
the now-retired templates were removed; all other deployment/runbook cases remain.
Two dependent daily forecast-worker cases and ten assertions exclusive to retired
service templates were also removed. Eleven native daily sensor-epoch cases and
three opt-in isolated generic systemd cases remain; a new cold-import check ensures
retained temperature tests do not depend on retired workers.
No installed file, model, credential, service, timer, resource safeguard or actuator
changes are included.

## Complete source scope

The original 47-path segment removes eight obsolete provider-specific operator
tools, their eight exclusive test modules and 27 old service/timer/drop-in
repository templates. The eight tools are:

- `scripts/forecast-recovery-files.py`
- `scripts/activate-forecast-recovery.py`
- `scripts/thermal-replay-bundle.py`
- `scripts/qualify-thermal-radiation-runtime.py`
- `scripts/thermal-radiation-files.py`
- `scripts/verify-thermal-natural-publication.py`
- `scripts/qualify-thermal-collector-baseline-bundle.py`
- `scripts/replay-thermal-forcing.py`

That segment also removes the implicit old-provider deployment manifest and
forcing-capture directory creation from `scripts/thermal-model-files.py`, requires
explicit manifests for shared file transactions, and rejects retired deployment
commands. It updates the two affected tests and the Forecast ML workflow.

The complete proposal additionally removes fourteen old forecast/evidence worker
modules and seventeen tests exclusive to those modules. Their exact names are in
the manifest. Six further shared test modules retain their current generic/native
checks while dropping only the old-worker integration cases/imports. The workflow
continues to run surviving checks. The separately committed local-measurement
fixture helper keeps current household/BMS tests independent of retired tests.

## Preserved shared behavior

The shared file-transaction library, its ownership/receipt/compare-and-swap/privacy
guards, and the local energy-quality installer's explicit-manifest path remain.
The library's existing prepare/archive CLI and both model archive entry functions
are preserved. The draft's ASTs match the originals for those entry points and
all 33 functions in their transitive helper closure.

Generic forecast-fetch recovery, solar comparison, thermal archive and archive
preparation tests remain. The manifest lists preserved shared test functions.
No backup/recovery implementation or rehearsal is added. The separate recovery
finishing work stays deferred. No installed recovery capability is removed by
this source-only patch; old source remains available through its Git preimages.

## Approval history

Automatic approval review rejected an earlier broader cleanup before execution:
it removed recovery/replay tools and archive/CLI functions, which the review
considered beyond the instruction to shelve recovery work and a risk to recovery
capability. A separate legacy-worker removal was also refused before execution.
Those refusals were not bypassed. The subsequent explicit approval authorizes
this exact source-retirement scope; the earlier decision blocker is resolved.

This consolidated proposal preserves generic archive/CLI functionality and makes
the entire remaining source scope reviewable together. The operator approved removal of the obsolete provider-specific tools, workers
and exclusive tests from the active branch while retaining their code in Git and
leaving installed services unchanged. This supersedes the narrower 47-path
question and does not approve production cutover.

## Verification and next steps

The proposal builder parsed the virtual surviving Python tree and found no imports
of the fourteen removed workers or seventeen removed test modules. It checked the
workflow's surviving test paths and preserved archive ASTs. Those original checks were static. After application, the same 33 archive helper
ASTs still match their originals, and a fresh tracked-production scan finds no
imports or exact module/file borrowers of the fourteen retired workers.

The applied source passes **285 focused transaction/archive/energy-quality/retirement
tests**, **603 completion tests** (42 skipped), **216 WeatherNext tests**,
and **2,551 frontend tests across 168 files**, plus the UI build. The full surviving
operational suite passes **1,396 tests** with three explicit opt-in skips.

A local full OpenHAB attempt reached 3,000 cases (2,996 passed, three failures, one
skip) before it was deliberately stopped to avoid duplicating a known failed run.
Two failures were obsolete AST assertions reading the retired worker; the third
was a public-lock negative fixture made private by an inherited umask. Only those
two obsolete cases were removed; the lock fixture now sets its intended public
mode explicitly, with the production lock guard unchanged. All **196 tests** in
the affected boundary/lock/isolation modules pass under umask 077. The partial run
is not a full-suite pass; automatic full repository CI remains pending.

An independent source review
of the complete migration and staged patch found no confirmed Critical or Important
defects; it did not run services, cloud requests, fitting or tests. The first broad local attempt was stopped by host
pressure safeguards; an outdated local messaging dependency also required a
separate environment matching the declared test dependencies. No production
resource or interpreter changes were made. Any substantive
change to this proposal requires an updated manifest and review scope. Final source
freeze, fresh model fits, approved qualification gates and coordinated attended
production retirement remain separate required work.
