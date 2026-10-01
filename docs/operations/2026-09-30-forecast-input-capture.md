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

## September 30 21:02 natural shadow follow-through

The next actual timer invocation began at **21:02:48 MDT**, not the previously
displayed 21:01 planning time. Invocation
`bc088a6d067b4c4ea2d2312d135b6a67` exited successfully at 21:02:51, status zero,
with 2.129158 seconds of CPU usage. The service is terminal/inactive with no
main PID; it was not manually rerun, restarted or mistaken for a running job.
Memory/swap peak properties are unset for this invocation and are not claimed.

The Item, local `shadow.json`, verified original forcing capture and exactly
one JDBC receipt match. Decision is `2026-10-01T03:02:50.049882+00:00`; original
JDBC receipt is `2026-10-01T03:02:51.725+00:00`. Output SHA-256:
`0f26b44311f20bd12a140ec2496800a5e0abad75935797efa5a24676c5a6c8eb`.
Private capture:
`/home/sat/.local/state/thermal-intel/forcing-captures/2026-10/20261001T030250Z-0f26b44311f20bd1.json.gz`.

The complete capture reproduces exactly under installed manifest
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/replay-thermal-forcing.py \
  --runtime-root /home/sat/openhab/scripts \
  --capture /home/sat/.local/state/thermal-intel/forcing-captures/2026-10/20261001T030250Z-0f26b44311f20bd1.json.gz \
  --expected-runtime-revision 7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095
