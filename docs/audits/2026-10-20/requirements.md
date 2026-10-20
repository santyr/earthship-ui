# Earthship UI current audit — 2026-10-20

Audit base: `65ee7e95d58e6a6101700da3eccea67c9fea0ec7` (remote main verified unchanged; no open PRs). Isolated checkout: `/home/sat/.codex/worktrees/d4ee/earthship-ui`. The dirty live checkout remains at `02e3fcbc405d6018ad01977bbd7a3fa3af5f2ea5`; its overlays and immutable packages are preserved.

## Execution contract

The supplied October 20 handoff is the approved specification. Use bounded repairs within existing architecture, tests before behavior changes, original-version replay, and the current shared resource launcher. No planner actuation, automatic feeder recommendations, paid Google acquisition, provider fallback, private evidence publication, or new actuator/recovery expansion.

## Work sequence

1. Reproduce six CI failures and isolate injected geometry fixtures without changing production validation. Verify real caps/swap/priority/headroom guards.
2. Reproduce and repair night-load ledger retention/capacity/conflicts and exact durable override-policy commitment; preserve owner matrices and restart semantics.
3. Reproduce and repair OpenHAB reconciliation/order/retry/timeouts/replacement, control-mode agreement and Home history lifecycle.
4. Reproduce and repair sensor supervised duration, PV local-day counts/train-serve arithmetic, thermal interval overlap. Change numerical identities and preserve archived producers.
5. Map each architecture/active subsystem contract to source/tests; repair further confirmed defects. Reconcile newer closure evidence and older tracker statements with supersession links.
6. Repair advertised browser commands and maintained CI coverage; run all disjoint required gates, capture skips and resource refusals honestly.
7. Independent final review, fixes and final revision verification, authorized scoped integration/handoff with source readback and explicit deployment/measurement limits.

## Status vocabulary

Every requirement receives one of: implemented and verified; implemented but unverified; defective; missing within approved scope; intentionally excluded; externally blocked; superseded. Source, automated verification, deployment and physical qualification are distinct columns. Initial mapping is in progress; no comprehensive completion claim yet.

## Historical reconciliation

Latest evidence is [historical learning](../../operations/2026-10-19-historical-model-learning.md) and [forecast closure](../../operations/2026-10-19-forecast-closure.md). [Architecture](../../superpowers/plans/2026-10-07-household-intelligence-architecture.md), [outstanding work](../../operations/outstanding-work.md) and [October 16 tracker](../../operations/household-program-progress.json) remain historical evidence; unchecked statements require present-source investigation, not presumed absence.

## Active capability and boundary mapping

The source inventory is [inventory.json](inventory.json). Listed test families are current source contracts, not an assertion they have all executed yet. Final gate evidence and exact revision are tracked only in [verification.md](verification.md). “Physical blocked” below always identifies an independent measurement dependency, never a test skip promoted to qualification.

