# History Extrema Markers Design

Date: 2026-07-20

## Context

The shared history modal currently renders lines, legends, tooltips, and
period controls but does not identify extrema. The Home page's Outdoor
Temperature and Battery SoC modals need High and Low markers calculated from
the history returned for the currently selected 4-hour, 24-hour, or 7-day
period.

openHAB's analyzer models markers as a per-series option and expands its
`min-max` selection into distinct minimum and maximum markers. Earthship UI
will follow the same series-level opt-in model rather than adding logic keyed
to modal titles.

Official reference:

- https://github.com/openhab/openhab-webui/blob/main/bundles/org.openhab.ui/web/src/pages/analyzer/chart-time.ts
- https://github.com/openhab/openhab-webui/blob/main/bundles/org.openhab.ui/web/src/pages/analyzer/analyzer-helpers.ts

## Scope

- Add High and Low markers to measured Outdoor Temperature history.
- Do not mark the Outdoor Forecast overlay.
- Add High and Low markers to Battery SoC history.
- Recalculate markers whenever the selected modal period changes or history
  refreshes.
- Make the extrema calculation and ECharts marker construction reusable by
  any history series.
- Include the marked values in the modal's accessible description.

All other modal series remain unchanged unless they explicitly opt in.

## Series Contract

A history series may opt in with:

```js
{
  name: 'BMS_SOC',
  label: 'SoC',
  color: '#...',
  markers: ['min', 'max'],
  markerUnit: '%',
}
```

`markers` is declarative and series-scoped, mirroring openHAB's marker
configuration. The supported values for this change are `min` and `max`.
Omitting the field produces the current chart with no extrema markers.

## Shared Extrema Logic

Add a focused chart utility that consumes normalized points for one selected
history window and returns explicit High and Low marker records. It will:

- Ignore non-finite values.
- Preserve the timestamp and raw value of each selected extreme.
- Choose the earliest point when the same extreme value appears more than
  once, matching a deterministic first-match interpretation.
- Return no marker data when the series has no usable points.
- Leave the input points unchanged.

The same result feeds both the ECharts `markPoint` configuration and the
screen-reader description, keeping visual and accessible values identical.
Marker labels use `High` or `Low`, a value rounded consistently with existing
history tooltips, and the configured `markerUnit`.

## Chart Integration

`buildHistoryOption()` already prepares each selected-period series before
constructing its ECharts line option. For opted-in series it will pass the
prepared normalized points to the shared extrema utility and attach the
resulting pin-shaped `markPoint` data to that line only.

The ECharts bundle will register `MarkPointComponent`. Marker color follows
the source line color and label text uses the existing high-contrast chart
palette. Existing line, legend, tooltip, downsampling, gap, and forecast
behavior remains unchanged.

Because `ChartModal` reloads history and rebuilds options after each period
selection, extrema automatically track 4h, 24h, and 7d without separate
state or requests.

## Home Modal Configuration

The measured Outdoor series will opt in with `markers: ['min', 'max']` and
`markerUnit: '°'`. The Forecast series will not opt in.

The Battery SoC series will opt in with `markers: ['min', 'max']` and
`markerUnit: '%'`.

No fixed `OutdoorTemp_24h_High` or `OutdoorTemp_24h_Low` item is used by the
modal because those values would not follow the selected range. No additional
openHAB requests or synthetic history series are introduced.

## Accessibility and Failure Behavior

When markers exist, the modal's live accessible description will announce
the marked series label and its High and Low values. Empty, unavailable, or
partially failed series produce no extrema announcement and retain the
existing loading and error messaging.

A marker-construction failure must not hide the underlying history line. The
shared utility returns an empty marker result for unusable data, and the
existing chart error boundary continues to handle unexpected rendering
errors.

## Testing

- Unit-test extrema selection, duplicate ties, non-finite values, empty data,
  units, and input immutability.
- Test that `buildHistoryOption()` attaches markers only to opted-in series.
- Test that Outdoor markers apply only to measured history and Battery SoC
  carries percent markers.
- Test a period change with different returned extrema and verify both chart
  options and the accessible description update.
- Verify ECharts tree-shaken registration includes `MarkPointComponent`.
- Run the focused chart/modal tests, full Vitest suite, production build, and
  the existing household viewport checks at 1340x800 and 1280x720.

## Acceptance Criteria

- Outdoor Temperature shows High and Low pins for measured data in the
  selected modal period.
- Battery SoC shows High and Low pins for the selected modal period.
- Switching among 4h, 24h, and 7d recalculates the displayed extrema.
- Forecast and all non-opted-in modal series remain unmarked.
- Other modals can enable the same behavior using the series contract without
  changing `ChartModal`.
- Visual and accessible extrema values agree.
- Tests, build, and target viewport checks pass.
