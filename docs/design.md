# Earthship Console UI — Design

**Date**: 2026-07-17 · **Approved direction**: custom SPA, WS-2000-console
aesthetic, tablet-first · **Operator**: Sat

## Goal

A custom household UI for the openHAB system, styled after the Ambient
Weather WS-2000 console (dark instrument-panel tiles, everything visible at
once, signature colors per domain) but specific to this application: weather
+ battery/solar + Earthship passive-thermal + greywater on one pane of
glass. Replaces MainUI as the *household* interface; MainUI remains the
admin/fallback surface.

## Devices (priority order)

1. **Lenovo Tab M9 (2023), landscape — the reference canvas.** 1340×800,
   Chrome/WebView, modest GPU. The Home console must fit this viewport with
   NO scrolling. Light on effects: no blur, minimal animation, crisp tiles.
2. **Laptop browsers** — same console, more whitespace, wider charts.
3. **Phones** — functional 2-column reflow of the same tiles; no dedicated
   design effort in v1.

PWA (manifest + service worker): installable on the tablet, last-known
state shown when offline with a stale banner. Time-of-day auto-dim
(console-style "auto brightness"): normal palette by day, dimmed variant
after dusk (driven by the astro sun phase item, not the clock).

## Design language

- Near-black background (#0b0e11-ish), tile panels with subtle rounded
  borders (1px, low-contrast), small-caps tile labels, hi/lo minima with
  timestamps in the console tradition.
- Large clean numerals (system/Inter, tabular figures) — modernized
  console, no faux-LCD segments.
- Signature colors: amber = temperature, cyan/green = wind, blue =
  rain/water, yellow = solar, battery = green→yellow→orange→red by SoC
  bands (the operator-approved 60/40/12 interim scheme, 50/30/12 at
  full-bank), violet = forecast/predictions, orange = advisories.
- Gauges where gauges belong: wind compass rose, battery SoC arc.
  Mini-graphs inside tiles (baro trend, SoC 24h) via ECharts sparklines.

## Architecture

- **Stack**: Svelte + Vite + Tailwind; ECharts (custom console theme) for
  charts. Single static bundle, no SSR.
- **Serving**: nginx (or caddy) static site on the LAN, e.g.
  `http://ogsatoth:8090`. Config (openHAB URL + API token) injected via a
  small `/config.json` served alongside the bundle, never committed;
  file perms 0640. LAN-only trust model, same as MainUI today.
- **Data layer** (one module, `openhab.ts`):
  - Initial load: `GET /rest/items` (single call, filtered client-side).
  - Live: **SSE** `/rest/events?topics=openhab/items/*/statechanged` with
    auto-reconnect + backoff; stale banner if silent > 90 s.
  - History/forecast: `GET /rest/persistence/items/{item}` — including
    FUTURE rows (forecast strategy) so charts draw prediction ahead of now.
  - Commands: `POST /rest/items/{item}` (plain text) for the control set.
- **Repo**: `github.com/santyr/earthship-ui` — **private**, under Sat's
  personal `santyr` account (NOT the lightning-goats org). Local clone at
  `~/earthship-ui`. `config.json` (openHAB URL + token) is gitignored and
  never committed. Build artifacts deployed to `/var/www/earthship-ui`
  (or equivalent).

## Screens (bottom tab bar on phone; left rail on tablet/laptop)

### 1. Home — the full console (fits 1340×800, no scroll)

Tile grid (indicative 4×3 landscape arrangement):
- **Outdoor** (hero, 2×1): big temp, feels-like, hi/lo+timestamps,
  condition icon (SkyConditionIcon), AQI chip.
- **Wind**: compass rose (direction needle, speed center, gust ring),
  max-today.
- **Rain**: day/event/week/month totals, rate when raining (tile pulses
  subtle blue while rate > 0).
- **Battery** (hero, 2×1): SoC arc gauge in band colors, charging bolt /
  discharging arrow, runtime-to-empty with basis label, current W in/out.
- **Solar**: PV today so far vs predicted (progress pair), current PV W,
  curtailment state lamp.
- **Indoor/Earthship strip**: room air, north-wall mass, south glazing —
  three mini-temps with delta arrows.
- **Baro**: pressure + trend mini-graph + tendency word.
- **Forecast strip** (wide 2×1): today/tomorrow icons+hi/lo, then D3–D7
  compact; PV kWh estimate under each day.
- **Sun & Moon**: rise/set, moon phase glyph, daylight remaining.
- **Advisory bar** (full-width, only when active): thermal advisory or
  deep-cycling warning, amber; taps to relevant screen.
- **Greywater lamp** (small): pump state + last-circulation age; green
  breathing dot while running.

### 2. Energy

SoC 24h+ curve with predicted trough drawn AHEAD of now-line (violet
dashed); PV production curve today vs prediction with accuracy badge
(±7d %); runtime + basis; curtailment window bar; 7-day PV outlook bars;
battery vitals (temp °F, cycles, capacity Ah, BMS health lamp).

### 3. Weather

Current header (console style); 14-hour strip chart (temp line, precip
bars, radiation ribbon); 7-day rows with PV integration; measured
wind/rain/pressure tiles; AQI tile with EPA bands; analyzer-grade charts
(temp forecast-vs-measured overlay).

### 4. Earthship

The thermal loop drawn as a loop: south glazing → room air → north mass
with live temps and flow-direction arrows sized by delta; buffering ratio
dial; thermal advisory panel; greywater block (pump status, mode
narrative from SouthOutlet_AutoStatus, last circulation, cycle history
strip); zone humidity row.

## Controls (view + key controls; rules stay the authority)

- Lights: living-room bulbs on/off + circadian enable toggle.
- Goat outlets 1/2 (existing switches).
- **Pump "request cycle" button**: writes ON to a new
  `SouthOutlet_ManualRequest` item; the SouthOutlet rule adds a trigger
  honoring it THROUGH every existing safety gate (comms, SoC cutoff,
  cooldown, hydrology timing), then resets it. UI never drives the outlet
  item directly.
- All controls require a press-and-confirm (600 ms hold) on the tablet to
  prevent pocket/child taps.

## Error handling

- SSE drop → auto-reconnect w/ backoff; >90 s silent → amber "live data
  stale" banner; >10 min → tiles dim to 50%.
- openHAB unreachable → full-screen console-style "STATION OFFLINE" state
  with last-known values and their age.
- NULL/UNDEF item states render as "—" with dimmed tile, never `undefined`.
- Charts degrade to "no data" panels on persistence errors.

## Testing / verification

- Vitest for the data layer (SSE reconnect, NULL handling, command posts).
- Playwright smoke at 1340×800, 1920×1080, 390×844 viewports: every tile
  renders, no overflow at reference resolution, controls confirm-hold works.
- Live verification on the actual M9 before each screen is called done.
- Perf budget: initial load < 2 s on the M9, SSE update → paint < 100 ms.

## Rollout

1. Repo + serving skeleton + data layer with SSE (proved via a bare tile).
2. Design tokens + tile primitives (the console look, approved on the M9
   with a static sample screen BEFORE building all screens).
3. Home console.
4. Energy → Weather → Earthship.
5. Controls + `SouthOutlet_ManualRequest` rule change (last — safety review).
6. PWA polish, auto-dim, offline state; retire MainUI links for household
   use (MainUI stays for admin).

## Out of scope (v1)

Phone-optimized layouts beyond reflow, user accounts/multi-profile, remote
(off-LAN) access, historical analytics beyond the shipped charts (Grafana
remains the deep-analytics option later), voice, cameras.