| Requirement / end-to-end path | Implementation | Normal verification family | Source / automation status | Deployment / physical qualification |
|---|---|---|---|---|
| Six reachable routes, navigation, console geometry, modals, charts | `src/routes.js`, `App.svelte`, `screens/*`, `lib/ui/*` | `routes`, `ui/*`, seven general browser specs | Implemented; final browser gate pending (A09) | Live UI uses dirty checkout overlay; 1340×800 and1280×720 simulated checks independent from tablet physical signoff |
| Startup/config/item/Thing/SSE→store→control state | `config.js`, `openhab/{client,store,sse,readRequest}.js` | init/store/client/config/SSE/reconciliation/read-timeouts/AppStartup | A03 fixed in source; focused verified | Candidate only; GET reconciliation must precede live eligibility |
| Source freshness/Astro/temperature/current DC/AC/BMS | `alerts/staleness.js`, `weather/astroPresentation.js`, evidence readers and receipt sources | staleness/Astro/current-source/Python evidence tests | Implemented; source clocks remain distinct from arrival | Runtime qualified source receipt required; held state is not a heartbeat |
| Control hold→one request→accepted/terminal/uncertain result | `controls/{catalog,controlState,requestClient,outcomeStore,holdAction}.js`, Controls/Home | control-state/request-client/outcome/hold/typed-controls/proxy | A04 mode discrepancy fixed; final gate pending | Manual/payment feeder retained; no automatic repost; owner safety remains authoritative |
| Night-load ingress→durable admission→policy→provider→receipt | `rules/night-load-owner.js` | night-load override/recovery/provider-delay + request-ledger | A01/A02 fixed and52 focused cases verified | Installed old source proven by runtime-start; candidate needs scoped release/readback; provider confirmation is not physical load metrology |
| Alternating East/South greywater, no overlap, daytime/quiet/cooldown/SoC/Astro/watchdog | `rules/southoutlet-cycle-installed.js`, existing evidence rules | greywater installed/SOC/sky/timer/durable recovery suites | Implemented, independently inspected; final all-owner gate pending | Exact installed source matches,60min starts/15min run; no new family or safety bypass |
| Manual/payment feeder counters, status, durable result | `rules/feeder-owner.js`, manual request catalog | feeder/request-ledger/recovery tests | Implemented;5s cooldown independently bounds admissible32-entry eviction reachability | Exact installed source matches; no test feeding and no automated qualification |
| Lighting/circadian and shade preview | lighting/circadian rules, shade server/catalog/UI | light/circadian/Dooya/preview/binding tests + shades browser | Implemented; Office Hallway reference preserved | Existing authority retained; preview does not commission motors or add automatic control |
| Home measured history and Energy measured/predicted overlay | `Home.svelte`, history coordinator, Energy/chart/forecast modules | HomeHistory, history lifecycle, Energy overlay and browser runtime/layout | A04 histories fixed; earlier delayed start/SoC overlay preserved | Forecast expires independently of measured-history fetch; source identity separate |
| Google-only acquisition full/interim independent horizons→archive→publication | `weather_learning/{production_worker,provider,production_publish,native_forecast,archive}.py`, public weather parsers | WeatherNext foundation/SDK, source/dual-horizon/publication tests, comparison browser | Implemented; prior closure supersedes older migration notes |84 live Things/zero retired-provider matches; no billing or fallback; cloud availability remains upstream |
| Native trailing-hour solar/rain, local-day/DST, remaining-day and unsupported fields | native forecast/provider/features, weather presentation | weather interval/rain/DST/schema/UI tests | A08 overlap repair; probabilities/codes/AQI explicitly unsupported | Marginal percentiles never become daily probability; no paid ensemble collection |
| Local thermal learning/four regimes, shade/vent context, source-bound inference/replay | native thermal modules, installed-shade origin, thermal weather conditioning | native fit/artifact/forecast/conditioned/frozen replay/ML workflow | A08 fixed;68 focused tests verified; source numerical identity changes | Old model sources remain immutable; new producer/admission required; causal/action and prospective skill unqualified |
| PV potential DC vs captured controller power; terrain and empirical response | `household_pv_model.py`, daily PV modules, calibration/policy | PV model/window/calibration/local-day/pair baseline/refresh/source tests | A06/A07 fixed; retained737-pair reassessment separate from prospective scores | Array/horizon declarations and uncensored proxies provisional; old original scores remain immutable |
| Nominal storage, current/learned AC demand, scenario outcomes and accuracy | calibrated/profiled energy, power flows, load models and outcome sources | calibrated/profiled/power/battery/scenario/source receipt tests | Implemented; no arbitrary clipping or borrowed cohort skill | Usable capacity/rate/taper/conversion assumptions explicit; maturity of independent outcomes external |
| Immutable evidence→snapshot with explicit missing/inconsistent domains | `household/{evidence,snapshot,adapters,capture,model_snapshot,...}.py` | evidence/capture/model/weather/power/sensor snapshots | Implemented; no observation grants new permission | Source/received/available/as-of clocks distinct; unknown cistern remains unknown |
| Capability registry, Item roles, owner-v2 contracts and typed intents | `household/{capabilities,control_contracts,intents,owner_sources,owner_policy}.py` | capabilities/contracts/intents/owner-source/owner-policy tests | Software implemented; legacy/manual parsing retained | Future owner-v2 existence is not deployment/actuation authorization |
| Pure model→candidate→constraints→arbitration→public report | `household/{pipeline,planning,replay,resources}.py`, observation projection | planning/pipeline/replay/resources/observation/qualification tests | A10 current automated-family boundary repaired;285 affected Python cases verified | Translator permanently disabled; physical per-intent/action-effect qualification external |
| Corrupt/missing/future/stale retained dependencies and schema evolution | strict codecs, source/runtime manifests, original producer registry and replay CLIs | archive/replay/runtime/receipt-integrity/private-file tests | Implemented; final native gate pending | Immutable original producer/environment required; no recovery expansion authorized |
| Bounded public reports→fixed server routes→strict parser→actual rendering | observation/energy/report server + frontend household modules | observation-server/proxy/private-files/public parser/UI tests | Implemented; v1/v2 qualification parser compatible | Parser-first rollout required for v2 producer; no query-selected file access or private extract publication |
| Radio/MQTT raw→decoder→supervision→DB→OpenHAB→UI software | `services/{lorawan,observations}`, provider/rule/retained Ventilation component | sensor contracts/extensions/supervised-history/container integration/browser component harness | A05 fixed;66 contract cases passed, container gate pending | Production online/empty registry verified; firmware/polarity/heartbeat/radio/coverage commissioning blocked on actual devices |
| Sensor optional household attachment and unknown water calibration | observation registry/water/replay, household sensor adapter | sensor observations/water/registry/epoch tests | Implemented observation-only; no added authority | Surveyed depth-volume/connectivity/reserve and actual commissioned sensors required |
| Nostr signatures/auth/sender-recipient/idempotency/cursor/outbox/backup | confirmation/messaging/NIP04/recurring release code | completion + operational + exact binary crypto/delivery and disposable PostgreSQL | Implemented; generic source gates default-off; current complete gates pending | Approved recurring release differs from generic defaults; natural eligible question/human reply and relay service behavior external; no messages sent |
| Shared host admission, CPU/RAM/IO/no-swap, deadlines/publication retries | job launch/pool/budget, cycle resources/pressure/deadline/source | job/resource/cycle/deploy/slow-failure tests | Implemented; real guard rejection suite unchanged | Live6GiB max/5GiB high/8CPU/256tasks/no-swap verified; headroom refusals recorded, never bypassed |
| Existing durability/migrations/atomic replacement and dependency outages | bounded source readers, journal/storage/outbox, maintenance/qualification tools | operational/completion/sensor disposable DB tests | Within existing contracts only; full native gate pending | No full-house restart, new migration/recovery project or private config rewrite |
| Host/origin/path/method access matrix and private browser exclusion | proxyPolicy, observationServer, shade server, Vite fs deny | proxy/server/private-file/cross-origin/encoded-path tests | Implemented; .codex deny preserved; final standard gate runs outside .codex | Public test fixtures must never contact production; no private config in bundle |
| Executable advertised verification and all discovered families | package scripts, workflows, QA matrix, inventory | gate regressions, test discovery and full disjoint gates | A09 repair in progress | Browser and sensor release/main gating required; skips name actual dependencies |

