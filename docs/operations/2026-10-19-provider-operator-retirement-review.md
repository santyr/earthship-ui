# Complete old-provider source-retirement proposal

Status: **unapplied; owner decision pending following automatic approval rejection**.
This complete proposal supersedes the earlier 47-path operator-only request.
It prepares the source removal required by Task 9 of the approved WeatherNext
migration. Installed services and production ownership are outside this patch.

## Exact review artifact

- Base: `6ba1cfcf41d631d07dd769810703cc9fffd803c4`.
- Private patch: `.superpowers/sdd/2026-10-05-weathernext-exclusive-forecast/proposal-complete-provider-retirement-unapplied.patch`.
- SHA256: `9dc8395861ee7284efcfc19f7890c133a182a968d30f6b6990120a2e54177cdb`.
- Size: 659,083 bytes; **84 paths: 74 removals and 10 modifications**.
- [Complete path/preimage/postimage manifest](2026-10-19-complete-provider-retirement-proposal.json).

Every removal has a tracked Git preimage. `git apply --check` passes against the
current branch; the exact patch passes Gitleaks. Neither the patch nor its
proposed implementation has been applied or executed. No installed file, model,
credential, service, timer, resource safeguard or actuator changes are included.

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

## Why an owner decision is still needed

Automatic approval review rejected an earlier broader cleanup before execution:
it removed recovery/replay tools and archive/CLI functions, which the review
considered beyond the instruction to shelve recovery work and a risk to recovery
capability. A separate legacy-worker removal was also refused before execution.
Those refusals were not bypassed and no protected removal has occurred.

This consolidated proposal preserves generic archive/CLI functionality and makes
the entire remaining source scope reviewable together. The specific owner decision
is whether the obsolete provider-specific tools, workers and exclusive tests may
be removed from the active branch as migration work, while retaining their code
in Git and leaving installed services unchanged. This replaces the narrower
47-path question; it is not a production-cutover approval.

## Verification and next steps

The proposal builder parsed the virtual surviving Python tree and found no imports
of the fourteen removed workers or seventeen removed test modules. It checked the
workflow's surviving test paths and preserved archive ASTs. These are static draft
checks, **not an applied implementation test result**.

After approval, apply the exact patch and run shared file transactions, local
energy quality, archive/prepare CLI, retained shared tests, retirement/native
checks, WeatherNext tests and the full required CI/test/build scope. Any substantive
change to this proposal requires an updated manifest and review scope. Final source
freeze, fresh model fits, approved qualification gates and coordinated attended
production retirement remain separate required work.
