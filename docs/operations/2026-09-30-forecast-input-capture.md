# Exact morning weather-input archive

## Why this is needed

The September 25–29 qualified charge-time/afternoon outcomes can be paired
with contemporaneous UI forecast companions, but those companions are not
proof of the exact raw fetch used by the original prediction. Their JDBC
receipts are roughly 0.10–0.13 seconds after the original prediction origin.
They preserve radiation/wind/precipitation/weather code but correct temperature,
omit daily raw radiation/cloud means and have no origin-bound raw input digest.
The private prediction records retain daily radiation but no complete raw
hourly snapshot. Later two-hour display refreshes fetch different weather.

Treat these historical UI companions as diagnostics, not strict original
forcing inputs. Do not backdate the 06:45 analytics capture, manufacture old
solar-context records, or assign a later revision to an earlier prediction.

## Prospective implementation and deployment

`forecast_input_capture.py` preserves the complete **parsed Open-Meteo response**
and exact public request URL before the daily worker assigns its prediction
origin. This is not the provider's original response bytes or a claim about
the provider's model issuance time. Raw daily/hourly values, units, timezone
and API metadata survive; no learned correction is applied to the archive.

The worker retains `weather_origin` in the existing private prediction record.
The optional public receipt field `weatherInputSha256` cross-checks the exact
archive identity. It is added only if the existing 1,024-byte receipt limit
allows it; existing BMS/solar origins are never evicted. If this optional field
is omitted, later joins require the retained private reference. Do not infer
an unbound reference from a nearby file or similar values. Private prediction
state still retains 30 dates; increasing that retention is a separate change.

Private storage is
`/home/sat/.local/state/forecast-intel/weather-inputs/YYYY-MM/<sha256>.json.gz`:

- Owned non-symlink directories, mode 0700; immutable owned files, mode 0600.
- Canonical finite JSON with a digest of the complete capture record, including
  capture time and request identity. A different later fetch has a different ID.
- At most 256 KiB decoded / 64 KiB compressed per record; bounded decompression
  and exact reference/date/digest validation on reads.
- Atomic no-replace installation with file/directory synchronization. Corrupt
  collisions are refused, never overwritten. Temporary staging files are removed.
- No historical backfill or automatic destructive retention. The real test
  fetch occupied 12,356 decoded bytes / 2,821 compressed bytes: approximately
  1 MiB/year at one similar capture per daily run, excluding reruns.

`capturedAt` is assigned after fetch and before serialization. The worker waits
for durable capture completion before assigning `temperature_issued_at` and
the weather receipt origin. The BMS source assessment retains its separate
original clock. Failed capture returns an explicit missing reference and a
static sanitized diagnostic; it never blocks or changes forecasts, calibration,
notification policy or controls. A capture alone is not a successful published
prediction or a qualified outcome. Feature consumers must still validate units,
target dates, source coverage and original publication identity.

The two installed files were exact-readback deployed on September 30 around
18:14 MDT while forecasting/shadow/training jobs were inactive. The previous
forecast worker matched source HEAD exactly (`f68d4179...`); its private rollback
copy remains at
`/home/sat/.local/state/forecast-intel/weather-capture-preimage-ZhRKuBX8`.
No unit, timer, OpenHAB configuration, model artifact or control was restarted.
The production archive directory will first be created by the natural daily
worker; no synthetic production prediction was issued for testing.

## Verification and next gates

315 affected Python tests and 26 forecast UI contract tests pass. Tests cover
exact raw round-trip, later/future revision refusal, private file/path safety,
corrupt collisions, size/decompression bounds, static failure diagnostics,
unchanged forecast values and the public receipt byte budget. A real 10-day /
240-hour fetch round-tripped exactly in an isolated temporary directory; a
separate installed-helper test also passed. Both test directories were removed.

The installed thermal consumer pin is now
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`
because its manifest includes `forecast_intel.py`. The retained 17:01 forcing
capture (`bb716882e2bb0d92...`) replays **exactly** under this explicitly pinned
runtime, without action evidence or a new publication. The accepted artifact
is unchanged and its training revision still differs from the runtime pin.
This is behavioral replay evidence, not a natural timer or training receipt.

The exact v2 production journal schema audit still passes. A fresh, separate
process using the actual installed `ActionJournal` successfully reads seven
effective actions / three modes over January 1–now; this broader read interval
is not the earlier narrower two-action/one-mode diagnostic. There were no
production writes. The first combined verification command mistakenly unpacked
the action tuple as `(actions, modes)` and failed; the corrected check calls
the two real installed methods separately. Transient verification units were
collected; no failed check is claimed as evidence.

Next required checks:

1. October 1 06:40 natural morning capture: exact private reference, archive
   digest, raw request/site/units and capture-before-origin ordering. Verify
   the optional public digest if present; never silently accept a missing link.
2. Pair future qualified charge/full-charge/sunset outcomes only with those
   bound original snapshots and original solar/BMS clocks. Score chronological
   joint-model candidates; do not promote a five-day fit.
3. The natural shadow gate is now closed by the September 30 19:01 run below.
   Training remains October 1 06:50. Record actual whole-run time/memory/swap then.
4. Future signed-trial/recovery checks must requalify against this current
   installed pin, not reuse the earlier `5e69e941...` qualification unchanged.

The thermal collector and all six source release flags remain off. Production
journal vocabulary is already v2; do not rerun the v1-only migration preflight.

## September 30 natural shadow gate closed

The existing timer invoked `thermal-model-shadow.service` naturally at 19:01:48
MDT, invocation `0dd71b70ece54e30859c8c22f4ddf0ce`. It exited zero at 19:01:51;
no manual invocation, timer reset, model training or collector activation ran.
The finite watcher ended after observing the actual new invocation's terminal
state, not an observation timeout.

Fresh readback matches the published Item, local `shadow.json`, original forcing
capture and exactly one JDBC receipt. Decision:
`2026-10-01T01:01:50.144198Z`; JDBC receipt:
`2026-10-01T01:01:51.825Z`. The output is still `shadow` / `low` confidence.
Its canonical SHA-256 is
`138ff098ff6bf6925c17acaf10d3081ba70ff87cd99b27e8b28ae86fd6b2aee8`.
The private capture is
`/home/sat/.local/state/thermal-intel/forcing-captures/2026-10/20261001T010150Z-138ff098ff6bf692.json.gz`.

Exact as-issued replay passes against the current `7f57eb3f...` installed runtime.
Accepted-artifact SHA-256 remains
`66bc754135da743f402e00c34e07d8ffaeb7c8e97061873e06808619fe734353`,
identical to the retained 17:01 capture. The artifact's training revision remains
`a4a68a17...`, distinct from the current runtime; no new training or skill is
implied. The next natural shadow is September 30 21:01:48 MDT. Training and
original morning weather-input capture gates remain October 1 06:50 / 06:40.
