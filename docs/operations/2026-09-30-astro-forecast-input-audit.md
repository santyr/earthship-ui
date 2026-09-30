# Astro inputs for forecast tuning

Read-only household inspection on September 30, 2026, approximately 14:46–14:49
MDT. This adds the operator's day-length hypothesis to the forecast-divergence
work. No Thing, Item, link, rule, prediction, coefficient, timer or control was
changed. No action method was executed; availability was checked against the
live action-module registry and the official
[Astro binding documentation](https://www.openhab.org/addons/bindings/astro/).

## Live inventory

`astro:sun:local` is ONLINE, with a 16-second refresh interval and astronomical,
not meteorological, seasons. It exposes 67 state channels and 15 trigger
channels; 26 state channels have links. Phase has two linked Items, including
the transformed UI icon. The inspected time/event channel offsets are zero.

| Forecast-relevant channel | Existing linked Item | Intended use |
| --- | --- | --- |
| `daylight#duration` | `Sun_Daylight_Duration` | Continuous daily solar-window length |
| `daylight#start` | `Sun_Daylight_Start` | Start of full daylight |
| `rise#start`, `rise#end` | `Sun_Rise_Start`, `Sun_Rise_End` | Dawn/charging context with an explicit event definition |
| `set#start`, `set#end` | `Sun_Set_Start`, `Sun_Set_End` | Dusk, remaining charge opportunity and discharge timing |
| `night#duration` | `Sun_Night_Duration` | Astro night duration; not a synonym for battery discharge duration |
| `astroDusk#end` | `Sun_AstroDusk_End` | Astronomical darkness boundary |
| `position#elevation`, `position#azimuth` | `Sun_Position_Elevation`, `Sun_Azimuth` | Solar geometry for PV and glazing/shade exposure |
| `position#shadeLength` | `Sun_ShadeLengthRatio` | Calculated shadow geometry, not an observed shade position |
| `radiation#direct`, `radiation#diffuse`, `radiation#total` | `Sun_DirectRadiation`, `Sun_DiffuseRadiation`, `Sun_TotalRadiation` | Calculated solar reference; not cloud-aware forecast or measured irradiance |
| `season#name`, `season#nextName`, `season#timeLeft` | `Sun_SeasonName`, `Sun_NextSeason`, `Sun_TimeLeft` | Calendar context, not a substitute for solar geometry |
| `phase#name` | `Sun_SunPhaseName`, `SunPhaseIcon` | Current solar phase and UI icon |

Existing linked seasonal dates and eclipse channels were inspected too; they
are not priority predictive inputs. Unlinked channels include `daylight#end`,
solar noon, civil dawn/dusk and their durations. Sunrise, sunset, daylight,
twilight, night and midnight trigger channels are available. Trigger events
need no state Item; do not link or persist every channel just because it exists.
Circadian brightness/temperature are calculated lighting suggestions, not
measured brightness or outdoor temperature.

### Definitions and persistence

Today's daylight Item is 42,299.467 seconds (11 h 44 m 59 s). It exactly matches
sunrise **end** (07:01:49.187) to sunset **start** (18:46:48.654). The Home page
instead uses sunrise start to sunset end: 42,624.471 seconds, 325.004 seconds
longer. Neither interval may silently replace the other in a learned feature.
No UI change is included here.

Astro night is 33,269.184 seconds today; it is not `86400 - daylight`.
Battery net-discharge starts/ends depend on PV versus load, not an astronomical
night or an assumed fixed overnight schedule. Use measured source-bound
current/SoC for those outcome boundaries.

Bounded JDBC reads found 30 rows on 30 distinct local dates, September 1–30,
for each duration Item, with no missing September date. Today each has one
persisted row while live updates continue. That is expected change-only
persistence, not stale acquisition. Today's bounded reads also returned 3,329
rows each for elevation and azimuth and 1,687 for calculated total radiation.
These are row counts, not proof of continuous observation quality or historical
forecast provenance. Do not add 16-second duration receipts or interpret these
astronomical calculations as source-health evidence for weather/BMS sensors.

## Actions actually registered on this installation

The live `/rest/module-types` registry exposes all four methods and includes
`astro:sun:local` in their Thing options:

- `getEventTime(phaseName, date, moment)` returns a `ZonedDateTime`; request a
  specific date and START/END for sunrise, sunset, daylight or twilight.
- `getElevation(timeStamp)` and `getAzimuth(timeStamp)` return angle quantities.
- `getTotalRadiation(timeStamp)` returns an intensity quantity.

These calculation actions allow future-date geometry without treating today's
held Items as tomorrow's values. They are in-process OpenHAB binding actions,
not an already-qualified HTTP calculation API for the Python forecast jobs.
Their actual result semantics, date/zone handling and version must be checked
in an isolated harness before adding an observational exporter. Do not create
or manually execute a production rule merely to probe them. Cache geometry by
site/date/time grid; avoid per-sample remote calls or new frequent polling.

## Current model use and next experiment

`forecast_pre_dusk.py` already uses `Sun_Set_Start` to require a fresh atomic
SoC issue 60–90 minutes before sunset. Its trough is issue SoC minus a trailing
drop proxy; it has no season/day-length coefficient to turn up. The morning
`forecast_intel.py` energy calculation uses cloud-aware daily radiation sum,
demand/SoC deficit and recent qualified minima, not an explicit season weight.
Its drop proxy is `99 - measured trough`, **not measured dusk-to-trough drop**;
that discrepancy remains an important tuning target. The existing qualified
night-start reader uses 20:00 local, explicitly not necessarily sunset.

The thermal model already calculates site/date-specific solar elevation and
clear-sky normalization in `thermal_model/solar.py`. Its seasonal behavioral
reconstruction is distinct from its physical temperature/radiation dynamics.
Changing a coarse season label alone will not resolve missing genuine
window/skylight/shade observations or thermal lag. Do not remove existing
solar geometry, silently replace the solar contract, or promote reconstructed
behavior to observed action labels.

Next, compare the unchanged baseline with solar-context variants on identical
chronological, as-issued holdouts:

1. Continuous daylight duration, hours until sunset/next sunrise and duration
   of the actual modeled overnight interval. Test these before giving calendar
   season labels more influence; retain weather, SoC and demand inputs.
2. Solar elevation/azimuth or a cached clear-sky energy integral, plus cloud-aware
   hourly radiation. Account for their correlation: daily forecast radiation
   sum already includes the length and strength of the solar window. Do not
   multiply it by day length again without out-of-sample evidence.
3. Day-length change and recent thermal/mass history, with and without season
   context, to distinguish equal-length spring/autumn days and seasonal lag.
4. Qualified dusk-to-trough discharge and PV/load crossover timing, rather
   than assuming a full bank at dusk. Score full-charge timing separately and
   retain curtailment/demand-limit context when evaluating actual harvested PV.

Fit feature scaling and any weights on training data only. Compare baseline,
solar-context only and solar-context plus seasonal residuals with nested
chronological tuning, horizon-specific bias/MAE, weather/SoC regimes and
coverage counts. Historical astronomical geometry can be reconstructed for
the relevant date; historical weather forecasts must be the snapshots issued
then, not hindsight actual weather. Sparse/absent snapshots remain withheld.
Do not claim winter/general-season skill from September rows alone. Deploy
only a tested improvement without changing existing issued history or outcome
definitions. This audit adds an experiment, not a live model weight change.

## Executable historical comparison checkpoint

`scripts/experiment-forecast-solar-context.py` now assembles one 08:45 Mountain
origin per local date, a 24-hour raw outdoor-temperature forecast from one
complete weather issuance captured before that origin, and a source-qualified
WH65B/206 temperature receipt at the target. It reuses the existing restricted
forecast reader and exact temperature identity/expiry policy. Historical Astro
daylight and season are selected only from original rows persisted by the
origin. The daylight feature is **the origin day's duration**, not a claimed
tomorrow calculation. The Sun Items are not readable by `energy_power_reader`;
the existing authenticated read-only OpenHAB JDBC endpoint supplies them without
any new database grant. No in-process Astro action or exporter was installed.

`openhab/scripts/forecast_solar_ablation.py` compares raw forecast, fitted
constant bias, season-only, daylight-only and combined residual corrections.
Ridge strength is fixed at 1; feature scaling, intercept and coefficients use
training rows only. Training targets must have elapsed before the frozen split.
Unseen/constant training features acquire no invented effect, daily forecast
windows do not overlap, and missing observations are not interpolated. The
tool refuses spring-forward daily origins with overlapping 24-hour targets;
fall-back origins preserve 08:45 local time and remain nonoverlapping.
This is not the current production Kalman correction or a thermal simulation.

The September 30 15:10 MDT household run was:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/experiment-forecast-solar-context.py \
  --start-day 2026-09-05 --end-day 2026-09-30 --split-day 2026-09-25
```

Of 25 origin dates, 14 had no qualified outdoor target receipt and 11 paired:
six training days and five held-out days. The fixed minimum remains ten training
and five test days, so the fitted comparison correctly reports
`withheld_insufficient_pairs`, with no variant scores. Do not lower that minimum
after inspecting the result just to manufacture a comparison. Unfitted raw
forecast scoring remains legitimate: those five held-out origins have MAE
**1.553°F** and signed forecast-minus-actual bias **+1.085°F**. Their outcomes
occur September 26–30 at 08:45; these numbers must not be attributed to the
learned UI correction or to an improved daylight model. Pair digest:
`8517d771162318768cf00f31ba7b03ad1ff117ed4eda6430026d2f9d0f65f6d6`.

A separate restricted, read-only 90-day forecast capture census found 386
distinct issues on 34 local dates, August 20–September 30, with no issue dates
August 28–September 4. A capture date is not necessarily a qualified target or
a complete issue; this does not satisfy a 90-paired-day model prerequisite.
Later expansion needs a newly specified chronological split with enough mature
training/holdout days, not hindsight backfill of the missing receipts.

All 68 affected ablation, archive-reader and temperature-history tests pass.
The first household attempt refused a 400-row solar archive limit: the retained
season history has 856 rows, including older repeated observations. Only the
season reader's explicit limit was corrected to 2,048; daylight remains bounded
to 64 rows. Original ordering and as-of selection remain enforced; no rows were
deduplicated or source TTLs relaxed. No temporary data, model artifact, timer,
learned state, Item, notification, collector or control was created or changed.
