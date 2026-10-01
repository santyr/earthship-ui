# Default-off radiation receipt candidate

The approved source candidate extends the existing weather receiver rather than
reusing the unrelated latest-only Lightning Goats exporter or adding a second
RF process. **It is not installed or enabled.** No OpenHAB Item, JDBC mapping,
grant, service override, weather restart or forecast/learning activation was made.

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

1. Recheck exact installed relay/receiver/WSGI hashes and actual decoder timestamp
   format; privately back up those narrow files, preserve RF/HTTP service posture
   and exercise rollback in isolation. Do not restart OpenHAB.
2. Install only the reviewed extension and ingress metadata change, first off;
   then explicitly activate during a bounded weather-service window. Require
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
