# Deployed source reconciliation — 2026-10-29

This publication reconciles the verified running components with remote main.
It does not activate the integration checkout or replace selected model artifacts.

| Component | Verified source authority | Integration |
|---|---|---|
| Native forecasts and retained replay | `39b0070`, included through suggestion parent `0b52dc1` | Original branch history merged |
| Five-minute suggestion transport and stale presentation | `0b52dc1`; immutable `ui-release-suggestions-20261029-a03` | Original commit merged; exact deployed UI source retained |
| Sensitivity segmented-temperature reader | `0075a1d` | Original branch history merged |
| Date/time, two energy rows, forecast readability and OpenHAB consumers | Active immutable UI release | Component source and maintained tests integrated |
| Private sensor qualification component | `9060ef3` | Exact component files integrated without unrelated historical whole-tree differences |
| OpenHAB temperature polling and Bedroom identity/location | Reviewed installed source manifests and current provider files | Exact deployed provider and location records integrated |
| RTL-SDR decoder compatibility | Active 25.02 `8e813` release with current librtlsdr | Installed selector and dependency/rollback documentation included; binary remains an external dependency |
| Current forecast analytics and live health | `analytics-reader-release-2fd49d818476` | Companion `santyr/Solar_PV` main publication |
| Project workflow | OpenSpec 1.15.0 integration | Project instructions, six generated OpenSpec skills, changes and evidence included |

UI packaging contains historical Python context. That context was not copied over
the separately selected native numerical source. The remote-main component-PV
measurement-cohort identity correction is preserved. Current planning keeps human
advice separate and automatic actuation disabled; historical receipts continue to
use their original legacy producers. Merge regression tests cover current planner
refusal and original policy-fact expiry as well as historical replay.

The current UI source matches the running release, including the 64px second-row
time to the left of energy, Today on a separate energy row, first-row date,
immediate advice publication notifications, a five-minute fallback and visible
original evaluation age/stale status. Sensor and recommendation expiry clocks
are unchanged. Saved human observations invalidate older target-specific advice.

Private runtime configuration, receiver binaries, database data, fitted artifacts,
raw recordings and large local evidence archives remain outside publication.
Original dirty UI and Solar_PV checkouts and their indexes are preserved. Newer
Solar_PV electrical documentation on remote main is retained. No production
service, scheduler, model selection, device or database was changed by this merge.

The completed merge checklist, exact final test results and remote verification
are recorded in `openspec/changes/merge-deployed-repairs-to-main/`. Local detailed
manifests and original failed checks are retained in
`artifacts/merge-deployed-main-20261029.local/`.
