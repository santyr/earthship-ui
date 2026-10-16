# Household control contract definitions

This stage implements pure definitions from PR #3. It installs no owner rule,
changes no existing v1 payload, and creates no OpenHAB request transport.

`household.control_contracts` defines the closed correlated request/result v2
schemas and a versioned immutable reason vocabulary. Requests require an opaque
8–128-character request ID, aware requested/expiry clocks, a supported owned
intent family and strict parameters. All source labels share the same checks.
Planner-origin requests require intent ID, snapshot SHA256 and planner version;
manual provenance may be explicitly null. Owner age is at most 120 seconds,
matching all three current owner sources, and may be tightened by a caller.
Overlong lifetimes are refused, and stale/future/expired requests fail closed.
Request identity and idempotency are still enforced by the durable owner ledger,
not by this stateless parser.

The initial parameter families describe the existing greywater, feeder and
night-load owner interfaces. Greywater/feeder cycle parameters are empty.
Night-load override parameters contain only ON/OFF command. Device parameters
contain only one declared device ID and ON/OFF. No actuator name or endpoint is
accepted as a parameter. These are future protocol definitions, not a live v2
migration of any owner.

Results require the original request, exact request/intent/snapshot correlation,
expected owner version, aware original timestamp and catalogued status/reason.
Accepted and running are distinct from owner-reported completed. A terminal result
can arrive after request expiry, since physical work may outlive admission.
Acceptance or reported start after expiry is refused. The bounded sequence checker requires
acceptance before running/completed and refuses changed terminal outcomes,
regressed clocks or owner identity changes. A parsed result alone proves neither
persistence nor physical completion; original receipt/outcome qualification
remains mandatory at the future live consumer boundary.

A pure compatibility helper normalizes legacy `complete` to `completed`. No
existing v1 reader is changed or required to use it yet.

`household.intents` seals immutable shadow-only intents to a frozen snapshot and
original evidence digests. IDs cover all parameters, effects, provenance and
expiry. Action proposals require source references that still satisfy their
original expiry and age limits. Effects remain nullable estimates, not measured
benefits or authorization. Their explicit units are kWh, SoC percentage points,
Fahrenheit change, litres and normalized cycle cost. NO_ACTION cannot claim an
optional resource effect. Unsupported families and unknown parameters fail.

`intent_to_request` is deliberately disabled and always returns a catalogued
refusal by raising `ContractRefused('planner_authority_disabled')`. It accepts
no sender, endpoint or enable flag. Live planner authority remains absent.

Later stages must add pure domain projections, constraints, arbitration,
deterministic shadow planning and original outcome/replay qualification. Owner
v2 migrations and any physical request release remain independently qualified.


## Observed installed greywater inventory, 2026-10-14

Live read-only inspection found the registry still described the older single-pump source. The installed rule exactly matches historical revision `2c94b3c:openhab/rules/southoutlet-cycle-current.js`, SHA256 `4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b`. Source `177a8a1` retains those exact bytes in `openhab/rules/southoutlet-cycle-installed.js` and points the managed descriptor there. The separately prepared daylight-freshness candidate remains unchanged in `southoutlet-cycle-current.js`; its additional checks are not present in the observed live rule. The snapshot filename records this observation, not continuous live-source qualification.

The descriptor now protects both `SouthOutlet_Outlet2_Switch` and `East_Bed_Socket_Outlet_2_Power`, and names `BMS_SOC_Evidence_JSON` as the actual SoC safety input. This prevents another declared owner or request binding from claiming the East pump. Authority remains descriptive-only and safety inputs remain explicitly incomplete. No subset installer was invoked. Live owner rule source, triggers, conditions and configuration were re-read unchanged for greywater, feeder and night-load after the ML rollout.

Regression verification: four failures reproduced the old source and missing East protection;406 affected Python tests and32 JavaScript manifest/proxy tests passed. Final review found no issues and independently checked all six owner orders plus twelve collision cases. ML deployment `7afb91b2011a70e3f0bf03e2116eca2f22f38e6b0f2744f5add4205f9f6bc835` activated at2026-10-15T00:34:14UTC with the original trained model. Geometry for00:35:15UTC was retained before cutover. Physical-state facts, actual-policy baselines and owner contract migrations remain unfinished. Private original observations/readback are retained in `.superpowers/sdd/2026-10-12-household-common-cycle/owner-policy-20261014/`.

The first scheduled forecast on the corrected stage issued at2026-10-15T00:35:15UTC and exited0 at00:35:29UTC. Its household receipt `28bc0b9aeb103e2231f910d8a3550d24bbc696b8453e2c912edeaa595a0e7191` contains both protected pumps and the corrected source-boundSoC dependency, and replays identically through pure and exact-stage privateCLI paths. Prepopulating geometry before cutover preserved this forecast. The daily checkout matches177a8a1; its installed unit and morning schedule remain unchanged.
