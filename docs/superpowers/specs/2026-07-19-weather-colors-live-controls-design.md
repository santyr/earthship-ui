# Weather Condition Colors + Live Controls Completion — Design

**Date:** 2026-07-19
**Status:** Approved by Sat (conversation, 2026-07-19)

Two workstreams: (A) color every forecast/condition weather icon on the Home
and Weather pages by weather condition; (B) finish the live-control activation
plan so every Controls-page switch is live, with amendments Sat approved.

## A. Condition-colored weather icons

### Single source of truth

`src/lib/ui/wmo.js` — each WMO band gains a `color` field. New exports:

- `wmoColor(code)` — condition color for a WMO weather code; returns `null`
  for unknown/NULL codes (callers fall back to `currentColor`, today's
  rendering).
- `skyIconColor(iconName)` — maps the openHAB-provided current-condition icon
  names (`iconify:mdi:...` or bare `mdi:...`) to the same palette by name
  category: sunny/clear, clear-night/moon, partly, cloudy, fog, rain,
  pouring, snow, lightning. Unrecognized names return `null`.

### Palette (anchored to existing `tokens.js` accents)

| Condition | Color | Rationale |
|---|---|---|
| Sunny / clear day | `#eab308` | existing solar yellow |
| Clear night / moon | `#cbd5e1` | silver |
| Partly cloudy | `#cbd5e1` | bright silver |
| Cloudy | `#94a3b8` | slate |
| Fog | `#8b93a1` | existing label gray |
| Drizzle / rain / showers | `#3b82f6` | existing rain blue |
| Heavy rain / pouring | `#2563eb` | deeper blue |
| Snow / snow showers | `#bfdbfe` | ice blue |
| Thunderstorm | `#8b5cf6` | existing forecast violet |

All colors have ≥3:1 contrast against the tile background `#11151c`.

### Render sites

Colored via the existing `OhIcon color` prop (same pattern as
`pressureStatus.color` / `solarColor`):

1. Home ten-day forecast strip (`DailyForecast.svelte`, variant `home`).
2. Weather current-condition icon (`Weather.svelte`, `SkyConditionIcon`,
   via `skyIconColor`).
3. Weather hourly strip (`HourlyStrip.svelte`).
4. Weather ten-day rows (`DailyForecast.svelte`, variant `weather`).
5. Detail modal day-summary icon and per-hour icons
   (`WeatherDetailModal.svelte`).

**Exclusion (Sat's decision):** the Home outdoor card's condition icon keeps
its temperature-band color and exact sparkline color match
(HOME-SPARK-COLOR audit row). No change there.

### Testing

- Unit tests for `wmoColor` band edges and `skyIconColor` name categories,
  including NULL/unknown → `null`.
- Component tests asserting each render site passes the mapped color to
  `OhIcon` (and that the Home outdoor card does not switch).
- Existing e2e layout specs must keep passing; no geometry changes.

## B. Controls page — all switches live

Execute the remaining Tasks 3–6 of
`docs/superpowers/plans/2026-07-18-live-control-activation.md` (Tasks 1–2 are
complete: tap lights shipped; feeder owner rule + tests landed in d617bcd).
All global constraints of that plan remain in force (no browser token, no
direct actuator commands, 2xx ≠ success, no auto-retry, persisted correlated
request/result pairs, attended deployment, receipt-bound transactions).

### Amendments (Sat, 2026-07-19)

1. **Greywater adopts the audit-plan spec** (Task 15 contract): canonical
   source `openhab/rules/southoutlet-cycle.js` replaces the live
   `hex_southoutlet_cycle` script.
   - 5-minute cycles (change from live 10-minute).
   - 230-minute start-to-start gap retained.
   - Eligibility: `SkyCondition == CLEAR` → SoC ≥90%; any other or
     unavailable value → SoC ≥98%. Curtailment-only logic removed.
   - BMS comms staleness, voltage sanity, and SoC fail-closed chain kept.
   - Aerobic fallback never bypasses the SoC thresholds.
   - Correlated `SouthOutlet_ManualRequest` / `SouthOutlet_ManualResult`
     path evaluated through the same gates; provider item stays
     proxy-denied.
   - **After-dark curfew preserved** (Sat's 2026-07-19 request, explicitly
     re-approved with this spec): cycle starts require astro
     `Sun_Position_Elevation > 0`, a cycle caught running past sunset is
     forced OFF, missing/NULL elevation fails closed. The curfew gates the
     manual-request path too.
2. **Feeder goes live from the UI**: Feed-once submits correlated manual
   requests like any other protected control. **No per-source attribution**:
   the owner rule treats every accepted request identically and never
   branches on the requesting client/source (verified: current rule has no
   such branching; none may be added).
3. **Night-load owner (Task 4)** as planned: one serialized owner for
   Override, Dishwasher, Shureflo, Goat Cam; ON/OFF matrices, persisted
   ledgers, commit-before-command, provider-generation matching,
   restart-uncertain recovery, existing Goat Cam coupling direction.
4. **UI request client (Task 5)** as planned: `src/lib/controls/requestClient.js`
   with unique request IDs, matching-result correlation, distinct
   denied/failed/unknown terminal states, bounded acknowledgement, no
   auto-retry; wired through `controlState.js`, `Toggle.svelte`,
   `Controls.svelte`. Proxy POST allowlist is exactly the four request items
   (`GoatFeeder_ManualRequest`, `SouthOutlet_ManualRequest`,
   `NightLoadDevice_Request`, `NightLoadOverride_Request`) plus the four
   existing direct light/policy items.
5. **Deployment and sign-off (Task 6)**: attended, receipt-bound openHAB
   transactions (snapshot → apply disabled → rehearse rollback → verify →
   enable). Greywater deployment requires an observer able to see the pump.
   Sat operates every control from the live UI; agent observes
   request/result/provider/rule/log evidence and records only observed
   results in `docs/qa/ui-audit-matrix.csv`.

### Error handling

Per the parent plan: transport errors, timeouts, and unknown outcomes render
distinct terminal states and never retry automatically; owned devices disable
during override ON, owner transition, or owner busy; capability gates keep
controls status-only until their owner is verified live.

### Testing

TDD RED→GREEN per task. Exact-source rule simulations for greywater
(including curfew gating of manual requests) and night-load owner; request
client unit tests; proxy allowlist tests; full `npm test`,
`npm run test:e2e -- --workers=1`, and `npm run build` gates before each
commit checkpoint.

## Out of scope

- Any change to the Home outdoor card icon/sparkline temperature convention.
- Per-source feeder attribution or changes to external feeder trigger paths.
- Phone layouts, HTTPS, reverse proxies (unchanged from parent plans).