```

Accepted-artifact SHA remains
`66bc754135da743f402e00c34e07d8ffaeb7c8e97061873e06808619fe734353`, identical
to its embedded artifact and the preceding verified publication. Its training
revision is still `a4a68a17...`, distinct from the runtime pin. Publication is
still `shadow` with `low` confidence. Exact mechanical replay does not establish
predictive skill, action truth or graduation.

At verification the next shadow timer is **23:02:48 MDT**. Natural raw-weather
capture/training remain October 1 06:40/06:50. The training service is inactive,
with its last start still September 30 06:50:29; no new optimized whole-run
performance result exists yet. No configuration, model, source flag, control,
collector or DM changed, and no temporary files were created by these reads.

### Mature six-hour outcome checkpoint

A separate read-only audit around September 30 21:10 MDT used the installed
runtime, exact forcing captures and independently qualified indoor/outdoor
outcomes. Publication bounds were `2026-09-30T00:00:00Z` through
`2026-10-01T03:07:00Z`, six-hour horizon, with the current accepted artifact
explicitly identified by its full digest above. Of 15 publications, eleven
mature pairs have verified captures; four future outcomes remain unscored.
The issue-window `--until` does not freeze assessment time: subsequent reruns
may legitimately mature more pairs.

For the **current artifact**, four overlapping mature pairs yield indoor MAE
**2.4185°F** versus persistence **0.765°F**, signed bias **-2.4185°F** and zero
model wins (persistence wins all four). The non-overlapping subset has only
one pair: model MAE 2.482°F versus persistence 0.9°F. This is insufficient
independent evidence for fitting/promoting a correction. All four intervals
contain their outcomes, but their mean width is 10.4137°F; broad interval
coverage is not evidence of an accurate point prediction.

Across both artifacts in that issue window, eleven pairs have indoor model
MAE 2.4019°F versus persistence 1.0309°F. Their paired outdoor forcing has
MAE 1.5673°F and signed bias **+0.5709°F**. The opposite indoor/outdoor bias
directions do not support blaming this cold indoor bias solely on an outdoor
forecast that is too cold; they do not identify a causal airflow, solar, mass
or occupancy coefficient either. No recalled window state is made a signed
label and no coefficient/schedule is changed to fit these few outcomes.

The current artifact therefore still fails the better-than-persistence gate
in this new short-horizon checkpoint. Continue chronological divergence work
with qualified forcing/outcomes and genuine action observations. Do not confuse
the successful natural delivery/replay with thermal model readiness.

### Six-hour forcing and shade-assumption diagnosis

Read-only diagnostics on September 30 around 21:35 MDT replayed the
same four current-artifact captures above exactly under the complete installed
`7f57eb3f...` revision. Instrumentation wrapped the pure simulator only inside
the diagnostic process and restored its functions afterward. No capture,
artifact, installed source, Item, journal, service, control or DM was changed.

The ten-day capture's first midnight radiation rows are not the simulation's
initial forcing. The pipeline selects the decision-time five-minute origin
and interpolates its future weather brackets. These four scored windows each
contain 78 five-minute endpoints, ending at the nearest hourly six-hour target
(about 6.5 elapsed hours). Their actual window mean irradiance is respectively
125.785, 174.160, 97.952 and 61.974 W/m²; the first forcing is positive in all
four. This rules out treating the midnight prefix as a demonstrated forecast
indexing defect. It does not qualify these predicted irradiances against
measured irradiance.

All captured weather rows use `warm` mode. The internal baseline assumes
exterior shade **present** through `protocol_fallback`, not a qualified current
shade receipt. All 78 endpoints in each scored window therefore have
`outdoor_shade_present=1`. The accepted air and mass `solar_outdoor` coefficients
are both exactly zero. The first two windows have 36 and 29 modeled indoor-closed
endpoints; the later two have none. In this legacy three-regime solar basis,
open indoor shades plus present exterior shade therefore select a zero-gain
solar term. This is a model/state-identification limitation, not evidence that
the actual building receives no solar heat. Closing the modeled indoor shade
can instead select a positive gain, reproducing the joint-interaction limitation
already documented in the
[prediction-learning review](2026-09-29-prediction-learning-review.md#september-30-versioned-joint-shade-solar-candidate).

Three separate hypothetical changes were compared at the exact original
target timestamps. They are diagnostic scenarios, **not action observations**:

| Issue MDT | Original error °F | Closed-vent change °F | Exterior-absent change °F | 1.5× forecast-radiation change °F |
| --- | ---: | ---: | ---: | ---: |
| 08:30 | -2.482 | 0.000 | +2.953 | +2.345 |
| 10:31 | -1.934 | 0.000 | +5.303 | +0.520 |
| 12:31 | -2.728 | +0.099 | +9.078 | 0.000 |
| 14:31 | -2.530 | +0.521 | +3.585 | 0.000 |

Closed vents reduce approximate mean absolute error from 2.4185 to 2.2635°F;
they explain little of the miss. Exterior shade absent instead yields errors
approximately +0.471, +3.369, +6.350 and +1.055°F, mean absolute error 2.8113°F:
removing this assumption blindly is not an accuracy fix. Scaling radiation
by 1.5 yields approximate MAE 1.7023°F on these four overlapping pairs, but
leaves both later predictions unchanged. It can also change internal shade
timing; unchanged public vent schedule fields do not prove an unchanged whole
schedule. These are not four independent days, a calibrated multiplier,
causal shade effects or promotion evidence.

An initial exploratory 2× radiation run returned an unavailable forecast, and
the diagnostic attempted to locate its absent trajectory point. That failed
check produced no scored counterfactual. The corrected 1.5× run explicitly
checked bounded radiation and usable trajectories; it is the run recorded
above. No failed run or unavailable trajectory is counted as success.
A direct normalizer check confirms the 2× input reaches 1,616 W/m², exceeding
the 1,600 W/m² limit. Its first verification assertion expected the wrong
error wording; the corrected exact-message check passed. This was an invalid
diagnostic input, not a production forecast failure.

The publication's action provenance remains `historical_reconstruction` /
`reconstructed`. The artifact's manifest records four reconstruction, two
manual-DM and eight model-inferred events; these counts do not make the current
exterior shade or learned future shade/vent timing independently observed.
The 27 uncommissioned motorized indoor-shade preview slots likewise say nothing
about existing exterior screens. A separate question requests that physical
distinction; a chat recollection will not be inserted as a signed training label.

Next work is to qualify the actual independent shade/airflow state and join
original radiation forecasts to qualified irradiance outcomes. Use the already
versioned joint-shade candidate and chronological refit/replay to test any
model correction; do not relabel legacy coefficients, force exterior shade
absent from season or UI preview, fit a solar multiplier to these four pairs,
or graduate the current artifact. Live model and collector remain unchanged.
