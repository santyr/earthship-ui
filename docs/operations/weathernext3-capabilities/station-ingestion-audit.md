# WS-2902 data gathering audit

The outdoor decoder and principal unit conversions check out, but the complete
pipeline cannot yet be described as correct. Confirmed defects affect derived
rain products, pressure naming, freshness reporting and counter recovery.
This was a read-only audit of the running installation on October 22, 2026.
No receiver process was restarted, no RF device was opened, and no live weather
state or hardware was changed.

The active chain is `rtl_weather.service` → `/usr/local/bin/rtl_433` →
`/home/sat/bin/rtl_weather.py` → local HTTP `/weather` → Gunicorn
`weather_evidence_wsgi:app`/`weather.py` → OpenHAB HTTP channels → JDBC.
The relay matches the repository copy byte for byte. The installed decoder reports
`25.02-17-g8e813dda`. Its local C source has no Git metadata; actual binary replay,
rather than an assumed source checkout match, verifies the decoding below.

## Confirmed findings

| ID | Finding and evidence | Consequence and required correction |
|---|---|---|
| AW01 | `rtl_weather.py:224` converts WH32B `pressure_hPa` directly to `baromrelin`; `weather.py:598` and the live `pressureRelative` channel call it relative pressure. No sea-level adjustment occurs. Live readback was approximately 23.89 inHg. | This is station pressure under a relative-pressure identity. Preserve station pressure and its history explicitly. A separate sea-level product needs a declared, validated correction; renaming does not perform that correction. |
| AW02 | `weather.py:414–428` sums an hour of rain differences and publishes that amount as `RainFallHourlyRate`, whose live Item unit is `in/h`. An isolated case with 0.10 inch 40 minutes ago still reports 0.10 in/h. | Separate the rolling-hour amount from the documented rate definition. A rate needs its own window, timing, completeness and freshness semantics. |
| AW03 | `weather.py:440–445` uses ISO week numbers. Offline replay retains 2 inches across Sunday midnight and clears it on Monday. Its event accumulator resets after one dry hour (`:452–472`). | Weekly and event products differ from Ambient's definitions. Migrate their identities or implement the intended definitions without reinterpreting old history. The daily model's separately declared scientific wet episodes are a different product. |
| AW04 | `weather.py:505–528,640–655` renews model-level health even when field values come from old fallback state. Existing isolated tests also reproduce acceptance of nonfinite temperature and mixing unpinned WH32B identities. | “Health OK” does not prove fresh, identified, valid observations for every field. Keep field-level validity and source identity; do not renew old values as new evidence. The stricter receipt paths provide separate protections and must remain authoritative for qualified learning. |
| AW05 | `weather.py:398–410` calls a small counter decrease noise, but `:489–491` still changes the baseline. Replaying `100 → 99.99 → 100` creates 0.01 inch of new daily rain. | A rejected decrease must not become a lower accumulation baseline. A genuine reset needs a declared discontinuity, not a fabricated increment when the old counter returns. |
| AW06 | `weather.py:383–394` holds the old baseline after a jump over 0.5 inch. `weather_rain_receiver.py:69–82` does the same. Replaying `100`, a six-hour gap, then `101,101,101.01` leaves the legacy total at 100 and subsequent strict receipts invalid. | The fixed per-packet guard has no post-gap recovery. Retain an unknown-gap barrier, then use a tested recovery state to establish a new baseline from natural consistent packets. Merely raising the cap can admit spikes and still fails after a larger genuine gap. |
| AW07 | The relay and legacy receiver clamp lux-derived radiation at 1200 W/m². The strict radiation contract reproduces that same conversion. Raw lux is retained separately. | Values above 152,040 lux lose amplitude in the legacy watts field. Keep original lux; evaluate a versioned modest bound increase consistent with the station's documented light range and downstream contracts. Preserve the original conversion for old models and receipts. |

The rainfall definitions used for comparison come from the
[WS-2902 manual](https://ambientweather.com/mwdownloads/download/link/id/567/)
and [manufacturer support](https://ambientweather.com/support/ws-2902-weather-station-support):
nominal tip depth 0.01 inch (0.254 mm); rate uses the last ten minutes multiplied
by six; hourly rain is a one-hour amount; the week starts Sunday; event reset
uses a 24-hour accumulation criterion. The old manual prints inconsistent metric
and inch event thresholds; support specifies 1 mm (0.039 inch). The event replay
uses one inch only two hours earlier, so that typo cannot explain the failure.
The manual distinguishes station pressure from sea-level relative pressure.

Ambient also documents the [126.7 lux per W/m² sunlight approximation](https://ambientweather.com/support/ambient-weather-station-support/).
That factor is consistent with this relay. Its variable-spectrum approximation
and our additional clamp must not be described as independently calibrated
physical irradiance. Console calibration settings are not read by this RF path;
no agreement with a user's nondefault console offsets or gain settings was established.

## What passed

- Eight synthetic demodulated frames were decoded by the **installed binary**
  using its offline `-y` option. Both WH24 and WH65B heuristic labels passed at
  tip counts 0, 1, 10,491 and 65,535. The relay recovered the same 0.254 mm tips
  and normalized wind values from both labels. Temperature, humidity, direction,
  lux and UV outputs matched the constructed frame values. Four additional
  malformed frames separately tested CRC and checksum rejection under both
  heuristic labels; none produced a decoded observation.
- Outdoor station ID 206 is filtered in the relay; foreign, missing and wrong-type
  identities are covered by tests. The WH24 scaling correction is necessary:
  [upstream decoder source](https://github.com/merbanan/rtl_433/blob/master/src/devices/fineoffset.c)
  uses different rain and wind factors for those labels.
- Celsius/Fahrenheit and metres-per-second/mph conversion are consistent. Live
  OpenHAB wind channels declare mph, rain-depth channels inches and pressure inHg;
  the audit found no additional mph-to-m/s conversion at those channels.
- The live SDR process uses 914.98 MHz, 250 ksample/s and UTC decoder timestamps.
  The manual specifies nominal 915 MHz. Natural outdoor reception was active;
  a second SDR reader was unnecessary.
- Live raw rain evidence matched the relay's counter convention. Its snapshot
  reported valid ID 206 with zero recorded drops, jumps or invalid packets.
  OpenHAB retained the original JSON envelope. This is a timestamped readback,
  not certification of all historical intervals or physical gauge accuracy.
- **93 isolated relay/receiver/receipt tests passed** under the host interpreter,
  including the receiver characterization cases that require `flask_cors`.
  Six additional legacy numerical cases and one strict-counter recovery case
  reproduced the findings above without production state access.

## Disposition

Keep the raw, source-bound observations distinct from the derived legacy fields.
Do not train on legacy rain-rate/week/event totals or compare the mislabeled
station pressure with forecast sea-level pressure. Preserve unknown gaps and
original history. Receiver corrections require their own source-bound tests,
compatible Item/report migration and release readback before being described as
fixed. The ordinary-capacity preference applies to byte/row limits supported by
measured workloads; it does not justify weakening physical or freshness checks.

[Machine-readable verification](station-ingestion-audit.json) pins the evidence.
Private originals include the manufacturer PDF, exact installed scripts, binary
identity, offline frames, source manifests and timestamped live readbacks. These
must remain available with the capability experiment evidence.
