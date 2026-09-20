# Qualified daily temperature learning integration — September 20

Update:the [live activation](2026-09-20-daily-temperature-activation.md) completed
at08:52:58MDT after natural training finished. The source/preflight notes below
are historical; natural daily/day-3 model updates remain future evidence gates.

Source implementation only. No production code/configuration, learned state,
service cadence, Item, notification or control has been changed by this step.
Deployment must wait for the currently running natural thermal training job to
finish: changing shared forecast/runtime files mid-run would compromise revision
attribution. Do not restart training to clear that gate.

## Contract

Both daily high/low Kalman learning and day-3 high scoring now share one optional
qualified-actuals boundary. Without the activation flag, the legacy input path
remains available. An explicitly invalid opt-in refuses temperature scoring;
there is no numeric-history fallback. Rain and PV retain their separate contracts.

The initial policy is explicitly `complete_receipt_coverage_v1`: every instant of
the completed local calendar day must have qualified receipt-as-of coverage.
This stricter criterion is intentional for extrema: a missing interval could
hide the high or low, even when aggregate coverage looks good. It does not claim
that persisted observations captured every physical fluctuation between polls.

The worker accepts only complete America/Denver midnight-to-midnight days,
including 23/25-hour DST days. It binds outdoor Fineoffset-WH65B ID206 to the
reviewed -40..140F, 120-second policy. Its restricted DB transport preserves
receipt expiry, invalid/restart barriers and original carry, with no interpolation.

- Read-only subprocess timeout:30seconds; request bound:4096bytes;
  parent response bound:8192bytes. No learned-state or OpenHAB write path in worker.
- Parent validates closed result shape, exact request/source/policy binding,
  coverage consistency, finite extrema and a canonical input-history SHA256.
  Duplicate JSON keys, nonfinite numbers and failed workers refuse both actuals.
- The digest covers the complete bounded query input, including original carry
  and invalid barriers, rather than only the resulting high/low values.
- Whole day must start at/after an explicit evidence cutover. New forecast records
  carry versioned local capture/issuance timestamps; these are not provider issue
  times. Both raw forecast horizons must have a post-cutover origin of the correct
  local lead. Older records are never backdated or relabeled.
- Successful updates retain day, quantity, raw forecast, issuance time, actual,
  source/coverage policy, request window and evidence digest (latest96records).
  Existing Kalman state, error histories and consumed markers are preserved.
- Daily scoring is saved before the subsequent fallible forecast fetch. Retries
  do not double-learn; unavailable evidence leaves the target unconsumed.
- Runtime revision and installer dependency manifests include the new worker.

## Verification

Final full Python suite:1,146passed,42subtests passed, one skipped, in138.86seconds.
Log:`/tmp/hex-daily-temperature-integration-final-tests.log`. This final run
includes the finite-forecast and independent rain/PV regressions.

Focused integration tests cover both scoring horizons, exactly-once retry after
fetch failure, preserved models for missing evidence/old origins, finite raw
forecasts, cutover checks, DST, strict schemas and independent rain/PV scoring.
Golden advisory comparisons use a fixed clock and still compare complete states,
including new issuance metadata; timestamps were not stripped to make tests pass.

The actual read-only child worker was exercised at2026-09-20T13:11:39Z against
September19. Parent validation accepted its evidence report, not its eligibility:

- Covered20576.812587/86400seconds; longest gap65823.187413seconds.
- Observed low48.02F, high60.08F; `fully_covered=false`.
- Input-history digest:
  `363f8015a657b923ad5210babde7f1dad2bf7aed990ac4dd5d903769bd13dee4`.

No synthetic complete day, backdated forecast origin, model update or notification
was created by this check.

## Activation gate and rollback

After natural training is terminal and before installing shared code, verify that
forecast and shadow jobs are also idle, back up exact code/model/state/unit files,
and use a receipt-bound deployment with unchanged timer definitions. Then add a
scoped forecast-service override using:

```
DAILY_TEMP_QUALIFIED_ENABLE=1
DAILY_TEMP_COVERAGE_POLICY=complete_receipt_coverage_v1
DAILY_TEMP_EVIDENCE_CUTOVER=<actual activation instant; never backdate>
DAILY_TEMP_DB_CONFIG=/home/sat/.config/hex/weather-temperature-db.json
DAILY_TEMP_POLICY=/home/sat/.config/hex/weather-temperature-policy.json
```

Keep the existing hourly and advisory capture/assessment overrides unchanged.
Verify installed hashes, effective configuration and a read-only child request.
Do not force a forecast run to manufacture a new origin. With activation on
September20 before the next06:40run, the first ordinary daily origin is September21
and first eligible assessment September22; the first day-3 target is September24,
assessed September25, subject to full coverage and correct origins.

Removing only the new override returns daily temperature inputs to the prior
path. Keep compatible code and newer model state; do not restore old model/state
backups over later learning. Activation and natural qualified daily/day-3 updates
remain unverified until separately recorded.

## Read-only release preflight, 07:24 MDT

Every existing installed runtime file still matches reviewed commit63529ea by
content. Four files need replacement and one new worker needs installation:

| Source under openhab/scripts | Intended SHA256 |
| --- | --- |
| forecast_intel.py | 905f033e305c10266ba51fc113702748f4f3ef5eaeda23f917233bd3ccaf6faa |
| thermal_intel.py | d22e1e04762022bd65caa23a9847dd9720979d0f3a7692a331da87266ed95c5e |
| daily_temperature_runtime.py (new) | 89f67dc1053828fbff78f63fac5e0da68cad38b80937965abfe711a99625cfe2 |
| weather_temperature_reader.py | cc616076bca34a77e4a2a6b827927272c4e92646432dabbf9dca57f83ad17f79 |
| weather_temperature_history.py | 5291874247e2fd82f20013f97890c571cbe7bcbd63f5cc70d8e7701932aa6fdd |

The live forecast script's mode is0775, while the default thermal manifest lists
0755 for its verify-only entry. Preserve0775 explicitly in the receipt-bound
release manifest when treating forecast as code to install. Do not use the
unmodified default manifest: its forecast entry verifies rather than installs.
All other checked runtime modes match the manifest. Revalidate this baseline
after training is terminal; this preflight made no changes or backups of active
training state.
