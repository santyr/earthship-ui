# Earthship Console UI

A custom household dashboard for our off-grid Earthship's openHAB system —
weather, battery/solar, passive-thermal loop, and greywater on one pane of
glass, styled after the Ambient Weather WS-2000 console.

**Primary device:** Lenovo Tab M9 (2023), landscape (1340×800), wall-mounted.
Laptop and phone are secondary. Tablet-first, no-scroll console layout.

**Stack:** Svelte + Vite + Tailwind, ECharts. Talks only to openHAB REST +
SSE on the LAN. PWA-installable.

**Status:** design phase. See `docs/design.md`.

## Config (not committed)

Runtime config lives in `config.json` (openHAB base URL + API token),
served alongside the static bundle. It is gitignored — never commit it.
Copy `config.example.json` and fill in your own values.
