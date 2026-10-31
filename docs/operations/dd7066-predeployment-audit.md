# DD7066 coordinated pre-deployment audit

Started October 24, 2026. This is the applicability and progress ledger for the
operator's DD7066 handoff, not a new household-model backlog. Preserve the five
current-source fixes and shade permissions in UI revision
`09b1a2e5d77c277a5866e98c21e53eb05379d7ea`. Adapter baseline:
`88e09b098cc65ec9a528b3dba0234d39b41209e2` (42 actual-module tests pass).

Target DD7066 P-Box, not DD7066M/DD7006. The existing Ubuntu/OpenHAB host has
OpenHAB 5.2.3-1, Mosquitto 2.0.18 and Python 3.12.3; both existing services are
active. No adapter service is installed. Hardware is not installed yet; its label, firmware, motor models,
RF inventory and compatibility are unobserved. No physical traffic, movement,
production service/configuration changes or automatic release is authorized by
this audit. Reuse the existing broker only after its actual endpoint/auth is
read back; an installed broker is not proof of a suitable anonymous endpoint.

The pinned PDF was actually retrieved and read: v1.03, revision 2022-03-17,
Git blob `973f2d224bb15a40933932085cb28db8d83be12d`, SHA-256
`39cd7ae5e4aa5da75b48c4735b723209bba023714b5eaa6f4915b8ceb4a9ac81`.
It does not certify exact DD7066 firmware. Its discovery example omits msgID,
reply-routing prose/examples conflict, and Report boot/sequence/measurement-clock
semantics are unproven. Strict correlation remains the default. An explicit pinned-only missing-ID
discovery compatibility profile has strict source/schema limits; it does not
relax read/write correlation or establish firmware compatibility. The adapter's
`docs/DD7066_COMPATIBILITY.md` records evidence and limitations;
`docs/DD7066_VENDOR_REQUEST.md` is an unsent clarification packet.

## Findings and repair disposition

All eight findings apply to adapter baseline 88e09b0. They are repaired in the
coordinated v2 producer/consumer change. The final verification record identifies
the exact committed pair; no earlier baseline pass is substituted for it.

| ID | Root cause | Repair and maintained regression |
| --- | --- | --- |
| D01 | MQTT binding ignores up/down configuration | on/off/stop mapping; actual OpenHAB 5.2.3 binding emits UP/DOWN/STOP and native percentages in disposable profile |
| D02 | Decimal arithmetic generated invalid calendar IDs | Calendar-aware monotonic high-water with locked private durable restart state; protocol calendar/concurrency/restart tests |
| D03 | Loose enum/JSON validation admitted bool/nonfinite values | Exact finite types, duplicate-key/size/depth limits, transactional inventory/profile validation; protocol/state tests |
| D04 | Poll list reset starved the tail of 26-device inventory | Fair retained cycle, paced requests and bounded cancellation/flood processing; actual Service run-loop tests at 30/60/600-second profiles |
| D05 | Bare queue entries lacked authority, identity and expiry | HMAC envelopes, monotonic TTL, durable dedup/no replay, commissioned source context and final locked policy check; command/service/owner tests |
| D06 | Separate LWT left per-shade retained history looking online | Composite provider/service/bridge/session consumer gating; actual Service SIGKILL and broker restart fixtures |
| D07 | Duplicate/delayed Report renewed apparent freshness | Original observation/watermark and known-order checks; never renew on duplicate/cache/heartbeat, preserve last-known uncertainty; state/history tests |
| D08 | Group/external commands bypassed zone ownership | Trusted authenticated per-member manual path, signed policy effective ACK and hard-disabled automatic release; queue/policy/UI integration tests. App/timer/third-party hardware inventory is still a release blocker |

Review also repaired an actual Paho publish/PUBACK lock inversion, bounded its
real outbound queue, retained operator STOP capacity after saturation, corrected
journal/policy-expiry dispatch races and prevented Vite from serving private owner
files. The HTTP regression uses synthetic keys and actual Vite.

## Ordered work

| Task | Software disposition | Remaining physical/installation boundary |
| --- | --- | --- |
| 0 Reconcile/research | UI 09b1a2e and adapter 88e09b0 baselines reconciled; exact available public PDF read; authenticated broker/binding versions read back | Exact DD7066 firmware API is unverified; vendor packet is an unsent draft |
| 1 Protocol/config | Strict transactional parser/correlation, durable IDs, pinned identity and supported single-axis profile implemented | Optional pinned no-ID discovery is explicit, not a demonstrated device capability; actual ports/timing/firmware pending |
| 2 State/outcomes | Observation v2 preserves original provenance; ACK/cache/target/uncertain/last-known distinct; durable historical restore only | Unseen delayed Report, RF measurement time, physical boot and actor remain unknown |
| 3 Command/policy queue | Signed expiring source-bound requests, no replay, STOP reserves and final policy lock implemented | No automatic release; external autonomous writers not inventoried |
| 4 Fair scheduling | Actual run-loop coverage, timeout/flood bounds, STOP cancellation and configuration refusal tested | RF rate/latency envelope requires physical evidence |
| 5 OpenHAB/MQTT | Real disposable 5.2.3/2.0.18 binding, ACL, LWT and restart tests maintained | No household mappings, credentials or ACLs installed/changed |
| 6 Zone/nightly policy | Existing preferences preserved; exact ACK sync, trusted manual independence, per-member groups and negative authority defaults implemented | Manual release requires individual commissioning; automatic path remains unreleased |
| 7 UI/observation | Partial inventory, preview isolation, manual result feedback and v2 source-bound history/provider collector implemented | Empty installation/provider mappings remain defaults; actual persistence not qualified |
| 8 Fake end-to-end | Actual Node owner → Python publisher → MQTT → Service → loopback UDP fake → Report → OpenHAB → current UI parser profile maintained | Synthetic traffic only; no real bridge, radio or motor observation |
| 9 Hardware | **Pending: operator confirms not installed yet** | Gates A–E require actual hardware and their separate supervised authorizations |
| 10 Final verification | Required commands and compatibility pair recorded in the final verification artifact | Source publication does not install a running package; scoped rollback below |

