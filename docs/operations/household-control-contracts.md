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
