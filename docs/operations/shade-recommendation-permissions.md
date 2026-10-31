# Shade recommendation permissions

Operator contract added October 24, 2026. This extends decision support; it does
not authorize installation, automatic actuation, or physical commissioning.
The five current-source bug repairs are separate from these two new requirements.

## Scope and policy

| Zone | Saved OpenHAB preference | Extra override gate |
| --- | --- | --- |
| Kitchen (`kitchen`, planned slots 1–8) | `Shade_Kitchen_RecommendationAutomation` | None |
| Living Room (`living`, 9–17) | `Shade_LivingRoom_RecommendationAutomation` | None |
| Bathroom (`bathroom`, 18–21) | `Shade_Bathroom_RecommendationAutomation` | Authoritative `OverrideSwitch` OFF |
| Bedroom (`bedroom`, 22–26) | `Shade_Bedroom_RecommendationAutomation` | Authoritative `OverrideSwitch` OFF |

These are policy switches, never motor endpoints. The October 24 read-only
inventory contained 460 Items, including `OverrideSwitch`, with none of the four
preferences or an equivalent shade automation setting. The sunlight geometry
and Living Office sensor Items are unrelated. No Item was created by that read.
Recheck inventory before any separately authorized installation.

**SCOPE-SHADE-01:** Bathroom and Bedroom are ineligible for recommendation-driven
automatic movement whenever `OverrideSwitch` is ON or its read is unknown or
unreconciled. This covers daytime manual activation, partial moves, schedules,
retries, deferred work, group members, and energy/thermal-origin recommendations.
There is no separate night timer and no efficiency exception. Read the existing
policy without changing its owner, ON/OFF matrices, or schedules.

**SCOPE-SHADE-02:** Each zone has one “Automate recommendations” switch. New
preferences default OFF; an unrestored or unconfirmed preference is Unknown,
not confirmed OFF. Explicit choices survive UI/service/model restarts through
trusted OpenHAB persistence. Save OFF and ON independently for each zone. Nightly
protection overlays the preference: Bathroom ON can remain saved ON while its
effective status is “Paused — nightly override.” Changing a preference while
paused never bypasses that overlay.

A valid stable override value can last all day/night. Its authority comes from a
current reconciled source read and owner generation, not its last-change age or
a cached browser receipt. Loss of unrelated override authority alone does not
block Kitchen/Living Room, but loss of their own required policy/control inputs
does. State changes invalidate automatic work even if values later return to
identical Booleans. Session identity also changes after authority loss/restart.

## Source implementation

`src/lib/shades/policyModel.js` is the backend evaluator. The constrained
`policyServer.js` endpoint is wired by Vite at `/api/shades-policy`; browser
presentation in `policy.js` consumes the evaluated result and cannot authorize a
move. GET reconciles current OpenHAB reads. POST accepts only one known zone,
a Boolean preference, and the exact expected generation/session. Its server-owned
OpenHAB credential never reaches the browser, and the general REST proxy still
forbids arbitrary Item writes. Same-origin JSON checks protect policy saves.

Prepared file-owned definitions are in
`openhab/file-config/items/shade-recommendation-policy.items` and
`automation/js/shade-recommendation-policy.js`, with ownership marked prepared.
The four saved Switches and durable revision use the existing JDBC service.
`Shade_RecommendationAutomationRevision` binds each transition to a new UUID,
preferences, override and confirmed persistence timestamps.
`Shade_RecommendationAutomationSession` is a volatile current-owner marker:
exclude it from JDBC persistence/restoration while retaining all previous
selectors. The owner clears this marker on load, restores choices/default OFF
only after startup reconciliation, then binds the new marker to its durable
receipt. An old restored receipt alone cannot authorize a current session.

The server requires exact persisted receipt/state agreement and matching owner
session reads bracketing the complete read. A successful command response is not
confirmation. Loss of authority rotates the browser-facing session identity;
concurrent/stale saves must reread policy. Persistence queries use explicit UTC
receipt/proof windows and `pagelength`, with boundary/current-state synthesis
disabled. Select the last real record at the latest timestamp, including binary
transition duplicates, and require exact preference proof timestamps. Stable
choices outside the default 24-hour query window remain readable. UI requests have a bounded 30-second
transport/body deadline; teardown aborts them, late results are ignored, and
polling recovers from failed reads. No local-storage preference is authoritative.

`createShadeAdmissionHarness` is explicitly a non-actuating contract harness.
It exercises generation/source binding, queue invalidation, subset effects,
health/feedback and final serialized rechecks using mocks. It has no device
transport, generic manual bypass, physical dispatcher or invented STOP. No
current shade candidate/queue/execution path exists outside this harness; future
commissioned owner integration remains required and must share the inhibition
lock. `shadeAdviceMetadata` exposes evaluated manual-only/conditional modes for
that future advice contract without enabling a current shade action type.

## Advice, observations, and execution

The backend evaluates zone policy. The UI shows its validated saved choice and
effective status separately, with pending/failed saves. A preference ON must
never be called active solely because it is ON. Uncommissioned hardware and
unreleased global automation remain explicit independent gates. Page opening,
reconnecting, tab changes, restoration and preference changes do not move shades.

OFF or nightly protection preserves human advice (labeled Manual only), manual
controls and actual position-history collection. Do not create queued commands
from manual-only advice. Explicit manual requests must use a trusted manual
owner path, never a caller-controlled `source='manual'` exception. Existing
physical remotes and authorized manual commands keep their normal safety gates.
No automatic reversal is permitted after a manual change.

