# Ten-Day Weather Detail Modals

**Date:** 2026-07-18
**Status:** Approved for implementation planning
**Approach:** OpenHAB-owned, versioned forecast payload
**Surfaces:** Earthship UI Home and Weather routes

## 1. Goal

Show ten forecast days on both Home and Weather. Activating any day opens a
focused modal with ten hourly forecast points:

- today: the next ten local forecast hours, including a midnight crossover;
- future days: 08:00 through 17:00 local time.

The first release shows temperature, precipitation probability, solar
radiation, wind, and weather conditions. The payload and component boundaries
must allow more hourly fields later without changing the modal controller.

## 2. Current State and Compatibility Boundary

The current pipeline materializes:

- `Forecast_Hourly_JSON`: the next 14 hours, consumed by Earthship UI and an
  OpenHAB MainUI repeater;
- `Forecast_Daily_JSON`: seven summaries, consumed by Earthship UI and an
  OpenHAB MainUI repeater.

The MainUI repeaters iterate every array entry. Expanding either existing item
would change retained MainUI layouts and violate compatibility. Both existing
items therefore remain structurally and behaviorally unchanged.

The generic Open-Meteo Forecast API supports up to 16 forecast days, so a
ten-day hourly horizon is within the provider contract:
<https://open-meteo.com/en/docs>.

## 3. Architecture

The existing OpenHAB producer remains the only external weather client:

1. `forecast_intel.py` fetches a single ten-day Open-Meteo snapshot containing
   the daily and hourly variables required by this feature.
2. It continues publishing the existing 14-hour and seven-day items without
   changing their contracts.
3. It additionally publishes a versioned `Forecast_10Day_JSON` String item.
4. Earthship UI receives that item through the existing OpenHAB REST bootstrap
   and SSE item stream.
5. A pure adapter validates the payload and selects the requested ten-hour
   window.
6. Home and Weather render a shared day-button primitive.
7. One application-level modal controller and modal render detail from either
   route.

No browser request goes directly to Open-Meteo. The feature remains usable on
the LAN with the same credential and proxy boundaries as the rest of the UI.

## 4. OpenHAB Forecast Contract

### 4.1 Item

Create one unlinked String item:

`Forecast_10Day_JSON`

It is display data only. No rule or UI surface may command it. Provisioning
must use a narrowly scoped, reversible snapshot/create/readback procedure.

### 4.2 Payload

The item state is a JSON object:

```json
{
  "version": 1,
  "generatedAt": "2026-07-18T14:00:00-06:00",
  "timezone": "America/Denver",
  "days": [
    {
      "date": "2026-07-18",
      "label": "Today",
      "summary": {
        "highF": 83,
        "lowF": 52,
        "precipPct": 18,
        "weatherCode": 1,
        "pvKwh": 6.4
      },
      "hours": [
        {
          "at": "2026-07-18T14:00:00-06:00",
          "tempF": 81,
          "precipPct": 12,
          "radiationWm2": 690,
          "windMph": 9,
          "weatherCode": 1
        }
      ]
    }
  ]
}
```

Contract rules:

- `version` is exactly `1`.
- `generatedAt` and every `at` value include a UTC offset.
- `timezone` is `America/Denver`.
- `days` contains at most ten unique, ascending ISO dates.
- Each day contains its summary and all available hourly records for that
  calendar date, ordered by timestamp.
- Numeric provider nulls remain `null`; they are not converted to zero.
- Unknown extra fields are ignored for forward compatibility.
- The serialized payload must remain below 64 KiB. A larger or malformed
  snapshot is rejected before publication.

### 4.3 Provider Query and Refresh

The producer requests ten forecast days with:

- hourly temperature;
- hourly precipitation probability;
- hourly shortwave radiation;
- hourly 10 m wind speed;
- hourly weather code;
- the existing daily summary variables.

The existing `forecast-json.timer` remains on its two-hour cadence. The daily
prediction/scoring run continues at 06:40.

One provider response builds all three outputs. Preserve the existing
publication path first, then publish the additive capability:

1. existing `Forecast_Hourly_JSON`;
2. existing `Forecast_Daily_JSON`;
3. `Forecast_10Day_JSON`.

Each state update is atomic. A new-detail build or publication failure does not
block either existing item from refreshing. The new payload contains both its
summaries and supporting hours, so it cannot expose a new day without that
day's detail.

## 5. UI Boundaries

### 5.1 Pure Forecast Adapter

Add a framework-independent module responsible for:

- payload size and schema validation;
- stable date ordering and duplicate rejection;
- stale-state classification;
- day lookup by ISO date;
- ten-hour window selection;
- partial-coverage reporting.

Window selection:

- selected date is today: select the first ten records at or after the current
  local hour, continuing into the next date when necessary;
- selected date is in the future: select records from 08:00 through 17:00 on
  that date;
- never substitute hours from a different future day;
- preserve chronological timestamp order across midnight and daylight-saving
  transitions.

### 5.2 Shared Day Buttons

One shared component consumes validated daily summaries and emits the selected
ISO date. It has two bounded presentation variants:

- Home: one full-width strip of ten compact day buttons;
- Weather: two columns with five day buttons each.

