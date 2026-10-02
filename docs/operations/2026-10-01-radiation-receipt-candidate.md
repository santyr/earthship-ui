# Default-off radiation receipt candidate

The approved source candidate extends the existing weather receiver rather than
reusing the unrelated latest-only Lightning Goats exporter or adding a second
RF process. **Its exact five-file extension is now installed but inactive**, as
qualified below. No OpenHAB Item, JDBC mapping, grant, service override, weather
restart or forecast/learning activation was made.

## Contract

`rtl_weather.py` forwards original `light_lux` and, when present, the decoder's
UTC `time` as `radio_decode_utc`. The existing numeric `solarradiation` conversion
and all other legacy fields remain unchanged. No send-time replacement is used
for missing source time. The receiver observes raw HTTP arguments before the
legacy handler can select cached fallback values.

The radiation policy explicitly selects station ID 206 and a 1–300-second
lifetime (proposed 120 seconds). Both WH65B/WH24 decoder labels are accepted,
with the original label retained. The closed receipt includes source identity,
process epoch, sequence, raw lux, derived W/m², conversion provenance, original
decode time, receiver time and expiry. Conversion is the existing
`round(min(lux / 126.7, 1200), 2)`; raw lux is bounded to 0–200,000. This is
**lux-derived irradiance**, not a calibrated pyranometer or sensor measurement
timestamp. HTTP arguments are trusted local ingress, not cryptographically
authenticated radio messages.

Expected-source missing/duplicate/invalid identity, lux, conversion or timestamp
creates an invalid barrier at the HTTP observer. Foreign identities/models
cannot renew or poison the configured stream. Decode time must be in the actual
rtl_433 `-M utc` format `YYYY-MM-DD HH:MM:SS`, no more than five seconds ahead
and less than the policy lifetime old. Expiry is bounded by both original
decode age and receiver time; its monotonic deadline deducts transport delay.
The existing relay still filters incomplete RF packets; filtered packets do
not create HTTP barriers, and accepted evidence expires without new receipts.

Identical decode timestamps/values do not renew evidence. Conflicting or
regressing source times invalidate it; replaying the previous good packet cannot
recover a fault. A later original packet with the same value (including zero)
is accepted. Getter reads never mint observations. Clock rollback/process
changes reset the volatile epoch and withhold values; in-process high-water
marks survive resets. Errors are sanitized and never prevent the legacy weather
handler from running.

The optional `/radiation_evidence` GET endpoint is localhost-only, `no-store`,
and volatile. Policy loading rejects duplicate keys, unsafe file types,
symlinks, non-owned/group-or-world-writable files, oversized content and
unsupported schemas. No policy is read unless
`WEATHER_RADIATION_EVIDENCE_ENABLE=1` explicitly; the WSGI entrypoint has **no
implicit radiation enable or policy fallback**.

Proposed private policy (owned by receiver user, mode 0600):

```json
{"version": 1, "sensor_id": 206, "validity_seconds": 120}
```

Its absolute path would be supplied as `WEATHER_RADIATION_EVIDENCE_POLICY` only
in a separately qualified deployment. Existing temperature/rain defaults are
unchanged. Do not copy the whole repository into the installed thermal runtime.

## Release gates still open

1. Exact source hashes, private narrow backups, unchanged service posture and
   isolated candidate/rollback now qualify. Actual original decoder format
   remains to be verified from natural radiation ingress, not reconstructed from
   the other project's normalized latest-only export. Do not restart OpenHAB.
2. The reviewed extension, ingress metadata and private policy are staged off.
   Explicitly activate during a bounded weather-service window. Require
   natural raw lux/derived watts receipts, unchanged temperature/rain behavior,
   zero/delayed/malformed/expiry/recovery behavior and no getter renewal.
3. Qualify a file-owned evidence Item/Thing and change-only-safe JDBC history,
   with exact mapping/least-privilege grants and restart/continuity gates. This
   volatile endpoint alone is not a historical collection pipeline.
4. Define a strict radiation interval/day reader and require complete clean days
   before forecast scoring/calibration uses this stream. Do not backfill source
   qualification from cached numeric irradiance history or another field's health.

Regression-first tests cover the pure receipt, collector, real Flask legacy
parity, default-off configuration/WSGI and RF forwarding without network/RF I/O.

