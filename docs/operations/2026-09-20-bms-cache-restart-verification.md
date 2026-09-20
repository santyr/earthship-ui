# Atomic BMS observer cache-restart qualification — September 20

The approved observer restart check passed using only a brief disable/re-enable
of `hex_bms_soc_evidence`. No rule definition, acquisition/poller setting, health
Item, control, persistence policy or stored history was changed. No source value
was injected, no rule was run manually, and OpenHAB was not restarted.

## Why a separate check was needed

A bounded read-only scan of public.item0613 from September10 through
September20 13:42:40.921044Z returned16006records. All parsed with the production
parser:16004valid/ok, one initial input_unavailable and the previously qualified
input_stale/source-recovery event. They shared a single observer epoch and had
no source_unavailable transitions. Healthy history was not treated as proof of
fault or restart handling.

## Lifecycle and persisted evidence

Before the check, the observer was IDLE, its source exactly matched the tracked
script SHA256b55d4e002379087fb5cc8f39dc56761951f3c87a4e1519d27bfc680e752d824b,
and its current atomic receipt was valid/unexpired. BMS communications wereOK
and DevicePresent1.

Only the observer was disabled at13:46:21.865886Z and re-enabled by
13:46:21.890637Z. Re-enabling was protected by a finally block, including an
ambiguous disable acknowledgement. Its original definition was preserved.
Natural incoming source events, not a forced execution, initialized the new epoch.

| Persisted UTC | Epoch | Status/reason | Producer recorded UTC |
| --- | --- | --- | --- |
|13:45:45.103137|864142d5-99ee-4b7a-b5fc-e6a96e7274d8|valid/ok|13:45:45.100|
|13:46:25.938124|2b174eb7-ac22-4289-aebf-8140eae1135e|unavailable/input_unavailable|13:46:25.936|
|13:46:36.133147|2b174eb7-ac22-4289-aebf-8140eae1135e|valid/ok|13:46:36.128|

The first new-epoch record had null raw/scale/expiry/SoC fields. Its recovery used
raw observedAt13:46:36.128Z and scaleObservedAt13:46:31.024Z, both after the
new-epoch unavailable record, with SoC84 and exact expiry13:48:31.024Z.
It did not hydrate cached pre-restart measurements as fresh observations.

Production `parse_evidence` accepted the persisted records, and
`build_soc_intervals` left the entire10.197147-second interval from new-epoch
unavailable recordedAt through recovery persistence time unqualified. No segment
bridged it and no retired observer epoch reappeared in the checked window.
The old record remains historical evidence; nothing was deleted or relabeled.

## Final scope and status

- Observer IDLE/NONE and unchanged; BMS communicationsOK, DevicePresent1.
- Definition fingerprints unchanged for Schneider safety, BMS scaling,
  communications watchdog, smoothed runtime, greywater and night-load control rules.
- Both greywater pumps remainedOFF. No new observer ERROR/Exception in the
  checked07:46–07:49MDT log window.
- The existing natural thermal training process remained active and undisturbed.

This closes the live observer lifecycle/private-cache restart check. It is not
an induced physical BMS fault or a full OpenHAB process restart. Independent
power-source health and physical fault qualification remain separate unfinished
work; previously verified source-pause expiry/recovery and full-day SoC coverage
remain separate evidence as well.
