# Original measured-weather source implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The full written architecture and continuing implementation goal are already approved. Use one independent final immutable branch review and one Important/Critical TDD correction pass. Preserve the full program; this source stage is not completion of PR#3.

**Goal:** Carry current original radiation-proxy and raw rain-counter evidence into the same frozen household model/source snapshot without changing either source's physical meaning or existing receipt contracts.

**Architecture:** A pure prepared context retains the exact two original receiver envelopes and their original explicit policy texts, digests, expected current stream epochs and availability clocks. Reuse the existing radiation `_snapshot` and rain `parse_rain_snapshot` validators; assess each independently at the common model clock. A typed measured-weather snapshot extends the existing energy-source snapshot and retains all originals through versioned plan/pipeline/outcome replay. Acquisition reads the existing original localhost owner endpoints already used by the tracked qualified source Things, and fixed owned policy files, with no database grants or receiver/publisher changes. Logical source Item identity and actual owner endpoint are both retained; direct receiver availability is not mislabeled as JDBC persistence.

**Tech stack:** Existing Python frozen dataclasses, canonical JSON/SHA256, pure weather receipt validators and read-only OpenHAB GET collection.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, especially phases2A,3 and7. Published integration depends on PR25 exact-head hosted checks and merge. Pure implementation may proceed in a separate worktree from its reviewed30beba8 head while those checks run; no changes to that published head or production are allowed.

## Global constraints

- Shadow-only; planner authority none, automatic actuation false, translator disabled. No provider writes, owner migration, training or service restart.
- Keep calibrated irradiance, rainfall rate/daily amount, humidity, wind measurements and daylight geometry explicitly unavailable until their own qualified sources exist. Lux/126.7 is a radiation proxy; totalRainIn is a cumulative counter. A receiver/decoder clock is not an invented sensor measurement timestamp.
- Fixed source transports are http://127.0.0.1:5000/radiation_evidence and http://127.0.0.1:5000/rain_evidence, mapped to Weather_Radiation_Evidence_JSON and Weather_Rain_Evidence_JSON by the tracked READONLY Things. Fixed policy paths are /home/sat/.config/hex/weather-radiation-policy.json and /home/sat/.config/hex/weather-rain-policy.json. Before/after owner epochs come from those original receiver envelopes, independently of a held OpenHAB Item state. Preserve source identity/endpoint and original point semantics; no arbitrary URL or path arguments.
- Original radiation envelope8192bytes; original rain envelope4096bytes; each policy4096bytes; complete context65536bytes. Closed source/policy records, exact SHA256 and independently nullable missing source/policy/owner binding. No fallback to numeric weather Items or forecast rows.
- Radiation/v2 fault visibility is required for qualified point observations. Retain v1 originals diagnostically without promoting their missing fault visibility. Rain/v1 is the existing current counter contract; never fabricate a new native packet or continuous-history total.
- Original availability≤collection as_of≤created_at≤as_of+15s; later projection clocks recheck expiry, never backdate collection. Keep original raw expiry; original owner/configuration/runtime checks all inside one common15s monotonic acquisition deadline.
- Existing snapshot1/2/3/4/5, source contexts and old pipeline/plan receipts retain exact shapes and replay behavior. Add explicit new-version dispatch rather than changing historical renderers or global evidence role defaults.
- Serial local CPU20%, memory256MiB, swap0, tasks24, IOWeight10, nice15, idleI/O, one numerical thread. Use bounded affected-suite groups if necessary, with every group terminal before another numerical process. Private packets0600/staging0700. No off-host execution requirement; hosted checks remain publication gates.

## Review focus

1. Legacy, absent, malformed or expired weather evidence cannot invalidate the independent bank/thermal/source context or become qualified by numeric fallback.
2. Original decoder/receiver clocks, owner epochs, source policy and original expiry remain authoritative at the common model clock; future availability and owner changes fail closed.
3. A lux-derived proxy cannot populate calibrated solar radiation or a physical action effect, and a raw rain counter cannot populate rain rate or a qualified daily amount.
4. Root, genuinely distinct candidate and actual enclosing outcome must retain the complete new context, all original producer modules and replay identically without live reads.
5. Acquisition deadline covers before/after policy, owner and runtime verification; missing/invalid source transport cannot silently renew evidence or suppress a separately valid source.

