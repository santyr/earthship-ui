# Native Temperature Source Density Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute sequentially; no implementation agents in parallel. This is dependent Task10 of the existing post-upgrade repair goal, not another Task6 fix round.

**Goal:** Restore regular thermal publication, complete replay/scoring and downstream household/analytics products for the actual dense temperature history without dropping original observations.

**Architecture:** Acquire the three thermal role contexts once in a stable read-only snapshot, store every original row once in bounded content-addressed segments, and replay all roles continuously across segment boundaries. Route only a newly qualified operational successor to the new format; retain exact old readers, models, reports and runtime identities.

**Tech Stack:** Existing Python3.12 qualified runtime, PostgreSQL18 read-only transport, canonical JSON/deterministic gzip, immutable runtime bundles and original household admission/activation machinery.

**Spec:** docs/superpowers/specs/2026-10-26-native-temperature-source-density-design.md

## Global Constraints

- Baseline runtime source e5828bd4c5e4059032713f5d628fa097e0264d34; immutable active release is B/release-task6-reviewed-r5. B=/home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local. Parent-owned spec/plan are the only initial dirty files and belong in the first scoped signed commit.
- Existing authorization covers scoped repairs and necessary qualified deployments; no additional design/permission round, pushes, physical/financial actions or provider reactivation. No implementation in parallel with Task8R5.
- Explicit NEW-profile amendment: replace old8MiB whole-logical-query limit with <=3 segments, each raw/canonical <=8388608; manifest<=65536; all decoded segments+manifest and total raw and total stored bytes EACH<=24000000. Keep old v1/v2 readers/caps byte-identical. This uses the existing24,000,000-byte issue aggregate once across three roles; do not claim the old whole-query8MiB bound is unchanged.
- Global <=10000 original observations including <=1 original carry, <=8192 rawUTF8bytes/row, <=289 targets/elapsed24h, exactly air/mass/outdoor contexts; one unchanged _fetch_rows read-only REPEATABLE READ snapshot. No sampling/deduplication/barrier omission/JSON normalization, per-segment selector reset or extra carry.
- Preserve receivedAt/storedAt/validUntil/sensorEpoch/receiptVersion/snapshotSha256/None and all numeric results against the legacy pure reader on identical complete inputs. New shared acquisition does not claim identical late-arrival snapshots to three independent old transactions.
- Original global6144MiB/8CPU/256tasks/no swap/permanaged<=128, unit memory/CPU/task caps,85s acquisition/90s publication,50s score acquisition/120s full scoring/240s activation/150s safe window, original2s statements/1s locks/5s idle/read-only rollback and all permission/identity/freshness gates unchanged.
- Keep2s live polling, strict120s TTL, Bedroom relocation boundary2026-10-24T23:14:52Z and all sensor epochs. No held-value cache or persistence thinning.
- Fitted base closure files enumerated in the spec stay byte-identical. New optional operational helpers must have literal digests and loaded-path checks. No changing fit validator/accepted hashes, model/evidence/admission/dispatch pins or old code-revision labels.
- All heavy work uses ORIGINAL trusted household_job_run.py with bytecode disabled BEFOREouterimports, absolute commands/taskset/one-thread env. Root coordinates heavy windows; no worker Docker/service/production DB/model/activation actions.

## Review Focus

- Moving invalid/copy barriers across a segment boundary must remain barriers for arbitrarily long valid chains; compare every metadata field against the unchanged pure v2 oracle.
- A malformed unselected role cannot invalidate a valid selected role beyond the old shared-envelope checks; collector reset and wrong hardware epoch remain strict per-role barriers.
- Missing/replaced child segment after replay or during final publication/reuse must invalidate the complete source; manifest-only fingerprints or trusted cached selector state are forbidden.
- A decompression bomb/concatenated gzip/duplicate JSON key/forged totals or extra segment must refuse within the actual input/time/resource bounds.
- Historical capture versions and old dispatch entries must replay with their original runtime and original source files; the new optional profile cannot reinterpret old artifacts.

---

### Task 1: Inactive bounded shared source format and continuous selector

**Files:** create openhab/scripts/weather_temperature_source_segments.py and openhab/scripts/test_weather_temperature_source_segments.py; preserve legacy source/history/reader and fitted base closure unchanged.

**Interfaces:** export SharedTemperatureSource (immutable original-source handle, no authority), build_shared_temperature_source(*,rows,targets,assessed_at,contexts,guard=None), fetch_shared_temperature_source(connection_factory,*,targets,assessed_at,contexts,remaining_timeout=None,guard=None), write_shared_temperature_source(directory,source,*,guard=None)->Path, read_shared_temperature_source(directory,path,*,guard=None)->SharedTemperatureSource, replay_shared_temperature_source(source,*,guard=None)->mapping of role to original(target,metadata-or-None) pairs, and shared_temperature_source_files(source)->tuple[Path,...]. contexts is an exact air/mass/outdoor mapping; each context contains stream, TemperaturePolicy and sensor_epoch. The build/fetch/read functions return the same source type. A retained handle enumerates its manifest and every segment; a not-yet-sealed handle cannot masquerade as retained file evidence. Private representation is the implementer's choice; publish exact interface/closed schemas in report for Task2.