## Explicit exclusions and supersessions

- Planner actuation, new actuator families, automated feeder proposals/recommendations/qualification: intentionally excluded. Feeder legacy/manual contracts remain supported.
- Paid Google access, raw paid ensembles and retired-provider fallback: intentionally excluded. Local measurements are training/scoring truth.
- Retired Ventilation/Sensors route: superseded by the October19 operator decision in [Home/Energy recovery](../../operations/2026-10-19-home-energy-chart-recovery.md). Old links resolve Earthship; backend and retained component software can be fixture-qualified without claiming an active production sensor dashboard.
- PWA installation/offline controls and unspecified phone compatibility must reflect actual source; no control-state caching introduced to support documentation.
- Recovery/migration expansion, hardware commissioning, nominal-capacity qualification and causal action identification remain separate from these software repairs.

## Current evidence superseding old tracker statements

The historical learning document's final October20 closure table records deployed conditioned thermal serving, dedicated PV accuracy, Energy SoC overlay and Office Hallway shade reference. Its178-file/2642-test frontend run and build are historical evidence; the Python run interrupted after1625 cases was not complete. Earlier “activation pending”/“PV accuracy outstanding” text is superseded by that final table. The October16 program tracker remains a historical milestone snapshot, not a current completeness oracle.

Nostr recurring production status follows [October3 recurring confirmations](../../operations/2026-10-03-thermal-recurring-confirmations.md), not the older October1 “collector off” note: approved release process gates differ intentionally from default-off generic source. Natural recommendation→question→human reply and external relay rejection recovery cannot be manufactured as audit evidence.