Each day is a native button with an accessible name containing its date,
condition, high/low, and precipitation probability. The component does not own
modal state or parse raw JSON.

### 5.3 Modal Controller

One store/controller owns:

- open state;
- a monotonically increasing open identity;
- selected ISO date;
- opener element for focus restoration.

Opening from Home or Weather replaces the current selection atomically. Closing
clears the selection and restores focus to the exact day button that opened
the modal.

### 5.4 Weather Detail Modal

Mount one application-level modal alongside the existing chart modal. It shows:

- selected date and condition;
- daily high/low and maximum precipitation probability;
- ten hourly weather icons and local-hour labels;
- temperature line;
- precipitation-probability bars;
- solar-radiation ribbon;
- wind line and hourly values.

The first release is read-only and has no period picker. Future metrics may be
added to the validated hourly record and chart configuration without changing
the controller or day-button interface.

## 6. Interaction and Accessibility

The modal:

- uses `role="dialog"` and `aria-modal="true"`;
- has a programmatic title and description;
- moves focus to its close button on open;
- traps Tab and Shift+Tab while open;
- closes with Escape, the close button, or backdrop activation;
- does not close when its content is activated;
- restores focus to the opener on close or route change;
- locks background interaction while open;
- respects reduced-motion settings.

Home and Weather activation must work with touch, pointer, Enter, and Space
without custom keyboard emulation on non-button elements.

## 7. Layout

Supported targets remain:

- Lenovo Tab M9 landscape: 1340×800;
- laptop floor: 1280×720.

At both targets:

- all ten day buttons remain visible;
- the page, forecast card, and modal do not scroll;
- no required label, icon, value, legend, or close control is clipped;
- modal chart dimensions are measured from the available container;
- the modal presents exactly ten hourly columns when coverage is complete.

Phone layouts remain out of scope.

## 8. Failure and Stale States

The UI never throws on missing, sentinel, oversize, malformed, duplicated, or
unsupported payloads.

- Missing or invalid payload: existing route content remains usable; day
  detail is unavailable.
- Daily summary present but selected detail missing: open a named modal that
  says `Hourly detail unavailable`.
- Age over four hours: retain the forecast and show a visible stale warning
  with the generation time.
- Fewer than ten selected hours: render available records and state the exact
  coverage, such as `7 of 10 hours available`.
- Missing individual metric: render an em dash for that metric without
  dropping the hour.
- Unknown weather code: use the existing unknown-condition icon and label.

The existing 14-hour strip and seven-day MainUI forecast remain available even
if the new item is absent.

## 9. Verification

### 9.1 Producer

Automated tests cover:

- one provider snapshot producing ten ordered days;
- unchanged 14-hour and seven-day compatibility payloads;
- wind inclusion and provider-null preservation;
- offset-bearing timestamps;
- midnight and daylight-saving transitions;
- payload size rejection;
- unchanged legacy publication before the additive detail item;
- continued legacy publication when detail build or publication fails.

### 9.2 UI Adapter and Components

Tests cover:

- strict version and schema validation;
- duplicate, unordered, oversize, and corrupt payload rejection;
- today rolling ten-hour selection;
- future 08:00–17:00 selection;
- midnight crossover and daylight-saving ordering;
- stale and partial coverage;
- Home strip and Weather two-column variants;
- activation from both routes;
- modal charts and unavailable states;
- Escape, backdrop, focus trap, and focus restoration.

### 9.3 Browser Geometry

Playwright fixtures at both supported targets prove:

- ten day buttons on Home;
- ten day buttons on Weather;
- each route can open the same modal;
- complete data renders ten hourly columns and all five requested metric
  surfaces;
- no document, card, or modal scrolling;
- every required child remains inside its container;
- no console or page errors.

### 9.4 Live Rollout

Live deployment is a separate approval gate. It must:

1. snapshot the current producer, timers, item state, and item definition;
2. provision/read-verify only `Forecast_10Day_JSON`;
3. deploy and test the producer without changing its timers;
4. run one display-only JSON refresh;
5. verify the new item and unchanged legacy item shapes;
6. deploy the UI;
7. verify both routes and modal behavior on live forecast data;
8. retain an exact rollback procedure.

No actuator, OpenHAB command endpoint, or household control is involved.

## 10. Acceptance Criteria

The feature is complete when:

- Home and Weather display ten forecast days from the new versioned item;
- every day opens the shared ten-hour modal;
- today rolls from the current local hour and future days use 08:00–17:00;
- temperature, precipitation, radiation, wind, and weather condition render;
- missing, stale, and partial data are explicit and non-destructive;
- existing `Forecast_Hourly_JSON`, `Forecast_Daily_JSON`, and MainUI layouts
  retain their current contracts;
- all focused, full-suite, build, and supported-viewport checks pass;
- live item and UI rollout are read-verified after separate approval.

## 11. Non-Goals

- More than ten forecast days;
- humidity, cloud cover, visibility, air quality, or ensemble uncertainty in
  the first modal version;
- direct browser access to Open-Meteo;
- changing the existing 14-hour strip;
- changing retained OpenHAB MainUI weather layouts;
- phone-specific layout work;
- forecast-provider or battery-model recalibration;
- any household actuation.
