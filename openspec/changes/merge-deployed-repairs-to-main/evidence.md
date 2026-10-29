# Deployed-source publication evidence — 2026-10-29

## Source reconciliation

Clean integration worktrees were created from current remote main in each
repository. Original UI and Solar_PV working files, HEADs and Git indexes remain
unchanged, including intentionally dirty files and newer private state.

UI remote-main baseline: `5c41b40`. Signed merge `32b1e8b` brings in native/advice
history through `0b52dc1` (including deployed `39b0070`); signed merge `1d30b9d`
brings in sensitivity fix `0075a1d`. Fourteen textual conflicts were resolved
against the actual deployed native or immutable UI component source. Separately
packaged historical Python files were not copied over the native source.

The active UI source was integrated from
`ui-release-suggestions-20261029-a03`. All **174** selected UI runtime/config/asset
files match that release byte for byte. The final sensor component matches
`9060ef3` without importing unrelated historical whole-tree differences from its
old branch. Reviewed installed source manifests identify the provider polling,
test/dependency and operator-documentation updates. Current Bedroom mapping and
the active radio compatibility selector/dependency document are included.
Private configuration and receiver binaries remain local.

Solar_PV integration starts from newer remote `890a0f7`, preserving its electrical
and fuse documentation. The **54** analytics Python modules match deployed
`analytics-reader-release-2fd49d818476`. Added source includes the current-product
adapter, reader/health correction, maintained tests, actual acquisition
service/timer and operator documentation. Signed commit `3213415` is pushed to
Solar_PV main. The original source-only documentation is superseded by a clear
deployment/reconciliation record, not rewritten as historical deployment proof.

OpenSpec project instructions, its six generated skills and completed repair,
thermal-analysis and suggestion-refresh changes are retained. No Superpowers
workflow or security scan was invoked.

## Validation

All final successful jobs use the existing admitted shared resource launcher.
Their memory/task counters have zero new events; resource limits and source
validators were preserved.

| Check | Result | Receipt prefix |
|---|---|---|
| Full maintained UI suite | 3,453 passed | `ui-full-a03` |
| Production UI build | passed | `ui-build-a01` |
| Full analytics suite | 935 passed | `analytics-full-a03` |
| Sensor helper suite | 606 passed, 11 opt-in container tests skipped | `sensor-helpers-a02` |
| Resolved planner/original-replay contracts | 227 passed | `native-merge-contracts-a02` |
| Advice, original expiry and closed observation contracts | 115 passed | `native-advice-a01` |
| Publication budgets, source reuse, score lifetime and sensitivity | 49 passed | `native-publication-sensitivity-a01` |
| OpenSpec strict validation | passed | command readback |

This is source publication, not a fresh numerical-model activation or physical
sensor topology qualification. Earlier complete qualification and live evidence
remain associated with their original release identities.

The first combined UI run exposed an obsolete thermal-alert fixture and a README
expectation. The final test uses the supported source-staleness monitor lifecycle
while retaining both polite-warning and assertive-critical transition assertions.
Analytics initially lacked its cross-repository import path and two deployed
service files; these were included, then the complete suite passed.

The overbroad initial native unit selection is not claimed as passing. Its first
run accumulated large failure fixtures and reached its original 512 MiB limit.
Diagnosis showed group-writable files inherited by the new checkout and mixed
current/legacy test expectations after automatic merge. Only isolated checkout
modes/umask were corrected; source guards and production files were unchanged.
Historical test fixtures were restored from the deployed source, and separate
current-planner refusal/expiry regressions preserve the remote-main contract.
The three final appropriate contract groups above pass within the same caps.
Original failed runs, import/filename mistakes and diagnostics remain retained.

## Retained detailed evidence

`artifacts/merge-deployed-main-20261029.local/` contains component inventories,
exact byte-equality checks, scoped prior integration manifests, original checkout
hashes, merge resolutions, source-mode diagnosis, complete logs, JUnit/JSON
results and capped resource receipts. All 174 UI and 54 analytics source
comparisons are verified independently of the tests. The preexisting remote-main
component-PV cohort-identity correction is preserved alongside the separately
deployed sensitivity reader.

Final Earthship remote publication, exact remote IDs and live-selector/index
preservation are recorded after the normal Git push succeeds.
