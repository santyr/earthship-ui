# Household consumption and battery storage

Source `a9eb2901340d6d057110b61886631d0afb64dd51` is deployed as
`4804d057d54b13e8ff4a93dc21e99f6db4f98192c853a1115637458efa478d75`.
The owned ML family activated on **2026-10-15 at 14:26:29 UTC**. All five
installed definitions, effective commands, three active timers, both score
calendars and public UI/model/forecast endpoints passed readback. The complete
current trained candidate `188a42a8` is unchanged. The clean, idle daily
checkout was advanced to the same source without changing or starting its unit.

## Meaning and provenance

The operator confirmed on October 15 that the only DC loads concern the
battery and solar-PV system. `openhab/household-energy-topology.json` retains
that declaration, effective from its recording at 13:36:41 UTC. It is current
operator configuration, not a measured zero DC load or a retroactive topology
assertion. Update it if household DC loads are installed.

Qualified inverter AC load represents household consumption only when its
original inverter-only/no-bypass/no-generator attestation and the operator's
AC-only declaration both apply. Net battery DC power separately identifies
charging and discharging, using the original validated sign, scale and unit
configuration. Charging does not increase the household consumption learning
target. Reported controller PV output remains distinct from potential solar
generation. System DC consumption and conversion losses remain unknown; the
model does not claim a closed power balance.

Every reading preserves original source identity, digest, acquisition clocks,
expiry and explicit age policy. Missing or expired data remains unknown.
Missing or unsupported optional topology withholds the total-household label
while preserving independent AC/storage observations. Supplied hash or
availability corruption refuses replay. Optional decoder failures cannot
disable unrelated household observations.

## Receipt and execution contract

Cycle sources/v6 retain the original topology declaration. The private
`earthship-household-power-flow-receipt/v1` sidecar binds the unchanged external
model-plan/v6 by semantic and canonical document hashes, plus its own runtime
and verifier source closure. Normal cycles retain it under an immutable
content-hash filename. Existing plan and battery outcome formats are unchanged.
The file-only replay command is:

```sh
python3 openhab/scripts/household_power_flows.py --receipt FLOW --plan ORIGINAL_PLAN
```

Replay reconstructs the original configured snapshot, checks source/runtime
closure, rederives flows and checks original files again. It has no database,
network, fitting or actuator path.

The rollout reached the original 31-entry scoring dispatch cap. No evidence
was deleted. Dispatch now accepts up to 63 explicitly pinned historical stages,
within the unchanged 128 KiB metadata bound. Current native scoring retains its
31 historical-model inference envelope; older stages keep independent rotating
worker opportunities. The actual package retains all 32 prior stages in
8,680 bytes. Deadlines, resource coordination and fitted numerical sources are
unchanged. Historical lifecycle retention remains future work.

## Verification and natural observation

After the single immutable review and correction pass, **1,892 regression
cases passed in 375.15 seconds**, including the 310 directly affected flow,
source, cycle and owner tests. Review corrections validated original battery
semantics, included the executing plan verifier and isolated optional decoder
recursion. The separate dispatch-capacity correction passed **227 affected
cases in 46.94 seconds**, including 32/63-stage roundtrips, complete historical
rotation, the original inference envelope and 64-stage refusal.

Normal preparation completed at 14:28:09 UTC. The first scheduled forecast
issued at **14:30:15 UTC** and the service exited successfully at **14:30:30**.
The retained flow receipt reported:

| Quantity | Observed value |
|---|---:|
| Household AC consumption | 292 W |
| Net battery charging | 705 W |
| Battery discharge | 0 W |
| Reported controller PV output | 1,039 W |
| System overhead / conversion losses | Unknown |

Receipt `52812b5762c883d498c61da75f93ed7ee5a17950ec4a8dd5a9900e793c9d47b2`
binds original plan
`dc7a106a9f3784d5e03e4b6c81ab6f3a2817723d4554a3d59a8211c9150834db`.
Pure replay and the exact deployed CLI returned identical results. The 42 W
difference between these observed quantities is not a qualified loss estimate.
Private rollout proof is in the existing common-cycle workspace under
`weather-energy-20261015/`; no extra forecast, score or fit was triggered.

## PV model follow-up

[PV forecast practice and recovery-day diagnosis](2026-10-15-pv-forecast-practice.md)
records the research, array geometry and remaining work. The source profile
`openhab/household-pv-system.json` records the quoted 4.2 kW DC rating,
approximately 165° azimuth and operator-measured 57.4° tilt above horizontal.
It retains the raw 32.6° inclinometer reading and horizontal-at-90° convention.
That profile prepares the next model; a new geometry-aware PV forecast is not
yet deployed. Rolling PV/load prediction, usable-energy calibration, action
outcomes and the full PR #3 architecture remain incomplete.
