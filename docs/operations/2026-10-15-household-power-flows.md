# Household consumption and battery storage

The operator confirmed on October15 that the only DC loads are associated with the battery and solar-PV system. The current declaration is retained in `openhab/household-energy-topology.json`, effective from the time it was recorded (13:36:41UTC). It describes current topology and must change if household DC loads are installed. It is operator configuration, not measured power or hardware authorization.

Household consumption is the source-qualified inverter AC load when the original inverter-only/no-bypass/no-generator topology applies. The operator's separate AC-only declaration permits calling that quantity household load. Net battery DC power retains its positive-charging sign: positive becomes battery charge, negative becomes battery discharge. Charging is storage, not an addition to the household consumption learning target. Controller PV output remains its own measured quantity, not total available solar. System DC consumption and AC/DC conversion losses remain unknown; the balance is not claimed closed.

The new pure power-flow model consumes the same immutable configured snapshot used by household forecasting. Each original measurement retains its source identity, digest, acquisition clocks and explicit age policy. Missing or expired measurements remain unknown. Missing or unsupported operator topology retains the known AC and storage observations while withholding the total-household label. Supplied original hashes or availability that disagree refuse replay. No capacity calibration, action effect, reserve permission or actuator authority is introduced.

Cycle sources/v6 add the before-issue operator declaration. A separate compact `earthship-household-power-flow-receipt/v1` binds the unchanged external model-plan/v6 by semantic and canonical document hashes, plus its own model/runtime source closure. The normal cycle retains this private sidecar under an immutable content-hash filename. Original cycle-source versions retain their previous outputs. Neither the existing plan format nor battery outcome format changes, preserving current chronological evaluation.

The private CLI is file-only:

```sh
python3 openhab/scripts/household_power_flows.py --receipt FLOW --plan ORIGINAL_PLAN
```

It validates the external original snapshot/source closure, rederives every flow, checks its own runtime and original file bytes again, and prints only the reconstructed receipt. There is no database, network or action path in this replay.

This establishes distinct consumption/storage inputs for subsequent rolling energy models. Weather-driven response, learned load patterns, calibrated usable energy and qualified action outcomes remain unfinished. The Open-Meteo radiation field used by the next energy model represents the preceding hour's mean, so future energy integration must use those intervals and preserve partial-hour boundaries ([provider documentation](https://open-meteo.com/en/docs?past_days=1)).

Initial verification:13 new flow tests failed before implementation;66 affected flow/energy cases then passed. Six original-plan/CLI tamper cases reproduced the missing receipt implementation;19 combined flow/receipt cases passed. Four collector/cycle/package cases failed before integration, then263 affected cases passed in63.25seconds. Broader regression, immutable review and deployment evidence remain pending.

The broader run passed1,880 cases and found two obsolete cycle-source/v5 assertions in owner-policy tests. Their original receipt/hash/clock checks remain; only the expected current source version changed to v6. An additional RED regression found that a malformed clock inside an otherwise readable optional topology declaration erased the flow observation. It now leaves the household-DC scope unknown while preserving qualified AC/storage readings. All82 focused flow/owner cases pass after those corrections. The final broad run and one immutable review are pending.
