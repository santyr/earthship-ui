# Exact morning weather-input archive

## October 3 native held-shade forcing diagnostic

The source-only `hold_confirmed_shades` helper now overlays only recent,
qualified indoor/outdoor shade observations onto an independently supplied
native forcing grid. It preserves ventilation and all weather/initial inputs.
Unknown, inferred, zero-confidence, future-received/committed or more-than-48-hour
old physical states are refused or excluded. A late receipt cannot renew the
age of its physical observation. The 48-hour hold limit is an explicit diagnostic
assumption, not learned persistence or proof the shades remained unchanged.
The complete five-minute grid is bounded at the actual 72-hour model horizon;
no future forcing is labelled as observed action evidence or control authority.
Window and skylight observations never become aggregate-vent forcing.

`replay-thermal-forcing.py` has a Python-only selected-forcing observer. It
records native schedule simulations in memory, restores the simulator on both
success and failure, and exports a private copy only after exact as-issued
output equality, final runtime-pin equality and matching every published
air/mass trajectory point. Empty or inconsistent trajectories refuse export.
The normal CLI/output does not expose private five-minute forcing grids.

Two original captures were assessed using restricted, exact-v2-schema-audited
journal reads at their original publication clocks. Only indoor shades were
qualified as closed; no window/skylight/vent/outdoor-shade state was added.
Both native outputs replay exactly under installed runtime
`cd77cd16bda18fa2beb60391e5663518650b2aaac0119b7ced09b2726505252e`.
An independent unchanged-grid re-simulation of the 17:53 capture also equals
every retained native prediction, not merely the rounded public points.

| Original UTC issue | Capture basename | Origin action-snapshot SHA-256 |
| --- | --- | --- |
| 2026-10-03T15:40:07.386987Z | `20261003T154007Z-08a89eacdf72363b.json.gz` | `1ec8bcd04f916298f60114c2b091d5df020a64c759d2a97177e9c697278add14` |
| 2026-10-03T17:53:37.617985Z | `20261003T175337Z-4e1729cc5ab6ba22.json.gz` | `5d3d15412ae3851c64c793b521add3009005e8079f17edbd626f3911662675c4` |

Holding indoor shades closed leaves the near-one-hour predictions unchanged.
For the 15:40 issue the six-hour result is unchanged, but the 12/24/48-hour
differences are **+2.0208/+5.6439/+6.6622°F**. For the 17:53 issue the
6/12/24/48-hour differences are **+1.2967/+1.2917/+8.9721/+11.0170°F**.
These are modeled differences, not outcome scores or evidence of useful skill.
Targets are the nearest native five-minute steps, not the public near-hour
evaluation grid. Timestamp keys were normalized to UTC before comparisons.

The surprising warming reproduces the already documented **legacy joint-shade
paradox**, not a replay or clock mismatch. At October 3 23:45Z, the original
forcing is indoor-open/outdoor-present, radiation 201.75 W/m² and vent closed.
Its legacy solar terms are `(0, 0, 1300)`; closing the indoor shade changes
them to `(0, 1300, 0)`. The accepted air gains are approximately
`solar_outdoor=2.8138e-17` and `solar_indoor_closed=0.00033936`, yielding
an immediate **+0.44117°F** modeled difference. Indoor closure bypasses the
assumed outdoor shade in this old three-regime basis. No outdoor shade
observation was established by the diagnostic.