### Task1: Pure original measured-weather context

**Files:** Create household/measured_weather.py and test_household_measured_weather.py.

**Interfaces:** PreparedMeasuredWeather(content:bytes), prepare_measured_weather(*,sources,as_of,created_at), project_measured_weather(context,*,as_of=None). Exact source keys radiation/rain; Each exact source row has source_identity, source_endpoint, raw, sha256, available_at, expected_epoch, policy_raw, policy_sha256 and policy_available_at. Receipt/digest and policy/digest pairs are independently nullable; a missing policy or expected epoch cannot qualify a receipt. Structural source identities/endpoints and aware original clocks remain mandatory. The complete context has schema, sources, as_of, created_at and measured_weather_sha256. Source-local errors return unavailable with explicit reason; structural context/digest or future clock corruption refuses the context.

**Output:** qualified light_lux, qualified solar_radiation_proxy_wm2 with basis lux_proxy_126_7 and calibration false, and qualified rain_counter_in with basis original_cumulative_counter. Qualified references get distinct role-bound identities with original raw/policy digests as parents. Decoder time is retained separately; observed_at remains null when sensor measurement time was not supplied. Receiver/availability/original expiry and software stream epoch remain unchanged. No calibrated radiation, rainfall rate/daily total or effect qualification.

- [x] RED exact raw/policy retention, v2 radiation/v1 rain, explicit current epoch/identity, independent absent/invalid/policy failure, source-future/expired/common-clock boundary, zero values, counter/proxy semantics, resealed malformed sources and no reads.
- [x] Implement and GREEN the pure boundary; verify no old renderer/role map changes. Commit measured evidence.

### Task2: Snapshot, model, candidate and enclosing-outcome replay

**Files:** Create household/measured_weather_snapshot.py and test_household_measured_weather_pipeline.py; update model_snapshot.py, energy_model.py, intents.py, planning.py, pipeline.py and operational pipeline/plan/outcomes closure profiles explicitly.

**Interfaces:** MeasuredWeatherSnapshot(EnergySourceSnapshot), bind_measured_weather_snapshot(*,source_receipt,source_runtime_manifest,weather_context,energy_configuration,measured_weather,code_revision), restore_measured_weather_snapshot(document,context); snapshot/v6 and new exact source-context retaining original power, original weather/model, original bank/topology and measured weather. Use measured-source-context/v1 with exact fields schema, power_receipt, weather_inputs, energy_configuration and measured_weather. New shadow-plan/v5 and model-plan/v5 carry the full new originals and measured-weather projection; preserve every old version and its existing output shape.

- [x] RED same common issue/availability, independent source failures retaining nominal bank and unchanged original thermal/forecast output, distinct source identities and deadline enforcement, invalid/resealed new context and old-version parity.
- [x] Add genuinely distinct v6 candidate and an actual enclosing outcome replay, plus direct v5 candidate/outcome regression coverage from PR25's recorded Minor review follow-up; no runtime-helper-only substitute.
- [x] GREEN pure/no-read replay, strict producer closure, private operational CLI equality and partial-runtime refusal; run the complete affected set under caps and commit.

### Task3: Bounded actual acquisition and publication

**Files:** Create household/measured_weather_capture.py, corresponding collector tests, docs/operations/household-measured-weather.md; update canonical household-program-progress.json.

- [x] RED fixed original receiver GETs and owned bounded policy reads, explicit before/after current owner epochs, common monotonic deadline, symlink/replacement/bytes/config/runtime drift, absent/invalid independence and private output bounds.
- [x] GREEN collector and complete one final independent review correction pass (128 refreshed checks).
- [x] Actual read-only committed-source proof must retain original owner/policy/raw metadata and bind to a normal naturally delivered model issue without forcing a publisher or relaxing freshness. Preserve a precise refusal when appropriate.
- [x] Verify actual pure/private CLI equality, qualifications and zero authority; single final review and one Important/Critical TDD pass.
- [x] Publish PR26, require every exact-head hosted check, merge, and record canonical evidence.

## Scope audit

This advances original current weather evidence in the approved common household snapshot. Calibrated usable battery energy, predicted PV/rolling energy, daylight geometry, authority/owner inputs, correlated owner migrations, causal effects/outcomes, operator UI and independent release gates remain required. Physical actuation is not authorized merely by implementing this source stage.