- [ ] Write RED tests for raw-day>8MiB and separate canonical/three-role aggregate crossings using labeled synthetic data; old source readers refuse, unchanged pure v2 reader provides the complete-grid oracle. Preserve supplied original Oct24/25 packets untouched.
- [ ] Add independent full-field differential cases:10000 bounded rows, all three policies, moving copied-receipt barrier chain split across boundaries, NULL/malformed/oversized/wrong or missing role/epoch/collector reset/backwards receipt, exact expiry/carry/targets, UTF8/microsecond instants, equal/conflicting timestamps. Never reset selection at internal segments.
- [ ] Implement closed manifest+segment schemas, deterministic gziplevel1/mtime0, context/transcript/stored+decoded digests, global counts/offsets/byte accounting and exact content addresses, chunks-first/manifest-last publication and guarded atomic private writes. Reject +1 boundaries, duplicate fields, corruption/splicing/reordering/truncation/concat/bombs/path aliases or mutation/deletion before returning any grid.
- [ ] Use one envelope decode/hash per row and continuous per-role selected/barrier_at/epoch state; keep the legacy pure reader unchanged as the independent oracle. Deadline guards run within bounded loops and before/after IO; no global/cross-issue cache.
- [ ] Under original256MiB24tasks90s/taskset2,3/pinned3.12-B run new tests plus openhab/scripts/test_weather_temperature_sources.py, test_weather_temperature_reader.py, test_temperature_grid.py, test_temperature_window.py, test_weather_temperature_sensor_epochs.py and test_weather_temperature_history_postgres.py as applicable to actual local prerequisites. Record real prerequisites; do not add skips to conceal a required live gate. Use owned disk basetemps; no full-tree scans/extra repeat after green.
- [ ] Check source closure/archive480-file bound before committing proposed new modules; identify any actual conflict without raising it. Signed clean scoped commit; write task1 report with exact RED/GREEN command/output/counts/interface/sourcehashes and measured resource limits. No active backend/routing change yet.

### Task 2: Explicit operational successor, complete binding and replay integration

**Files:** create weather_temperature_segmented_binding.py and weather_learning/native_segmented_backend.py; modify native_thermal_live.py, native_thermal_forecast.py, native_thermal_score.py, household_score_report_reuse.py, household_cycle.py, household/thermal_model.py, household/weather_context.py and weather_learning/correction_monitor.py with their focused existing tests. All paths relative to openhab/scripts/. The spec's fitted-base files remain byte-identical; no generic framework/refactor.

**Consumes:** Task1 exported immutable source interface, schemas and complete child inventory. **Produces:** explicit new segmented backend, origin-binding/v3, unconditioned/conditioned capture v4/v5 with content-addressed suffixes and exact optional-helper runtime pins; all existing engine/conditioning numerical outputs unchanged. The same source manifest is required for all three role references. No fallback selected by packet size or failure.

- [ ] Write RED integration tests showing old runtime rejects the new explicit profile and current unconditioned/conditioned/cycle/scoring/report-reuse consumers lack its complete child-source binding; preserve all legacy cases.
- [ ] Implement shared native acquisition/store/fresh file replay, exact role/context/grid binding and literal helper/loaded-file pins through existing optional native adapters. Keep the current private configuration field shape; qualified successor runtime explicitly selects the new backend.
- [ ] Route exact new capture versions/suffixes through all listed consumers. Add every segment to absent/gap/pre/post/reuse/final publication fingerprints. One source-file deletion/replacement or changed bytes after replay must fail. Never trust a cached scalar grid or reinterpret historical captures with current runtime.
- [ ] Prove retained fit/base-source equality, unchanged source/model/admission originals, old v1/v2 and capture v2/v3 independent replay, current full new capture/binding/replay and hostile child mutation cases. Keep old score endpoint query contracts/equations unchanged.
- [ ] Run focused existing native forecast/score/cycle/conditioning/correction/reuse tests through original admitted caps; record exact tests and output. Add measured full original1/6/12/24h scoring/report/cycle replay work under original120s and activation10s leaves/240s/150s gates; parent may execute operational private qualification after source review, never replace numerical replay with mocks. Any runtime/size/archive conflict is an explicit finding, not permission to relax a bound.
- [ ] Signed clean scoped commit plus complete task2 report and review package. Source-only is not deployment or normal-operation proof.

### Task 3: Parent qualification, guarded deployment and natural operation

**Files/artifacts:** NEW immutable qualified successor package and private B/native-temperature-density-20261026 evidence; original canonical repair-tracker/progress ledger; no edits to old releases or prior receipts.

- [ ] Independently review Task1 and Task2 source; retain all actual old/source regression and refusal evidence. Produce complete clean-source archive and pin inventory with ignored bytecode disabled.
- [ ] Execute one fresh private current full-day single-snapshot capture and independent retained replay. Record actual per-segment/global rows/bytes, original carry, acquisition wall/CPU/RSS/cgroup events/source reads and exact all-role metadata equality; no fit/publish/activation as a diagnostic shortcut.
- [ ] Complete original cold whole-runtime candidate/admission/forecast/cycle/score/report replay and source mutation/deadline/rollback gates with retained numerical evidence and original caps. Qualify optional operational runtime through the existing mechanism, identify any concrete builder incompatibility before changing code. Do not forge retained-fit eligibility or copy old pins into the new release.
- [ ] Install only qualified new external runtime/candidate/receipt/dispatch/deployment identities through existing safe handoff; preserve all old artifacts. Guard current before-signatures, exact rollback and owner/timer restoration. Never install source in place or modify writer/private credentials.
- [ ] Observe actual scheduled fresh thermal publication plus persisted delivery/readback/complete new-source replay, downstream household cycle and analytics refresh, regular native refresh and later mature scoring against the new capture. Keep statuses separate; no model graduation/actuation claim.
- [ ] Reconcile original all-findings/UI6routes×2sizes/sourceguard/system-error gates and perform ONE combined goal-level whole-branch review with this subplan's commits included. Final completion requires current behavioral and deployed evidence for every required gate; source tests/manifests alone are insufficient.
