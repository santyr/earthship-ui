# Installed shadow-planner authority paths

This read-only audit binds PR #3's protected-actuator requirement to the actual
installed shadow planner and same-origin Vite development server. It records
current execution boundaries for a separate release review. It does not qualify
physical safety, v2 owner migration or a future active-request path, and it
grants no planner authority.

At2026-10-16T15:07:25UTC the installed backend is source1a3d5d8,
deployment097e4f75, with registry7b27669b. Nine relevant backend source files
match their deployment-manifest hashes. Eleven live UI authority/observation
files match the reviewed branch exactly. The listening Vite process uses the
live checkout, development serving and `safe-compat` mode. The actual browser
configuration has an empty `openhabUrl` and no browser API token. Thus commands
from its general client pass through the server's allowlist. This audit is
specific to those observed sources and configuration.

## Planner and publication boundary

`household/intents.py:intent_to_request` always raises
`planner_authority_disabled`. Intent validation also requires `shadowOnly:true`;
the registry requires `plannerAuthority:none`. The pure pipeline and observation
panel do not invoke the control request client.

The native publisher's public `put` transport admits only the existing String
telemetry Items `Thermal_OriginalForecast_JSON` and `Thermal_Model_JSON`. Its
normal publication and withdrawal loops use those fixed names. The allowlist is
enforced before credential reads and HTTP calls. Offline calls against the
actual deployed transport reject every registered protected actuator, legacy
ingress, request and result Item, with zero credential/network calls. Existing
private low-level transports and the broad credential are not new isolation
mechanisms; the source-bound conclusion concerns these declared execution paths.

The household observation transport has seven fixed read routes. It admits GET
only, rejects query-selected files and mutations, and projects closed bounded
artifacts. The panel has no request/actuator controls. Original decision clocks,
expiry and unqualified authority flags remain unchanged.

## Browser and owner boundary

| Registered intent | Request ingress | Declared owner with matching live definition | Protected physical Items |
|---|---|---|---|
| Feeder cycle | `GoatFeeder_ManualRequest` | `88bd9ec4de` | `Goat_Plugs_Outlet2_Switch` |
| Greywater cycle | `SouthOutlet_ManualRequest` | `hex_southoutlet_cycle` | `SouthOutlet_Outlet2_Switch`, `East_Bed_Socket_Outlet_2_Power` |
| Night-load override | `NightLoadOverride_Request` | `hex_night_load_override` | Shared night-load devices below; legacy `OverrideSwitch` is also denied directly |
| Night-load device | `NightLoadDevice_Request` | `hex_night_load_override` | `Dish_Washer_Power`, `ShurefloPump_Power`, `Goat_Plugs_Outlet1_Switch` |

The actual installed proxy policy rejects all six protected actuators, the
legacy override ingress and four result Items for POST/PUT/PATCH/DELETE. The
four manual request channels are allowed only in `safe-compat`/`full` mode;
maintenance/unknown modes refuse them. Direct writes to the three existing
living-room lights and circadian enable remain separate declared controls.
Protected Items do not occur in that direct allowlist.

A registry-derived matrix exercises528 denied method/path/mode combinations
against the live policy module offline, including direct Item, state and query
shapes. It checks the exact four request channels and their mode behavior.
No live write or rule invocation is used to prove rejection.

At15:09:38UTC, GET-only reads of the three live owner definitions confirm that
all request/legacy Item triggers match the declared registry and every live
script is byte-identical to its reviewed source mirror. The greywater mirror
is `openhab/rules/southoutlet-cycle-installed.js` in the review worktree; it is
not part of the independently maintained UI checkout. Source/trigger equality
is provenance, and does not demonstrate hardware operation or current physical
safety. `safetyInputsComplete:false` remains explicit.

## Verification and qualification scope

Existing backend intent/registry/telemetry regressions pass48 tests. Existing
browser proxy, catalog, read-only HTTP, observation-client, qualification and
safe-control regressions pass62 tests across6 files. The HTTP tests use their
own disposable local fixture server. All jobs use the shared host resource
launcher. This audit triggered no fit, forecast, production write, owner migration,
resource-policy change or service restart.

Private source pins, live-mode observations, the offline matrix and GET-only
owner bindings are under
`.superpowers/sdd/2026-10-12-household-common-cycle/shadow-authority-audit-20261016/`.

This adds source-bound installed-shadow evidence for the protected-write-path
requirement. The per-intent public assessment continues to describe its original
plan only; this later audit is not silently attached to that original decision.
No family is promoted. A separately reviewed active-request release still needs
its own complete write-path and physical-owner qualification. Independent
chronological windows, uncertainty/action effects, policy benefit and full
PR #3 completion remain outstanding. The proposed chronological shadow summary
continues to await its separate design approval.