## Acceptance matrix

These map T01–T40 to maintained actual-module suites. A synthetic software pass
closes only that software behavior. Physical portions remain pending explicitly.

| IDs | Maintained evidence | Disposition |
| --- | --- | --- |
| T01–T07 | Adapter test_protocol.py/test_config.py; AES/calendar/source/correlation/transaction/profile cases | Software regressions; exact-model evidence still pending |
| T08–T10 | test_state_provenance.py/test_service.py; UI dd7066-shade-observations tests | Cache/ACK never measured position; known duplicates cannot renew freshness; unknown delivery age explicit |
| T11 | v2 observation/history + PostgreSQL tests and UI parser | Synthetic original individual observations retained; real remote/partial stop pending hardware |
| T12–T16 | test_command_contract.py/test_service.py/test_service_run.py | TTL/idempotence/generation/no-replay/STOP races covered; latency is a software bound |
| T17–T18 | test_service_run.py/test_service_mqtt_concurrency.py | 26-device fairness, unreachable devices, flood, queue/real-Paho bounds |
| T19–T23 | tests/integration/run_openhab_mqtt.py and run_signed_stack.py | Real binding/broker/Service with fake UDP source; no hardware certification |
| T24–T30 | test_command_contract.py plus existing shade policy tests and dd7066-execution-owner tests | Truth tables, committed inhibition, manual independence, no catch-up and owned STOP; automatic production release hard false |
| T31 | Command contract membership and Node manual batch tests; automatic request refusal | Per-member admission/results; no raw broadcast or automatic-release endpoint |
| T32 | Compatibility/vendor request and commissioning checklist | App/bridge timers/third-party writers unknown: unresolved automatic-release blocker |
| T33–T35 | shades-installation, shades-layout and shades-policy browser suites; policy/store unit suites | Both supported viewports, partial inventory, preview/gesture/lifecycle isolation and persisted multi-client preferences |
| T36 | Existing household planner/night-load owner/greywater and feeder scope suites | Prior exclusions and owner behavior preserved; no new pump/feeder writer |
| T37–T39 | DEPLOYMENT.md Gates A–E and commissioned epoch tests | Actual WAN/reboot/RF/per-device controls pending; replacement epoch cannot reuse old qualification |
| T40 | Adapter journal/queue and Node owner-ledger restart tests; actual broker/adapter restart integration | Historical evidence preserved, no motion queue restored; physical rollback not performed |

## Verification, rollout and rollback

Run adapter pytest in the tested Python/Paho/PyCryptodomex environment, then both
explicit disposable integration profiles. UI gates are npm ci, test:unit, build,
test:e2e and test:geometry under Node 22. Run the affected v1/v2 history and
PostgreSQL tests, policy owners, household exclusions and relevant receipt/native
replay suites with the workflow's immutable companion profile. Record each exit
code, skip reason, exact revisions, source hashes and non-overlapping result scope
in `artifacts/dd7066-predeployment-20261024.local/final-verification.json` and its
self-contained report. Test from a secure disposable checkout rather than relaxing
runtime source-permission checks or Vite's .codex exclusion.

Installation status: **nothing installed by this change**. Existing runtime
packages and original producers remain separate from this source pair. Manual
operation is prepared but disabled with the empty installation. Real-device
observation, supervised control, automatic release and thermal causal benefit
are all unqualified. The provider-history collector and Items are prepared,
uninstalled templates; no private household mapping was guessed.

A later authorized rollout starts read-only with an individually commissioned
inventory. Keep private profile/key/journal/publisher files together in an owned
0700 directory outside every served root; 0600 files alone do not prevent HTTP
exposure. Keep both automatic release and new motion disabled during rollback,
revoke the manual publisher, restore a compatible source/configuration pair,
preserve all historical receipts/observations under their original producer and
never replay retained/journaled requests. Do not reset pairing or mechanical
limits. See adapter DEPLOYMENT.md for Gates A–E and scoped service steps.

Bathroom/Bedroom automatic moves require authoritative OverrideSwitch OFF;
Kitchen/Living retain their independent permissions. Saved choices are not
rewritten at night. Manual paths and actual-report history remain independent.
Greywater and feeders stay excluded; existing load demand, manual controls,
night-load matrices, source-bound receipts and original producers are preserved.