The final focused weather suite plus permission-sensitive regression checks
passed **345 tests** (umask 022; bytecode and pytest cache disabled). The initial
broader Python run had 2,891 passes, six skips and nine failures: three
permission-fixture failures caused by inherited umask 077 passed on that
rerun; the unchanged persistence-source fixture lacks the newer runtime
evidence exclusion, and five messaging integration tests require the absent
`websockets.sync` dependency. Those remaining six unrelated suite failures
are not claimed resolved by this candidate. No dependency was installed or
unrelated production configuration changed to hide them.

## October 1 broader regression closure

The later [Primal source qualification](2026-10-01-primal-compatibility-candidate.md)
corrected the stale persistence fixture and made the negative-permission
fixtures explicitly chmod their task-only directories. The existing cached
`websockets` package was supplied on test PYTHONPATH, not installed into the
runtime. The combined suite now passes 2,935 tests and 74 subtests, with six
optional integration skips, under umask 077. This closes those suite failures
without changing production persistence or the default-off radiation boundary.

## October 1 exact inactive installation and rollback qualification

At `2026-10-01T18:28:43.314231Z`, only the reviewed three radiation modules,
WSGI hook and five-line radio forwarding addition were atomically installed
under `/home/sat/bin`. The radio diff adds only original `light_lux` and optional
`time` forwarding; the sensor-223/channel-2, indoor/north-wall, model-label
normalization and optional project observer paths remain intact. No shared
thermal scripts, model, OpenHAB definition, systemd unit or control was changed.

The exact nine-file preimage and five-file candidate are retained mode 0600
under the private directory
`/home/sat/.local/state/weather-radiation-rollback-qRdObu`. Its independently
recorded `preflight-manifest.json` SHA-256 is
`b4cc03aece66515a8a1ac13978f48670f0113b5e33cfdbebffdd5793507c932b`.
This is a narrow source recovery point, not a complete receiver mutable-state,
OpenHAB, signing-authority or off-host backup. Existing six temperature/rain
modules and `weather.py` were backed up but not changed.

| Narrow source | Installed SHA-256 |
| --- | --- |
| `rtl_weather.py` | `a22f458d563ab5e95c67e69cc1e39060a7212708b37afc7d80ce8d686e7c967d` |
| `weather_evidence_wsgi.py` | `f36b3badca148a2f3bfc0df4c1a96d49661a2e85f3e3e2bdf6d0b53bf4f8548d` |
| `weather_radiation_config.py` | `2b7afe8cefff6254810768721d2a216159f73f62abca232a7e4fd3fb59d8b95c` |
| `weather_radiation_evidence.py` | `f84b7ff6d1247fe4d4b9da52724a63b93dc5d5ee4568fcc77c2ae51f455c34bb` |
| `weather_radiation_receiver.py` | `c4ff6cdede9ae9448c57d7223be106687c0fcc4206fd64b08201221a50e2a550` |

The actual preimages were rehearsed in separate working copies: original WSGI,
candidate with radiation unset, candidate explicitly enabled, then exact source
rollback with the three new modules removed. All four produced identical legacy
read responses and saved fixture state; all four temperature streams and rain
were valid. The enabled fixture returned original lux/derived watts, while
disabled and rollback fixtures returned 404. Three AST-only radio comparisons
covered both outdoor decoder labels and sensor 223. RF execution, network,
production mutable state and OpenHAB writes were blocked throughout. The copied
policies were observational configuration; only dummy credentials were used.
The fixtures were removed, not retained as observations.

`/home/sat/.config/hex/weather-radiation-policy.json` is installed mode 0600,
owned by sat, parses as station 206 with a 120-second lifetime, and has SHA-256
`01832c2f720efb649d4765cefa4dfb3233ac588ef3a92931ff3ef676a3e09098`.
Its presence does not enable capture. The weather master's radiation settings
remain absent, and the root activation drop-in is absent.

Both live service main PIDs remained unchanged: weather 1607215 and radio
119092. Gunicorn has no automatic reload flag. All four natural temperature
streams and rain were valid before/after staging; `/radiation_evidence` still
returns 404. No signal, service restart, OpenHAB restart or equipment command
was issued. These processes have not reloaded the new files; an unrelated
future radio restart can forward the additive metadata, but radiation stays
off without its explicit weather setting.

