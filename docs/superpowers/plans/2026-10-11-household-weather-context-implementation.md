# Original weather and operator context implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one independent whole-branch review at the end. This implements the already approved household architecture's original-source adapters, with no new authority or forecast equations.

**Goal:** Represent the original weather forcing and origin operator context in the common immutable household snapshot and rederive them through model, intent, plan and outcome replay.

**Architecture:** Freeze the complete verified original provisional capture together with its separately prepared thermal projection. Pure validation binds the capture digest, original metric receipts, action snapshot, exact interpolated forcing, issue/availability and prepared identity. A new explicit snapshot/v4 adds those retained context rows to an unchanged model-bound v3 derivation. New v3 plan/pipeline receipts restore the complete original context; older v1/v2 branches retain their structure and numerical behavior.

**Tech stack:** Existing Python dataclasses, canonical JSON, mature forecast/action validators and local original archives.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases2/3/4/7.

## Global constraints

- Serial CPU20%, memory256MiB, swap0, tasks24, nice15, idle I/O, single numerical thread. No fitting or recovery tests/work.
- No publisher start, forecast/actuator write, owner migration, grants, credentials, vent calculation or physical policy change.
- Snapshot256KiB, weather context256KiB, plan512KiB, pipeline1MiB. Complete original captures retain their existing2MiB decoded limit in an explicit canonical, digested compressed envelope; decode enforces size, EOF and no trailing data. Reject oversize; never drop originals or candidates to fit.
- Preparation may verify original files; projection, snapshot binding and replay perform no I/O.
- Original weather forecasts and operator context are metadata, not measured weather, calibrated effects or actuator position. No wind/rain/daylight/physical bank facts are inferred from radiation or a software epoch.
- Preserve exact original thermal output, measured versus latent mass, November operator-default semantics, and original shade/legacy coarse vent/mode declarations. Never invent window/skylight split states.
- The full bank/load/authority/owner/outcome/resource/UI/release requirements remain active beyond this stage.

### Task 1: Frozen original weather context

Create `household/weather_context.py` and `test_household_weather_context.py`.

Interfaces: `PreparedWeatherContext(content:bytes)`, `prepare_weather_context(capture,prepared_thermal)`, `project_weather(context)`. The closed canonical context stores a complete compressed original capture, prepared thermal and its own digest. Strong preparation reuses the original capture validator. Pure construction checks capture/thermal identity and clocks, original metric receipt reconstruction, original action snapshot semantics, exact five-minute forcing equality and original thermal output.

- [x] RED: module/API unavailable.
- [x] GREEN: original provider issue/receipt digests, hourly wind/weather codes and exact outdoor/radiation forcing are retained; confidence/input qualification is not_assessed; origin actions remain declarations.
- [x] Reject changed/resealed weather, capture/prepared linkage, availability, action snapshot or forcing. Returned dictionaries and caller originals cannot mutate frozen content.
- [x] Prove projection and restoration have no file/SQL reads. Keep current physical solar radiation, humidity, precipitation and wind unknown when no measured source exists.
- [x] Commit tested boundary; record RED/GREEN evidence and any rulings.

### Task 2: Snapshot and replay adoption

Create `household/weather_snapshot.py` and `test_household_weather_pipeline.py`. Modify `model_snapshot.py`, `intents.py`, `planning.py`, `pipeline.py` and operational plan/pipeline/outcome closure dispatch.

Interfaces: `WeatherSnapshot(ModelSnapshot)` with immutable original source and weather context; explicit snapshot/v4. Root source/model clock and physical rows rederive from unchanged v3 construction. Retained forecast issue, exact future outdoor/radiation arrays, hourly forecast wind/weather codes and original shade/legacy coarse vent/mode rows use nonphysical context quality. Unknown mode stays unknown. Missing weather context uses v3; it cannot masquerade as v4.

Source-context map values are explicitly versioned for v4 and retain both original power receipt and weather context. Pipeline/plan receipt/v3 dispatch restores root and candidate snapshot types. V1 and v2 shapes stay unchanged. Energy and thermal share the new identity; weather projection binds the exact same prepared model. Operational replay validates the complete original producer closure and original weather/thermal executing dependencies, including the actual enclosing outcome receipt.

- [x] RED then GREEN: snapshot/clock/source lineage, exact original weather/thermal parity, shared energy binding, typed proposal generation and disabled translator.
- [x] Metadata cannot become physical action evidence. Later source/context, stale sources, forged generic snapshots, changed/resealed originals or derived outputs and incomplete executing closure are refused.
- [x] Original v1/v2 receipt shapes and replays remain equal; root/candidate contexts deduplicate without discarding candidates.
- [x] Full affected suite under serial caps.
- [x] Actual original source/context from a normal naturally delivered publisher issue; pure and private CLI replay match. Report current/full source incompleteness honestly; no forced issue.
- [ ] Commit, one independent final review and one Important/Critical TDD fix pass. Publish; exact-head hosted checks gate merge.

## Review focus

Future forecasts cannot become observed source facts; interpolation cannot extrapolate or change original units; weather identity cannot be detached from the original capture/model; legacy coarse ventilation cannot become separate window/skylight positions or new calculations; retained shade presence cannot become actuator position; original mode/default policy cannot be silently overridden; nested root/candidate/outcome restoration and full operational execution closure must dispatch by the actual version; old receipt branches cannot gain new fields; oversized originals/candidates cannot be silently removed; snapshot source clocks and measured mass must survive enrichment.