The existing source-only observation readers remain independent of preferences:
`thermal_model/shade_observations.py` and `shade_history.py` require commissioned
Item names, real matching `motor_report` diagnostics, availability, original
receipt timestamps and scalar positions. Requested positions, command ACKs,
bridge caches, preview positions, stale reports and mixed group averages cannot
substitute for actual feedback. Missing actor provenance remains missing.
The UI catalog's 26 unmapped slots and shared preview do not qualify any motor
observation. Actual feedback changes invalidate an older position-bound advice
assessment before any future admission.

## Admission and cancellation contract

Bind an automatic evaluation to its original recommendation, actual per-shade
zone membership, observed-position identity, current policy generation and
source session. Check every applicable gate at scheduling/admission and again
inside the final commissioned owner's serialized command admission. After an
inhibition commits, that owner must admit no later automatic command for the
affected zone. A previously queued ON → OFF → ON request stays obsolete; reopening
a gate allows only a fresh assessment under current observations and forecasts.
Retain the original recommendation and inhibition reason; never modify an old
receipt or replay historical recommendations into a queue.

Expand an automatic group/batch to actual mapped members before admission;
exclude protected, OFF, unknown, offline or unmapped members. Recompute coupled
thermal/energy effects for the eligible subset with excluded shades left at
observed positions. Do not forward an unfiltered all-device command or retain
all-shade effect estimates for a partial group. Explicit manual all-shades work
remains on the trusted manual owner path.

Policy inhibition can prevent queued work; it cannot undo already dispatched
motion. A future commissioned owner may issue STOP only for its own identified
in-flight automatic move through a separately tested supported adapter function.
Otherwise record the honest in-flight limitation and actual feedback. Never
invent STOP, reverse movement, or interrupt an unrelated manual move.

## Installation and commissioning boundary

The source additions and mocks do not install an owner or enable device access.
The current household intent translator always refuses planner execution, and
there are no current shade intent types, scheduler jobs, mapped motor Items or
commissioned final shade owner to activate. A test-only admission contract does
not replace that missing physical owner. Every real execution route must adopt
the serialized final check above before future actuation can be released.

A separately authorized policy-only installation must first inventory the real
OpenHAB version, duplicate writers, persistence service and restore behavior;
install the new source definitions with their owner metadata; verify OFF/ON
persistence and restoration by authoritative readback across restart; and verify
same-origin authenticated policy saves affect only the addressed preference.
Keep the existing JDBC provider rather than introducing a second persistence
owner. Missing owner/revision/persistence proof must withhold enablement.
The prepared rule initializes only at completed restoration/startlevel 100.
A hot installation after that event intentionally remains Unknown until a
separately authorized completed-startup cycle; no restart was performed here.

Motor integration remains in `santyr/dooya_blinds_openhab`. Require actual device
identity/zone mapping, protocol/direction/limits, fresh actual feedback,
post-command report correlation, manual hold/provenance, owner serialization,
provider/restart behavior and independently authorized global release. A policy
switch grants none of these. Preserve requested/reported positions and all
original observations. No physical behavior is qualified by browser or mock tests.

Rollback of a future authorized policy installation: first inhibit automatic
admission in the actual owner, retain saved choices and receipts, stop the
policy-only UI write endpoint, then restore the previous policy owner/config
package using reviewed file/managed ownership. Do not delete retained choices,
restore missed jobs, or change `OverrideSwitch`, night loads, greywater or feeders.
Removing policy inputs must fail closed. A software source merge is not an
installation and does not modify immutable running packages.

## Acceptance tracker

The maintained tests and final repair report record evidence separately from
live installation and physical commissioning. Required cases are:

| Area | Required regression |
| --- | --- |
| Scope | Four ON preferences + override ON blocks only Bathroom/Bedroom by this gate; daytime ON is identical |
| Overlay | Private-zone ON while paused preserves saved ON; override OFF does not enable a saved OFF |
| Isolation | Each preference changes only its addressed zone; loads and `OverrideSwitch` stay unchanged |
| Unknown | NULL/UNDEF/missing/unreconciled override blocks private zones; missing settings never enable |
| Stable inputs | Authoritative repeated reads retain all-night protection without last-change expiry |
| Persistence | Confirm explicit choices across restart; failed save/persistence/readback never confirms enablement |
| Generations | Pre-inhibition work and ON/OFF/ON work remain obsolete, including reconnect/restart |
| Groups | Expand actual membership, reject unknown/offline members, recompute effects for eligible subset |
| Observations | Partial and mixed reports remain individual; real changes invalidate position-bound advice; preview/ACK remain excluded |
| Manual work | Protection does not gate trusted manual requests or feedback; no automatic reversal or fabricated provenance |
| In-flight | No invented STOP; mock owner distinguishes own automatic work from unrelated manual movement |
| Release | Preference ON with global automation disabled or hardware uncommissioned sends zero motor commands |
| UI | Four heading switches, saved/effective/pending/error/unknown distinct, keyboard/touch, 1340×800 and 1280×720 |
| Lifecycle | Multiple clients reconcile; page/reload/tab/reconnect/restoration sends zero preference/motor writes |
| History | Original recommendations/receipts remain readable and never requeued when a gate reopens |
| Exclusions | Greywater/feeder behavior, household demand, night-load matrices and manual paths unchanged |

The canonical program tracker references this contract. Installation and
commissioning dependencies must remain incomplete even after source tests pass.