Consequently **do not deploy this overlay with the legacy accepted model**.
The [versioned four-regime candidate](2026-09-29-prediction-learning-review.md#september-30-versioned-joint-shade-solar-candidate)
already addresses the source-model interaction without imposing a false ordering
between indoor-only and outdoor-only gains. It still requires independently
qualified action data, chronological household refit, captured origin-time
inputs and out-of-sample validation. Unknown windows/skylights remain unknown;
old coefficients and artefacts cannot be relabelled into the new model.

All **255 affected tests and 17 subtests** pass (including the initial 128-test
focused run), covering observation age,
confidence/source bounds, independent fractions, full native horizon, exact
private-grid export, runtime drift, combined-shade monotonicity and legacy
compatibility. Installed model/training code, artifacts, journal, Items,
collector and controls were not changed. The source-only v2 reader gate remains
off outside the bounded read-only qualification process.

## October 3 authenticated action availability and recovered weather fetch

A restricted, exact-v2-schema-audited **read-only** journal batch checks three
original clocks in one repeatable-read transaction. Its two journal-data queries
are shared; later receipts/corrections are selected separately at each origin.
The diagnostic opened the v2 reader gate only in its own process, then closed
it; generic source gates, installed forecast/training code and controls remain
unchanged. No journal row or training label was written.

| Original UTC clock | Confirmed indoor-shade closure available? |
| --- | --- |
| October 3 training cutoff, 12:50:57.029705Z | No |
| Original shadow issue, 13:39:05.222543Z | No |
| Original shadow issue, 15:40:07.386987Z | Yes |

The authenticated closure was physically effective October 2 18:30Z, first
received October 3 **14:02:23.796322Z**, and committed as a receipt at
**14:02:24.430268Z**. Event `8cb8510c8040bfb265634fb7` has source
`nostr_confirmed`, confidence 1 and state `closed`. Both receipt clocks must
precede an origin. Window/skylight states remain unknown at all three clocks;
chat recollections cannot fill them or become aggregate-vent labels.

The installed daily dataset reads journal actions and can project this supported
shade state on its next fit. Today's trained artifact predates the receipt.
The installed shadow entrypoint reads journal **modes only**, while its scenario
engine supplies an assumed behavior schedule. Verified captures contain no
origin action snapshot. Thus later shadow publication is not proof that known
physical shade/window/skylight state entered its forcing. Qualifying a causal,
original-input-captured action-aware forecast and independent split airflow
remains required; do not retrospectively relabel old scenarios as observations.

`fetch_origin_actions_batch` now supports up to 96 unique origins within 14 days,
preserving the single-origin API, schema/role/gate checks, per-table row bounds,
read-only transactions and correction availability. The historical-origin audit
uses it instead of two action queries per origin. Incomplete/misaligned batches
and dual readers refuse before forecast reads. All **132 affected tests plus
five subtests** pass, including delayed commit, late correction, requested order,
closed gates, connection cleanup and downstream split-airflow/capture checks.
This is an audit efficiency improvement, not deployed model-input activation.

Separately, the actual 11:40 MDT shadow job exhausted three Open-Meteo attempts
and stopped at 11:41:05 with exit 1 and a read timeout; it published no new
forecast. After confirming terminal failure and PID 0, one bounded retry of the
unchanged observational unit began at 11:53:36, used fresh inputs/current time,
and finished at 11:53:39 with exit zero. No early/fake-time job or fit was run.
Its **17:53:37.617985Z** publication matches the live Item, verified private
capture and one new JDBC row at **17:53:39.874Z**. Original-input capture:
`20261003T175337Z-4e1729cc5ab6ba22.json.gz`; output SHA-256
`4e1729cc5ab6ba22560847452957aa1b0ce28522d88dc90187566b96fac5a3b3`.
It retains artifact `d9163729...` and low confidence. This is successful bounded
recovery, not a scheduled natural run, autonomous retry qualification or new
action knowledge in the model. The morning-only recovery timer does not cover
shadow-job failures.

## October 3 fixed-clock assessment and second 24-hour outcome

The read-only audit now accepts an elapsed `--assessed-at` clock. It refuses
future or timezone-naive clocks and publication windows extending beyond that
clock before any external read. Outcome maturity and original receipt/capture
qualification remain unchanged. This does not override training or live-job
clocks, create labels, or enable advice or controls. All **124 affected tests**
pass, including repeated-score equality and rejection of premature outcomes.

Two actual live reads used this exact assessment:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/sat/Solar_PV/analytics/src \
  python3 scripts/audit-thermal-shadow-publications.py \
  --since 2026-10-02T14:00:00Z --until 2026-10-03T17:00:00Z \
  --assessed-at 2026-10-03T17:05:56.834594Z \
  --require-capture --horizons 1 6 12 24 --include-pairs \
  --runtime-root /home/sat/openhab/scripts
```

Both canonical reports have SHA-256
`8f002ec1d063a48061ae6e574a7c5ec8af2ca5841d439cd0086cc53c267c68dd`.
Fifteen persisted publications bind fifteen verified original forcing
captures. Twenty-five distinct indoor/outdoor targets use two bounded
transactions per source stream, not one query per overlapping forecast.
The installed verifier runtime remains `cd77cd16...`.

| Horizon | October 2 artifact overlapping pairs | Model / persistence MAE °F | Non-overlapping pairs | Non-overlapping model / persistence MAE °F |
| --- | ---: | --- | ---: | --- |
| Near 1 hour | 13 | 1.0304 / 1.4400 | 12 | 1.0152 / 1.4700 |
| Near 6 hours | 12 | 1.9083 / 5.5200 | 3 | 1.2437 / 7.2000 |
| Near 12 hours | 9 | 2.1234 / 6.6800 | 2 | 0.6445 / 6.4800 |
| Near 24 hours | 2 | 2.6755 / 3.4200 | 1 | 2.2810 / 2.8800 |

The predecessor `2435c019...` has a second mature 24-hour pair: its
October 2 15:32:11.579258Z issue predicts October 3 16:00Z **3.070°F cold**,
versus persistence **3.960°F cold**. Original outdoor forcing is **1.540°F
cold**, unlike the first pair's **7.400°F warm** outdoor error. Two cold
indoor misses under opposite outdoor-error signs do not establish a blanket
weather correction. The second pair overlaps the first; these are not two
independent physical days.

The new artifact `d9163729...` is scored separately. Its only two mature
near-one-hour pairs have MAE **0.291°F** versus persistence **1.800°F**,
bias **+0.181°F**, and two non-overlapping windows. Their model errors are
−0.110°F and +0.472°F. It has **no mature 6/12/24-hour pairs** at this
assessment. Intervals still span roughly **10.414°F** with low confidence;
coverage alone is not useful calibration or action-benefit evidence. No
retrospective correction, model promotion, gate relaxation or action label
was made. Continue chronological, artifact-specific scoring and genuine
confirmed-action evaluation before graduation.

## October 3 new-artifact publication and first prior-artifact 24-hour outcome

The next natural shadow job started at 07:39:03 MDT, finished at 07:39:07,
and exited zero. Its original publication at **13:39:05.222543Z** embeds the
new canonical artifact `d9163729...`, created at 12:50:57.029705Z. The private
forcing capture, current `Thermal_Model_JSON` and exact JDBC row at
**13:39:07.463Z** agree. Output SHA-256:
`0a2f55931fbcbf1beebaf83b9ba458390a7ee756fdee3b441245bd08c71b2fe6`.
Capture:
`/home/sat/.local/state/thermal-intel/forcing-captures/2026-10/20261003T133905Z-0a2f55931fbcbf1b.json.gz`.
Exact as-issued replay under the pinned installed `cd77cd16...` runtime passes;
the new artifact's training/publication revisions match. No worker was started
manually, fit repeated or current data substituted for original forcing.

The 14:21:19Z capture-strict shared-grid audit preserves the prior October 2
artifact `2435c019...` as a separate target. Fourteen publication rows yield
13 distinct verified captures and 22 qualified indoor/outdoor targets through
one bounded transaction per stream. The new artifact has no mature outcome in
this window and is not assigned its predecessor's scores.

| Horizon | Prior-artifact overlapping pairs | Model / persistence MAE °F | Non-overlapping pairs | Independent model / persistence MAE °F |
| --- | ---: | --- | ---: | --- |
| Near 1 hour | 13 | 1.0304 / 1.4400 | 12 | 1.0152 / 1.4700 |
| Near 6 hours | 11 | 2.0205 / 5.9400 | 3 | 1.2437 / 7.2000 |
| Near 12 hours | 8 | 2.3604 / 7.1325 | 1 | 1.0610 / 9.9000 |
| Near 24 hours | 1 | 2.2810 / 2.8800 | 1 | 2.2810 / 2.8800 |

The first mature operational 24-hour target is **2.281°F cold**, versus
persistence **2.880°F cold**; its original outdoor forcing is **7.400°F warm**.
All intervals cover their outcomes, but their width remains about 10.414°F,
confidence is low, and one 24-hour target is not independent-day support.
No coefficient or advisory graduation is promoted from this score. The new
authenticated shade receipt first arrived at 14:02:23Z, after the new artifact
and 13:39 publication: do not backdate its availability into either. Confirmed
action-outcome evaluation and approved graduation thresholds remain required.

## October 3 natural training — terminal result and new artifact

The same observed PID 1871293 finished naturally with exit zero and
`Result=success` at 07:17:00 MDT, after starting at 06:50:56: **26m04s**.
Final systemd counters retain peak memory **382,889,984 bytes (365.15 MiB)**
and peak swap **0 bytes**. The observation deadline was not a failure and no
job was restarted. This run is longer than October 2's 19m26s, but swapping
does not explain it; retain performance/parity requirements for further tuning.

The actual accepted v4 artifact passes eligible-artifact validation and binds
the installed `cd77cd16...` runtime. Its canonical SHA-256 is
`d9163729bcc75e38e147c33eb76c863b9e125179abc92088352192d5bc6d3be9`;
the exact accepted file SHA is
`9baa9f4931e9f8c6ca26ba6ba98e36e43289a9769b6b9f4dbc03bf3cb9b21a0b`.
The window advances to August 29, 2025 through October 3, 2026 at
`12:50:57.029705Z`, exactly 400 days. Canonical training data and fitted
dynamics changed: compared with the retained predecessor it has 287 additional
qualified air/outdoor targets and 286 mass targets. This was not a duplicate
fit of byte-identical inputs; the canonical sample count is 99,882.

Retrospective 24-hour air MAE remains **2.17855°F**, versus **1.689895°F**
for persistence (119 targets). Confirmed-action training/evaluation support
remains zero, operational graduation thresholds are null and `shadow_only`
is true. The historically named `air_24h_beats_persistence` provisional gate
actually permits the operator-approved **0.75°F** MAE tolerance; its true flag
is not proof of beating persistence or graduating advice. No gate was relaxed.
The next natural publication must bind the new artifact; the first old
`2435c019...` 24-hour target must still be scored separately after 08:05 MDT.

## October 2 late-evening independent-window solar rejection

At `2026-10-03T04:49:18.093326Z`, the capture-strict shared-grid audit scores
nine original publications for the fixed October 2 artifact `2435c019...`.
Eight distinct captures verify; 12 indoor and 12 outdoor targets require only
one bounded read transaction per stream. Targets remain nearest hourly points
within 30 minutes, with the unchanged five-minute maturity and original-source
qualification gates. The current-radiation delivery proof remains valid and
the accepted artifact/configuration still match the original rollout receipt.

| Horizon | Mature overlapping pairs | Model / persistence MAE °F | Non-overlapping pairs | Independent model / persistence MAE °F |
| --- | ---: | --- | ---: | --- |
| Near 1 hour | 8 | 1.1851 / 1.8225 | 7 | 1.1811 / 1.9286 |
| Near 6 hours | 5 | 1.4222 / 7.7040 | 2 | 0.9650 / 9.0900 |
| Near 12 hours | 2 | 1.1195 / 8.2800 | 1 | 1.0610 / 9.9000 |
| Near 24 hours | 0 | withheld | 0 | withheld |

The new near-12-hour target, issued `2026-10-02T15:32:11.579258Z` for
`2026-10-03T04:00:00Z`, is **1.178°F cold**, versus persistence **6.660°F
cold**. Its original outdoor forecast is **5.180°F warm**. The earlier
12-hour target is **1.061°F warm**, so neither a constant cold-bias correction
nor an outdoor-forecast-only correction is established by this cohort.
The new six-hour window, issued `2026-10-02T21:35:05.178763Z` for that same
04:00Z outcome, is **1.812°F cold** and is the second selected non-overlapping
six-hour window. Overlapping 6/12-hour scores against one target are not two
independent physical observations. Every interval still covers its outcome
but is approximately 10.414°F wide; all outputs remain low-confidence.

### Unchanged hypotheses tested against the later outcome

All five contributing original captures replay **exactly** under pinned
installed runtime `c732feed...`. The earlier fixed 90% solar hypothesis and a
separate closed-vent hypothesis are independently applied in memory; they do
not combine, change initial observations, refit coefficients or create action
labels. The solar hypothesis does not change any modeled schedule.

The new six-hour solar result is **-2.544°F**, worse than the original
**-1.812°F**. Across all five overlapping six-hour targets, MAE superficially
improves from **1.4222 to 1.2966°F**, but just **one of five** targets improves.
The two selected independent windows instead worsen from **0.9650 to
2.0475°F**. Both mature 12-hour targets worsen under 90% solar: errors become
**-1.517 and -2.781°F**, raising MAE from **1.1195 to 2.1490°F**. This later
outcome rejects a blanket solar reduction despite its improvement on the
earlier largest afternoon miss. It does not identify a calibrated irradiance,
shade, mass or airflow coefficient, nor constitute seasonal validation.

Assuming closed vents changes none of the five six-hour targets. At 12 hours,
it changes errors to **+1.516 and -0.233°F**: overlapping MAE improves to
**0.8745°F**, but the one independent selected 12-hour window worsens. This
is sensitivity to a coarse legacy modeled vent schedule, not confirmation of
windows/skylights, causal action benefit or permission to relabel chat reports.
Independent source-bound shade/window/skylight observations and chronological
joint-model identification remain the next path; no scalar adjustment is
promoted from these mixed errors.

The existing multi-horizon command in the section below reproduces the audit;
add `--horizons 1 6 12 24` for the full maturity check. The five-capture replay
uses `replay-thermal-forcing.py` with explicit runtime SHA, `--solar-scale 0.9`
and `--assume-vents-closed`; each hypothesis starts separately from the original
capture, and comparison joins targets by aware UTC timestamp, not string prefix.
Audit source SHA remains `2a89cae4...`; replay source SHA remains `d999c917...`.
No code, accepted artifact, journal, sensor state, forecast, worker/timer or
household control changed. No new temporary files or test containers were
created by this diagnostic. The first fixed-artifact 24-hour target is due
after October 3 08:00 MDT plus the five-minute lag; use this captured artifact
identity even if the next scheduled trainer accepts a newer artifact first.

## October 3, 10:50Z — nighttime forcing basis isolated

The exact `20261003T015802Z-5f053eec5272386d.json.gz` capture was verified
under installed runtime `cd77cd16...`, not the separate newer repository model
schema. Two bounded qualified-temperature grids assessed all nine elapsed
hourly targets at `2026-10-03T10:50:56.146206Z`. Every forcing temperature
equals the original raw Open-Meteo hour after explicit America/Denver-to-UTC
conversion; the archived unit is Fahrenheit. This rules out an added learned
correction or time/unit mismatch for these nine captured values, not a general
sensor, location or provider accuracy claim.

| Target UTC | Raw outdoor forecast | Qualified outdoor actual | Indoor model error |
| --- | ---: | ---: | ---: |
| 02:00 | 59.70°F | 55.40°F | -0.201°F |
| 03:00 | 57.50°F | 50.18°F | -1.213°F |
| 04:00 | 55.60°F | 47.12°F | -1.932°F |
| 05:00 | 54.00°F | 45.14°F | -2.300°F |
| 06:00 | 52.50°F | 43.16°F | -2.769°F |
| 07:00 | 51.60°F | 41.54°F | -2.863°F |
| 08:00 | 51.90°F | 40.10°F | -2.795°F |
| 09:00 | 52.90°F | 39.02°F | -2.768°F |
| 10:00 | 53.00°F | 38.30°F | -2.821°F |

`thermal_intel._forecast_rows()` calls `build_forecast_payloads()` without
the learned daily adjustment/hourly model; that path uses raw temperatures.
The weather UI supplies those corrections separately. Current learned state
must not be substituted retroactively into this capture or called as-issued
corrected forcing. A future forcing comparison needs origin-frozen corrections
and held-out qualification. Raw outdoor bias grows from +4.30°F to +14.70°F
while the indoor forecast remains cold: correcting weather alone is not
established as a fix for the building forecast. Existing closed-vent sensitivity
and the remaining airflow/thermal-dynamics qualification therefore remain
important. This is one overlapping night, not nine independent training cases.
No model, coefficient, source receipt, action label or production configuration
was changed.

## October 3, 09:45Z — additional overnight targets and current-runtime replay

The same fixed `2435c019...` artifact now has additional source-qualified
targets. The bounded read-only audit verified 11 original captures and used
only two receipt-grid transactions across 12 publications:

| Near horizon | Overlapping pairs | Model / persistence MAE, °F | Non-overlapping pairs |
| --- | ---: | --- | ---: |
| 1 hour | 11 | 1.1085 / 1.6036 | 10 |
| 6 hours | 8 | 2.0826 / 6.9075 | 2 |
| 12 hours | 4 | 1.8075 / 5.7600 | 1 |

These are not independent days or seasonal/action qualification. All remain
low-confidence with roughly 10.414°F-wide intervals. The two additional
12-hour errors are -2.379/-2.612°F at 06:00/08:00Z, while their original outdoor
forecast errors are +6.64/+10.30°F. The six-hour 01:58Z issue misses the 08:00Z
indoor outcome by -2.795°F despite outdoor forcing being +11.80°F warm.
Cold indoor bias therefore is not explained by uniformly cold outdoor forcing.
No model, coefficient, action label or publication changed.

An initial replay with the older `c732feed...` pin correctly refused: the
shared forecast instrumentation changed the runtime fingerprint. Independently
comparing all **26** named source files against the retained radiation rollout
source shows exactly one change, `forecast_intel.py`, from SHA `943c09d4...`
to the reviewed `1b902853...`. All other source bytes are identical. Current
runtime revision is
`cd77cd16bda18fa2beb60391e5663518650b2aaac0119b7ced09b2726505252e`.

With that independently verified pin, the original
`20261003T015802Z-5f053eec5272386d.json.gz` replays **exactly as issued**.
The closed-vent hypothesis adds 1.132°F at six hours, reducing that miss to
-1.663°F but not eliminating it. A separate uniform -3°F outdoor hypothesis
lowers the forecast another 0.273°F, worsening the miss to -3.068°F; it also
reselects the modeled schedule. These are independent in-memory hypotheses,
not observed ventilation/weather or learned corrections. Continue identifying
actual airflow/shade and stored-heat dynamics; do not promote a weather-only
offset or override the existing solar-rejection result.

The refreshed private publication replay archive is
`/home/sat/backups/earthship-energy/thermal-replay-pub-cd77-20261003T095300Z.tar.gz`,
SHA-256 `98abea33b4cd210e3fe852578cee7b44394a37c7dcc636535e980e313fe24274`.
It verifies 148 members/117 captures, explicitly separates training revision
`7f57eb3f...` from publication runtime `cd77cd16...`, and passes the exact
overnight replay from a fresh restored source/capture tree. That temporary
tree is removed; original recovery points are preserved. This qualifies this
same-host replay scope, not a whole-host/off-host or PostgreSQL restore.
The first fixed-artifact 24-hour target still must wait until 08:05 MDT.

## October 2 evening mature 12-hour outcome and batched scoring

At `2026-10-03T02:19:25.104725Z`, the current captured artifact
`2435c01964842c98829d25499b161b68dfab1d83a389e8b4ce0689eff2391d79`
has its first mature near-12-hour target. Original captured publications and
receipt-qualified indoor/outdoor outcomes are used; these are nearest hourly
targets within 30 minutes, not exact elapsed horizons.

| Horizon | Mature overlapping pairs | Model / persistence MAE °F | Non-overlapping pairs / model MAE °F |
| --- | ---: | --- | --- |
| Near 1 hour | 6 | 1.1372 / 1.9800 | 6 / 1.1372 |
| Near 6 hours | 4 | 1.3247 / 8.1450 | 1 / 0.1180 |
| Near 12 hours | 1 | 1.0610 / 9.9000 | 1 / 1.0610 |

The first 12-hour target was issued at `2026-10-02T14:14:36.083052Z`,
targeting `2026-10-03T02:00:00Z`. Its indoor error is **+1.061°F**, persistence
error **-9.900°F**, and original outdoor forecast error **+2.800°F**. Unlike
the previous artifact's cold errors, this target is warm. One target cannot
justify a signed-bias correction or seasonal graduation. All scored intervals
cover outcomes but remain about 10.414°F wide; confidence remains low, and
confirmed-action evaluation and reviewed numerical graduation gates are absent.

### Exact replay and solar-forcing tradeoff

The newly matured six-hour miss from
`20261002T173305Z-934722f199e5e15c.json.gz` predicts **81.570°F** at
`2026-10-03T00:00:00Z`, versus qualified **77.360°F** (error +4.210°F).
Its entire as-issued output first replays exactly under explicitly pinned
installed runtime `c732feed23f4a9dd323a85a77dec9872d821c626d6619a642548dc7b752baaac`.
Separate hypotheses show zero six-hour closed-vent change (modeled opening is
later), only -0.077°F change for a uniform -3°F outdoor shift, but -15.574°F
for a 50% solar reduction. These are modeled sensitivities, not observations,
solar calibration, confirmed shade/vent state or a fitted correction.

A fixed 90% solar hypothesis was then evaluated against **all four** mature
six-hour targets of this artifact, each after exact replay and independent
receipt validation. No schedules changed. Assessment ended at
`2026-10-03T02:22:16.026579Z`.

| Target UTC | Original error °F | 90% solar error °F |
| --- | ---: | ---: |
| October 2 20:00 | -0.118 | -1.551 |
| October 2 22:00 | +0.646 | -0.833 |
| October 3 00:00 | +4.210 | +0.457 |
| October 3 02:00 | +0.325 | -1.098 |

Overlapping MAE improves from **1.32475 to 0.98475°F**, but only the largest
miss improves; the other three worsen. The audit's one selected non-overlapping
window worsens from 0.118 to 1.551°F. This is not independent held-out tuning
or evidence for deploying a solar multiplier. It identifies solar/shade/mass
forcing as a useful diagnosis path without proving which term is wrong. The
operator's chat shade report remains context, not a signed training label.

### Efficient repeatable multi-horizon audit

`audit-thermal-shadow-publications.py --horizons 1 6 12` now shares immutable
original-capture verification and sorts/deduplicates receipt targets. Reads
remain within the existing 289-target/24-hour qualified grid contract, with
original source/expiry clocks revalidated at every target. Future targets,
missing captures and unavailable indoor outcomes cause no unnecessary outdoor
read; missing outcomes remain withheld, not fabricated or interpolated.
The existing single `--horizon-hours` output and all per-horizon metrics,
artifact grouping, independent-window policy and readiness blockers are
preserved. No new schedule, learner, action or release authority is supplied.

At `2026-10-03T02:27:44.549713Z`, actual restricted live batch reads reproduce
the original point-reader results **exactly** on the same eight publications
and assessment time: six original capture verifications and ten targets per
stream, using **two** transactions rather than **20** cached point transactions.
Canonical full `results` SHA-256 is
`a24b39ea896e212f4b8c19da3682b3fa51a82266f336e234b3939e6e71f14957`;
audit source SHA is
`2a89cae4aae90b52ca9798eef5196188fde5c4bfd85252b05321af3ebdab4f76`.

Reproduce from the repository using the existing private host environment:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit-thermal-shadow-publications.py \
  --since 2026-10-02T14:00:00Z --require-capture --horizons 1 6 12 \
  --include-pairs --artifact-id 2435c01964842c98829d25499b161b68dfab1d83a389e8b4ce0689eff2391d79 \
  --runtime-root /home/sat/openhab/scripts
```

Later maturity can legitimately change counts. All **160 affected scorer,
replay, graduation and qualified-temperature reader tests pass**, no skips.
Tests cover differential score equality, legacy CLI, bad/expired receipts,
missing/future evidence, invalid options, ordering, day-span and 289-target
batch limits. This is not a whole-project or fresh container-backed audit.
No model, artifact, journal, sensor state, production forecast, service/timer
or household control was changed. The tool runs from the repository and needs
no forecast-worker install or restart.

## October 2 later mature outcomes and qualified-weather attribution

At `2026-10-02T22:16:30.024515Z`, a bounded GET/SELECT-only multi-horizon
audit scored the current accepted artifact
`2435c01964842c98829d25499b161b68dfab1d83a389e8b4ce0689eff2391d79`.
It fetched five original publications since 14:00Z once, cached original
capture verification, and retained receipt-qualified source clocks. No later
artifact or weather fetch replaces original inputs. Targets remain the existing
nearest hourly point within 30 minutes of issue+horizon, **not exact elapsed
horizons**. Missing/future outcomes are withheld.

| Horizon | Mature overlapping pairs | Model MAE °F | Persistence MAE °F | Non-overlapping pairs / model MAE °F |
| --- | ---: | ---: | ---: | --- |
| Near 1 hour | 4 | 0.8145 | 2.3850 | 4 / 0.8145 |
| Near 6 hours | 2 | 0.3820 | 12.4200 | 1 / 0.1180 |
| Near 12 hours | 0 | unavailable | unavailable | 0 / unavailable |

The second six-hour pair was issued at `15:32:11.579258Z`, targeting
`22:00:00Z`: indoor model error **+0.646°F**, persistence **-12.600°F**, and
outdoor forecast error **+0.060°F**. Both six-hour outcomes overlap; their
MAE does not represent two independent days. Four short-horizon pairs split
three model wins and one persistence win. They also show changing weather-error
signs (+4.40, -4.32, -2.72 and -1.96°F), not one constant outdoor bias.
All scored intervals cover their outcomes but remain about 10.414°F wide.
Low confidence, absent confirmed-action evaluation and unspecified operational
graduation thresholds remain; there is no model graduation or coefficient fit.

### Retrospective observed-outdoor-only counterfactual

The largest previously scored cold miss was examined more directly than a
uniform temperature-offset hypothesis. The original October 1
`20261001T150530Z-25496c123c0be79f.json.gz` capture first replayed **exactly**
under a private, temporary reconstruction of its original full runtime pin
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`.
Only the code-only diagnostic copy used the retained pre-correction behavior
module; installed source and the accepted artifact were untouched.

The experiment copied `forecast_rows` in memory and replaced only `tempF`
at the 13 hourly timestamps from the origin's lower interpolation bracket
(`2026-10-01T15:00:00Z`) through the mature target (`2026-10-02T03:00:00Z`).
Every replacement comes from the existing strict outdoor reader and passes its
closed receipt/identity/expiry contract at that timestamp. The qualified indoor
target is independently validated. Current observations, embedded artifact,
weather timestamps, solar radiation and all other forcing fields stay exact;
later unelapsed temperatures remain the original forecast. Interpolation
between hourly observations is still modeled, not measured five-minute forcing.

This is explicitly **retrospective**: later observations were not available
at original issue and cannot be used as an as-issued forecast, training/action
label, learned correction or live publication. The comparison includes modeled
schedule reselection, but selected schedules happen to remain unchanged here.

| Target result | Temperature / error °F |
| --- | ---: |
| Qualified indoor outcome | 68.540 |
| Original indoor prediction | 64.039 / -4.501 |
| Observed-outdoor-only counterfactual | 63.743 / -4.797 |
| Change from original prediction | -0.296 |

The hourly original outdoor errors vary from **-6.64 to +9.24°F**; the
target-hour error alone (+6.70°F) does not describe the entire forcing path.
Using qualified outdoor measurements at every hourly bracket does **not**
remove this case's indoor cold bias. It therefore does not justify an
outdoor-temperature-only indoor correction. It also does not identify which
solar/shade/airflow/mass/internal-gain coefficient is wrong: those inputs and
states have not been independently observed throughout this window.

Assessment: `2026-10-02T22:19:26.580143Z`.
Original output SHA:
`25496c123c0be79f021e4858fb6dfe93f04cf106fdbb07dd2a594c6e1994de89`.
Original artifact SHA:
`5dc0d548aefe0e60299dab1ae4b71372dc0f95f49f3034ab480f56194fe32be6`.
The exact original output/artifact references, target timestamp and 13 outdoor
plus one indoor receipt objects are bound by canonical, sorted compact JSON
(aware datetime values serialized with `isoformat`) SHA
`110caa2513fd021a84b97dccc7e8e326e76a6fa1694768b1fae3172e067b30f0`.
No original archive, journal, SQLite database, SQL row, service, Item, artifact
or coefficient was written. The owned temporary replay directory was removed.

The existing original-publication scoring and exact-replay regression suites
pass **57 tests in 0.61 seconds**, with no skips. Task-owned fixtures were
removed and pytest cache/bytecode generation stayed disabled. This is validation
of those existing contracts, not a new production model or whole-project audit.

## October 2 completed targets and offline temperature sensitivity

The existing read-only audit was rerun after all nine original October 1
artifact targets in the publication window below matured. It verifies each
original archive/publication and receipt-qualified indoor/outdoor outcome;
neither later weather fetches nor current artifact substitutions are used.

| Completed near-12-hour pairs | Model MAE | Persistence MAE |
| --- | --- | --- |
| Nine overlapping pairs | 2.2122°F | 3.3400°F |
| Two greedy non-overlapping windows | 2.4970°F | 2.4300°F |

The model wins six overlapping comparisons and loses three; the two
non-overlapping comparisons split one each. Model bias is -2.0853°F, outdoor
forecast bias +6.3067°F and outdoor MAE 7.5156°F. The last two outdoor errors
are -3.12°F and -2.32°F: the earlier six-pair observation that all weather
errors were warm does not describe the completed nine-pair set. All intervals
cover their outcomes but average 10.4136°F wide. The target artifact remains
slightly worse than persistence on the independent-window check, low
confidence, without confirmed-action evaluation or graduation thresholds.

Today's artifact was assessed **separately** with the same audit, using
`--since 2026-10-02T14:00:00Z --until 2026-10-02T15:00:00Z
--horizon-hours 6 --require-capture --include-pairs --artifact-id
2435c01964842c98829d25499b161b68dfab1d83a389e8b4ce0689eff2391d79
--runtime-root /home/sat/openhab/scripts`. Its first mature pair was issued
at `14:14:36.083052Z`, targeting `20:00:00Z`. Model error is **-0.118°F**
versus persistence **-12.240°F**; corresponding outdoor error is **+0.020°F**.
This single target is not a six-hour seasonal qualification or evidence of a
causal improvement from one daily training run.

The offline `scripts/replay-thermal-forcing.py` now accepts
`--outdoor-offset-f` (finite -20 to +20 Fahrenheit degrees). It requires exact
as-issued replay first, copies only forecast temperatures, preserves all
initial readings/captured facts, and refuses original or hypothetical values
outside the simulator's -40 to 140°F bounds. Optional vent, solar and
temperature hypotheses are **independent**, not compounded. Each output now
also identifies this diagnostic's own source SHA-256. Schedule-change reporting
compares baseline/candidate choices rather than modeled effect summaries,
which can change even when selected schedule times do not.

For original capture `20261001T150530Z-25496c123c0be79f.json.gz`, its output
digest is `25496c123c0be79f021e4858fb6dfe93f04cf106fdbb07dd2a594c6e1994de89`.
The currently installed shade-corrected runtime **refused exact replay** of
this particular capture; no comparison was accepted under changed behavior.
An isolated runtime copy with the privately retained original `behavior.py`
restored then matched the original full source pin
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095` and
reproduced the original publication exactly. It was automatically removed.

At its 12-hour target, the original prediction was 64.039°F, observed
68.540°F (error -4.501°F). A **uniform hypothetical -10°F forecast shift**
produced 62.986°F, another -1.053°F with unchanged modeled schedules. The
separate assumed-closed-vent scenario produced 64.491°F, only +0.452°F.
Neither scenario supplies actual weather or an authenticated vent label.
This one case supports investigating action/solar/thermal forcing, not applying
a temperature-only correction to erase the indoor cold miss. No coefficient,
artifact, journal, Item, recurring collector or household control changed.

Verification: the new cases first failed against the old diagnostic; the final
combined replay, operational-score, immutable-capture, pipeline and behavior
slice passed **200 tests in 37.37 seconds**, no skips. This is the affected
slice, not a new full-project test claim. Today's original 08:14 capture also
replays exactly under the installed `7316fa8b...` pin with a zero temperature
shift: all reported horizon deltas are zero and schedules unchanged. Final
diagnostic source SHA-256:
`d999c9170977827a8d0b9bc4449c8fc669f1e3bb2f7c784f50200bfb9d991ac2`.
The tool runs from the local repository; no forecast worker/service deployment
or restart is needed. Primal's separate bounded follow-through still accepted
zero authenticated replies and reported one relay failure; no new question.

## October 2 natural training and newly mature 12-hour outcomes

The natural training journal records start at 06:50:29 MDT and successful
completion at 07:09:55, with 19m23.462s consumed CPU. This is a completed
pre-reboot invocation, not the empty timestamps reported by the new user
manager after the host's later boot. Accepted and candidate canonical artifact
SHA-256 both equal
`2435c01964842c98829d25499b161b68dfab1d83a389e8b4ce0689eff2391d79`;
`previous.json` retains October 1's
`5dc0d548aefe0e60299dab1ae4b71372dc0f95f49f3034ab480f56194fe32be6`.
The rolling data manifest contains 99,873 samples, from
`2025-08-28T12:50:29.152925Z` to `2026-10-02T12:50:29.152925Z`.
The accepted artifact remains `shadow_only=true`, with zero confirmed action
training rows/evaluation targets and no operational graduation thresholds.

The restored 08:14 forecast's frozen artifact is this new October 2 artifact.
Exact replay of `20261002T141436Z-b62ec2084fc3986a.json.gz` under installed
revision `7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`
returns `exact_as_issued=true`, with output SHA-256
`b62ec2084fc3986a913088482aa209b89b54647e0a702a8b77698f51ec732e44`.
This proves reproducibility, not accuracy or graduation.

The separate read-only 12-hour operational audit was restricted to the October
1 artifact and original captured publications issued within
`[2026-10-01T15:00:00Z, 2026-10-02T08:00:00Z]`. It scored six mature pairs and
withheld three not-yet-due targets. Targets use the existing closest hourly
point within 30 minutes of issue+horizon, not exact elapsed 12-hour targets.

| Statistic | Model | Starting-temperature persistence |
| --- | --- | --- |
| Mean absolute error, six overlapping pairs | 2.9315°F | 2.7600°F |
| Signed mean error | -2.9315°F | +2.1600°F |
| Paired wins | 3 | 3 |
| MAE, one greedy non-overlapping pair | 4.501°F | 1.800°F |

All six indoor errors are cold, from -4.501°F to -1.808°F. The corresponding
outdoor forecast errors are warm, from +6.70°F to +11.16°F, mean +9.3833°F.
This association does not identify causality: simply reducing outdoor forecast
temperatures is not demonstrated to correct the indoor cold bias. All observed
targets lie within the broad modeled intervals (mean width 10.4133°F), which
also does not establish useful point-forecast accuracy.

Reproduce the bounded, source-bound audit without writes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit-thermal-shadow-publications.py \
  --since 2026-10-01T15:00:00Z --until 2026-10-02T08:00:00Z \
  --require-capture --horizon-hours 12 --include-pairs \
  --artifact-id 5dc0d548aefe0e60299dab1ae4b71372dc0f95f49f3034ab480f56194fe32be6 \
  --runtime-root /home/sat/openhab/scripts
```

Later reruns may mature the remaining targets and therefore change the counts.
These outcomes strengthen the existing decision to retain shadow mode and
investigate forcing/action assumptions. No artifact, coefficient, source,
training label, journal or control was modified by this audit. Durable radiation
history and the zero-duration shade fix were subsequently approved and deployed;
see [the October 2 live qualification record](2026-10-02-radiation-history-and-shade-collision.md).
The truthful signed Primal trial remains separate, with its reply pending.

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

## October 1 natural original-input qualification

The actual daily invocation `f402931b61a64890b557cece2738221e` ran at
06:40:29–31 MDT and exited zero. A read-only inspection of the private
prediction record, installed archive validator, live receipt and bounded
repeatable-read JDBC window qualified its original weather linkage. No
forecast rerun, Item write, training, collector or control was started.

Prediction origin is `2026-10-01T12:40:30.513835+00:00`. The exact capture is
`2026-10-01T12:40:30.510517+00:00`, 3.318 ms before the origin, with digest
`ea7bac6fb4a7435bb80f4e72fd967da9191aa3a7a6c0549005693509ab6c72e7`.
Its original reference resolves to
`2026-10/ea7bac6fb4a7435bb80f4e72fd967da9191aa3a7a6c0549005693509ab6c72e7.json.gz`
under the documented private archive root. Root/month are owned mode 0700;
archive is owned mode 0600. Exact bounded decompression, canonical digest,
reference, date and capture-before-origin validation passed.

The request identifies the configured 38.3739919/-105.7744609 site,
America/Denver, ten days, Fahrenheit, mph and inches. The response grid point
is 38.367577/-105.776054; this is not a change to the configured request site.
All ten daily and 240 hourly arrays have matching lengths. Raw daily radiation
(`MJ/m²`), temperatures (`°F`) and precipitation (`inch`) match the retained
original prediction inputs exactly; radiation-to-kWh/m² conversion is checked.
Hourly radiation is `W/m²`, wind `mp/h`, probabilities `%`, and `is_day` is
the provider's dimensionless field. This records units, not a claim that every
hour is qualified forcing for every downstream model.

The 988-byte public prediction receipt includes the exact weather digest,
qualified SoC origin and solar-context origin. Its raw body exactly matches
the sole original JDBC row in the bounded issue window: unique Item **654**,
receipt `2026-10-01T12:40:30.617953+00:00`, body SHA-256
`462708823957cfab9484a88b54696d59dabfa7c7f4e5b7632e016b74220c8852`.
Original PV is 6.58 kWh; live Home and Energy render 6.6 kWh.

The natural 00:10 Astro context also qualifies: unique Item **662**, sole
post-midnight JDBC receipt `2026-10-01T06:10:00.158091+00:00`, exact body digest
`e9b4d698aacf3521cf9da915fa52035138edf90505eabb8228850d96a58c99bd`.
The installed strict Astro validator reproduces the retained prediction's
entire context at its original origin; the public solar digest agrees. Today
and tomorrow daylight durations are 42,151.462 and 42,003.545 seconds.

Exact installed file digests at qualification:

| File | SHA-256 |
| --- | --- |
| `forecast_intel.py` | `943c09d414c6265d5a9527bb1901c3e8aa7355fc190f261a61cf58d02fbed58e` |
| `forecast_input_capture.py` | `ece90822c94d7ac7fb81fcd6bc5a9dd664eaf9f994bef65042e0b4f0ffdb03fa` |
| `astro_forecast_context.py` | `c65f647befed00c9a00922583544ecb0a8675624f218ed3ff69b1ea63427ac04` |

This closes the **first natural original-input archive and daily Astro
capture gates**. It does not backdate earlier weather, qualify a completed
October 1 charge/overnight outcome, increase retained prediction history,
release PV calibration, or establish thermal skill. Next work is joining
future qualified outcomes to these exact bound inputs and scoring chronological
joint-model candidates without future-data leakage.

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

### Measured-radiation source qualification gap

September 30 around 21:47 MDT, a bounded read-only source/runtime inspection
traced `AmbientWeatherWS2902A_SolarRadiation` to
`http:url:weatherData:solarRadiation`. The Thing is ONLINE and the nighttime
Item is `0 W/m²`, but those facts do not establish a fresh radiation receipt.
The installed `rtl_weather.py` filters station ID 206 and computes
`round(min(light_lux / 126.7, 1200.0), 2)`. This is a lux-derived irradiance
proxy with a fixed conversion and clamp, not independently calibrated incident
solar energy. The receiver can fall back to `WH65B_solarradiation` when the raw
field is missing; its model-level health timestamp is renewed before that
field is validated. Repeated HTTP reads must not renew source evidence.

The existing temperature receipt does not contain the radiation field, and
the rain receipt is counter-specific. Neither can make the radiation value
atomic/source-bound merely because the station's other fields are healthy.
Existing numeric JDBC irradiance history therefore remains diagnostic under
this inspected path; no source-qualified historical pairing is claimed.

The separate, already-running radio exporter does retain an original UTC
decoder observation time and rejects incomplete selected-station packets.
Its read-only SQLite inspection found exactly one `snapshot` table and one
singleton observation, not an observation history. At inspection the packet's
`radio_decode_utc` time was `2026-10-01T03:47:18.000Z`, age 13.616 seconds,
and derived radiation was 0 W/m². Polling or restarting does not manufacture
that timestamp. This is decoder receipt time, not sensor measurement time;
the latest-only export cannot backfill historical irradiance qualification.

Installed source fingerprints at this checkpoint:

- `/home/sat/bin/rtl_weather.py`: `3d281df04dc62d0dca7a43c1fbc85fc45debca960197a6ba8c3716c651b9893a`
- `/home/sat/bin/weather.py`: `1cd65bfe7966da558aed156373501ebfb7116c0dd5f6ca62a31e0901067e1572`
- `/home/sat/bin/weather_evidence_wsgi.py`: `366698fdccc7296060b1342c1a3f42d7a3b2c7cca57856c9e817af9a7ff7c51d`
- `/usr/local/lib/lightning-goats-weather/lightning_goats_weather.py`: `5ab66cfc92e8d2f794027daa432b71f9145aa8b215c2ee6817cc057d4613cda4`

A bounded extension of the existing weather receipt collector was proposed:
separate radiation evidence retaining raw lux, explicit conversion provenance,
station identity, receipt epoch and expiry; no cached substitute or poll-time
renewal. The user subsequently approved source-only/default-off preparation.
The [October 1 candidate](2026-10-01-radiation-receipt-candidate.md) records the
implemented contract and remaining live deployment/history gates. At the
original inspection no collector, dependency, Item, privilege, unit or source
modification was made; the inspection used a read-only database connection.

## October 1 expanded operational outcomes and shade-timing collision

At `2026-10-01T18:53:57.932515Z`, a bounded read-only audit scored the 16
original JDBC publications issued since September 30 12:00 UTC. Each scored
publication required its exact original forcing archive; every outcome used
the restricted indoor/outdoor source-receipt reader. One publication fetch,
16 cached capture reads and 54 cached stream/target reads served all four
horizons. Nothing was refitted, published, labelled or activated.

| Audit horizon | Qualified overlapping pairs | Model MAE °F | Persistence MAE °F | Chronological non-overlapping pairs |
| --- | ---: | ---: | ---: | ---: |
| 1 hour | 16 | 0.6642 | 0.2138 | 15 |
| 6 hours | 13 | 2.2155 | 1.0246 | 4 |
| 12 hours | 10 | 3.1476 | 1.8000 | 2 |
| 24 hours | 3 | 4.9593 | 2.1600 | 1 |

These are nearest hourly trajectory targets within the scorer's ±30-minute
tolerance, not necessarily exact elapsed horizons. Results mix three captured
artifacts; they must not all be attributed to today's model. Today's artifact
has canonical embedded digest
`5dc0d548aefe0e60299dab1ae4b71372dc0f95f49f3034ab480f56194fe32be6`,
distinct from its previously recorded file-byte digest. Only its two one-hour
targets have matured: model/persistence MAE is 0.3300/0.2700°F, with one win
each. It has no qualified six-, twelve- or twenty-four-hour outcome yet.

The three newly mature near-24-hour indoor errors are −4.836, −4.839 and
−5.203°F; their qualified outdoor forecast errors are +4.86, +5.78 and
+5.34°F. These warm outdoor-input errors do not identify an explanation for
the cold indoor bias. All three broad intervals cover the outcomes with about
10.414°F width; overlapping coverage is not calibration or graduation proof.

The September 30 08:30 and 10:31 MDT captures replay exactly under installed
runtime `7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`.
Separate in-memory hypotheses produce these changes at the same qualified
targets; neither is a physical observation or replacement prediction:

| Original issue MDT | Original near-24-hour error °F | Closed-vent delta °F | 1.5× forecast-radiation delta °F |
| --- | ---: | ---: | ---: |
| Sep 30 08:30 | −4.839 | +1.070 | +0.559 |
| Sep 30 10:31 | −5.203 | +1.039 | +0.384 |

Closing modeled vents leaves errors of −3.769/−4.164°F. The separate radiation
scenario leaves −4.280/−4.819°F and does not change either modeled schedule.
Neither isolated hypothesis explains these misses. Independent airflow/shade
observations and radiation outcomes remain necessary before a causal refit.

Today's natural 11:05 MDT capture also replays exactly, output SHA-256
`9915e9e5d8421131360cbd4f8d3ce047bd69dabaa1d55f336065c12515ba6b83`,
with training revision equal to the installed runtime. Its closed-vent
scenario adds 1.122°F at tomorrow's near-24-hour target, **not yet scored**.
The separate 1.5× radiation probe is refused, rather than assigned an outcome:
the original maximum is 796 W/m² (scaled maximum 1,194, within the input bound),
but both learned shade times round to 12:00. The producer emits simultaneous
`closed`/`open` transitions on three days; strict pipeline validation correctly
rejects them with `modeled shade transitions must be strictly ordered`.

This identifies a schedule-producer defect, not a reason to relax validation
or a failure of the unchanged as-issued publication. Its existing cyclic
initial-state formula interprets equal times as zero closed duration. A bounded
source-only correction was proposed: emit no transitions in that case, retain
the all-open modeled state, preserve other schedules and add unit/integration
regressions. Design approval is pending; no correction is installed. The first
audit attempt refused an incorrect `/home/sat/bin` runtime; the successful
audit uses the documented `/home/sat/openhab/scripts` closure. An exploratory
diagnostic print used a nonexistent output key; a separate corrected read
verified the exact refusal reason above. Neither failed probe counts as a
successful model comparison. No test fixture or new observation was retained.
The existing publication-audit and forcing-replay regressions pass **36 tests
in 0.46 seconds**. Only this run's disposable fixture directory is removed;
original captures and operational recovery backups are retained.