## Architecture program phase reconciliation

Every phase in the existing tracker remains represented. Historical complete flags are preserved; this table separates implemented software from independent qualification. Source/test detail is in the active capability table above.

| Phase | Approved requirement | Current source and verification boundary | Remaining qualification or exclusion |
|---|---|---|---|
| 0 | ML foundations and explicit graduation contracts | Evidence/skill/graduation contracts and explicit null metrics; tests for calibration/reports | Prospective skill and physical calibration require independent matured local outcomes |
| 1 | Shared original evidence references | household/evidence.py and evidence/adapters/capture tests | Original clocks and identities retained |
| 2 | Immutable HouseholdSnapshot and live evidence capture | household snapshot/native/weather/power/measured/sensor contexts and snapshot/cycle/replay tests | Unknown water inventory, capacity qualification and missing measurements stay explicit |
| 2B | Capability registry, Item roles, correlated v2 contracts and owner migrations | Capability registry, control_contracts.py, Item ownership and owner-source/policy tests | Future owner-v2 live migrations/physical qualification deferred; no activation implied |
| 3 | Pure domain models with numerical parity | Pure thermal/energy/PV models, source-bound numerical runtimes and goldens; A06–A08 repairs | New source identities require fresh calibration/admission; historic producers preserved |
| 4 | Typed household intents and disabled intent-to-request adapter | Typed intents, strict legacy/current parsers and intents tests | Translator disabled; feeder current automation excluded |
| 5 | Hard constraint registry and deterministic arbiter | Planning hard constraints, exclusive owners and deterministic exhaustive arbitration tests | Missing effects/owner facts reject or remain unknown; no new observation grants permission |
| 6 | Shadow household planner | Shadow planner, declared utility/baseline/resource analyses and planning/resources tests | No actuator authority or claimed physical benefit; independent action qualification external |
| 7 | Deterministic sealed household plan replay and outcome scoring | Pure pipeline and archived original replay/receipt/corruption tests | Original matching producer/environment required; no rewriting old receipts |
| 8 | Resource-effect vectors and drift metrics | household/resources.py, drift/CLI/source-bound resource tests | Unknown resource effects remain unknown; no invented causal effects |
| 9 | Read-only operator observability | Public observation/qualification/chronology/recommendation UI and strict server/parser/browser tests | Feeder never a current recommendation; source/deployed/physical status distinct |
| 10 | Per-intent release qualification | Current qualification v2 and historical v1 parser, independent-gate status tests | Per-intent physical/action-effect/uncertainty/release evidence externally blocked; no feeder qualification |
| 11 | Staged integration through existing owner rules | Existing legacy owners and pure v2 contracts, scoped handoff/source-readback/recovery tests | Planner actuation and new owner-v2 live activation intentionally excluded; existing owner repair requires qualified handoff |
