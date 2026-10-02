# October 2 forecast recovery and radiation activation

## Forecast outage and recovery

Production weather refresh last succeeded at 02:05 MDT. The 04:05 fetch timed
out; later weather and thermal jobs failed with `Temporary failure in name
resolution`. The weather UI's four-hour freshness limit correctly withheld the
old forecast. This incident was not the separately identified shade-transition
collision. At 08:13 MDT, host DNS resolved Open-Meteo and an HTTPS request
received an HTTP response; the forecast units have no private network or IP
deny configuration.

Under the standing deployment authorization, only `forecast-json.service` and
`thermal-model-shadow.service` were started at 08:14:34 MDT. Both exited zero.
Readback of `Forecast_10Day_JSON` returned ten days generated at
`2026-10-02T08:14:34-06:00`. `Thermal_Model_JSON` returned 72 trajectory points
generated at `2026-10-02T14:14:36.083052+00:00`, with low/reconstructed confidence.
The actual UI parsers accepted both as `ready`, with ten displayed days,
14 hourly source points, and 72 thermal trajectory points. This is source and
parser verification, not a browser screenshot or a claim of model graduation.

The new original forcing capture is
`20261002T141436Z-b62ec2084fc3986a.json.gz`. No notification, collector, model
training or household control was activated. The existing timers remain in
place; this recovery does not change retry cadence or prevent another DNS
outage. DNS outage root cause below name resolution was not established.

## Approved radiation capture activation

Noninteractive sudo was available on October 2, removing the previous
privileged activation blocker. The exact guarded block in
[the approved radiation plan](2026-10-01-radiation-receipt-candidate.md#pending-privileged-activation)
was executed after confirming four valid temperature streams, valid rain, an
absent radiation endpoint, and all seven exact reviewed SHA-256 pins. The
drop-in destination did not exist; no unrelated configuration was overwritten.

The installed root drop-in retains SHA-256
`7bcbeba80fbad97de88652e5401802cc9612dbc62e91588e026fd9fb403feceb`.
Only `weather.service` and `rtl_weather.service` restarted at 08:16:31 MDT;
their new main PIDs are 80148 and 80151. Both are active, with zero automatic
restarts. OpenHAB remained active at PID 1696; it was not restarted by this work.

Natural, unmodified RF ingress recovered all four temperature streams and rain
by `2026-10-02T14:17:29.695129+00:00`. The existing receiver slot named
`bedroom` still refers to sensor 223 physically located in **Office Hallway**;
this deployment does not reclassify it as Bedroom thermal evidence.

Two observed natural radiation receipts advanced sequence 3 to 4:

| Decoder UTC time | Receiver UTC time | Raw lux | Derived W/m² | Valid until UTC |
| --- | --- | --- | --- | --- |
| 14:17:08 | 14:17:09.177360 | 4882 | 38.53 | 14:19:08 |
| 14:17:24 | 14:17:24.904205 | 4712 | 37.19 | 14:19:24 |

Both are station 206, `Fineoffset-WH65B`, `status=valid`, `reason=accepted`,
with `timeBasis=radio_decode_utc`, radiation epoch
`0da90b57-2e63-4556-b962-4d8b35231057`, and the exact documented
`round(min(lux / 126.7, 1200), 2)` conversion. Their expiry is anchored to
original decoder time, not polling time. No synthetic packet was sent.

## Remaining gates

Radiation capture is currently **volatile receiver state**, not a durable
OpenHAB/JDBC evidence history. Actual live expiry/fault recovery and reversible
activated rollback remain separate from the earlier isolated tests. The
file-owned durable Item/writer, exact mapping/restricted grant, strict daily
reader, restart continuity and complete clean day must be qualified before a
learner consumes this new stream. October 2 contains a restart boundary and
must not be presented as a complete continuous radiation day.

The thermal collector remains off. A truthful reviewed question, exact changed
policy recovery, authorized signed Primal trial and bounded user-service release
remain required. The zero-duration shade schedule fix still awaits its specific
design approval; DNS recovery does not close that independent defect. Supporting
Energy publication also retains its physical/JVM recovery and reversible release
gates. No household control or new training label was written.