The isolated weather slice passed **100 tests in 0.32 seconds**. The complete
discovered Python suite then passed **3,029 tests and 74 subtests**, with **six
optional skips**, in 237.82 seconds, using the exact installed stdin signer
and explicitly supplied Solar_PV/dedicated dependency paths. This does not
qualify natural radiation ingress, its durable historical pipeline, a clean
source day, forecast scoring or model promotion. Task-owned test resources are
removed after terminal verification; the narrow private backup is retained.

## Pending privileged activation

**October 2 update:** this historical activation blocker is closed. The exact
guarded block below passed once noninteractive sudo became available, and
natural station-206 radiation plus all existing temperature/rain streams
recovered. See [activation evidence and remaining durable-history gates](2026-10-02-forecast-recovery-and-radiation-activation.md).

Noninteractive sudo currently requires a password. No source-level implicit
enable fallback or alternate receiver was added to bypass that boundary.
The existing single weather/RF system services are retained; adding parallel
user services would contend for the HTTP port or RF device. Model/collector
user units elsewhere remain unchanged.

The reviewed two-setting template is
`deploy/weather-radiation-evidence.conf`, SHA-256
`7bcbeba80fbad97de88652e5401802cc9612dbc62e91588e026fd9fb403feceb`.
When ready for a brief weather telemetry interruption, run this **one guarded
block**, without copying terminal prompts. It refuses an existing/dangling
destination and changed reviewed input files. It restarts only the two weather
services, not OpenHAB, and does not enable forecast learning or any control:

```bash
sudo bash <<'RADIATION'
set -euo pipefail
test ! -e /etc/systemd/system/weather.service.d/radiation-evidence.conf
test ! -L /etc/systemd/system/weather.service.d/radiation-evidence.conf
sha256sum --check <<'PINS'
7bcbeba80fbad97de88652e5401802cc9612dbc62e91588e026fd9fb403feceb  /home/sat/earthship-ui/deploy/weather-radiation-evidence.conf
01832c2f720efb649d4765cefa4dfb3233ac588ef3a92931ff3ef676a3e09098  /home/sat/.config/hex/weather-radiation-policy.json
a22f458d563ab5e95c67e69cc1e39060a7212708b37afc7d80ce8d686e7c967d  /home/sat/bin/rtl_weather.py
f36b3badca148a2f3bfc0df4c1a96d49661a2e85f3e3e2bdf6d0b53bf4f8548d  /home/sat/bin/weather_evidence_wsgi.py
2b7afe8cefff6254810768721d2a216159f73f62abca232a7e4fd3fb59d8b95c  /home/sat/bin/weather_radiation_config.py
f84b7ff6d1247fe4d4b9da52724a63b93dc5d5ee4568fcc77c2ae51f455c34bb  /home/sat/bin/weather_radiation_evidence.py
c4ff6cdede9ae9448c57d7223be106687c0fcc4206fd64b08201221a50e2a550  /home/sat/bin/weather_radiation_receiver.py
PINS
install -o root -g root -m 0644 /home/sat/earthship-ui/deploy/weather-radiation-evidence.conf /etc/systemd/system/weather.service.d/radiation-evidence.conf
systemctl daemon-reload
systemctl restart weather.service
systemctl restart rtl_weather.service
systemctl is-active --quiet weather.service
systemctl is-active --quiet rtl_weather.service
RADIATION
```

Tell Hex when the block succeeds. A changed hash, existing drop-in or failed
service command is a stop condition, not permission to overwrite or retry
blindly. Afterward Hex must verify the new processes, four temperature streams,
rain continuity and natural station-206 raw-lux/strict decoder-time receipts;
new receiver epochs make the activation day partial. No synthetic packet may
be sent to the live `/weather` endpoint to manufacture acceptance.

If recovery is needed, first recheck the exact installed candidate hashes and
private preimage manifest. Restore only the reviewed WSGI/radio preimages and
reload their verified service processes; do not replace `weather.py`, established
temperature/rain configuration or mutable `previous_data.json`. The original
WSGI ignores the radiation environment and leaves the existing evidence
extensions intact. Any root drop-in change requires the operator; do not delete
unverified root files or existing history. The isolated exact-file rollback
above is not a claim that a live activated rollback has already been exercised.
