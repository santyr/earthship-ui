# Proposed retirement of old provider operator tools

Status: **unapplied; explicit owner decision required after automatic approval rejection**.

This is source preparation for the approved WeatherNext-only migration. It does
not stop, restart or alter installed services, remove installed files, modify
credentials, activate a model, change resource safeguards or authorize actuators.
Production remains unchanged.

The proposed patch is private in the existing execution directory:
`.superpowers/sdd/2026-10-05-weathernext-exclusive-forecast/proposal-provider-operators-unapplied.patch`.
It applies cleanly to base `6c04131eb18220513f25ac0b8c1d36e1d28a8dc8` with `git apply --check`.
Patch SHA256: `08dd03f5035a9c13b40f321dcd02d5adf0efe3271400a15b64154f66095a241f`.

## Concrete scope

Remove eight old-provider operator tools and their eight exclusive test modules:

- `scripts/forecast-recovery-files.py`
- `scripts/activate-forecast-recovery.py`
- `scripts/thermal-replay-bundle.py`
- `scripts/qualify-thermal-radiation-runtime.py`
- `scripts/thermal-radiation-files.py`
- `scripts/verify-thermal-natural-publication.py`
- `scripts/qualify-thermal-collector-baseline-bundle.py`
- `scripts/replay-thermal-forcing.py`

Remove 27 repository service/timer/drop-in templates for the old forecast and
thermal weather workers. Installed definitions remain untouched:

- `deploy/forecast-intel.timer`
- `deploy/forecast-intel.service`
- `deploy/forecast-pre-dusk.timer`
- `deploy/thermal-model-shadow.service`
- `deploy/forecast-json.timer`
- `deploy/forecast-intel-fetch-recovery.service`
- `deploy/thermal-model-train.service`
- `deploy/thermal-model-train.timer`
- `deploy/forecast-intel-fetch-recovery.timer`
- `deploy/thermal-model-shadow.timer`
- `deploy/forecast-json.service`
- `deploy/forecast-pre-dusk.service`
- `deploy/forecast-intel.service.d/fetch-recovery.conf`
- `deploy/thermal-model-shadow.service.d/bounded-retry.conf`
- `deploy/thermal-model-shadow.service.d/qualified-radiation.conf`
- `deploy/thermal-model-shadow.service.d/forcing-capture.conf`
- `deploy/forecast-intel-fetch-recovery.service.d/enabled.conf`
- `openhab/systemd/user/forecast-temperature-score.service`
- `openhab/systemd/user/forecast-temperature-score.timer`
- `openhab/systemd/user/forecast-pre-dusk.timer`
- `openhab/systemd/user/forecast-pre-dusk.service`
- `openhab/systemd/user/forecast-pre-dusk.service.d/zzz-bounded-native-inputs.conf`
- `openhab/systemd/user/thermal-model-train.service.d/resource-limits.conf`
- `openhab/systemd/user/thermal-model-train.service.d/memory-preflight.conf`
- `openhab/systemd/user/thermal-model-train.service.d/memory-preflight.awk`
- `openhab/systemd/user/forecast-intel.service.d/qualified-soc.conf`
- `openhab/systemd/user/thermal-model-shadow.service.d/zzzz-legacy-origin-observer.conf`

Modify the shared `scripts/thermal-model-files.py` library to require explicit
manifests for file transactions, remove its built-in forecast deployment manifest
and implicit forcing-capture directory creation, and reject the retired provider
deployment commands. Preserve its existing prepare/archive CLI and every model
archive function unchanged. Preserve file ownership, receipt, transaction,
compare-and-swap and privacy guards. The local energy-quality installer already
supplies an explicit manifest and remains a caller.

Update retirement tests and the Forecast ML workflow; remove only the two generic
test cases specific to the removed built-in forecast manifest. Shared transaction
and model archive tests remain. No new backup/recovery implementation is proposed.

The patch changes 47 paths: 43 removals and four modifications. Every preimage is
tracked in the base commit and remains recoverable from Git; no source deletion
has been applied. The separately identified fourteen old worker/evidence modules
are outside this patch and remain present pending dependency closure and removal.

## Approval boundary and verification

Automatic approval review rejected the original broader cleanup because it
removed recovery/replay tools and archive/CLI functions, which it considered
beyond the earlier instruction to shelve recovery work and a risk to recovery
capability. That rejection occurred before execution; no cleanup was performed.

This narrower unapplied patch preserves all model archive functions and its
prepare/archive CLI. The remaining decision is whether obsolete provider-specific
recovery, replay, qualification and installation tools may leave the active
project as part of retiring Open-Meteo, with their exact code retained in Git.

Read-only checks prove patch applicability, tracked preimages and unchanged
archive-function ASTs in the draft. New retirement checks were observed failing
against the still-present operator tools/templates; they are included in the
unapplied patch. The proposed implementation has not been executed or tested.
After approval, apply it and run the complete shared transaction, local energy
quality, retirement/native and WeatherNext package checks before publishing code.
Final fresh model fitting, all approved qualification gates and attended live
cutover remain required afterward.
