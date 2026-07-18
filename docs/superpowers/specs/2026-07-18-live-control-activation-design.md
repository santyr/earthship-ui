# Earthship Live Control Activation Design

**Date:** 2026-07-18
**Status:** Approved in conversation; pending written-spec review

## Purpose

Make every control on the Earthship console truthful and usable from the
Lenovo Tab M9 and laptop targets without weakening the existing OpenHAB safety
and ownership boundaries.

The current UI has two distinct defects:

1. living-room lights discard ordinary tablet taps because every command uses
   an undiscoverable 600 ms hold; and
2. household controls are intentionally status-only because their correlated
   OpenHAB request/result items and owner rules have not been deployed.

Active-state color is also incorrectly suppressed whenever a control is
disabled, causing real `ON` states to appear inactive.

## Interaction Model

The three living-room lights use a normal single tap. A tap sends exactly one
command and cannot be retried automatically. Circadian policy, owned household
loads, Night Load Override, feeder, and circulation retain a 600 ms hold with
visible hold progress.

The UI distinguishes state from availability:

- `ON` always uses the configured active color, even when the control is
  disabled or read-only.
- offline, unavailable, denied, failed, pending, and outcome-unknown states
  remain visually distinct.
- a disabled control explains its owner, missing capability, or provider
  problem without falsifying its physical state.

Touch targets remain at least 44 by 44 CSS pixels at 1340x800 and 1280x720.

## UI Command Architecture

`Toggle.svelte` selects an activation mode from the typed control catalog.
Direct living-room binary controls use `tap`; all policy, owned-load, action,
and safety-request controls use `hold`.

The direct light path remains:

`UI tap -> same-origin server proxy -> OpenHAB item command -> provider event`

The browser never receives an OpenHAB token. Success requires a target-state
provider event received after command start while the provider Thing remains
ONLINE. HTTP success alone is only transport acceptance.

Protected controls send generated request IDs to request items and correlate
only matching result items. They never command provider or policy state items
directly.

## OpenHAB Ownership Contracts

### Feeder

Create `GoatFeeder_ManualRequest` and `GoatFeeder_ManualResult` as unlinked
String items. Extend canonical rule `88bd9ec4de` so it remains the sole feeder
owner. It preserves cooldown, one-second pulse, counter accounting, and the
redundant outlet-OFF cleanup. Requests are serialized and idempotent. Results
use matching request IDs and explicit accepted, denied, running, complete, or
failed states.

The household UI never commands `Goat_Plugs_Outlet2_Switch`.

### Greywater circulation

Create `SouthOutlet_ManualRequest` and `SouthOutlet_ManualResult` as unlinked
String items. Extend `hex_southoutlet_cycle` with a received-command trigger.
Manual requests pass the same BMS communication, data validity, low-SoC,
cooldown, hydrology, curtailment, run-duration, and force-off gates as
automatic cycles.

The household UI never commands `SouthOutlet_Outlet2_Switch`.

### Night-load owner

Create these unlinked String item pairs:

- `NightLoadOverride_Request` / `NightLoadOverride_Result`
- `NightLoadDevice_Request` / `NightLoadDevice_Result`

Deploy one serialized owner for Night Load Override, Dishwasher, Shureflo, and
Goat Cam. The owner is the only UI path that commands the three provider
items. Existing schedule semantics remain exact:

- override ON owns Dishwasher, Shureflo, and Goat Cam and drives the existing
  OFF matrix;
- override OFF restores Shureflo ON while leaving Dishwasher and Goat Cam
  unchanged; and
- Goat Cam provider-confirmed state continues to drive the existing
  `FeederOverride` coupling rules.

Device requests are accepted only when override state is definitely OFF, no
owner transition is active, and the provider Thing is ONLINE. Result payloads
include the matching request ID, target, outcome, reason, timestamp, and
provider receipt.

## Persistence and Recovery

Request items use `autoupdate=false`. Request ledgers and committed policy
state have JDBC every-change persistence and restore-on-startup coverage.
Accepted request state is persisted and read back before any protected
physical command.

Malformed, oversized, duplicate, stale, or unknown requests are denied before
actuation. On rule restart, accepted or running entries become
`failed/restart-uncertain`; recovery never commands equipment. No transport
failure is automatically retried.

## Deployment and Rollback

All OpenHAB changes use supported REST APIs. Live JSONDB and configuration
files are never edited directly.

Each subsystem is deployed as a separate receipt-bound transaction:

1. snapshot exact items, metadata, rules, links, and protected dependencies;
2. verify hashes and current runtime safety state;
3. disable the affected owner ingress;
4. install candidate resources while disabled;
5. read back and verify exact resources;
6. rehearse old-disabled to new-disabled restoration;
7. enable the owner before schedules or UI capability;
8. verify rules, Things, item states, persistence, logs, and receipt closure.

Failure restores the exact captured resources and keeps the corresponding UI
capability unavailable. Feeder ingress must also quiesce known external callers
during its rule replacement. Greywater deployment requires the provider outlet
to remain OFF and includes one attended emergency-OFF authorization only for an
unexpected maintenance race.

## Verification

Implementation follows test-driven development:

- component tests prove single-tap light submission and hold-only protected
  submission;
- styling tests prove disabled `ON` controls retain active-state color;
- catalog and proxy tests prove unsafe provider items cannot be direct command
  targets;
- exact-source OpenHAB simulations cover ownership, idempotency, persistence,
  restart, races, timeouts, denials, and cleanup;
- live read-only verification proves items, rules, links, providers,
  persistence, and clean logs before capability activation;
- Codex and implementation subagents do not actuate feeder, Goat Cam, Night
  Load Override, or any other protected production control; the user performs
  real switch operations from the UI while Codex observes request, result,
  provider, rule, and log evidence;
- any exceptional agent-operated physical actuation requires a new,
  control-specific contemporaneous authorization and an observer present;
- final Lenovo and laptop sign-off requires operator confirmation of tap/hold
  behavior, active-state color, readable feedback, and no scrolling.

The existing live light-cycle evidence proves the proxy and provider route but
does not close UI sign-off because the operator reported that ordinary tablet
interaction remained broken.
