# Earthship UI Tablet Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the complete Earthship household console so all five routes are
truthful, safe, readable, and fully contained without scrolling on the measured
Lenovo Tab M9 (2023) landscape browser/PWA viewports and on laptops at
1280×720 or larger.

**Architecture:** Keep Svelte as the presentation layer, but replace implicit
state and one-off chart/control behavior with pure, testable domain modules.
OpenHAB remains the safety and equipment authority; managed objects are changed
only through authenticated REST with exact backups and readback. Release the UI
through immutable compatibility, zero-write maintenance, and full stages so the
old raw-actuator surface is never a rollback target.

**Tech Stack:** Svelte 5, Vite 8, Vitest 4, Testing Library, Playwright,
ECharts 6 modular imports, Web Workers, `vite-plugin-pwa`, verified-live
openHAB 5.2.0 REST (re-check before mutation), and systemd user services for
the local immutable preview.

**Approved design:** `docs/superpowers/specs/2026-07-17-earthship-ui-tablet-audit-design.md`

**Live browser validation URL:** `http://192.168.1.161:5190/`

**Secure installed-PWA URL (established in Task 2):**
`https://192.168.1.161:5192/`

## Global execution constraints

- Work on `build/console-ui`; preserve unrelated user changes and stage only
  files named by the current task.
- Execute every `bash` fence in a fresh shell. Each fence explicitly enables
  `set -euo pipefail`; do not omit or bypass it. Any failed test, clean-tree check,
  snapshot/readback, build, or rollback verification stops that block; run the
  separately documented recovery state machine before any later mutation.
  Expected RED commands are not exceptions: run each through the tested
  `tools/qa/expect-failure.mjs` structured-report wrapper. Each command filters
  to exactly one sentinel test; the wrapper returns success only for one failed
  test whose exact title and error begin with that sentinel, with no load, hook,
  suite, or additional test failure. Never use bare `|| true` or let one
  expected failure skip later RED commands.
- Use test-first RED/GREEN cycles. A test must fail for the expected missing
  behavior before implementation is written.
- Do not change route-grid CSS until both actual M9 landscape geometries are
  recorded in `tests/e2e/device-profiles.json` and
  `docs/qa/ui-audit-matrix.csv`.
- Automated browser tests must intercept `/config.json`, `/rest/items`,
  `/rest/events`, `/rest/persistence/**`, and command requests. They must never
  fall through to the household openHAB instance.
- Read `/etc/openhab/AGENTS.md` before every live-openHAB task. Use managed REST
  APIs only; never edit JSONDB or create `.items`, `.things`, `.rules`, or
  `.persist` files under `/etc/openhab`.
- Load `/home/sat/.config/hex/openhab.env` without printing
  `OPENHAB_TOKEN`. Never commit `public/config.json`, environment files,
  backups, tokens, or live state.
- Live openHAB verification is read-only unless the task explicitly calls for
  a backed-up configuration mutation. Never send `runnow`, item commands, or a
  physical load command from an apply/verify/rollback script.
- Any live feeder, greywater, light, dishwasher, Shureflo, Goat Cam, or override
  command requires new, contemporaneous user approval and an observer at the
  equipment. Mock and pure-rule tests require no such approval.
- Keep the current 10-minute greywater run, 230-minute hydrology gap, 24-hour
  aerobic fallback, BMS/freshness fail-closed gates, and curtailment-only
  interim policy unchanged.
- Keep the existing chart/component visual language. Phone, portrait,
  split-screen, and arbitrary viewport work is out of scope.
- Use only the tested `tools/qa/update-matrix.mjs` transition command to change
  `docs/qa/ui-audit-matrix.csv`; never hand-edit status or evidence cells. Only
  the task mapped to a stable row ID may advance it, and only after the required
  automated, live-receipt, or device-signoff evidence passes.
- After each task run its focused tests and `git diff --check`, then make the
  listed narrow commit.

---

## Task 1: Establish the measured target and deterministic test harness

**Files:**

- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `vite.config.js`
- Modify: `src/App.svelte`
- Create: `src/lib/qa/ViewportProbe.svelte`
- Create: `public/qa/viewport/manifest.webmanifest`
- Create: `public/qa/viewport/sw.js`
- Create: `public/qa/viewport/icon.svg`
- Create: `public/qa/viewport/icon-192.png`
- Create: `public/qa/viewport/icon-512.png`
- Create: `tests/viewport-pwa.test.js`
- Create: `tests/device-profile.test.js`
- Create: `tests/audit-matrix.test.js`
- Create: `tests/audit-matrix-updater.test.js`
- Create: `tests/expect-failure.test.js`
- Create: `tools/qa/expect-failure.mjs`
- Create: `tools/qa/red-playwright-reporter.mjs`
- Create: `tools/qa/red-sentinel-inventory.mjs`
- Create: `tools/qa/matrix-contract.mjs`
- Create: `tools/qa/update-matrix.mjs`
- Create: `tests/component-environment.test.js`
- Create: `tests/setup.js`
- Create: `tests/e2e/device-profiles.json`
- Create: `tests/e2e/fixtures/openhab.js`
- Create: `tests/e2e/fixtures/device.js`
- Create: `tests/e2e/fixtures/requiredContent.js`
- Create: `tests/e2e/server.mjs`
- Create: `tests/e2e/harness.spec.js`
- Create: `tests/e2e-fixture-contract.test.js`
- Create: `tests/e2e/fixtures/states.js`
- Create: `tests/e2e/helpers/geometry.js`
- Create: `playwright.config.js`
- Create: `docs/qa/ui-audit-matrix.csv`

- [ ] **Install the component/PWA test dependencies and add bounded scripts**

Run:

```bash
set -euo pipefail
npm install --save-dev @testing-library/svelte @testing-library/user-event \
  @testing-library/jest-dom jsdom fake-indexeddb vite-plugin-pwa
```

Add scripts:

```json
{
  "test:unit": "vitest run",
  "test:e2e": "playwright test",
  "test:geometry": "playwright test tests/e2e/geometry.spec.js",
  "test": "vitest run"
}
```

- [ ] **Write only the failing measurement-shell tests first**

Before the first app RED, create the test-only
`tools/qa/expect-failure.mjs`, `tools/qa/red-playwright-reporter.mjs`,
`tools/qa/red-sentinel-inventory.mjs`, and `tests/expect-failure.test.js`, then
create only `tests/viewport-pwa.test.js`,
`tests/component-environment.test.js`, and
`tests/setup.js` from the remaining Task 1 file list. The PWA test requires the confined manifest/scope/start URL, exact
192x192/512x512 PNG icons, standalone display, a worker with no cache/fetch
handler, and no app/OpenHAB/command import. The environment test requires Node
as the default Vitest environment, per-file jsdom opt-in, registered
`test.setupFiles`, jest-dom, and deterministic matchMedia/canvas/ResizeObserver
fakes plus `fake-indexeddb/auto` for deterministic Node cache tests. Do not yet
create the measured profile JSON, audit matrix, required
content manifest, Playwright fixtures, or their contract tests.


- [ ] **Bootstrap the checked RED runner**

The Node-built-in-only wrapper accepts
`--runner vitest|playwright --sentinel RED:<stable-id> -- <command...>`. It
requires the command to include the exact anchored `-t` or `--grep` filter,
creates a unique report path, and configures a machine-readable reporter. For
Vitest it appends JSON reporter/output arguments; for Playwright the bundled
`red-playwright-reporter.mjs` writes only to that path. The wrapper trusts
neither stdout nor exit status alone: it requires exit 1, exactly one executed
and failed test, its title and error both beginning `[<sentinel>]`, and zero collection,
import, setup, hook, suite, timeout, crash, signal, or additional test errors.
It prints bounded diagnostics, removes its report/output files in `finally`, and
rejects success, a missing/duplicate/malformed report, a wrong filter, or any
unapproved failure. Unit tests inject every case and exercise both reporters.
Every later RED test group defines exactly one matching sentinel probe that
calls the real contract and throws `Error("[RED:<id>] expected missing
contract")` only for the intended absent behavior; full GREEN runs all tests
without the filter. Each sole producer must collect cleanly against the existing
harness; when the intended contract is a missing module/file/project, load it
inside the test and translate only that exact absence into the sentinel error,
rethrowing every syntax, transitive import, setup, or other error unchanged. The
exact producer inventory is fixed below; no other test title or error may use a
`RED:` prefix:

| Sentinel | Sole producer |
| --- | --- |
| RED:T1A-1 | tests/viewport-pwa.test.js |
| RED:T1B-1 | tests/device-profile.test.js |
| RED:T2A-1 | tests/safe-controls.test.js |
| RED:T3A-1 | tests/item-value.test.js |
| RED:T4A-1 | tests/reconcile.test.js |
| RED:T5A-1 | tests/history-periods.test.js |
| RED:T6A-1 | tests/history-request.test.js |
| RED:T7A-1 | tests/chart-options.test.js |
| RED:T7A-2 | tests/e2e/chart-activation.spec.js |
| RED:T8A-1 | tests/console-alerts.test.js |
| RED:T8A-2 | tests/e2e/header-alerts.spec.js |
| RED:T9A-1 | tests/e2e/home.spec.js |
| RED:T10A-1 | tests/weather-aqi-wiring.test.js |
| RED:T10A-2 | tests/e2e/energy.spec.js |
| RED:T11A-1 | tests/thermal-loop-order.test.js |
| RED:T11A-2 | tests/e2e/earthship.spec.js |
| RED:T12A-1 | tests/control-machine.test.js |
| RED:T12A-2 | tests/e2e/control-states.spec.js |
| RED:T13A-1 | tests/openhab/rest-manifest.test.js |
| RED:T14A-1 | tests/openhab/feeder-rule.test.js |
| RED:T15A-1 | tests/openhab/greywater-rule.test.js |
| RED:T16A-1 | tests/openhab/night-load-override-rule.test.js |
| RED:T17A-1 | tests/pwa-cache-policy.test.js |
| RED:T17A-2 | tests/e2e/offline-pwa.spec.js |
| RED:T17A-3 | tests/e2e-fixture-contract.test.js |
| RED:T17A-4 | tests/e2e/dim-mode.spec.js |
| RED:T18A-1 | tests/tablet-metrics-schema.test.js |
| RED:T18A-2 | tests/e2e/geometry.spec.js |
| RED:T18A-3 | tests/qa-gates.test.js |
| RED:T18A-4 | tests/qa-gates.test.js |

`red-sentinel-inventory.mjs` exports this exact frozen mapping and a
Node-built-in lexical validator. Before spawning, `expect-failure.mjs` requires
the command to name only the mapped producer file, scans all currently existing
test/spec sources, and requires the requested owner to contain exactly one
literal sentinel test-title prefix and one literal sentinel error prefix. It
rejects an unknown ID, a marker in any non-owner, a duplicate title/error, a
second selected file, or any unregistered `RED:` title/error. Missing mapped
future files are allowed only until their own task; the requested producer may
never be missing. `tests/expect-failure.test.js` exercises moved, duplicated,
unknown, missing-owner, extra-file, and comment/string false-positive fixtures
without embedding a literal unowned marker in its own test title/error.
Task 18 final `check-matrix.mjs` calls the same validator in `complete` mode,
which requires all 30 owner files and exact title/error pairs before release.

Run:

```bash
set -euo pipefail
npm test -- tests/expect-failure.test.js
```

- [ ] **Run measurement-shell RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T1A-1' -- \
  npm test -- tests/viewport-pwa.test.js \
    -t '^\[RED:T1A-1\]'
```

Expected: FAIL because the confined manifest, icons, worker, probe route, and
Vitest setup do not exist.

- [ ] **Implement a display-only viewport probe**

Mount the probe only for `?qa=viewport`. It must not call openHAB:

```svelte
<script>
  const standalone = matchMedia('(display-mode: standalone)').matches;
  const payload = {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
    displayMode: standalone ? 'standalone' : 'browser',
    safeArea: {
      top: getComputedStyle(document.documentElement)
        .getPropertyValue('--qa-safe-top').trim() || '0px',
      right: getComputedStyle(document.documentElement)
        .getPropertyValue('--qa-safe-right').trim() || '0px',
      bottom: getComputedStyle(document.documentElement)
        .getPropertyValue('--qa-safe-bottom').trim() || '0px',
      left: getComputedStyle(document.documentElement)
        .getPropertyValue('--qa-safe-left').trim() || '0px',
    },
  };
</script>

<main aria-label="Viewport measurement">
  <pre>{JSON.stringify(payload, null, 2)}</pre>
  <button on:click={() => navigator.clipboard.writeText(JSON.stringify(payload))}>
    Copy measurement
  </button>
</main>
```

Use `env(safe-area-inset-*)` to populate the four probe custom properties.
Configure Vitest's default environment as Node with
`test.setupFiles: ['./tests/setup.js']`; per-file jsdom directives switch only
component tests. The rendered root carries `data-qa-probe="viewport-v1"` and
`data-build-sha={__BUILD_SHA__}`. The payload includes `probeSchema: 1` and
`buildSha: __BUILD_SHA__`; Vite defines `__BUILD_SHA__` from committed HEAD at
server startup.

- [ ] **Commit the measurement shell before recording its SHA**

~~~bash
set -euo pipefail
npm test -- tests/viewport-pwa.test.js tests/component-environment.test.js
git diff --check
git add package.json package-lock.json vite.config.js src/App.svelte \
  src/lib/qa/ViewportProbe.svelte public/qa/viewport/manifest.webmanifest \
  public/qa/viewport/sw.js public/qa/viewport/icon.svg \
  public/qa/viewport/icon-192.png public/qa/viewport/icon-512.png \
  tests/viewport-pwa.test.js tests/setup.js tests/component-environment.test.js \
  tests/expect-failure.test.js tools/qa/expect-failure.mjs \
  tools/qa/red-playwright-reporter.mjs \
  tools/qa/red-sentinel-inventory.mjs
git commit -m "test: add isolated tablet viewport probe"
test -z "$(git status --short)"
~~~

Restart the measurement server only from this clean committed HEAD. The
`__BUILD_SHA__` shown by the probe must now identify the commit that actually
contains the probe.

- [ ] **Record both real M9 modes without installing the unsafe app**

After adding the probe, identify the process on 5190 and prove it is this
repository's Vite command at the expected committed HEAD. Restart that exact
development process if necessary, then verify the served DOM contains
`data-qa-probe="viewport-v1"` and its `data-build-sha` equals
`git rev-parse HEAD`. Do not accept measurements from a stale page.

Record browser landscape at:

```text
http://192.168.1.161:5190/?qa=viewport
```

The repository currently has no installable PWA and LAN HTTP is not a secure
service-worker context. Do not install/cache the pre-audit household app.
Instead, `App.svelte` exposes a measurement-only route at
`/qa/viewport/?qa=viewport`. It injects
`public/qa/viewport/manifest.webmanifest` with scope/start URL confined to
`/qa/viewport/` and registers `public/qa/viewport/sw.js` only when
`install=1`. That worker has no cache and no fetch interception; the route
never initializes OpenHAB. `tests/viewport-pwa.test.js` enforces the scope,
standalone display, zero cache APIs, no app import, no command/network surface,
and exact 192x192/512x512 PNG manifest icons by validating their PNG headers.
Before recording standalone geometry, Chrome must show the measurement shell as
installable with no manifest warnings and launch it in actual standalone mode;
otherwise stop rather than substituting a browser tab.

Use Android Debug Bridge to give this isolated measurement route a localhost
secure context. In terminal A start the server and leave it running:

```bash
set -euo pipefail
npm run dev -- --host 0.0.0.0 --port 5191 --strictPort
```

In terminal B install the reverse before opening the tablet URL:

```bash
set -euo pipefail
adb reverse tcp:5191 tcp:5191
```

After capture, remove the reverse and stop terminal A before the Playwright
harness claims port 5191.

On the M9 open and install:

```text
http://localhost:5191/qa/viewport/?qa=viewport&install=1
```

Open that isolated installed PWA in landscape and record its standalone
viewport/DPR/safe areas. Uninstall it and remove the ADB reverse after capture.
Task 2 establishes the separately trusted production PWA origin, and Task 18
must remeasure the real full PWA; any geometry delta invalidates affected
automated evidence until the tested profile-refresh gate passes.

Capture the exact CSS viewport, DPR, display mode, safe areas, measurement
origin, and probe build SHA in `/tmp/earthship-ui-m9-measurement.json`; do not
create the repository profile file before its RED test. Stop here if either M9
mode is still unmeasured. Do not guess from the nominal 1340×800 panel
resolution.

- [ ] **Write failing measured-profile, matrix, and fixture-contract tests**

`tests/device-profile.test.js`:

```js
import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('canonical device profiles', () => {
  it('contains measured browser, PWA, and laptop targets', async () => {
    const profiles = JSON.parse(await readFile(
      new URL('./e2e/device-profiles.json', import.meta.url)
    ));
    expect(profiles.map((profile) => profile.id)).toEqual([
      'm9-browser',
      'm9-pwa',
      'laptop-1280x720',
    ]);
    for (const profile of profiles) {
      expect(profile.measured).toBe(true);
      expect(profile.viewport.width).toBeGreaterThan(0);
      expect(profile.viewport.height).toBeGreaterThan(0);
      expect(profile.deviceScaleFactor).toBeGreaterThan(0);
      expect(['browser', 'standalone']).toContain(profile.displayMode);
      expect(Object.keys(profile.safeArea)).toEqual([
        'top', 'right', 'bottom', 'left',
      ]);
    }
    expect(profiles[0].displayMode).toBe('browser');
    expect(profiles[1].displayMode).toBe('standalone');
    expect(profiles[2]).toMatchObject({
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 1,
      displayMode: 'browser',
    });
  });
});
```

`tests/component-environment.test.js` statically requires every
`tests/ui/*.test.js` to begin with `// @vitest-environment jsdom` and asserts
`vite.config.js` sets `test.setupFiles: ['./tests/setup.js']`.
`tests/setup.js` imports `@testing-library/jest-dom/vitest` and installs
deterministic `matchMedia`, canvas, and `ResizeObserver` fakes. Chart component
tests inject/mock the modular ECharts adapter; they never depend on a real
canvas implementation.

Create one machine-readable selector inventory in
`tests/e2e/fixtures/requiredContent.js`. Its exact `data-required` IDs are:

```js
const fields = (root, names) => names.map((name) => `${root}.${name}`);
const rows = (root, count, names) => Array.from(
  { length: count },
  (_, index) => fields(`${root}.${index + 1}`, names)
).flat();

export const REQUIRED_CONTENT = {
  home: [
    'home.status-or-power-flow', 'home.greywater',
    ...fields('home.outdoor', [
      'temperature', 'condition', 'feels-like', 'humidity', 'high', 'low',
      'aqi', 'trend',
    ]),
    ...fields('home.indoor', ['temperature', 'humidity', 'high', 'low']),
    ...fields('home.battery', [
      'soc', 'current', 'direction', 'runtime', 'basis', 'trend',
    ]),
    ...fields('home.bitcoin', ['price', 'change-24h']),
    ...fields('home.wind', ['compass', 'speed', 'gust', 'daily-max']),
    ...fields('home.baro', ['pressure', 'trend']),
    ...fields('home.rain', ['day-total', 'footer']),
    ...fields('home.sun-moon', ['sun', 'moon']),
    ...fields('home.solar', [
      'actual', 'predicted', 'current', 'curtailment',
    ]),
    ...rows('home.zone', 3, ['label', 'temperature', 'delta']),
    ...rows('home.forecast.day', 7, [
      'label', 'condition', 'high', 'low', 'pv',
    ]),
  ],
  energy: [
    ...fields('energy.battery', ['history', 'predicted-trough', 'current-soc']),
    ...fields('energy.solar', ['actual', 'predicted', 'accuracy', 'history']),
    ...fields('energy.runtime', ['value', 'basis']),
    ...fields('energy.curtailment', ['value', 'bar']),
    ...rows('energy.pv-outlook.day', 7, ['label', 'pv']),
    ...fields('energy.vital', [
      'temperature', 'cycles', 'capacity', 'communications',
      'device-presence',
    ]),
  ],
  weather: [
    'weather.current-conditions', 'weather.current-aqi',
    ...rows('weather.hour', 14, ['label', 'condition', 'temperature']),
    ...rows('weather.forecast.day', 7, [
      'label', 'condition', 'high', 'low', 'precipitation', 'pv',
    ]),
    'weather.measured-wind', 'weather.measured-rain',
    'weather.measured-pressure',
  ],
  earthship: [
    'earthship.thermal-advisory',
    ...fields('earthship.tomorrow', ['high', 'low']),
    ...fields('earthship.thermal-loop', [
      'north-mass', 'room-air', 'south-glazing', 'left-flow', 'right-flow',
    ]),
    'earthship.thermal-mass', 'earthship.thermal-buffering',
    ...fields('earthship.greywater', ['status', 'last-cycle']),
    ...fields('earthship.humidity', ['north', 'room', 'south']),
  ],
  controls: [
    ...fields('controls.lights', [
      'living-room-1', 'living-room-2', 'living-room-3', 'circadian-policy',
    ]),
    ...fields('controls.appliances', [
      'dishwasher', 'shureflo', 'goat-cam', 'feed-once',
    ]),
    ...fields('controls.water-policy', ['circulation', 'override']),
    ...fields('controls.result', ['feeder', 'circulation', 'override']),
    'controls.circadian-health', 'controls.feeder-actuator-status',
    'controls.greywater-actuator-status',
  ],
};
```

Every route task adds these stable attributes; aggregate geometry imports this
manifest and fails if a selector is absent. No test may maintain a second
hand-written route-content list.

`tests/audit-matrix.test.js` must assert this exact header and unique,
non-empty IDs:

```js
const HEADER =
  'id,route,component,integration,target,state_fixture,expected,test_or_evidence,status';
```

Seed the CSV with every approved finding, using stable families
`LAY-*`, `CHART-*`, `STATE-*`, `AQI-*`, `EARTH-*`, `BTC-*`, `ALERT-*`,
`CTRL-*`, `OH-*`, `A11Y-*`, `PERF-*`, and `ROLL-*`. Initial status is
`open`; unmeasured target rows use `blocked-measurement`.

`tools/qa/matrix-contract.mjs` maps every exact stable row ID to one owner task,
required automated artifact paths, and optional live/device terminal phases.
There is no prefix fallback. Task 1 alone may use `--phase measurement`
with the measured profile to advance `blocked-measurement` rows to `open`.
`update-matrix.mjs --task N --phase automated` verifies the mapped artifacts exist and atomically writes canonical sorted
evidence only because the enclosing fail-fast block already passed them. It
moves software-only rows to `closed`, live rows to `blocked-live`, and device
rows to `blocked-device`. A live phase requires the exact mapped set of
checksum-valid non-secret receipt summaries with terminal `desired` or a proven
no-op `unmutated`; Task 14 additionally requires its restored ingress receipt,
and Task 16 requires its post-graph release evidence. Missing, extra, duplicate,
or `rolled-back` evidence cannot close a row. A device phase requires matching
passed sign-off, performance, rollback-rehearsal, and release IDs. The only allowed
lifecycle is `blocked-measurement -> open`, `open -> closed|blocked-live|
blocked-device`, `blocked-live -> closed|blocked-device`, and
`blocked-device -> closed`. While a row remains `blocked-device`, Task 18 alone
may run `--task 18 --phase profile-refresh` after the complete automated suite.
It requires the canonical profile plus both raw M9 CDP profile outputs, both
same-target proof files, and the expected active full release ID; it validates
origin, mode, target ID, viewport, DPR, safe areas, and release binding before
replacing canonical profile-hash evidence without changing status. It rejects
an unchanged, synthetic, substituted, or stale profile. Tests reject skipped
phases, foreign task IDs, unmapped or duplicate rows, arbitrary evidence,
reopening, and hand-edited status/evidence. Task 18 final checking imports this
same contract.

- [ ] **Run measured-profile and harness RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T1B-1' -- \
  npm test -- tests/device-profile.test.js \
    -t '^\[RED:T1B-1\]'
```

Expected: FAIL because the canonical profile/matrix, extended device fixture,
and isolated Playwright harness are not implemented yet.

- [ ] **Implement the isolated Playwright fixture**

Copy the two M9 measurements from the captured `/tmp` evidence into
`tests/e2e/device-profiles.json`; set the laptop profile to exactly 1280×720
and DPR 1. If the M9 measurements are identical, retain both profile IDs but
allow Playwright to reuse geometry. Never synthesize a profile that was not
captured from the committed probe.


`playwright.config.js` reads the measured JSON and uses a production
build/preview server on port 5191. In this task, `tests/e2e/server.mjs` starts a
local fixture/reject server on 5199, exports
`OPENHAB_PROXY_TARGET=http://127.0.0.1:5199` and
`EARTHSHIP_UI_ALLOWED_ORIGINS=http://127.0.0.1:5191`, builds `dist` with explicit
`RELEASE_ID=e2e` and `RELEASE_MODE=full` environment inputs, and previews that
directory. Task 2 upgrades this server to the real immutable release
builder/activator after those tools exist. This is required so the `m9-pwa`
project can later exercise the built service worker without any path to
household OpenHAB:

```js
import { defineConfig } from '@playwright/test';
import profiles from './tests/e2e/device-profiles.json' with { type: 'json' };

export default defineConfig({
  testDir: './tests/e2e',
  webServer: {
    command: 'node tests/e2e/server.mjs',
    url: 'http://127.0.0.1:5191/',
    reuseExistingServer: false,
  },
  use: { baseURL: 'http://127.0.0.1:5191/' },
  projects: profiles.map((profile) => ({
    name: profile.id,
    use: {
      viewport: profile.viewport,
      deviceScaleFactor: profile.deviceScaleFactor,
      earthshipDeviceProfile: profile,
    },
  })),
});
```

The fixture returns synthetic config/items/history and installs a fake
`EventSource` before app code runs. The local upstream records all requests and
returns a failing status for anything outside the fixture contract; every test
asserts its unexpected-request log is empty. This catches service-worker
NetworkOnly requests that `page.route` cannot reliably intercept. Page routing
is a second guard, and every unhandled `/rest/**` request throws:

```js
await page.route('**/rest/**', (route) => {
  throw new Error(`Unmocked openHAB request: ${route.request().url()}`);
});
```

Because Playwright cannot reproduce Android browser chrome, cutouts, or an
installed WebAPK exactly, `tests/e2e/fixtures/device.js` extends Playwright's
base `test` and registers `earthshipDeviceProfile` as an option. Before page
creation it installs a frozen `window.__EARTHSHIP_QA_DEVICE__` containing the
project ID, standalone matchMedia result, and recorded safe areas. The app
honors only that injected global and exposes the applied ID as
`data-device-profile`; fixture setup asserts it equals `testInfo.project.name`.
Every E2E spec imports `test/expect` from this extended fixture.
`tests/e2e-fixture-contract.test.js` rejects direct `@playwright/test` imports
from specs and asserts all three profiles apply their own ID. This makes
automated standalone layout deterministic without relying on an omitted query
parameter; the actual installed M9 PWA remains the release authority.
`tests/e2e/harness.spec.js` is the first consumer: it loads the shell, asserts
the applied profile ID and deterministic build inputs, and asks the local
fixture server to prove its unexpected-request log is empty.

- [ ] **Run GREEN and commit**

```bash
set -euo pipefail
npm test -- tests/device-profile.test.js tests/audit-matrix.test.js \
  tests/audit-matrix-updater.test.js tests/expect-failure.test.js \
  tests/component-environment.test.js \
  tests/viewport-pwa.test.js tests/e2e-fixture-contract.test.js
npx playwright test tests/e2e/harness.spec.js
node tools/qa/update-matrix.mjs --task 1 --phase measurement \
  --profile tests/e2e/device-profiles.json docs/qa/ui-audit-matrix.csv
node tools/qa/update-matrix.mjs --task 1 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add tests/device-profile.test.js tests/audit-matrix.test.js \
  tests/audit-matrix-updater.test.js \
  tools/qa/matrix-contract.mjs tools/qa/update-matrix.mjs \
  tests/e2e-fixture-contract.test.js \
  tests/e2e/device-profiles.json \
  tests/e2e/fixtures/openhab.js tests/e2e/fixtures/device.js \
  tests/e2e/fixtures/requiredContent.js tests/e2e/fixtures/states.js \
  tests/e2e/helpers/geometry.js tests/e2e/server.mjs tests/e2e/harness.spec.js \
  playwright.config.js docs/qa/ui-audit-matrix.csv
git commit -m "test: establish canonical tablet UI targets"
```

Expected: the focused tests pass, exactly one harness test passes in each of
`m9-browser`, `m9-pwa`, and `laptop-1280x720`, and the local upstream
unexpected-request log is empty. Immutable release-manifest assertions begin
in Task 2, after the builder exists.

---

## Task 2: Ship the immutable safe-compatibility surface first

**Files:**

- Modify: `.gitignore`
- Modify: `config.example.json`
- Modify: `src/lib/config.js`
- Modify: `src/lib/openhab/client.js`
- Modify: `src/lib/openhab/sse.js`
- Create: `src/lib/openhab/readCatalog.js`
- Create: `src/lib/ui/StatusControl.svelte`
- Modify: `src/screens/Controls.svelte`
- Modify: `src/screens/Earthship.svelte`
- Modify: `tests/config.test.js`
- Modify: `tests/client.test.js`
- Modify: `tests/sse.test.js`
- Create: `tests/proxy-auth.test.js`
- Create: `tests/release.test.js`
- Modify: `tests/e2e/server.mjs`
- Modify: `tests/e2e/harness.spec.js`
- Create: `tests/safe-controls.test.js`
- Modify: `vite.config.js`
- Create: `tools/release/build.mjs`
- Create: `tools/release/activate.mjs`
- Create: `tools/release/serve.mjs`
- Create: `tools/release/verify-policy.mjs`
- Create: `tests/release-server.test.js`
- Create: `tests/release-policy-verifier.test.js`
- Create: `deploy/earthship-ui-preview.service`
- Create: `deploy/earthship-ui-pwa.service`
- Create: `tools/tls/create-local-cert.sh`
- Create: `tests/tls-config.test.js`
- Create: `tools/openhab/auth.mjs`
- Create: `tools/openhab/mainui-safety.mjs`
- Create: `tests/openhab-auth.test.js`
- Create: `openhab/mainui/overview-safety-patch.json`
- Create: `openhab/mainui/earthship-safety-patch.json`
- Create: `openhab/mainui/page-fc7fed510c-safety-patch.json`
- Create: `openhab/mainui/page-69e95753c4-safety-patch.json`
- Create: `tests/mainui-safety.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing static safety tests**

```js
it.each([
  "src/screens/Controls.svelte",
  "src/screens/Earthship.svelte",
])("%s exposes raw items only through StatusControl", async (path) => {
  const source = await readFile(path, "utf8");
  const interactiveTags = [
    ...source.matchAll(
      /<(?:Toggle|BinaryControl|ActionControl|SafetyRequest)\b[^>]*>/gs
    ),
  ].map((match) => match[0]);
  for (const item of [
    "Goat_Plugs_Outlet2_Switch",
    "SouthOutlet_Outlet2_Switch",
    "OverrideSwitch",
    "Dish_Washer_Power",
    "ShurefloPump_Power",
    "Goat_Plugs_Outlet1_Switch",
  ]) {
    expect(interactiveTags.filter((tag) => tag.includes(item))).toEqual([]);
    expect(source).not.toMatch(new RegExp(
      `sendCommand\\s*\\(\\s*[\\x22\\x27]${item}[\\x22\\x27]`
    ));
  }
});

it.each([
  'overview-safety-patch.json',
  'earthship-safety-patch.json',
  'page-fc7fed510c-safety-patch.json',
  'page-69e95753c4-safety-patch.json',
])('%s has no owner-only action', async (name) => {
  const patch = JSON.parse(await readFile(`openhab/mainui/${name}`, 'utf8'));
  const unsafe = [];
  walk(patch, (node) => {
    const item = node.config?.item ?? node.config?.actionItem;
    if (
      [
        'Goat_Plugs_Outlet2_Switch', 'SouthOutlet_Outlet2_Switch',
        'OverrideSwitch', 'Dish_Washer_Power',
        'ShurefloPump_Power', 'Goat_Plugs_Outlet1_Switch',
      ].includes(item) &&
      (node.component === 'oh-toggle-card' || node.config?.actionItem)
    ) unsafe.push(item);
  });
  expect(unsafe).toEqual([]);
});
```

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T2A-1' -- \
  npm test -- tests/safe-controls.test.js \
    -t '^\[RED:T2A-1\]'
```

Expected: FAIL because the screens bind feeder, greywater, override, and owned
load items to interactive `Toggle` components, the safe MainUI patch does not
exist, and the browser/runtime build
still exposes the API token through `public/config.json` and the SSE query.

- [ ] **Replace raw controls with status-only compatibility cards**

Keep old-schema state readable, but do not expose the new request actions yet:

```svelte
<StatusControl
  label="Feeder actuator"
  item="Goat_Plugs_Outlet2_Switch"
  detail="Read-only · manual action unavailable during upgrade"
/>
<StatusControl
  label="Greywater actuator"
  item="SouthOutlet_Outlet2_Switch"
  detail="Read-only · circulation request unavailable during upgrade"
/>
<StatusControl
  label="Night Load Override"
  item="OverrideSwitch"
  detail="Read-only · correlated override unavailable during upgrade"
/>
```

Also replace dishwasher, Shureflo, and Goat Cam with `StatusControl` cards whose
detail says the shared owner is unavailable during upgrade. No compatibility
component may post to feeder, greywater, `OverrideSwitch`, or any of the three
owned-load provider Items. The new action controls stay absent/disabled until
Tasks 14–16 verify their request/result items.

- [ ] **Export, scan, and patch all four household MainUI pages**

`tools/openhab/mainui-safety.mjs` must manage the exact page UIDs `overview`,
`earthship`, `page_fc7fed510c`, and `page_69e95753c4`:

1. GET all four pages and record existence plus canonical sanitized hashes;
2. capture a log cursor and all six status/owner-only Item/provider states;
3. save every exact original and desired PUT DTO plus SHA-256 under one
   `/tmp/earthship-ui-openhab-<UTC>/mainui/` backup;
4. recursively replace any `oh-toggle-card`, `actionItem`, action variable, or
   other interactive binding for feeder, greywater, `OverrideSwitch`,
   dishwasher, Shureflo, or Goat Cam with an `oh-label-card` read-only status;
5. PUT only pages whose canonical desired DTO differs;
6. GET all four again and recursively assert no forbidden interaction remains;
7. prove all six Item/provider states are unchanged; and
8. scan only post-cursor logs and fail on a new ERROR/Exception.

It must reject every Item POST, `/runnow`, rule enable, page creation for an
originally absent UID, and mutation outside the four exact page UIDs. The
`earthship` page is expected to be a verified no-op; expectations for the other
pages come from their captured fixtures, not assumptions.
`tests/mainui-safety.test.js` walks every component/config/slot tree and fails
when a node has `component === "oh-toggle-card"` or an interactive `actionItem`
(or equivalent action binding) targeting any of the six exact status/owner-only
Items. Serialized adjacent-key substring matching is not sufficient. Tests
cover changed, already-safe, and absent-page fixtures plus exact rollback.

Expose one receipt-bound `transact` state machine rather than independent
snapshot/apply processes. It writes one explicit receipt directory supplied by
`--receipt`, fsyncs original/desired DTOs and hashes before the first PUT,
applies only from that receipt, verifies all four pages/states/logs, and writes
a non-secret terminal evidence summary. A no-op closes `unmutated`; a successful
change closes `desired`. Any failure after a PUT automatically restores every
changed original DTO in reverse order, verifies all four pages and unchanged
Items, and closes `rolled-back`. An interrupted/open receipt is recoverable only
with `recover --receipt <exact-path>`; rollback failure leaves it open with
`operatorActionRequired`. Tests inject interruption/failure before and after
every page PUT, readback, log scan, rollback, and terminal write.

- [ ] **Move OpenHAB authentication behind the same-origin proxy**

Make the committed/example and live browser config token-free:

```json
{
  "openhabUrl": "",
  "apiToken": "",
  "staleBannerSeconds": 90
}
```

`parseConfig()` accepts an empty token only with same-origin `openhabUrl`.
`client.js` omits Authorization when the token is empty; `sse.js` omits the
`accessToken` query entirely. Every write helper adds
`X-Earthship-Release-ID: __RELEASE_ID__`; it has no caller override. The build
injects that ID from the same value written to the manifest. Both Vite dev and
immutable release proxies read
`OPENHAB_TOKEN` server-side and set Basic auth for the upstream request without
logging it:

```js
const proxyAuth = process.env.OPENHAB_TOKEN
  ? `Basic ${Buffer.from(`${process.env.OPENHAB_TOKEN}:`).toString('base64')}`
  : undefined;
```

The proxy is an authorization boundary, not a transparent tunnel. Every write
requires a configured same-origin allowlist, a matching `Origin`, a
same-origin `Sec-Fetch-Site`, `X-Earthship-UI: 1`, and a compiled
`X-Earthship-Release-ID` exactly matching the active checksummed manifest;
failed/missing origin/header checks return 403 and a stale/mismatched release
returns 409 without forwarding. No CORS permission is emitted. This fences a
still-open old tablet tab after activation or rollback. `maintenance` permits no writes
at all. `safe-compat` permits POST only to this reviewed legacy catalog:

```js
[
  'living_room_1_Switch', 'living_room_2_Switch',
  'LED_living_room_1_Switch', 'LivingRoomCircadian_Enable',
]
```

`full` retains those same four non-owned controls and adds only
`GoatFeeder_ManualRequest`, `SouthOutlet_ManualRequest`,
`NightLoadOverride_Request`, and `NightLoadDevice_Request`. Every mode denies
direct writes to `OverrideSwitch`, `Dish_Washer_Power`, `ShurefloPump_Power`, and
`Goat_Plugs_Outlet1_Switch`; those three loads enter through the shared owner in
Task 16. All three modes allow GET/HEAD only for the UI
snapshot/item paths under `/rest/items`, Thing health under `/rest/things`,
`/rest/events` SSE, and `/rest/persistence/items/{item}` where `item` is in the
exact frozen `PERSISTENCE_READ_ITEMS` exported by
`src/lib/openhab/readCatalog.js`.

The Task 2 registry contains only these audited chart sources:

```js
export const PERSISTENCE_READ_ITEMS = Object.freeze([
  "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature",
  "Forecast_Temp",
  "AmbientWeatherWS2902A_IndoorSensor_Temperature",
  "BMS_SOC",
  "Predicted_SoC_Trough_Tomorrow",
  "AmbientWeatherWS2902A_WindSpeed",
  "AmbientWeatherWS2902A_WindGust",
  "AmbientWeatherWS2902A_RainFallDay",
  "MPPT60_PV_Power",
  "AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative",
  "BTC_USD_Price",
  "Shelly_HT1_Indoor_Temperature",
  "AmbientWeatherWS2902A_WH31E_193_Temperature",
]);
```

Task 5 makes each series policy reference this registry and tests that no
persistence call can name an unregistered item. They deny reads of rules, MainUI pages, services,
system/config administration, and unregistered persistence items. They always
return 403 for arbitrary item writes, feeder/greywater actuators,
`OverrideSwitch`, all three owned-load provider Items, `/state`, `/runnow`,
rules/config endpoints, and every browser PUT/DELETE. Tests prove those denials
are not forwarded upstream in maintenance, safe-compat, or full and cover
cross-origin, missing-header, every denied method/path, the exact persistence
registry, and all three mode-specific allowlists. Svelte source scans remain defense-in-depth, not the safety
boundary.

`tools/openhab/auth.mjs` securely loads and validates the exact protected
`/home/sat/.config/hex/openhab.env` itself for every production invocation of
both `mainui-safety.mjs` and, from Task 13 onward, `openhab-config.mjs`. It never
prints the token and rejects a conflicting ambient token. Tests alone may inject
an absolute temporary `--env-file`; production refuses any override. No task
relies on a prior shell retaining authentication.

Before serving a release, verify `/home/sat/.config/hex/openhab.env` contains a
non-empty token without printing it, replace the ignored `public/config.json`
with the token-free shape, and make `build.mjs` overwrite release
`config.json` with that safe shape before hashing. Tests scan `dist`, release
assets, manifests, and URLs for the former token and `accessToken=`. Add
`.releases/` to `.gitignore`.

- [ ] **Add versioned release tooling and preview proxy**

Use one immutable directory per release ID, with production IDs derived from
release mode plus exact git SHA so maintenance and full can coexist:

```js
const sha = execFileSync(
  'git', ['rev-parse', '--short=12', 'HEAD'], { encoding: 'utf8' }
).trim();
const mode = process.env.RELEASE_MODE;
const releaseId = process.env.RELEASE_ID || `${mode}-${sha}`;
const releaseDir = resolve('.releases', releaseId);
```

The manifest binds release ID, mode, and SHA; reuse or activation rejects a
name whose bound fields differ. Isolated E2E roots may use deterministic IDs
such as `e2e` because they cannot collide with production.

`build.mjs` runs `vite build`, replaces `config.json` with the token-free
same-origin configuration, scans the complete output for secrets, and writes
assets plus the standalone Node-built-in `serve.mjs` and generated frozen read
catalog to a unique sibling `.building-<release-id>-<pid>` directory.
`release.json` checksums every browser and server/runtime file and contains `releaseId`, `releaseMode`, build SHA, asset
hashes, and service-worker cache key. The release server reads the manifest in
its own resolved directory, serves immutable assets/navigation fallback,
streams SSE and proxied reads, and applies that versioned proxy policy; it never
imports working-tree `vite.config.js` or source after build. Only after all
scans/checksums pass does the builder make the temp tree read-only, fsync its
manifest, and atomically rename it to the final release ID. Any failure removes
the temp tree and never leaves a partial final ID. It refuses overwrite.
`--reuse-verified` builds normally when the ID is absent and is the sole rerun
path when it exists: reuse succeeds only when ID, mode, exact clean build SHA,
cache key, server/runtime hashes, and asset checksums all match; any mismatch
fails without changing it. Tests inject failure at every build/publish phase,
prove no poisoned final ID remains, and cover interrupted deterministic reruns.
`activate.mjs <release-id>` rejects missing/unknown IDs, verifies every
checksum, atomically changes `.releases/current`, and proves the current
manifest resolves to that requested ID. An optional `RELEASE_ROOT` exists only
for isolated tests; production defaults to `.releases`.

Task 1's `tests/e2e/server.mjs` is upgraded here to use a unique temporary
`RELEASE_ROOT`, deterministic `RELEASE_ID=e2e` and `RELEASE_MODE=full`,
`EARTHSHIP_UI_ALLOWED_ORIGINS=http://127.0.0.1:5191` and a synthetic
`OPENHAB_TOKEN=e2e-fixture-token`, the real builder/activator and release-owned
`serve.mjs`, plus the local port-5199 fixture/reject upstream. The synthetic
token exists only in the child-process environment; port 5199 asserts the
expected Basic header and tests prove it never appears in assets, manifests, or
logs. No E2E process loads the household token. It
cleans its temp root on exit. Later PWA tests therefore exercise the exact
release manifest/proxy/service-worker mode contract without touching production
releases or household OpenHAB.

`tools/release/verify-policy.mjs --release <id> --expect-mode <mode>` verifies
checksums, launches that immutable release server on an ephemeral loopback port
with a synthetic token and forwarding-counter upstream, sends valid-header reads
and writes, and asserts the exact mode allowlist plus forward count. It refuses
a non-loopback upstream, production token environment, fixed production port,
or unknown release. Maintenance verification requires every write return 403
and counter zero. Tests inject a broken allowlist and prove the verifier detects
the forward without contacting household OpenHAB.

Vite `server.proxy` is development-only and imports the same pure policy for
parity. Production never uses `vite preview`: each checksummed release carries
its own `serve.mjs`, proxy/read catalog, and manifest. On each write that server verifies its own release ID/mode, the client release
header, and the globally active `.releases/current/release.json` ID. A symlink
activation therefore fences old processes immediately, before either service
restart; any mismatch fails without forwarding. Only content-hashed assets get
long immutable cache headers. `index.html`, navigation fallback, `release.json`,
webmanifest, and the service-worker entry script are `no-cache, no-store` so
full-to-maintenance rollback cannot reuse an old bootstrap. Activation plus
service restart rolls browser assets, TLS/static behavior, and proxy
authorization together. Tests launch safe-compat, maintenance, and full servers
from temporary immutable releases; inject the activation-to-restart gap; and
assert served asset ID, manifest, service-worker key, cache headers, proxy mode,
read catalog, both allowed origins, stale-client denial, and old-process denial
always agree. The Task 2 two-release browser test proves no-cache bootstrap and
asset change on activation/rollback; it explicitly has no production service
worker. Task 17 adds the real worker takeover test after registration exists.

The unit must serve the immutable active directory at the existing URL:

```ini
[Unit]
Description=Earthship UI immutable preview
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/sat/earthship-ui
Environment=PATH=/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/home/sat/.config/hex/openhab.env
Environment=OPENHAB_PROXY_TARGET=http://127.0.0.1:8080
Environment=EARTHSHIP_UI_ALLOWED_ORIGINS=http://192.168.1.161:5190,https://192.168.1.161:5192
ExecStart=/usr/bin/node /home/sat/earthship-ui/.releases/current/serve.mjs --host 0.0.0.0 --port 5190
Restart=on-failure

[Install]
WantedBy=default.target
```

Create a second user unit, `earthship-ui-pwa.service`, with the same
working directory, token environment, active release, and guarded proxy, but:

~~~ini
Environment=OPENHAB_PROXY_TARGET=http://127.0.0.1:8080
Environment=EARTHSHIP_UI_ALLOWED_ORIGINS=http://192.168.1.161:5190,https://192.168.1.161:5192
Environment=EARTHSHIP_TLS_CERT=/home/sat/.config/earthship-ui/tls/server.crt
Environment=EARTHSHIP_TLS_KEY=/home/sat/.config/earthship-ui/tls/server.key
ExecStart=/usr/bin/node /home/sat/earthship-ui/.releases/current/serve.mjs --host 0.0.0.0 --port 5192 --https
~~~

The immutable server enables HTTPS only with `--https` and both TLS paths;
the 5190 unit remains HTTP for the existing browser URL. The 5192 origin is the
only installed production PWA/service-worker origin. Missing certificate,
manifest, checksum, token, mode, or a valid explicit HTTP(S) upstream prevents
the relevant server from starting. Tests launch both unit environments against
a loopback fixture and reject an absent, non-HTTP, or credential-bearing target.

`tools/tls/create-local-cert.sh` uses OpenSSL to create, under
`/home/sat/.config/earthship-ui/tls` with umask 077, a private local CA and an
825-day server certificate whose SANs include IP `192.168.1.161` and DNS
`earthship-ui.home.arpa`. It refuses to overwrite or rotate any existing key.
Tests inspect SANs, permissions, conditional Vite TLS, and absence of key/cert
material from git/build output.

After explicit operator approval, generate the certificate and install only
`root-ca.crt` (never its key) as a trusted user CA on the M9 and target laptops.
Verify Chrome reports a secure context at `https://192.168.1.161:5192/` without
a warning/bypass before any production PWA install. If trust is not established,
PWA/offline acceptance remains blocked; do not weaken browser security flags.

During implementation, use port 5191 for Vite development; reserve 5190 and
5192 for the safe/full immutable releases.

- [ ] **Run GREEN, commit, build, and activate the compatibility release**

```bash
set -euo pipefail
npm test -- tests/safe-controls.test.js tests/mainui-safety.test.js \
  tests/openhab-auth.test.js tests/config.test.js tests/client.test.js tests/sse.test.js \
  tests/proxy-auth.test.js tests/release.test.js tests/release-server.test.js \
  tests/release-policy-verifier.test.js tests/tls-config.test.js
npm test
npx playwright test tests/e2e/harness.spec.js
npm run build
node tools/qa/update-matrix.mjs --task 2 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add .gitignore config.example.json src/lib/config.js \
  src/lib/openhab/client.js src/lib/openhab/sse.js \
  src/lib/openhab/readCatalog.js src/lib/ui/StatusControl.svelte \
  src/screens/Controls.svelte src/screens/Earthship.svelte \
  tests/config.test.js tests/client.test.js tests/sse.test.js \
  tests/proxy-auth.test.js tests/release.test.js tests/safe-controls.test.js \
  tests/mainui-safety.test.js tests/openhab-auth.test.js \
  tests/e2e/server.mjs tests/e2e/harness.spec.js \
  vite.config.js tools/release/build.mjs \
  tools/release/activate.mjs tools/release/serve.mjs \
  tools/release/verify-policy.mjs tools/openhab/auth.mjs \
  tools/tls/create-local-cert.sh tests/release-server.test.js \
  tests/release-policy-verifier.test.js \
  tools/openhab/mainui-safety.mjs deploy/earthship-ui-preview.service \
  deploy/earthship-ui-pwa.service tests/tls-config.test.js \
  openhab/mainui/overview-safety-patch.json \
  openhab/mainui/earthship-safety-patch.json \
  openhab/mainui/page-fc7fed510c-safety-patch.json \
  openhab/mainui/page-69e95753c4-safety-patch.json \
  docs/qa/ui-audit-matrix.csv
git commit -m "fix: remove unsafe household actuator controls"
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
RELEASE_ID="safe-compat-$BASE"
RELEASE_MODE=safe-compat RELEASE_ID="$RELEASE_ID" \
  node tools/release/build.mjs --reuse-verified
node tools/release/activate.mjs "$RELEASE_ID"
```

Generate/trust the local certificate as described above. Install/start both
user services only after identifying the listener on 5190 as the exact current
Vite dev command and gracefully stopping that PID. Keep development on 5191:

```bash
set -euo pipefail
install -Dm0644 deploy/earthship-ui-preview.service \
  /home/sat/.config/systemd/user/earthship-ui-preview.service
install -Dm0644 deploy/earthship-ui-pwa.service \
  /home/sat/.config/systemd/user/earthship-ui-pwa.service
systemctl --user daemon-reload
systemctl --user enable --now earthship-ui-preview.service earthship-ui-pwa.service
systemctl --user status --no-pager earthship-ui-preview.service
systemctl --user status --no-pager earthship-ui-pwa.service
```

Then execute the one-process, receipt-bound MainUI safety transaction:

```bash
set -euo pipefail
BASE=$(git rev-parse --short=12 HEAD)
MAINUI_RECEIPT="/tmp/earthship-ui-mainui-safe-$BASE"
MAINUI_EVIDENCE="/tmp/earthship-ui-mainui-safe-$BASE-evidence.json"
curl -fsS http://192.168.1.161:5190/ >/dev/null
curl --cacert /home/sat/.config/earthship-ui/tls/root-ca.crt \
  -fsS https://192.168.1.161:5192/ >/dev/null
node tools/openhab/mainui-safety.mjs transact \
  --receipt "$MAINUI_RECEIPT" --mode safe-compat \
  --evidence-out "$MAINUI_EVIDENCE"
node tools/qa/update-matrix.mjs --task 2 --phase live \
  --receipt "$MAINUI_EVIDENCE" docs/qa/ui-audit-matrix.csv
```

The transaction must finish terminal `desired` or proven no-op `unmutated`.
On an interruption, do not rerun `transact`: run only the emitted exact
`recover --receipt <path>` command. Accept recovery only after terminal
`rolled-back` readback; a rollback failure keeps the receipt open, blocks every
later task, and requires operator action.

Expected: both confirmed origins return 200, Chrome trusts the secure origin,
the active release manifest matches,
and neither Earthship UI nor household MainUI can directly command feeder,
greywater, `OverrideSwitch`, or any owned-load provider Item. Record `ROLL-SAFE-*` evidence in the matrix. This release,
not the pre-audit build, is the rollback target only until Task 16 activates and
verifies its zero-write pre-graph maintenance release. Once graph mutation
starts, no `safe-compat` release may be reactivated; Task 16 later replaces the
pre-graph floor with its post-graph maintenance release. Commit the non-secret
evidence and leave the
handoff clean:

```bash
set -euo pipefail
git diff --check
git add docs/qa/ui-audit-matrix.csv
git commit -m "docs: record safe compatibility rollout"
test -z "$(git status --short)"
```

---

## Task 3: Add strict values, freshness policies, AQI, and thermal-flow models

**Files:**

- Create: `src/lib/openhab/itemValue.js`
- Create: `src/lib/openhab/freshness.js`
- Create: `src/lib/domain/aqi.js`
- Create: `src/lib/domain/thermalFlow.js`
- Modify: `src/lib/openhab/values.js`
- Modify: `src/lib/openhab/index.js`
- Create: `tests/item-value.test.js`
- Create: `tests/freshness.test.js`
- Create: `tests/aqi.test.js`
- Create: `tests/thermal-flow.test.js`
- Modify: `tests/values.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing parsing, envelope, AQI, and flow tests**

```js
it('accepts scientific notation only with an allowed unit', () => {
  expect(parseNumericState('1.25e3 W', ['W'])).toBe(1250);
  expect(parseNumericState('12 bananas', ['W'])).toBeNull();
  expect(parseNumericState('sensor12')).toBeNull();
});

it('carries rounded minutes before formatting', () => {
  expect(runtimeText(119.6)).toBe('2 h 0 m');
});

it.each([
  [-1, 'unavailable'], [0, 'good'], [50, 'good'], [51, 'moderate'],
  [100, 'moderate'], [101, 'sensitive'], [150, 'sensitive'],
  [151, 'unhealthy'], [200, 'unhealthy'], [201, 'very-unhealthy'],
  [300, 'very-unhealthy'], [301, 'hazardous'], [500, 'hazardous'],
  [501, 'beyond'],
])('classifies AQI %s as %s', (raw, band) => {
  expect(adaptCurrentAqi(raw, Date.now()).band).toBe(band);
});

it('points heat toward the room from both outer nodes', () => {
  expect(thermalCorridors({ mass: 22, room: 20, glazing: 24 })).toMatchObject({
    left: { direction: 'right', color: 'amber', magnitude: 2 },
    right: { direction: 'left', color: 'amber', magnitude: 4 },
  });
});
```

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T3A-1' -- \
  npm test -- tests/item-value.test.js \
    -t '^\[RED:T3A-1\]'
```

Expected: FAIL on missing modules and the current duration carry.

- [ ] **Implement the strict contracts**

Use an anchored numeric grammar:

```js
const NUMBER =
  /^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:\s*(\S.*))?$/;

export function parseNumericState(raw, allowedUnits = []) {
  if (raw == null || ['NULL', 'UNDEF', ''].includes(String(raw).trim())) return null;
  const match = NUMBER.exec(String(raw).trim());
  if (!match) return null;
  const unit = match[2] || '';
  if (unit && !allowedUnits.includes(unit)) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}
```

Export the approved `ItemValue` envelope, semantic item policies, and these
special AQI thresholds:

```js
export const AQI_FRESHNESS = {
  liveThroughMs: 75 * 60_000,
  staleThroughMs: 150 * 60_000,
};
```

`ItemValue` carries separate `changedAt` and `updatedAt` fields:
`statechanged` can advance both, while same-value `stateupdated` advances only
`updatedAt`. Stable switches derive trust from Thing/channel and transport
health, not the age of their last state change. Rain parsing rejects mixed/incompatible units.
Thermal flow must implement `mass - room` on the left and `glazing - room` on
the right; null endpoints produce a neutral unavailable corridor.

- [ ] **Run GREEN and commit**

```bash
set -euo pipefail
npm test -- tests/item-value.test.js tests/freshness.test.js tests/values.test.js \
  tests/aqi.test.js tests/thermal-flow.test.js
node tools/qa/update-matrix.mjs --task 3 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/openhab/itemValue.js src/lib/openhab/freshness.js \
  src/lib/openhab/values.js src/lib/openhab/index.js src/lib/domain/aqi.js \
  src/lib/domain/thermalFlow.js tests/item-value.test.js \
  tests/freshness.test.js tests/aqi.test.js tests/thermal-flow.test.js \
  tests/values.test.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: add truthful household value models"
```

Expected: every boundary including malformed, negative, scientific notation,
duration carry, AQI 501, and unavailable thermal endpoints passes.

---

## Task 4: Make bootstrap, SSE, cache, and request lifecycles race-free

**Files:**

- Create: `src/lib/openhab/reconcile.js`
- Create: `src/lib/openhab/snapshotCache.js`
- Create: `src/lib/openhab/providerHealth.js`
- Modify: `src/lib/openhab/client.js`
- Modify: `src/lib/openhab/sse.js`
- Modify: `src/lib/openhab/store.js`
- Modify: `src/lib/openhab/index.js`
- Modify: `tests/client.test.js`
- Modify: `tests/sse.test.js`
- Create: `tests/reconcile.test.js`
- Create: `tests/snapshot-cache.test.js`
- Create: `tests/provider-health.test.js`
- Create: `tests/sse-url.test.js`
- Modify: `tests/store.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing ordered-bootstrap and timeout tests**

Cover cache → buffered SSE → timed REST → timestamp merge → reconnect. Include
REST `lastStateUpdate`, both item `statechanged` and same-value `stateupdated`,
Thing-status events, keepalive transport health, separate
`changedAt`/`updatedAt`, per-item freshness, duplicate timestamp last-arrival
tie-breaking, and disconnect after a command POST. A
60-minute AQI refresh with the same numeric value must still refresh its age.

```js
it('replays a newer buffered event over the REST snapshot', () => {
  const records = reconcileBootstrap({
    cached: null,
    restSnapshot: [{ name: 'A', state: '1', lastStateUpdate: 1500 }],
    bufferedEvents: [{
      kind: 'item-state', name: 'A', state: '2',
      sourceAt: 2000, receivedAt: 2100, arrivalGeneration: 3,
    }],
    capturedAt: 1500,
  });
  expect(records.A.value).toBe('2');
});

it('counts ALIVE as transport traffic without refreshing items', () => {
  expect(parseOpenHABEvent('ALIVE', 1234)).toEqual({
    kind: 'transport-alive',
    receivedAt: 1234,
  });
});
```

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T4A-1' -- \
  npm test -- tests/reconcile.test.js \
    -t '^\[RED:T4A-1\]'
```

Expected: FAIL because keepalives, envelopes, aborts, and reconciliation do not
exist.

- [ ] **Implement the ordered state flow**

Public interfaces:

```js
getAllItems({ signal, timeoutMs } = {}) // retain type + lastStateUpdate
getAllThings({ signal, timeoutMs } = {})
getItem(name, { signal, timeoutMs } = {})
sendCommand(name, value, { signal, timeoutMs } = {})
iterateHistoryPages(name, {
  startTime, endTime, pageSize = 5_000, signal, timeoutMs,
}) // AsyncIterable<{ pageIndex, rows, decodedBytes }>
parseOpenHABEvent(raw, receivedAt)
reconcileBootstrap({ cached, restSnapshot, bufferedEvents, capturedAt })
loadCachedSnapshot(storage)
saveCachedSnapshot(storage, records, capturedAt)
```

`initOpenhab()` must start/buffer SSE before fetching REST:

```js
applyCachedSnapshot(loadCachedSnapshot(storage));
sse.start();
const restSnapshot = await client.getAllItems({ timeoutMs: 8_000 });
itemValues.set(reconcileBootstrap({
  cached: get(itemValues),
  restSnapshot,
  bufferedEvents,
  capturedAt: Date.now(),
}));
buffering = false;
```

Reconnect repeats item and Thing REST reconciliation. The EventSource URL
subscribes to the exact comma-separated topics
`openhab/items/*/statechanged`, `openhab/items/*/stateupdated`, and
`openhab/things/*/statuschanged`. `tests/sse-url.test.js` asserts the encoded
URL and proves each topic reaches its parser branch. The SSE parser accepts
those item/Thing events and `ALIVE`; a same-value `stateupdated` advances only `updatedAt`; a real
`statechanged` advances `changedAt` and `updatedAt`. `buildProviderIndex(things)` derives
`Map<itemName, { thingUID, channelUID }>` directly from each live Thing
channel's `linkedItems`; it does not depend on the later control catalog.
Collisions, unlinked items, and Thing/channel disappearance are explicit test
cases. `providerHealth(index, thingStatuses)` is the authority for stable
binary trust. Cache only read-only state plus capture time; it must never contain
commands or pending intentions. Keep a temporary derived raw `items` store only
until the explicit presentation migration in Task 8; Task 8 deletes that
compatibility store before any route stale/offline geometry test runs.

- [ ] **Run GREEN and commit**

```bash
set -euo pipefail
npm test -- tests/client.test.js tests/sse.test.js tests/reconcile.test.js \
  tests/snapshot-cache.test.js tests/provider-health.test.js \
  tests/sse-url.test.js tests/store.test.js
node tools/qa/update-matrix.mjs --task 4 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/openhab/reconcile.js src/lib/openhab/snapshotCache.js \
  src/lib/openhab/providerHealth.js src/lib/openhab/client.js \
  src/lib/openhab/sse.js src/lib/openhab/store.js src/lib/openhab/index.js \
  tests/client.test.js tests/sse.test.js tests/reconcile.test.js \
  tests/snapshot-cache.test.js tests/provider-health.test.js \
  tests/sse-url.test.js tests/store.test.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: reconcile openHAB state without races"
```

Expected: tests prove a late REST response cannot overwrite a newer SSE event,
keepalives affect only transport, same-value updates refresh AQI age, Thing
health governs stable switches, reconnect fills missed events, all fetches
abort/timeout, and cached state never authorizes commands.

---

## Task 5: Build the bounded pure history pipeline

**Files:**

- Create: `src/lib/charts/periods.js`
- Create: `src/lib/charts/seriesPolicy.js`
- Create: `src/lib/charts/historyPipeline.js`
- Modify: `src/lib/openhab/readCatalog.js`
- Modify: `src/lib/openhab/client.js`
- Create: `tests/history-periods.test.js`
- Create: `tests/series-policy.test.js`
- Create: `tests/history-pipeline.test.js`
- Create: `tests/history-pagination.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing period, unit, smoothing, gap, and cap tests**

Required period constants are exactly:

```js
export const HISTORY_PERIODS = [4, 24, 168, 720];
```

Test one captured `now` across N series, history
`[now-hours, now]`, independent forecast `[now, now+lookahead]`, invalid
period rejection, last duplicate arrival, rain unit rejection, gaps over three
cadences, zero/one/two-point smoothing identity, median-of-three plus EMA 0.25,
raw tooltip preservation, equal extrema, many fragments, width zero, and these
hard caps:

```js
expect(result.displaySegments.flat()).toHaveLength(400); // W=200, one series
expect(totalRenderedPoints(result)).toBeLessThanOrEqual(800); // floor(4W)
```

Pagination tests drive the exact `iterateHistoryPages()` async iterator:
at most 5,000 rows/page, reject declared-length and chunked/no-length bodies
as soon as they exceed 5 MiB, reject a series above 300,000 raw rows, forward one shared AbortSignal, and stop requesting the
next page immediately after cancellation. Parity fixtures split the same input
at multiple page boundaries across a duplicate timestamp, median-of-three
neighborhood, EMA continuation, real gap, and min/max bucket extrema; every
split must produce byte-for-byte identical normalized/raw-tooltip/display
output.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T5A-1' -- \
  npm test -- tests/history-periods.test.js \
    -t '^\[RED:T5A-1\]'
```

Expected: FAIL because the shared pipeline and bounded pagination do not exist.

- [ ] **Implement policy-driven normalization and smoothing**

```js
export function prepareHistorySeries(rows, {
  expectedCadenceMs,
  maxGapMs,
  smoothing,
  alpha = 0.25,
  allowedUnits,
  widthPx,
  pointBudget,
}) {
  const raw = normalizeHistory(rows, { allowedUnits });
  const gapMs = maxGapMs ?? 3 * inferCadence(raw, expectedCadenceMs);
  const segments = splitAtGaps(raw, gapMs);
  const filtered = smoothing === 'median3-ema'
    ? segments.map((segment) => ema(medianThree(segment), alpha))
    : segments;
  return {
    raw,
    displaySegments: downsampleSegments(filtered, { widthPx, pointBudget }),
  };
}
```

The explicit smoothing registry enables only temperatures, pressure, sustained
wind, and non-operational `MPPT60_PV_Power`. SoC, gust/max, rain,
switches, forecasts, curtailment, status, and operational steps must have
`smoothing: 'none'`. ECharts smoothing is not involved.

`iterateHistoryPages()` first rejects `Content-Length` above 5 MiB, then reads
the response body stream incrementally with a byte counter and cancels as soon
as the same cap is crossed, including chunked/no-length responses. Only the
bounded bytes are decoded and JSON-validated; the page is yielded before the
next request.
`packHistoryPage(rows, policy)` converts that one page into transferable
timestamp/value/arrival typed arrays; the decoded row objects are released
before the iterator advances. `createHistoryAccumulator(policy)`,
`appendPackedHistoryPage(accumulator, packet)`, and
`finalizeHistory(accumulator, { widthPx, pointBudget })` are the exact
incremental worker/reference interfaces. `prepareHistorySeries(rows, options)`
is only a small-input pure convenience that packs one synthetic page through
the same accumulator; production callers never pass it a complete decoded
response. No aggregate API named `getHistory()` is added,
and no caller reconstructs one full dense object graph.

- [ ] **Run GREEN and commit**

```bash
set -euo pipefail
npm test -- tests/history-periods.test.js tests/series-policy.test.js \
  tests/history-pipeline.test.js tests/history-pagination.test.js
node tools/qa/update-matrix.mjs --task 5 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/charts/periods.js src/lib/charts/seriesPolicy.js \
  src/lib/charts/historyPipeline.js src/lib/openhab/readCatalog.js \
  src/lib/openhab/client.js tests/history-periods.test.js tests/history-pipeline.test.js \
  tests/history-pagination.test.js tests/series-policy.test.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: bound and smooth history data safely"
```

Expected: display values are smoothed only for the registry, raw tooltip pairs
stay unchanged, gaps never bridge, and every point/page/raw-row cap is enforced.

---

## Task 6: Add one cancellable chart controller and worker

**Files:**

- Create: `src/lib/charts/historyRequest.js`
- Create: `src/lib/charts/history.worker.js`
- Create: `src/lib/charts/workerProtocol.js`
- Create: `tests/history-request.test.js`
- Create: `tests/history-worker.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing generation, partial-failure, refresh, and resize tests**

Test that one generation captures one `now`, shares one abort/timeout across N
`iterateHistoryPages()` iterators, transfers each packed page to the worker
before requesting the next, renders surviving series with
`N series unavailable`, fails only when all required series fail, ignores stale
worker completion, distinguishes timeout/error/superseded, terminates cleanly,
and re-downsamples retained aggregates after a material width change without
refetching. With fake timers, an active ready chart refreshes after exactly five
minutes with a newly captured `now`; close/destroy clears the timer.

```js
controller.load({ series, hours: 24, widthPx: 200, nowMs: 100_000 });
controller.load({ series, hours: 168, widthPx: 220, nowMs: 110_000 });
firstPage.resolve(oldRows);
expect(latest(controller).periodHours).toBe(168);
expect(client.iterateHistoryPages).toHaveBeenCalledTimes(series.length * 2);
expect(workerMessages).toContainEqual(
  expect.objectContaining({ type: 'append-page', generation: 2 })
);
```

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


```bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T6A-1' -- \
  npm test -- tests/history-request.test.js \
    -t '^\[RED:T6A-1\]'
```

Expected: FAIL because controller, worker, and protocol do not exist.

- [ ] **Implement the controller contract**

```js
createHistoryController({
  clientProvider,
  workerFactory,
  timeoutMs = 8_000,
  refreshMs = 5 * 60_000,
  clock,
  scheduler,
}) => {
  subscribe,
  load({ series, hours, widthPx, nowMs }),
  refresh(),
  resize(widthPx),
  cancel(reason),
  destroy(),
}
```

States are `idle`, `loading`, `ready`, `empty`, `timed-out`, `partial-error`,
`error`, and `superseded`. A new period, close, route change, or new generation
aborts the old one. A debounced width delta of at least 8 CSS px after 100 ms
reprocesses retained aggregates without network I/O. The controller consumes
each series' async pages incrementally and sends `append-page`,
`finish-series`, then `finish-generation`; cancellation aborts every iterator
before another page is fetched. Worker messages always echo generation and use
transferable numeric arrays. One five-minute timer is armed only after a
successful active load; refresh replaces the generation and timer, while
cancel/destroy removes both.

- [ ] **Run GREEN and commit**

```bash
set -euo pipefail
npm test -- tests/history-request.test.js tests/history-worker.test.js
node tools/qa/update-matrix.mjs --task 6 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/charts/historyRequest.js src/lib/charts/history.worker.js \
  src/lib/charts/workerProtocol.js tests/history-request.test.js \
  tests/history-worker.test.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: add cancellable chart processing"
```

Expected: stale and cancelled generations cannot commit; worker and
main-thread pure outputs are identical.


---

## Task 7: Unify responsive charts, modal behavior, Bitcoin history, and compass geometry

**Files:**

- Create: src/lib/charts/echarts.js
- Create: src/lib/charts/options.js
- Create: src/lib/ui/observeElementSize.js
- Create: src/lib/ui/ChartCanvas.svelte
- Create: src/lib/ui/HistorySparkline.svelte
- Create: src/lib/ui/compassGeometry.js
- Modify: src/lib/ui/HistoryChart.svelte
- Modify: src/lib/ui/ChartModal.svelte
- Modify: src/lib/ui/chartStore.js
- Modify: src/lib/ui/Sparkline.svelte
- Modify: src/lib/ui/HourlyStrip.svelte
- Modify: src/lib/ui/CompassRose.svelte
- Modify: src/screens/Home.svelte
- Modify: src/screens/Energy.svelte
- Modify: src/screens/Weather.svelte
- Modify: src/screens/Earthship.svelte
- Create: tests/chart-options.test.js
- Create: tests/chart-store.test.js
- Create: tests/compass-geometry.test.js
- Create: tests/ui/ChartCanvas.test.js
- Create: tests/ui/HistoryChart.test.js
- Create: tests/ui/ChartModal.test.js
- Create: tests/ui/HistorySparkline.test.js
- Create: tests/ui/CompassRose.test.js
- Create: tests/chart-call-sites.test.js
- Create: tests/e2e/chart-activation.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing chart/modal/compass integration tests**

Cover 4h/24h/7d/30d retaining 4/24/168/720 hours; modal seed once per
openId; cancellation; aria-pressed; 44x44 targets; focus trap/Escape/focus
return; immediate-parent ResizeObserver; `smooth:false` with raw tooltips;
fixed 24 h Outdoor inline history; no BTC history until card activation;
five-minute active refresh; exact accessible chart descriptions; native
Weather Wind/Rain/Pressure activation with no duplicate keyboard event; and
the largest square compass with gust/max outside the rose. Every
`tests/ui/*.test.js` file begins with `// @vitest-environment jsdom` and uses
the Task 1 observer/canvas/ECharts fakes.

~~~js
it('keeps 7d selected', async () => {
  render(HistoryChart, { series: [temperature], initialHours: 24 });
  await user.click(screen.getByRole('button', { name: '7d' }));
  expect(load).toHaveBeenLastCalledWith(
    expect.objectContaining({ hours: 168 })
  );
  expect(screen.getByRole('button', { name: '7d' }))
    .toHaveAttribute('aria-pressed', 'true');
});

it('fits the rose below dedicated gust rows', () => {
  expect(fitCompass({
    width: 220, height: 180, reservedRowsPx: 36, gapPx: 8,
  })).toBe(136);
});
~~~

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T7A-1' -- \
  npm test -- tests/chart-options.test.js \
    -t '^\[RED:T7A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T7A-2' -- \
  npx playwright test tests/e2e/chart-activation.spec.js \
    --project=m9-browser --grep '^\[RED:T7A-2\]'
~~~

Expected: FAIL because modal state resets periods, chart sizes are fixed,
BTC fetches eagerly, and the compass has a 4.6 rem cap.

- [ ] **Register only required ECharts modules**

~~~js
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent, LegendComponent, TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer,
]);
export { echarts };
~~~

buildHistoryOption() and buildSparklineOption() consume prepared segments, set
smooth:false, escape labels, and use retained raw samples in tooltips. No screen
imports the full ECharts package or a full icon set.

- [ ] **Implement one measured canvas and one modal controller**

ChartCanvas owns init/resize/dispose:

~~~js
const stop = observeElementSize(host, ({ width, height }) => {
  if (width <= 0 || height <= 0) return;
  chart.resize({ width, height });
  onSize?.({ width, height });
});
~~~

Change chartStore to `{ open, openId, title, series, initialHours, opener }` and
increment `openId` on every open. ChartModal seeds only when `openId` changes
and cancels on close/unmount/route change. Initial focus goes to the active
period button, or the close button when no period is available. Add
`aria-labelledby`, `aria-describedby`, focus trap, Escape, overlay close, and
focus restoration. The description is generated and tested to name every
series, selected period, current state, and most recent raw value (or its
explicit unavailable reason).

- [ ] **Migrate callers, BTC, and compass**

HistoryChart props become { series = [], initialHours = 24 }; remove fixed
heights. HistorySparkline owns the shared controller; Sparkline only renders
prepared segments. Convert HourlyStrip to parent fill.

Remove `btcSpark`, `refreshBtcSpark`, its timer, and markup from Home. Keep
price/change and native-button modal activation. `tests/e2e/chart-activation.spec.js`
proves Home mount performs no BTC history request; first activation loads once;
the active modal refreshes after five minutes; an SSE price update changes the
summary without loading history; route-away destroys it; and return remains
lazy until the next activation. Keep Outdoor inline history at exactly 24 h.

Migrate every `openChart` caller in Home, Energy, Weather, and Earthship to
`initialHours`. Remove hard-coded “(24h)” titles where a selectable period can
make them false. Weather's Wind, Rain, and Pressure cards become native buttons
(or contain one native full-card button) with visible focus; tests dispatch
Enter/Space and assert one activation each.

~~~js
export function fitCompass({ width, height, reservedRowsPx, gapPx }) {
  return Math.max(
    0,
    Math.floor(Math.min(width, height - reservedRowsPx - gapPx))
  );
}
~~~

Observe the card content, scale every rose primitive, move gust/max to dedicated
rows, and remove the 4.6 rem cap.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/chart-options.test.js tests/chart-store.test.js \
  tests/compass-geometry.test.js tests/ui/ChartCanvas.test.js \
  tests/ui/HistoryChart.test.js tests/ui/ChartModal.test.js \
  tests/ui/HistorySparkline.test.js tests/ui/CompassRose.test.js \
  tests/chart-call-sites.test.js
npx playwright test tests/e2e/chart-activation.spec.js
npm run build
node tools/qa/update-matrix.mjs --task 7 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/charts/echarts.js src/lib/charts/options.js \
  src/lib/ui/observeElementSize.js src/lib/ui/ChartCanvas.svelte \
  src/lib/ui/HistorySparkline.svelte src/lib/ui/compassGeometry.js \
  src/lib/ui/HistoryChart.svelte src/lib/ui/ChartModal.svelte \
  src/lib/ui/chartStore.js src/lib/ui/Sparkline.svelte \
  src/lib/ui/HourlyStrip.svelte src/lib/ui/CompassRose.svelte \
  src/screens/Home.svelte src/screens/Energy.svelte \
  src/screens/Weather.svelte src/screens/Earthship.svelte \
  tests/chart-options.test.js tests/chart-store.test.js \
  tests/compass-geometry.test.js tests/ui/ChartCanvas.test.js \
  tests/ui/HistoryChart.test.js tests/ui/ChartModal.test.js \
  tests/ui/HistorySparkline.test.js tests/ui/CompassRose.test.js \
  tests/chart-call-sites.test.js tests/e2e/chart-activation.spec.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "fix: unify responsive chart and compass behavior"
~~~

Expected: period, resize, accessibility, lazy BTC, and compass tests pass; the
build has no full ECharts import.

---

## Task 8: Replace the BTC/stale header rows with deterministic alerts

**Files:**

- Create: src/lib/alerts/consoleAlerts.js
- Create: src/lib/alerts/alertStore.js
- Create: src/lib/controls/outcomeStore.js
- Create: src/lib/ui/HeaderAlerts.svelte
- Modify: src/lib/ui/Header.svelte
- Modify: src/lib/ui/Shell.svelte
- Modify: src/lib/ui/Tile.svelte
- Modify: src/app.css
- Modify: src/screens/Home.svelte
- Modify: src/screens/Energy.svelte
- Modify: src/screens/Weather.svelte
- Modify: src/screens/Earthship.svelte
- Modify: src/screens/Controls.svelte
- Modify: src/lib/openhab/store.js
- Modify: src/lib/openhab/index.js
- Delete: src/lib/ui/BtcTicker.svelte
- Create: tests/console-alerts.test.js
- Create: tests/outcome-store.test.js
- Create: tests/item-value-consumption.test.js
- Modify: tests/store.test.js
- Create: tests/ui/HeaderAlerts.test.js
- Create: tests/e2e/header-alerts.spec.js
- Create: tests/e2e/shell-layout.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing alert and shell tests**

Test fixed priority, severity ties, dedupe, state clearing, 15-minute control
outcome expiry, same-value freshness preserving a state alert's
`activeSince`, unknown thermal diagnostics, stable +N, route navigation/global
list, no-active-alert accessibility, long one-line content, and announcement
mode. Predicted trough below 40 is warning and at or below 12 is critical;
`close_up_tomorrow` is warning; `vent_tonight` is advisory; only failed,
sent-unconfirmed, and outcome-unknown control phases alert. The next outcome
for one control replaces its predecessor and expires 15 minutes after its own
`transitionAt`, which is distinct from item/source freshness timestamps.
`tests/item-value-consumption.test.js` scans all five screens, Header, alerts,
and presentation components; it rejects imports/reads of the raw compatibility
`items` store and requires `ItemValue` adapters. `tests/store.test.js` fails
until that derived raw store/export is removed. Playwright asserts an exact
44 px header and no second banner in every profile. The no-alert region is visually blank but exposes `No active alerts`; routine
updates are polite and only a newly entered offline/critical state is
assertive.

~~~js
expect(selectHeaderAlerts(projectConsoleAlerts(fixture))).toEqual({
  winner: expect.objectContaining({ id: 'connection-offline' }),
  additionalCount: 2,
  ordered: expect.any(Array),
});
~~~

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T8A-1' -- \
  npm test -- tests/console-alerts.test.js \
    -t '^\[RED:T8A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T8A-2' -- \
  npx playwright test tests/e2e/header-alerts.spec.js \
    --project=m9-browser --grep '^\[RED:T8A-2\]'
~~~

Expected: FAIL because BTC and the banner occupy the shell and alerts do not
exist.

- [ ] **Implement exact alert projection**

~~~js
export const ALERT_PRIORITY = [
  'connection-offline',
  'battery-critical',
  'telemetry-stale',
  'thermal-close',
  'soc-trough',
  'aqi-unhealthy',
  'thermal-vent',
  'control-outcome',
];
~~~

Sources are only connection, `BMS_Comms_Status`, `BMS_DevicePresent`, current
SoC at or below 12, existing battery alarms, `Thermal_Advisory`, predicted
trough below 40, `Current_US_AQI` at or above 101, and correlated outcomes.
Thermal codes are `none`, `vent_tonight`, and `close_up_tomorrow`; an unknown
non-empty code is a warning plus diagnostic. Control outcomes enter only for
`failed`, `sent-unconfirmed`, or `outcome-unknown`. `outcomeStore` keeps one
latest record per control with its separate `transitionAt`; replacement and
15-minute expiry are deterministic and never use telemetry freshness time.
`alertStore` assigns state alerts an `activeSince` only when
their dedupe key enters or materially changes alert state; same-value freshness
updates never move it. Control alerts normalize their outcome `transitionAt`
to the same sort field. Sort by severity, fixed priority, newest active
transition, then ID; dedupe by `dedupeKey`. Alerts cannot be dismissed or persisted. The summary never wraps,
rotates, or changes header height; the connection lamp stays icon-only. The visible winner always has its full
text as an accessible name or an always-present visually hidden description,
even while the full list is closed. When empty it renders no visible
placeholder but retains an accessible `No active alerts` status; routine live
regions are polite and only a newly entered offline/critical transition uses a
separate assertive announcement.

- [ ] **Complete the truthful presentation migration before layout work**

Migrate every Home, Energy, Weather, Earthship, Controls, Header, and alert
presentation read to the Task 3 `itemValues` envelope. Each surface renders
live, stale, cached, unavailable, and provider-offline explicitly; no raw value
can stand in for freshness. Delete the Task 4 derived raw `items` store/export.
Alert state transitions use envelope health/value but preserve their own
`activeSince` as specified above. Tasks 9–11 may now exercise truthful
stale/offline fixtures.

- [ ] **Implement the bounded shell**

Delete BtcTicker and stale banner; render one HeaderAlerts slot:

~~~css
html, body, #app {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.shell {
  display: grid;
  grid-template-columns: var(--rail-size) minmax(0, 1fr);
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}
.nav-rail { grid-column: 1; grid-row: 1; block-size: 100dvh; }
.app-column {
  grid-column: 2;
  grid-row: 1;
  display: grid;
  grid-template-rows: 44px minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}
.header { grid-row: 1; block-size: 44px; min-block-size: 44px; }
.screen { grid-row: 2; min-width: 0; min-height: 0; overflow: hidden; }
~~~

Use measured breakpoints, a 52 px M9 rail, 60 px laptop rail, 44x44 targets,
`aria-current=page`, and a fixed-label/shrinkable-body Tile with no scrollbar.
Shell tests assert the rail touches viewport top/bottom, the app column owns all
remaining width, and `header.left === rail.right` in every profile.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/console-alerts.test.js tests/outcome-store.test.js \
  tests/item-value-consumption.test.js tests/store.test.js \
  tests/ui/HeaderAlerts.test.js
npx playwright test tests/e2e/header-alerts.spec.js \
  tests/e2e/shell-layout.spec.js
npm run build
node tools/qa/update-matrix.mjs --task 8 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/alerts/consoleAlerts.js src/lib/alerts/alertStore.js \
  src/lib/controls/outcomeStore.js src/lib/ui/HeaderAlerts.svelte src/lib/ui/Header.svelte \
  src/lib/ui/Shell.svelte src/lib/ui/Tile.svelte src/app.css \
  src/screens/Home.svelte src/screens/Energy.svelte src/screens/Weather.svelte \
  src/screens/Earthship.svelte src/screens/Controls.svelte \
  src/lib/openhab/store.js src/lib/openhab/index.js \
  tests/console-alerts.test.js tests/outcome-store.test.js \
  tests/item-value-consumption.test.js tests/store.test.js \
  tests/ui/HeaderAlerts.test.js tests/e2e/header-alerts.spec.js tests/e2e/shell-layout.spec.js
git add -u src/lib/ui/BtcTicker.svelte
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: turn the fixed header into an alert surface"
~~~

Expected: clock, connection affordance, one-line winner, and +N fit in 44 px;
no BTC/banner remains.

---

## Task 9: Recompose Home for distance readability and hard containment

**Files:**

- Modify: src/screens/Home.svelte
- Modify: src/lib/ui/StatTile.svelte
- Create: tests/e2e/home.spec.js
- Create: tests/e2e/home-long-content.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing Home geometry and style tests**

Normal, unavailable, stale/offline, and long fixtures import the Task 1
required-content manifest and assert every Home selector, no scroll, child
containment, Outdoor plot minimum 120x44 M9/160x64 laptop, visible line after
navigation/resize, compass non-overlap, native card activation, and these
computed styles. They also assert Indoor is pure white, Rain value/footer
containment and sizes, Sun/Moon at 0.82 rem or a recorded M9 fallback no smaller
than 0.8 rem, laptop Sun/Moon at 0.86 rem, and unchanged shared StatTile
computed defaults on Weather and Earthship:

~~~js
await expect(outdoorTemp).toHaveCSS('color', 'rgb(255, 255, 255)');
expect(px(await indoorTemp.evaluate((el) => getComputedStyle(el).fontSize)))
  .toBeGreaterThanOrEqual(profile.startsWith('m9') ? 38.4 : 41.6);
expect(px(await indoorMeta.evaluate((el) => getComputedStyle(el).fontSize)))
  .toBeGreaterThanOrEqual(13.6);
~~~

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T9A-1' -- \
  npx playwright test tests/e2e/home.spec.js \
    --project=m9-browser --grep '^\[RED:T9A-1\]'
~~~

Expected: FAIL on overflow, typography, Outdoor line, and compass geometry.

- [ ] **Implement the measured Home grid and typography**

~~~css
.home-grid {
  block-size: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  grid-template-rows:
    minmax(0, .38fr)
    minmax(0, 1.2fr)
    minmax(0, 1fr)
    minmax(0, .9fr)
    minmax(0, .72fr);
}
.big-temp, .indoor-temp { color: #ffffff; }
.indoor-temp { font-size: 2.4rem; }
.indoor-meta { font-size: .85rem; }
/* StatTile owns these scoped variables; Home passes them only to Rain. */
.stat-value { font-size: var(--stat-value-size, 2.4rem); }
.stat-footer { font-size: var(--stat-footer-size, .8rem); }

/* Home Rain instance props */
--stat-value-size: 2.15rem;
--stat-footer-size: .72rem;
.sunmoon-cell .sm-row { font-size: .82rem; }

@media (min-width: 1280px) and (min-height: 720px) {
  .indoor-temp { font-size: 2.6rem; }
  .sunmoon-cell .sm-row { font-size: .86rem; }
}
~~~

Use measured columns/gaps and only minmax(0,fr) rows. Preserve all design
section 4.4 content. If .82rem fails M9, reduce spacing first; floor is .8rem.
`StatTile` exposes optional CSS-variable props on its own root; Home passes
`--stat-value-size: 2.15rem` and `--stat-footer-size: .72rem` only to Rain.
Do not rely on a parent selector crossing Svelte style scoping. Do not change
shared Weather/Earthship StatTile sizing.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npx playwright test tests/e2e/home.spec.js \
  tests/e2e/home-long-content.spec.js
node tools/qa/update-matrix.mjs --task 9 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/screens/Home.svelte src/lib/ui/StatTile.svelte \
  tests/e2e/home.spec.js tests/e2e/home-long-content.spec.js \
  docs/qa/ui-audit-matrix.csv
git commit -m "fix: fit and clarify the tablet Home dashboard"
~~~

Expected: all Home content is contained and all four readability targets pass.

---

## Task 10: Fit Energy and Weather, and consume only current numeric AQI

**Files:**

- Modify: src/screens/Energy.svelte
- Modify: src/screens/Weather.svelte
- Modify: src/screens/Home.svelte
- Modify: src/lib/ui/HourlyStrip.svelte
- Modify: src/lib/domain/aqi.js
- Create: tests/weather-aqi-wiring.test.js
- Create: tests/e2e/energy.spec.js
- Create: tests/e2e/weather.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing route geometry and AQI-wiring tests**

~~~js
const home = await readFile('src/screens/Home.svelte', 'utf8');
const weather = await readFile('src/screens/Weather.svelte', 'utf8');
expect(home).toContain('Current_US_AQI');
expect(home).not.toContain('Forecast_AQI');
expect(weather).toContain('Current_US_AQI');
expect(weather).not.toMatch(
  /(?:num|fmt|adaptCurrentAqi|aqiColor|aqiBand)\([^)]*Forecast_AQI/
);
expect(weather).toMatch(/adaptHourlyAqiForecast\([^)]*Forecast_AQI/);
expect(AQI_BINDINGS).toEqual({
  current: 'Current_US_AQI',
  hourlyForecast: 'Forecast_AQI',
});
~~~

Playwright imports the Task 1 manifest and covers every required card/subrow
under normal, unavailable, offline, partial-chart-error, and long-content
fixtures. Its AQI fixture deliberately sets numeric current AQI to 42 with a
fresh timestamp and the hourly forecast to an incompatible categorical warning
with a stale timestamp. It asserts the current card renders
`Modeled US AQI 42`, the good band/color, current-item freshness, and
`data-source-item="Current_US_AQI"`; hourly rows alone expose
`data-source-item="Forecast_AQI"`. A second fixture sets current AQI to 501
with a benign hourly forecast and asserts literal `501` remains visible while
the current card and header alert use critical/beyond treatment; no clamp or
forecast color is accepted. Weather checks every daily row. Energy checks
both charts, outlook, and each Battery Vital. Two divergent fixtures set
communications healthy/device absent and then communications failed/device
present; exact per-node text, health attributes, and
`data-source-item` values must follow their own ItemValue rather than a combined
BMS value.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T10A-1' -- \
  npm test -- tests/weather-aqi-wiring.test.js \
    -t '^\[RED:T10A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T10A-2' -- \
  npx playwright test tests/e2e/energy.spec.js \
    --project=m9-browser --grep '^\[RED:T10A-2\]'
~~~

Expected: FAIL because pages use auto rows/fixed chart heights, Weather scrolls,
and Home/Weather parse Forecast_AQI.

- [ ] **Implement bounded rows and parent-sized charts**

~~~css
.energy-grid {
  grid-template-rows:
    minmax(0, 1.25fr) minmax(0, .9fr)
    minmax(0, .55fr) minmax(0, .55fr);
}
.weather-grid {
  grid-template-rows:
    minmax(0, .75fr) minmax(0, 1.05fr)
    minmax(0, 1.2fr) minmax(0, .55fr);
}
.energy-grid, .weather-grid {
  block-size: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
~~~

Remove chart height 200/160/150 props. Make hero-chart, pv-chart, and HourlyStrip
parent boxes authoritative. Compact daily rows/legends before required text.
Render `BMS_Comms_Status` and `BMS_DevicePresent` as two independent Battery
Vital nodes with their own `ItemValue` health/unavailable semantics and exact
`data-source-item` attributes; do not collapse them into the current combined
“BMS Health” value. Export and consume immutable `AQI_BINDINGS` from
`src/lib/domain/aqi.js` so current and forecast presentation cannot silently
swap sources.

- [ ] **Switch current-AQI presentation**

Home, Weather, and alerts consume Current_US_AQI through adaptCurrentAqi().
Label it Modeled US AQI; render live/stale/unavailable from the 75/150-minute
policy and keep values above 500 visible/critical. Forecast_AQI remains only an
hourly categorical forecast and is never commanded or parsed as current AQI.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/weather-aqi-wiring.test.js tests/aqi.test.js
npx playwright test tests/e2e/energy.spec.js tests/e2e/weather.spec.js
node tools/qa/update-matrix.mjs --task 10 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/screens/Energy.svelte src/screens/Weather.svelte \
  src/screens/Home.svelte src/lib/ui/HourlyStrip.svelte src/lib/domain/aqi.js \
  tests/weather-aqi-wiring.test.js tests/e2e/energy.spec.js \
  tests/e2e/weather.spec.js docs/qa/ui-audit-matrix.csv
git commit -m "fix: contain Energy and Weather tablet routes"
~~~

Expected: required rows are visible without scroll, charts fill their parents,
and current AQI wiring is numeric/current-only.

---

## Task 11: Correct Earthship physics/order and fit Earthship plus Controls

**Files:**

- Modify: src/screens/Earthship.svelte
- Modify: src/lib/ui/ThermalLoop.svelte
- Modify: src/screens/Controls.svelte
- Create: tests/thermal-loop-order.test.js
- Create: tests/e2e/earthship.spec.js
- Create: tests/e2e/controls-layout.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing semantic-order and geometry tests**

Assert DOM, SVG node, legend, humidity, and keyboard order:

~~~js
expect(names).toEqual(['North Mass', 'Room Air', 'South Glazing']);
~~~

Test both corridors with positive, negative, zero, and unavailable values,
including direction/color/magnitude. Geometry covers advisory, loop, distinct
Thermal Mass companion, buffering, greywater status/last cycle, humidity, all
control groups, unavailable states, and two-line long denial/failure text.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T11A-1' -- \
  npm test -- tests/thermal-loop-order.test.js \
    -t '^\[RED:T11A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T11A-2' -- \
  npx playwright test tests/e2e/earthship.spec.js \
    --project=m9-browser --grep '^\[RED:T11A-2\]'
~~~

Expected: FAIL because current order is South/Room/North and both routes can
grow/scroll.

- [ ] **Bind every Earthship order-dependent surface together**

ThermalLoop consumes:

~~~js
[
  { id: 'north', label: 'North Mass', value: mass },
  { id: 'room', label: 'Room Air', value: room },
  { id: 'south', label: 'South Glazing', value: glazing },
]
~~~

Render thermalCorridors().left and .right. Apply the same order to SVG, legend,
humidity, focus, and accessible description. Keep the analytic Thermal Mass
card visually distinct from the physical three-node model.

- [ ] **Implement bounded route boards**

~~~css
.earthship-grid {
  grid-template-rows:
    minmax(0, .55fr) minmax(0, 1.65fr) minmax(0, .9fr);
}
.controls-grid {
  grid-template-rows: repeat(3, minmax(0, 1fr));
}
.earthship-grid, .controls-grid {
  block-size: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
~~~

Preserve all design section 4.4 content. Long text uses fixed one/two-line
budgets with an accessible full label, never a scrollbar.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/thermal-loop-order.test.js tests/thermal-flow.test.js
npx playwright test tests/e2e/earthship.spec.js \
  tests/e2e/controls-layout.spec.js
node tools/qa/update-matrix.mjs --task 11 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/screens/Earthship.svelte src/lib/ui/ThermalLoop.svelte \
  src/screens/Controls.svelte tests/thermal-loop-order.test.js \
  tests/e2e/earthship.spec.js tests/e2e/controls-layout.spec.js \
  docs/qa/ui-audit-matrix.csv
git commit -m "fix: orient and contain Earthship tablet routes"
~~~

Expected: North/Room/South order is consistent and both routes fit without
scrolling.

---

## Task 12: Replace generic toggles with typed, correlated controls

**Files:**

- Create: src/lib/controls/catalog.js
- Create: src/lib/controls/outcome.js
- Modify: src/lib/controls/outcomeStore.js
- Create: src/lib/controls/controlMachine.js
- Create: src/lib/releaseMode.js
- Create: src/lib/actions/holdAction.js
- Create: src/lib/ui/BinaryControl.svelte
- Create: src/lib/ui/OwnedBinaryControl.svelte
- Create: src/lib/ui/ActionControl.svelte
- Create: src/lib/ui/SafetyRequest.svelte
- Modify: src/lib/ui/StatusControl.svelte
- Modify: src/screens/Controls.svelte
- Modify: src/screens/Earthship.svelte
- Delete: src/lib/ui/Toggle.svelte
- Modify: tests/safe-controls.test.js
- Create: tests/control-catalog.test.js
- Create: tests/control-outcome.test.js
- Create: tests/control-machine.test.js
- Create: tests/release-mode.test.js
- Create: tests/hold-action.test.js
- Create: tests/ui/typed-controls.test.js
- Create: tests/e2e/control-states.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing catalog/state-machine/hold tests**

Test 600 ms pointer/keyboard holds; early release, cancel, blur, route change,
second pointer, repeat key, and invalidation; one in flight; no retry; HTTP
acceptance versus provider acknowledgement; post-POST disconnect to
sent-unconfirmed or outcome-unknown; late/contradictory provider events;
unknown request ID; and correlated accepted/denied/running/complete/failed
outcomes. Alert tests prove both unconfirmed terminal phases project once and
expire from their own transition time. Static tests inspect every owned control
and prove its provider `stateItem` is never passed to `sendCommand`; only the
request Item can be submitted.

The catalog test asserts this exact mapping:

~~~js
{
  living1: ['living_room_1_Switch', 'binary'],
  living2: ['living_room_2_Switch', 'binary'],
  living3: ['LED_living_room_1_Switch', 'binary'],
  circadian: ['LivingRoomCircadian_Enable', 'binary-policy'],
  dishwasher: {
    stateItem: 'Dish_Washer_Power',
    requestItem: 'NightLoadDevice_Request',
    resultItem: 'NightLoadDevice_Result',
    device: 'dishwasher',
    kind: 'owned-binary-request',
    requiresCapability: 'night-load-owner-v1',
  },
  shureflo: {
    stateItem: 'ShurefloPump_Power',
    requestItem: 'NightLoadDevice_Request',
    resultItem: 'NightLoadDevice_Result',
    device: 'shureflo',
    kind: 'owned-binary-request',
    requiresCapability: 'night-load-owner-v1',
  },
  goatCam: {
    stateItem: 'Goat_Plugs_Outlet1_Switch',
    requestItem: 'NightLoadDevice_Request',
    resultItem: 'NightLoadDevice_Result',
    device: 'goat-cam',
    kind: 'owned-binary-request',
    requiresCapability: 'night-load-owner-v1',
  },
  feedOnce: ['GoatFeeder_ManualRequest', 'action'],
  circulation: ['SouthOutlet_ManualRequest', 'safety-request'],
  override: {
    stateItem: 'OverrideSwitch',
    requestItem: 'NightLoadOverride_Request',
    resultItem: 'NightLoadOverride_Result',
    kind: 'policy-request',
    requiresCapability: 'night-load-owner-v1',
  },
  feederActuator: ['Goat_Plugs_Outlet2_Switch', 'status'],
  greywaterActuator: ['SouthOutlet_Outlet2_Switch', 'status'],
}
~~~

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T12A-1' -- \
  npm test -- tests/control-machine.test.js \
    -t '^\[RED:T12A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T12A-2' -- \
  npx playwright test tests/e2e/control-states.spec.js \
    --project=m9-browser --grep '^\[RED:T12A-2\]'
~~~

Expected: FAIL because Toggle is pointer-only/fire-and-forget, unknown values
become OFF, and correlation/outcome-unknown do not exist.

- [ ] **Implement five explicit primitives**

~~~js
export const CONTROL_PHASES = [
  'confirmed', 'unavailable', 'holding', 'pending',
  'failed', 'sent-unconfirmed', 'outcome-unknown',
];
~~~

holdAction shows progress and emits once after 600 ms for pointer, touch, Space,
or Enter. controlMachine records command start and confirms physical binary only
from a target-state provider event received later while Thing/channel are
ONLINE. HTTP 2xx is only pending.

Parse rule outcomes as { requestId, status, reason, at }, where status is
accepted, denied, running, complete, or failed. Only matching IDs resolve
pending. Offline/cache/unavailable state disables commands; nothing queues or
retries.

Night Load Override UI commands a generated requestId plus target through the
String `NightLoadOverride_Request`. Each owned-load control renders from its
provider state item but sends `{ requestId, device, target }` only through
`NightLoadDevice_Request` and correlates only `NightLoadDevice_Result`; it never
commands the provider item. Until Task 16 verifies those request/result items
and the shared owner, these controls remain status-only. Task 12 records
`night-load-owner-v1` as unverified; only Task 16 can flip it after live receipt
closure. Schedules continue to command only `OverrideSwitch`; the Task 16
orchestrator serializes override and
owned-device paths. Provider-confirmed Goat Cam state continues to drive the
existing downstream `FeederOverride` coupling.

`OwnedBinaryControl` accepts separate `stateItem`, `requestItem`, `resultItem`, and
`device` props. Its only write call uses `requestItem`; provider state is read-only.
`outcomeStore` retains its Task 8 one-record-per-control API; this task wires
correlated phases into it without reusing source/freshness timestamps as
outcome transitions.

- [ ] **Wire exact labels and ownership**

Relabel LED_living_room_1_Switch as Living Room 3. Show circadian policy
separately from LivingRoomCircadian_LastResult; OFF remains eligible when bulbs
degrade. An owned-load control is enabled only when
`night-load-owner-v1` is live-verified, its provider channel is ONLINE, the
owner-committed `OverrideSwitch` state is exactly OFF, and no override/device
transition or owner busy state exists. ON, NULL, UNDEF, stale, transition, or
busy fails closed. Use `Owned by Night Load Override` for ON and an explicit
unavailable/busy reason otherwise. Show the Goat Cam to `FeederOverride` side
effect. Keep feeder/greywater actuators status-only.

Owned-load, feed, circulation, and override actions require both a verified
live schema gate and
`releaseMode === 'full'`. `src/lib/releaseMode.js` reads the immutable build
define/manifest, defaults unknown/dev builds to `maintenance`, and refuses a
mode mismatch. Its capability table supports exactly `maintenance`,
`safe-compat`, and `full`: maintenance disables every command primitive;
safe-compat permits only the four non-owned light/circadian controls from Task
2; owned loads remain status-only. Full alone permits the verified request
catalog, while direct owned provider writes remain denied. Full mode never
bypasses provider/offline/owner-capability/ownership gates. Tests cover every
control/mode pair, stale release ID, every owner-state denial, and no provider
Item command.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/safe-controls.test.js tests/control-catalog.test.js \
  tests/control-outcome.test.js tests/control-machine.test.js \
  tests/release-mode.test.js tests/hold-action.test.js \
  tests/ui/typed-controls.test.js
npx playwright test tests/e2e/control-states.spec.js
node tools/qa/update-matrix.mjs --task 12 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add src/lib/controls/catalog.js src/lib/controls/outcome.js \
  src/lib/controls/outcomeStore.js src/lib/controls/controlMachine.js \
  src/lib/releaseMode.js src/lib/actions/holdAction.js src/lib/ui/BinaryControl.svelte \
  src/lib/ui/OwnedBinaryControl.svelte src/lib/ui/ActionControl.svelte src/lib/ui/SafetyRequest.svelte \
  src/lib/ui/StatusControl.svelte src/screens/Controls.svelte \
  src/screens/Earthship.svelte tests/control-catalog.test.js tests/control-outcome.test.js \
  tests/control-machine.test.js tests/release-mode.test.js \
  tests/hold-action.test.js tests/ui/typed-controls.test.js tests/safe-controls.test.js \
  tests/e2e/control-states.spec.js
git add -u src/lib/ui/Toggle.svelte
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: add safe typed household controls"
~~~

Expected: all typed states/holds/correlation paths pass and no UI source
directly commands a read-only actuator.

---

## Task 13: Build reversible OpenHAB tooling and repair current AQI

**Files:**

- Create: openhab/managed-resources.json
- Create: openhab/aqi/current-us-aqi.json
- Create: scripts/openhab-config.mjs
- Create: tests/openhab/rest-manifest.test.js
- Create: tests/openhab/rest-safety.test.js
- Create: tests/openhab/aqi-migration.test.js
- Create: tests/openhab/fixtures/systeminfo-5.2.0.json
- Create: tests/openhab/fixtures/aq-thing-before.json
- Create: tests/openhab/fixtures/aq-thing-desired.json
- Create: tests/openhab/fixtures/forecast-aqi-item.json
- Create: tests/openhab/fixtures/current-us-aqi-item.json
- Create: tests/openhab/fixtures/overview-safe.json
- Modify: docs/qa/ui-audit-matrix.csv

- [ ] **Write failing sanitizer, manifest, and no-command tests**

Test exact sanitizer projections:

~~~js
expect(sanitizeItem(raw)).toEqual(pick(raw, [
  'type', 'name', 'label', 'category', 'tags', 'groupNames',
]));
expect(sanitizeRule(raw)).not.toHaveProperty('status');
expect(sanitizeRule(raw)).not.toHaveProperty('editable');
~~~

The manifest test requires canonical sanitized JSON hashes,
original-existence flags, exact restore method/path/body, dependency order,
original rule-enabled state, and post-restore verification. Static safety tests
reject item-command POST, generic item-state PUT, rule `runnow`, unapproved
rule enable/disable, and every automatic retry of POST/PUT/DELETE. Bounded
GET-only polling is permitted only with a monotonic deadline. The sole state
update exception is the explicit Forecast AQI contamination migration described
below; it cannot accept another item name or body.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T13A-1' -- \
  npm test -- tests/openhab/rest-manifest.test.js \
    -t '^\[RED:T13A-1\]'
~~~

Expected: FAIL because the versioned resource manifest/tooling do not exist.

- [ ] **Implement snapshot/apply/verify/rollback modes**

Import `tools/openhab/auth.mjs` and load the exact protected environment on
every invocation. Use its `OPENHAB_TOKEN` as the Basic-auth username with an
empty password, but never log the token or Authorization header. Supported
endpoints are:

~~~text
GET /rest/systeminfo
GET /rest/persistence
GET /rest/persistence/items/{name}
GET /rest/things/{encodedUid}
PUT /rest/things/{encodedUid}/config
GET|PUT|DELETE /rest/items/{name}
PUT|DELETE /rest/items/{name}/metadata/{namespace}
GET|PUT|DELETE /rest/links/{itemName}/{encodedChannelUID}
GET|PUT|DELETE /rest/rules/{uid}
POST /rest/rules
POST /rest/rules/{uid}/enable
GET|PUT|DELETE /rest/ui/components/ui:page/{uid}
PUT /rest/items/Forecast_AQI/state
~~~

The CLI is exact and fail-closed:

```text
snapshot --subset <name> --out-root /tmp --activate-backup
verify --subset <name> --from-active --read-only
apply --subset <name> --from-active --mode <mode>
rollback --subset <name> --from-active --mode maintenance
reapply --subset <name> --from-active --mode <mode>
rehearse --subset <name> --from-active --mode maintenance
close-backup --subset <name> --from-active --terminal desired
close-backup --subset <name> --from-active --terminal unmutated
close-backup --subset <name> --from-active --terminal rolled-back
```

Named subsets are `aqi`, `feeder`, `greywater`, `override-graph`,
`circadian`, and `mainui-ownership`; the manifest defines their exact resource
members and dependency order. `snapshot --activate-backup` atomically writes a
non-secret receipt at `/tmp/earthship-ui-openhab-active/<subset>.json` with the
absolute backup directory, canonical manifest hash, OpenHAB version, and state
`open`. It refuses another open receipt. Every mutating command requires
`--from-active`, verifies that receipt and every backup hash, records an
append-only operation receipt, and rejects a subset/mode/resource mismatch.
`close-backup` requires an explicit terminal outcome. `desired` requires the
full desired-state verification and rollback rehearsal. `unmutated` requires an
operation log with zero mutating calls plus canonical live-equals-backup
verification. `rolled-back` requires a recorded rollback after mutation,
canonical live-equals-backup resource and enabled-state verification, safe
provider/load preconditions, and clean post-cursor logs. It records receipt
state `closed-<terminal>` and a checksum-bound, token-free `matrixEvidence`
summary in the same exact active receipt JSON; it never deletes evidence. Any
mismatch leaves the receipt open. Tests exercise every CLI form, snapshot-then-abort, partial apply,
permanent rollback, and close I/O failure, and prove no implicit latest
directory or caller-supplied restore body is accepted.

For every durable virtual request ledger, add a read-only persistence audit. It
requires the `jdbc` service through REST and exact Item coverage. If REST cannot
expose effective strategy selection, it may read and parse active
`/etc/openhab/persistence/*.persist` files after re-reading
`/etc/openhab/AGENTS.md`; it must never edit them. Require `everyChange` plus
`restoreOnStartup` coverage or leave the capability disabled. Tests use
sanitized fixtures and reject a service-name assumption, wildcard mismatch, or
write to persistence configuration/database files.

`POST /rest/rules/{uid}/enable` is available only in explicit `maintenance`
mode, with body exactly `true` or `false` and `Content-Type: text/plain`, for
UIDs named in the selected manifest subset. Execution still requires
contemporaneous user approval; default snapshot/verify/apply modes cannot call
it. `/runnow` is never allowed. The Forecast state endpoint is available only
in `aqi-contamination-cleanup` mode, item exactly `Forecast_AQI`, body exactly
`UNDEF`, and only after its no-command-consumer precondition passes.

Encode every complete UID path segment with `encodeURIComponent`, including
all colons and `#` in a channel UID; do not perform a one-character textual
replacement. Save backups under a caller-supplied `/tmp` directory. Snapshot metadata only from the embedded `metadata` object returned by
`GET /rest/items/{name}` because the namespace GET endpoint returns 405.
Sanitize item to type/name/label/category/tags/groupNames; metadata to
value/config/editable; rule without GET-only status/editable; page to
component/config/slots/uid/tags/props; and AQ Thing to its complete
configuration object only. Hash canonical key-sorted JSON.

Rollback deletes newly created resources in reverse order and restores existing
ones in Thing config, ONLINE/channel wait, item, metadata, link, rule, page
order, except where Tasks 15 and 16 define stricter active-graph transactions.
It restores each rule's original enabled state through the guarded maintenance
endpoint. The unsafe pre-audit Overview page is evidence only: MainUI rollback
stops at the Task 2 safe compatibility page. If a newly persisted Item creates
a JDBC `itemNNNN` table, record the item/table mapping as an expected audited
orphan; configuration rollback does not claim to remove or directly edit the
database table.

- [ ] **Run GREEN and commit the exact tool and manifest before live access**

~~~bash
set -euo pipefail
npm test -- tests/openhab/rest-manifest.test.js \
  tests/openhab/rest-safety.test.js tests/openhab/aqi-migration.test.js
npm test -- tests/aqi.test.js tests/weather-aqi-wiring.test.js
node tools/qa/update-matrix.mjs --task 13 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add openhab/managed-resources.json openhab/aqi/current-us-aqi.json \
  scripts/openhab-config.mjs tests/openhab/rest-manifest.test.js \
  tests/openhab/rest-safety.test.js tests/openhab/aqi-migration.test.js \
  tests/openhab/fixtures/systeminfo-5.2.0.json \
  tests/openhab/fixtures/aq-thing-before.json \
  tests/openhab/fixtures/aq-thing-desired.json \
  tests/openhab/fixtures/forecast-aqi-item.json \
  tests/openhab/fixtures/current-us-aqi-item.json \
  tests/openhab/fixtures/overview-safe.json docs/qa/ui-audit-matrix.csv
git commit -m "feat: version reversible openHAB AQI integration"
test -z "$(git status --short)"
~~~

Expected: the complete exact-REST safety/tooling suite and AQI adapters pass
from the committed sources, automated rows are `blocked-live`, and the live
transaction starts only from this clean tested HEAD.

- [ ] **Snapshot the exact live resources and verify live version**

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs snapshot --subset aqi \
  --out-root /tmp --activate-backup
node scripts/openhab-config.mjs verify --subset aqi \
  --from-active --read-only
~~~

Expected: OpenHAB reports 5.2.0 at execution time, every current resource is
captured or explicitly marked absent, and every canonical hash rechecks. The
version/system-info compatibility check occurs before atomic receipt
publication. If the live version changed, publish no receipt, stop, update the
fixtures/tool, rerun the complete pre-live GREEN gate, commit that exact new
source, and restart snapshot from the new clean HEAD; never patch fixtures in an
open live transaction.

- [ ] **Rehearse real resource rollback before the AQI mutation**

Create a unique unlinked String
`EarthshipUI_RollbackProbe_<stamp>` plus inert metadata, verify its hashes, and
delete it back to 404. Create a triggerless no-op rule
`hex_earthshipui_rollback_probe_<stamp>`, disable/enable it only through the
approved maintenance gate, then delete it back to 404. Delete and restore the
existing non-actuating `Forecast_AQI` hourly link and verify the exact restored
hash. Use an exact no-op PUT/GET of the already-safe Overview page. Require
clean new logs and preserve evidence of every absent/restored state; no state
update or physical command occurs.

Run the exact receipt-bound rehearsal:

```bash
set -euo pipefail
node scripts/openhab-config.mjs rehearse --subset aqi \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset aqi \
  --from-active --read-only
```

- [ ] **Apply the AQI Thing/item/link migration**

The desired Thing configuration preserves all unrelated keys and changes:

~~~json
{
  "current": true,
  "airQualityIndicatorsAsNumber": true,
  "airQualityIndicatorsAsString": true,
  "hourlyTimeSeries": true
}
~~~

Run:

```bash
set -euo pipefail
node scripts/openhab-config.mjs apply --subset aqi \
  --from-active --mode maintenance
```

The command applies the complete configuration to
openmeteo:air-quality:local:aq, polls until ONLINE, and wait for exact dynamic
channel openmeteo:air-quality:local:aq:current#us-aqi. Then PUT a Number item:

~~~json
{
  "type": "Number",
  "name": "Current_US_AQI",
  "label": "Current US AQI",
  "category": "airquality",
  "tags": ["Measurement"],
  "groupNames": []
}
~~~

Create the exact link. Retain `Forecast_AQI` and its hourly string link only
as categorical forecast data. Prove no UI or rule commands it, then require a
provider-produced `stateupdated` and a value other than `REFRESH` for two
bounded provider cycles. If `REFRESH` remains, run exactly once:

```bash
set -euo pipefail
node scripts/openhab-config.mjs cleanup-forecast --subset aqi \
  --from-active --mode aqi-contamination-cleanup
```

That mode uses only the allowlisted `PUT /rest/items/Forecast_AQI/state` with
`text/plain` body `UNDEF`, then waits
for the next provider-produced `stateupdated` to supply real hourly forecast
data. Never send an Item command, synthesize forecast content, retry the PUT,
or restore the contaminated `REFRESH` runtime state. If the provider still
does not update, stop and investigate rather than claiming repair.

- [ ] **Read back numeric freshness evidence and prove AQI round-trip rollback**

Require:

- Thing ONLINE;
- dynamic current channel present;
- item type Number;
- exact link;
- numeric non-negative state;
- lastStateUpdate or stateupdated receive time;
- correct Home/Weather adapter classification; and
- no new ERROR/Exception log lines.

After the first successful desired-state verification, roll the AQ Thing,
`Current_US_AQI` item/metadata/link configuration back to the exact pre-change
snapshot, verify every canonical hash and clean logs, then reapply the desired
configuration and repeat numeric/provider freshness verification. This path is
non-actuating and is the required real configuration rollback rehearsal; a
no-op restore does not satisfy it. Record any expected JDBC orphan table
created by the temporary Number Item lifecycle. Execute the round trip and
close only after desired state is reverified:

```bash
set -euo pipefail
node scripts/openhab-config.mjs rollback --subset aqi \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset aqi \
  --from-active --read-only
node scripts/openhab-config.mjs reapply --subset aqi \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset aqi \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset aqi \
  --from-active --terminal desired
```

If apply, rollback-rehearsal, reapply, or final verification fails after a
mutation, stop that fail-fast block and run only the recovery transaction:

```bash
set -euo pipefail
node scripts/openhab-config.mjs rollback --subset aqi \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset aqi \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset aqi \
  --from-active --terminal rolled-back
```

A failed recovery leaves the receipt open and blocks later live tasks. Before
any mutation, an abort may close `unmutated` only after the exact zero-write and
live-equals-backup proof.

- [ ] **Re-run GREEN and commit only checksum-bound live evidence**

~~~bash
set -euo pipefail
npm test -- tests/openhab/rest-manifest.test.js \
  tests/openhab/rest-safety.test.js tests/openhab/aqi-migration.test.js
npm test -- tests/aqi.test.js tests/weather-aqi-wiring.test.js
node tools/qa/update-matrix.mjs --task 13 --phase live \
  --receipt /tmp/earthship-ui-openhab-active/aqi.json \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add docs/qa/ui-audit-matrix.csv
git commit -m "docs: record live AQI migration evidence"
test -z "$(git status --short)"
~~~

Expected: repository tests pass, live Current_US_AQI is numeric/current, and
the restore manifest is checksum-verified under /tmp.

---

## Task 14: Correlate manual feeder requests without breaking payment/runnow callers

**Files:**

- Create: openhab/rules/feeder-timer.js
- Modify: openhab/managed-resources.json
- Create: tests/openhab/rule-harness.js
- Create: tests/openhab/feeder-rule.test.js
- Create: tests/openhab/feeder-compatibility.test.js
- Create: tests/openhab/feeder-ingress.test.js
- Create: tests/openhab/request-ledger.test.js
- Create: scripts/feeder-ingress.mjs
- Modify: scripts/openhab-config.mjs
- Modify: docs/qa/ui-audit-matrix.csv
- Modify: `src/lib/controls/catalog.js`

- [ ] **Capture and write failing exact-rule tests**

The harness executes the exact script text embedded into the deployed rule DTO.
Test manual success, five-second cooldown, busy/concurrent IDs, duplicate ID,
exception cleanup, unrelated `GoatFeedings` change, exact ON → one-second
timer → OFF/counter/result command order, redundant expire-driven OFF, outlet
OFF, and matching result phases. Reload/restart the rule between two identical
manual request IDs and prove the second request never pulses.

Compatibility tests prove UID 88bd9ec4de and triggerless runnow/payment
invocations still use the same cooldown/busy/pulse/counter owner without
requiring a ManualResult. A dedicated test proves OpenHAB `runnow` still
executes a disabled rule, so no implementation or runbook may treat disable as
an ingress lock. This preserves current external callers in:

- /home/sat/bin/middleware/main.py
- /home/sat/bin/fastapi_ap.py
- LNbits lightning_goats/services/openhab.py

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T14A-1' -- \
  npm test -- tests/openhab/feeder-rule.test.js \
    -t '^\[RED:T14A-1\]'
~~~

Expected: FAIL because manual request/result items and the versioned canonical
rule source do not exist.

- [ ] **Implement one canonical feeder owner**

Create unlinked String items `GoatFeeder_ManualRequest` and
`GoatFeeder_ManualResult`; set request metadata `autoupdate=false`. The request
Item state doubles as the bounded durable ledger: browser input is a command
and autoupdate is false, so incoming JSON never overwrites state. Initial
`NULL`/`UNDEF` is empty only when JDBC history proves there has never been a
ledger; missing restore with prior history fails closed. Reject corrupt or
oversize state. Before any accepted actuation, post the canonical newest-32
checkpoint, explicitly persist it to JDBC, and read-verify the same request ID;
then persist the terminal outcome. Trigger only on received commands so ledger
updates cannot retrigger the rule. Tests reject a third ledger Item, mutable
operational metadata, unbounded state, and actuation before accepted-ledger
persistence. Add a received command trigger to existing rule
UID `88bd9ec4de` while keeping `runnow` valid. Snapshot, preserve, and hash the
live actuator's `expire=0h0m1s,command=OFF` metadata as a redundant OFF
backstop.

~~~js
function result(requestId, status, reason, at = time.ZonedDateTime.now()) {
  items.getItem('GoatFeeder_ManualResult').postUpdate(JSON.stringify({
    requestId, status, reason, at: at.toString(),
  }));
}
~~~

Manual flow emits accepted then running, commands ON, and schedules one
one-second callback. That callback commands OFF first, confirms the same
invocation incremented `GoatFeedings`, emits complete or failed, and in its own
`finally` commands idempotent OFF and clears busy. An exception before the timer
exists also commands OFF and clears busy. There is no outer normal-path
`finally` that would end the pulse immediately. Cooldown and busy emit denied.
`cache.shared` serializes all invocation sources; the persisted request-Item
state, not volatile cache, prevents a duplicate ID after reload. Triggerless
runnow/payment executions use the same machinery but
do not require or forge a correlated result.

- [ ] **Run GREEN before live apply**

~~~bash
set -euo pipefail
npm test -- tests/openhab/feeder-rule.test.js \
  tests/openhab/feeder-compatibility.test.js \
  tests/openhab/feeder-ingress.test.js tests/openhab/request-ledger.test.js \
  tests/openhab/rest-safety.test.js
node tools/qa/update-matrix.mjs --task 14 --phase automated \
  docs/qa/ui-audit-matrix.csv
~~~

Expected: all exact-script simulations pass; no physical outlet is contacted.

- [ ] **Apply a receipt-bound, disabled feeder transaction**

Obtain contemporaneous approval for a brief feeder API maintenance window; no
feed is authorized. `scripts/feeder-ingress.mjs` must first capture into the
exact `/tmp/earthship-ui-feeder-ingress-active.json` receipt whether
`lightning_goats.service` and `lnbits.service` exist in user or system scope,
their enabled/ActiveState/SubState values, owning PIDs/command hashes,
listeners on 3002/8090, the two known Python caller paths, and established
non-loopback OpenHAB API connections. It refuses scope ambiguity, an unmapped
process, or an existing open receipt and never kills a PID directly.

Only with separate approval may `quiesce --allow-stop-known-services` drain and
stop captured-active known units. It records an acyclic dependency graph, stops
dependents before their dependencies in reverse topological order, waits for
mapped processes/listeners/connections to clear, and records every transition.
A unit that was inactive remains inactive. Require an operator commitment that
no ad-hoc `runnow` will be sent. If quiescence cannot be proven, do not proceed
to OpenHAB. `quiesce` attempts an internal compensating restore before it
returns failure; any interruption leaves the ingress receipt open for the exact
pre-OpenHAB recovery below. Tests inject partial stop/start failures,
verify-quiescent failure, interruption at every transition, stale PIDs, port
reuse, dependency cycles, and originally inactive units. Exact ordered-call
tests prove reverse-topological stop, forward-topological start, dependency
readiness before a dependent starts, and either original caller state is
restored or explicit operator action remains.

Snapshot, verify, and apply the exact OpenHAB subset only after the durable
ingress receipt proves quiescence:

```bash
set -euo pipefail
node scripts/feeder-ingress.mjs capture \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs quiesce \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --allow-stop-known-services
node scripts/feeder-ingress.mjs verify-quiescent \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs snapshot --subset feeder \
  --out-root /tmp --activate-backup \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs bind-openhab \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --openhab-receipt /tmp/earthship-ui-openhab-active/feeder.json
node scripts/openhab-config.mjs verify --subset feeder \
  --from-active --read-only \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs apply --subset feeder \
  --from-active --mode maintenance \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
```

Before an OpenHAB receipt exists, a failed or interrupted quiesce and an atomic
snapshot failure use no OpenHAB receipt. After confirming no
`openhab-config.mjs` process remains and the exact feeder receipt path is absent,
run only:

```bash
set -euo pipefail
node scripts/feeder-ingress.mjs restore-pre-openhab \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --assert-openhab-receipt-absent \
  /tmp/earthship-ui-openhab-active/feeder.json
node scripts/feeder-ingress.mjs verify-restored \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs close \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --terminal restored-no-openhab
```

`restore-pre-openhab` refuses a bound ingress receipt or any present OpenHAB
receipt, restores only units captured active, preserves captured-inactive units,
and verifies exact service/process/listener state. A failed pre-OpenHAB restore
leaves the ingress receipt open with exact operator actions.

The snapshot receives the ingress receipt and atomically publishes the OpenHAB
receipt with its generation and checksum. `bind-openhab` validates that binding
and atomically writes the reciprocal OpenHAB receipt generation/checksum into
the ingress receipt. It is idempotent for the exact pair and refuses any other
pair. Tests interrupt immediately after snapshot publication and at every bind
write/fsync/rename edge, then prove the same bind command either completes the
exact pair or leaves both receipts open with operator action.

If the OpenHAB receipt exists but bind or the first read-only verify fails before
mutation, never use `restore-pre-openhab`. Keep callers quiescent, wait until
read-only access is healthy, and run this exact idempotent unmutated-recovery
block. `verify` must prove receipt write count zero and live equality with the
backup before either receipt can close:

```bash
set -euo pipefail
node scripts/feeder-ingress.mjs bind-openhab \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --openhab-receipt /tmp/earthship-ui-openhab-active/feeder.json
node scripts/openhab-config.mjs verify --subset feeder \
  --from-active --read-only \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs close-backup --subset feeder \
  --from-active --terminal unmutated \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs restore \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --openhab-receipt /tmp/earthship-ui-openhab-active/feeder.json
node scripts/feeder-ingress.mjs verify-restored \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs close \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --terminal restored-unmutated
```

If the exact bind, zero-write/live-equality proof, or restore cannot complete,
leave both receipts open and callers quiescent; print the same retry command and
current receipt generations as operator action. Never infer `unmutated` from a
failed snapshot/verify or restore callers against an unbound receipt.

The feeder-specific apply phase must require the old rule IDLE, provider
`Goat_Plugs_Outlet2_Switch === OFF`, no busy marker, and no just-started
feeding. It then disables UID `88bd9ec4de` before any PUT and rechecks rule
IDLE, counter stability, and provider OFF for at least two 1-second expire
periods. Disable suppresses triggers but is explicitly not the `runnow` lock;
the independently verified caller quiescence remains mandatory through the
entire apply/rehearse process. If any request appears after the ingress receipt,
the preserved actuator `expire=0h0m1s,command=OFF` backstop must return the
provider to OFF, but the transaction aborts and does not replace the rule. Never disable or replace while the provider
is ON.

After `bind-openhab`, feeder `apply`, `rehearse`, final `verify`, rollback, and
close refuse to run without the exact checksum-valid `--ingress-receipt`.
Inside apply/rehearse/rollback, the CLI continuously checks unit/process/
listener/connection state, rule execution events, counter, provider state, and
the receipt generation before and after every transition. Any ingress drift or
UID invocation aborts before the next PUT/enable and is failure-injected in
tests; the one-second OFF backstop remains the only automatic physical safety.

`re-quiesce --allow-stop-known-services` is the only recovery entry after such
drift. It preserves the same receipt generation, drains and stops only captured
known units that unexpectedly became active, in reverse topological order, and
re-proves no mapped process/listener/connection or rule execution remains. It
never kills a PID, follows an unknown process, or advances OpenHAB. An unmapped
caller, ad-hoc `runnow`, provider ON, counter movement, receipt mismatch, or
failed stop leaves both receipts open and emits exact operator action; rollback
does not begin until `re-quiesce` and `verify-quiescent` both pass. Tests inject
each drift before and after every OpenHAB transition and prove rollback cannot
start while ingress is live.

With ingress locked, `apply` PUTs items/metadata and the candidate rule while
it remains disabled, hash-readbacks, and exits with the candidate still
disabled. The subsequent single `rehearse` process keeps ingress disabled for
its entire old-disabled → new-disabled round trip, then enables the new rule
exactly once to the captured original state. Require rule IDLE, provider OFF,
unchanged counter after enable, request state still initial `NULL`/`UNDEF` or
a valid canonical bounded ledger, exact JDBC/restore coverage, exact expire
backstop, and clean post-cursor logs. No `runnow`, ManualRequest, external state
PUT, or actuator command is a proving action.

Run and close the exact receipt only after that atomic disabled rehearsal and
final verification. Recheck the ingress receipt immediately before and after
this one process:

```bash
set -euo pipefail
node scripts/feeder-ingress.mjs verify-quiescent \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs rehearse --subset feeder \
  --from-active --mode maintenance \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs verify-quiescent \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs verify --subset feeder \
  --from-active --read-only \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs verify-quiescent \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs close-backup --subset feeder \
  --from-active --terminal desired \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs restore \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --openhab-receipt /tmp/earthship-ui-openhab-active/feeder.json
node scripts/feeder-ingress.mjs verify-restored \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs close \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json --terminal restored
node tools/qa/update-matrix.mjs --task 14 --phase live \
  --receipt /tmp/earthship-ui-openhab-active/feeder.json \
  --adjacent-receipt /tmp/earthship-ui-feeder-ingress-active.json \
  docs/qa/ui-audit-matrix.csv
```

Restore starts only units captured active, with dependencies before dependents
in forward topological order. Before starting each dependent, it proves every
captured-active dependency has reached its expected enabled/ActiveState/SubState,
mapped process/listener, application readiness endpoint, and OpenHAB
connectivity. Captured inactive units stay inactive. A partial restore fails
closed with exact operator actions and does not advance the matrix or enable the
UI capability.

If snapshot/bind/verify fails before mutation, use only the exact idempotent
unmutated-recovery block above. If apply/rehearse/final verify fails after
mutation, run this separate fail-fast recovery block before restoring callers:

```bash
set -euo pipefail
node scripts/feeder-ingress.mjs re-quiesce \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --allow-stop-known-services
node scripts/feeder-ingress.mjs verify-quiescent \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs rollback --subset feeder \
  --from-active --mode maintenance \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs verify --subset feeder \
  --from-active --read-only \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/openhab-config.mjs close-backup --subset feeder \
  --from-active --terminal rolled-back \
  --ingress-receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs restore \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json \
  --openhab-receipt /tmp/earthship-ui-openhab-active/feeder.json
node scripts/feeder-ingress.mjs verify-restored \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json
node scripts/feeder-ingress.mjs close \
  --receipt /tmp/earthship-ui-feeder-ingress-active.json --terminal restored
```

If old/new feeder-rule health or rollback cannot be proved, keep callers
quiescent and emit operator action instead of restoring them into an unknown
owner. If a live pulse test is desired, stop and obtain contemporaneous user
approval for that one feeder action.

- [ ] **Enable the UI action only after the live schema gate**

Change the control catalog capability from unverified to ready only when both
String items, request `autoupdate=false`, request-state ledger parser and
newest-32 bound, JDBC every-change/restore-on-startup coverage, accepted-record
persist/readback gate, exact expire metadata, rule hashes, and healthy rule
status are present. Initial `NULL`/`UNDEF` is allowed only when persistence
history proves no earlier request; corrupt or unrestored state fails closed. The actuator remains status-only.

- [ ] **Commit**

~~~bash
set -euo pipefail
git diff --check
git add openhab/rules/feeder-timer.js openhab/managed-resources.json \
  scripts/openhab-config.mjs scripts/feeder-ingress.mjs \
  tests/openhab/feeder-rule.test.js tests/openhab/feeder-compatibility.test.js \
  tests/openhab/feeder-ingress.test.js tests/openhab/request-ledger.test.js \
  tests/openhab/rule-harness.js src/lib/controls/catalog.js \
  docs/qa/ui-audit-matrix.csv
git commit -m "feat: correlate safe feeder requests"
test -z "$(git status --short)"
~~~

Expected: all existing external runnow callers remain compatible, the UI can
request by ID, and no household surface commands the feeder relay directly.

---

## Task 15: Add correlated greywater requests without weakening hydrology or safety

**Files:**

- Create: openhab/rules/southoutlet-cycle.js
- Modify: openhab/managed-resources.json
- Create: tests/openhab/greywater-rule.test.js
- Create: tests/openhab/greywater-recovery.test.js
- Modify: tests/openhab/request-ledger.test.js
- Modify: scripts/openhab-config.mjs
- Modify: src/lib/controls/catalog.js
- Modify: docs/qa/ui-audit-matrix.csv

- [ ] **Write failing gate, timing, collision, and recovery tests**

Execute the exact deployed source. Cover first-denial precedence:

1. already running/request in flight;
2. BMS communication/freshness;
3. valid SoC and 40-60 V voltage;
4. low-SoC cutoff;
5. cooldown;
6. 230-minute start-to-start hydrology constraint;
7. current curtailment/energy-availability policy; and
8. existing 10-minute run/force-off prerequisites.

Also test duplicate IDs, concurrent IDs, already-running, cron/request
collision, 24-hour aerobic fallback, restart/orphan recovery, exception
cleanup, current single-bank curtailment-only behavior, and separate automatic
versus manual timestamps. Reload/restart between duplicate IDs and prove the
persisted ledger prevents a second cycle.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T15A-1' -- \
  npm test -- tests/openhab/greywater-rule.test.js \
    -t '^\[RED:T15A-1\]'
~~~

Expected: FAIL because manual correlation and persistent all-origin cycle
timestamps do not exist.

- [ ] **Implement the exact timing and outcome contracts**

Create unlinked String items `SouthOutlet_ManualRequest` and
`SouthOutlet_ManualResult` with request `autoupdate=false`. As in Task 14, the
request Item state is the canonical newest-32 request/outcome ledger. Incoming
commands do not change it; initial `NULL`/`UNDEF` is empty only when JDBC history
proves no prior ledger; corrupt, unrestored, or oversize state fails closed.
Before a manual cycle, post, explicitly persist, and read-verify the accepted
checkpoint; persist the terminal outcome afterward. Verify JDBC every-change
and restore-on-startup coverage. Tests reject a third ledger Item, mutable
operational metadata, unbounded state, and a cycle before accepted-ledger
persistence. Create DateTime items
`SouthOutlet_LastCycleStart` and `SouthOutlet_LastCycle`.

- LastCycleStart is posted at the start of every automatic/manual cycle and is
  the restart-safe 230-minute start-to-start authority.
- LastCycle is posted only after a completed cycle of any origin and is the UI
  truth.
- LastAutoRun remains automatic-only for compatibility.
- On first rule evaluation after migration, seed LastCycleStart logically from
  LastAutoRun before gate evaluation; persist the seed without starting or
  stopping equipment.

Manual accepted flow emits accepted, running, then complete/failed. Denied
reports the first gate. Duplicate IDs return the ledger's prior outcome without
a cycle. Volatile `cache.shared` is only serialization state; persisted request-Item state is the
durable idempotency authority. Every path clears busy/request bookkeeping in
`finally`. Preserve the live
10-minute run, 230-minute gap, 24-hour fallback, freshness/BMS fail-closed
chain, and interim curtailment-only thresholds exactly.

- [ ] **Run GREEN before live apply**

~~~bash
set -euo pipefail
npm test -- tests/openhab/greywater-rule.test.js \
  tests/openhab/greywater-recovery.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/rest-safety.test.js
node tools/qa/update-matrix.mjs --task 15 --phase automated \
  docs/qa/ui-audit-matrix.csv
~~~

Expected: exact-script simulations pass and prove no gate/timer regression.

- [ ] **Apply only as a disabled, attended maintenance transaction**

Record the known runbook drift before mutation: live/operator-approved OpenHAB
is 5.2.0 and the rule runs a ten-minute cycle, while
`/etc/openhab/AGENTS.md` still says 5.1.4 and describes a protected five-minute
cycle. Re-read that policy, cite this explicit approved exception in the
backup/evidence, and never change the live cycle back to five minutes.

Obtain contemporaneous user confirmation before touching the active rule. The
observer must be able to see the pump, and approval authorizes one emergency OFF
only if provider state shows an unexpected start. No manual request is sent.
Snapshot the exact subset and preflight state:

```bash
set -euo pipefail
node scripts/openhab-config.mjs snapshot --subset greywater \
  --out-root /tmp --activate-backup
node scripts/openhab-config.mjs verify --subset greywater \
  --from-active --read-only
node scripts/openhab-config.mjs apply --subset greywater \
  --from-active --mode maintenance
```

Before apply, capture current time, every gate input, `LastAutoRun`,
`LastCycleStart`, `SouthOutlet_AutoStatus`, and provider outlet state. Execute
the exact candidate evaluator locally and require a non-start result. Also
require provider `SouthOutlet_Outlet2_Switch === OFF`, AutoStatus not
`reason=cycle_started`, and no just-started timestamp. Rule IDLE alone is not
sufficient because its ten-minute timer can outlive rule execution.

The greywater-specific apply must disable `hex_southoutlet_cycle` before any
PUT, then immediately recheck outlet/status/timestamps and rerun the local
evaluator. If a trigger raced and provider state became ON, keep the rule
disabled, use the one pre-authorized emergency OFF, require provider-confirmed
OFF, and restore the old DTO disabled before returning it to its captured state.
If hashes/health fail while provider remains OFF, disable/restore without
sending OFF; approval for an unexpected start is not authority for an
unnecessary command.

When the disabled recheck is quiet, `apply` PUTs and hash-verifies the
candidate, then exits with it still disabled. The subsequent single `rehearse`
process keeps the rule disabled through old-disabled → new-disabled restore and
reapply, then enables the new rule exactly once to the captured original state.
Wait through one bounded safe cron evaluation, whose local evaluator was already
proven non-starting, to verify the LastCycleStart migration seed. Require
provider OFF, stable AutoStatus/timestamps, initial `NULL`/`UNDEF` with no
history or a valid canonical bounded request-state ledger, accepted-record
persist/readback gate, and registered JDBC every-change/restore-on-startup
coverage for the request ledger, LastCycleStart, and LastCycle. Clean
post-cursor logs are mandatory; missing proof rolls back and leaves capability
unverified.

Run final receipt checks and close only after that atomic disabled rehearsal and
final health gate:

```bash
set -euo pipefail
node scripts/openhab-config.mjs rehearse --subset greywater \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset greywater \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset greywater \
  --from-active --terminal desired
node tools/qa/update-matrix.mjs --task 15 --phase live \
  --receipt /tmp/earthship-ui-openhab-active/greywater.json \
  docs/qa/ui-audit-matrix.csv
```

If apply, rehearsal, or final verification fails after any mutation, run the
separate fail-fast rollback block. Use the pre-authorized emergency OFF only if
provider readback is unexpectedly ON; otherwise rollback is configuration-only:

```bash
set -euo pipefail
node scripts/openhab-config.mjs rollback --subset greywater \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset greywater \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset greywater \
  --from-active --terminal rolled-back
```

A failed rollback keeps the receipt open, the rule disabled when safe, and the
UI capability unverified. A pre-mutation abort closes `unmutated` only after
zero-write and live-equals-backup proof.

- [ ] **Enable the UI request only after live verification and commit**

~~~bash
set -euo pipefail
git diff --check
git add openhab/rules/southoutlet-cycle.js openhab/managed-resources.json \
  scripts/openhab-config.mjs tests/openhab/greywater-rule.test.js \
  tests/openhab/greywater-recovery.test.js tests/openhab/request-ledger.test.js \
  src/lib/controls/catalog.js docs/qa/ui-audit-matrix.csv
git commit -m "feat: add safety-gated greywater requests"
test -z "$(git status --short)"
~~~

Expected: the UI can submit only a correlated safety request, the actuator is
read-only, and existing automatic hydrology/safety behavior is unchanged.

---

## Task 16: Consolidate override orchestration, preserve Goat Cam coupling, and audit circadian readback

**Files:**

- Create: `openhab/rules/night-load-override.js`
- Create: `openhab/rules/living-room-circadian.js`
- Create: `openhab/rules/override-schedule-on.js`
- Create: `openhab/rules/override-schedule-off.js`
- Create: `openhab/rules/goat-cam-coupling-on.js`
- Create: `openhab/rules/goat-cam-coupling-off.js`
- Modify: `openhab/managed-resources.json`
- Create: `tests/openhab/night-load-override-rule.test.js`
- Create: `tests/openhab/override-trace.test.js`
- Create: `tests/openhab/owned-load-race.test.js`
- Modify: `tests/openhab/request-ledger.test.js`
- Create: `tests/openhab/circadian-rule.test.js`
- Create: `tests/openhab/provider-readback.test.js`
- Create: `tests/openhab/mainui-ownership.test.js`
- Create: `openhab/mainui/overview-ownership-patch.json`
- Create: `openhab/mainui/earthship-ownership-patch.json`
- Create: `openhab/mainui/page-fc7fed510c-ownership-patch.json`
- Create: `openhab/mainui/page-69e95753c4-ownership-patch.json`
- Modify: `scripts/openhab-config.mjs`
- Modify: `src/lib/controls/catalog.js`
- Modify: `src/lib/releaseMode.js`
- Modify: `tests/control-catalog.test.js`
- Modify: `tests/release-mode.test.js`
- Modify: `tests/proxy-auth.test.js`
- Modify: `tests/ui/typed-controls.test.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Activate a zero-write maintenance release before graph work**

Before writing or applying Task 16 OpenHAB changes, require the Task 15 commit
and a clean worktree. Build `pregraph-maintenance-<HEAD>` from that exact source
in `maintenance` mode with verified reuse, activate it, restart both HTTP/HTTPS
services, and verify the manifest and zero-write proxy on both origins:

~~~bash
set -euo pipefail
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
MAINT_ID="pregraph-maintenance-$BASE"
RELEASE_ID="$MAINT_ID" RELEASE_MODE=maintenance \
  node tools/release/build.mjs --reuse-verified
node tools/release/activate.mjs "$MAINT_ID"
systemctl --user restart earthship-ui-preview.service earthship-ui-pwa.service
curl -fsS http://192.168.1.161:5190/release.json \
  -o /tmp/earthship-ui-http-release.json
curl --cacert /home/sat/.config/earthship-ui/tls/root-ca.crt \
  -fsS https://192.168.1.161:5192/release.json \
  -o /tmp/earthship-ui-pwa-release.json
jq -e --arg id "$MAINT_ID" \
  '.releaseId == $id and .releaseMode == "maintenance"' \
  /tmp/earthship-ui-http-release.json
jq -e --arg id "$MAINT_ID" \
  '.releaseId == $id and .releaseMode == "maintenance"' \
  /tmp/earthship-ui-pwa-release.json
node tools/release/verify-policy.mjs --release "$MAINT_ID" \
  --expect-mode maintenance
~~~

The synthetic forwarding-counter verifier proves valid-header writes are denied
without risking a household Item; production checks remain read-only. Verify the
active symlink still resolves to `MAINT_ID`, both service processes resolve
that release-owned server, and old tabs carry a fenced release ID. From this
point until the post-graph floor below is verified, `MAINT_ID` is the sole UI
rollback release. Never reactivate the Task 2 `safe-compat` release after the
first override-graph mutation.

- [ ] **Write failing exact ownership, race, trace, and circadian tests**

The target matrix remains exact:

~~~js
expect(targetsForOverride(true)).toEqual({
  Dish_Washer_Power: "OFF",
  ShurefloPump_Power: "OFF",
  Goat_Plugs_Outlet1_Switch: "OFF",
});
expect(targetsForOverride(false)).toEqual({
  ShurefloPump_Power: "ON",
});
~~~

Test repeated same-state idempotence, malformed/oversize/unknown requests,
duplicate IDs across rule reload, manual and schedule trace equivalence, partial
provider failures, and no false complete. Race tests cover both device-first and
override-first orders, pending-device supersession, late provider events from a
superseded generation, claim-before-command, receipt-before-release, OFF failure
remaining ON, NULL/UNDEF/transition/busy denial, synthetic schedule IDs,
restart recovery of accepted/running ledger entries, and no false complete
before committed OFF. A manual override must issue zero `OverrideSwitch`
commands and execute one matrix. Static tests prove only
`hex_night_load_override` can command the three provider Items and every proxy
mode denies direct writes without upstream forwarding.

Version and execute the exact source of coupling UIDs `3e8f265498` and
`GoatCamOff`. Preserve the approved direction exactly: provider-confirmed Goat
Cam ON clears `FeederOverride`, while provider-confirmed Goat Cam OFF sets it.
Assert the owner never commands `FeederOverride`; coupling rules never command
Goat Cam or `NightLoadDevice_Request`; override OFF leaves Goat Cam unchanged;
and each real Goat provider transition produces exactly one existing downstream
policy update regardless of override mode.

Circadian tests require the exact three-bulb mapping, `kasa --type bulb`,
bounded backoff, no flapping, disabled/healthy/degraded/failed LastResult, OFF
eligibility during bulb degradation, and ON blocked only when the rule/enable
item itself is unavailable. LastResult contains only normalized health, target
bucket, offline-bulb set, and backoff state/reason, never raw elevation,
countdown, or a per-run timestamp. Advance elevation and backoff countdown
across multiple five-minute triggers while normalized fields stay equal and
require zero diagnostic posts; only a normalized transition may post.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T16A-1' -- \
  npm test -- tests/openhab/night-load-override-rule.test.js \
    -t '^\[RED:T16A-1\]'
~~~

Expected: FAIL because owned loads still have direct command paths,
`OverrideSwitch` cannot carry a request ID, device-specific rules can race, and
no versioned shared owner exists.

- [ ] **Implement one serialized owner for override and owned devices**

Create unlinked String pairs `NightLoadOverride_Request` /
`NightLoadOverride_Result` and `NightLoadDevice_Request` /
`NightLoadDevice_Result`. Set both request Items and existing `OverrideSwitch`
to exact `autoupdate=false`. Only each request Item state is a canonical
newest-32 durable ledger; each result Item holds the latest single outcome.
Verify JDBC every-change and restore-on-startup coverage for both request
ledgers and `OverrideSwitch`. A NULL/UNDEF request ledger is initial only when
JDBC history proves no earlier request; corrupt, unrestored, or oversize state
fails closed. Persist and read-verify an accepted checkpoint before any physical
command and persist every terminal checkpoint.

Override requests are `{ requestId, target }`. Device requests are
`{ requestId, device, target }` with exact devices `dishwasher`, `shureflo`, and
`goat-cam`, and targets ON/OFF. Override results are
`{ requestId, target, status, reason, at, providerStates }`; device results are
`{ requestId, device, target, status, reason, at, providerState }`. Reject
malformed, oversize, unknown-device, invalid-target, and duplicate-ID requests
before actuation. The full proxy can write only request Items; every mode denies
direct browser writes to `OverrideSwitch` and the three provider state Items.

`OverrideSwitch` is owner-committed policy state, not provider readback.
Schedules `1f692c798b` and `b1501047a9` command it, but autoupdate false prevents
speculative state change. On each received schedule/external policy command the
owner creates a unique synthetic ID
`override-switch:<target>:<event-time>:<sequence>`, carries it through the same
trace/result schema, and persists its terminal diagnostic outcome; it never
pretends to know which source emitted the command. A manual correlated request
calls the same transition
function directly and never commands `OverrideSwitch`; the owner uses
`postUpdate` for visible state. This removes the ambiguous command echo and
double-matrix path.

Every request, schedule command, provider event, and timeout enters one
serialized owner reducer guarded by one `cache.shared` lock. Never hold the lock
while waiting for a timer/provider event; callbacks reacquire it and carry a
generation ID. Never invoke the owner through `runnow`. On restart, initialize
only from a restored valid `OverrideSwitch` ON/OFF state; NULL/UNDEF leaves
ownership unknown and denies device requests. For the one initial cutover only,
if the current state is valid and its exact owned-load matrix passes but JDBC has
no prior row, final candidate activation may postUpdate the same captured value
and explicitly persist/read-verify it before arming schedules. This
non-actuating seed cannot change state or command a load; any mismatch aborts.
Afterward, missing restore always fails closed. Before accepting a new event on
startup, scan both restored request ledgers. Mark every `accepted` or `running`
entry `failed` with reason `restart-uncertain`, persist/read-verify that recovery
and the matching result, and tombstone its generation so late provider events
are ignored. `release-ready` is not a status: it is exactly a `running` entry
with `reason: release-ready`, so this scan cannot miss it. A terminal complete
ledger with a missing or mismatched result may republish only that same complete
result after verifying its recorded policy/provider receipt; it never commands
a load. An orphan override transition retains committed ownership ON; an orphan
device request retains restored policy but remains busy/denied until its
recovery receipt is durable. No restart recovery commands a load.

For an ON transition, set desired policy ON, postUpdate and persist/read-verify
`OverrideSwitch` ON before superseding any pending device request or commanding
a load. Mark superseded requests failed, then issue the exact dishwasher,
Shureflo, and Goat Cam OFF matrix. A late provider event cannot complete a
superseded generation. Partial failure or timeout leaves ownership ON and emits
a truthful failed result.

For an OFF transition, retain desired policy and visible `OverrideSwitch` ON
while Shureflo is commanded and provider-confirmed ON. Persist/read-verify a
nonterminal checkpoint/result with exact `status: running` and
`reason: release-ready`, then set desired policy OFF and
postUpdate/persist/read-verify `OverrideSwitch` OFF. Only after that committed
state may the request ledger be written terminal `complete` and
persisted/read-verified; only after the terminal ledger is durable may the
matching result become `complete`. Failure before the OFF commit leaves
ownership ON. Failure after the OFF state write but before the
terminal receipt never reports complete. While all writes remain gated, its
recovery branch first attempts a non-actuating bookkeeping reclaim: set desired
policy ON, postUpdate `OverrideSwitch` ON, and persist/read-verify it. A verified
reclaim emits failed `off-release-not-committed`, retains ON, records the
provider-matrix mismatch, and denies new device requests until separately
approved reconciliation. If even that reclaim cannot be proved, ownership
becomes `outcome-unknown` and all requests remain denied. Neither branch
commands a load or leaves a terminal visible OFF state without a complete
receipt. Dishwasher and Goat Cam remain unchanged.

A device request may command its provider only while its reducer event holds the
lock and only when desired policy plus visible `OverrideSwitch` are exactly OFF,
no override transition is pending, provider health is ONLINE, and its accepted
ledger checkpoint has been persisted/read-verified. Provider waits happen after
releasing the lock and resolve only the matching generation. A Goat Cam
operation, including its role in the override matrix, completes only after both
the matching provider event and existing downstream `FeederOverride` state (ON
clears it, OFF sets it) are observed for that generation. The owner never writes
`FeederOverride`; a missing or late coupling side effect remains failed or
outcome-unknown.

Retire backed-up duplicate rules `ab8a59e1da`, `4e234eabea`, and `e647476610`
only inside the receipt transaction. Preserve coupling UIDs `3e8f265498` and
`GoatCamOff` without reversing or rerouting them. The shared owner is the sole
UI/override path that commands Goat Cam; only after provider confirmation do the
unchanged downstream coupling rules update `FeederOverride`. Include their
exact DTO/source hashes as protected read-only dependencies and show the
resulting feeder-policy state beside Goat Cam.

- [ ] **Make every other household surface ownership-safe**

Export and structurally scan MainUI pages `overview`, `earthship`,
`page_fc7fed510c`, and `page_69e95753c4`. Live `overview` has direct toggles for
`OverrideSwitch`, Shureflo, dishwasher, and Goat Cam at the captured paths in
the audit fixture. Replace all four with permanent `oh-label-card` read-only
status cards that direct users to the correlated Earthship UI controls. Use
`Owned by Night Load Override` when ON, `Use Earthship Console for changes` when
OFF, and `Override status unavailable - read-only` otherwise. Do not retain a
conditional direct toggle when override is OFF; that still races the owner.
Preserve the Task 2 feeder/greywater read-only patch and allow the separate
circadian policy toggle. Across all four pages, recursive tests reject an
`oh-toggle-card` or interactive `actionItem` targeting the four owner-only
Items. Svelte tests reject every provider Item passed to `sendCommand`.

Read-only inspect item links, channel/Thing health, and recent provider
`stateupdated`/`statechanged` evidence for the three living-room items plus
`Dish_Washer_Power`, `ShurefloPump_Power`, and
`Goat_Plugs_Outlet1_Switch`. For every reliably bidirectional channel, and unconditionally for both request
Items plus `OverrideSwitch`, include in the override-graph receipt a PUT of
OpenHAB 5.2 metadata DTO
`{"value":"false","config":{},"editable":true}` at namespace `autoupdate`,
then exact canonical readback. Verify JDBC every-change/restore-on-startup
coverage for `OverrideSwitch` and both request ledgers. If physical provider
readback cannot be proven, do not issue a proving command; keep the applicable
UI terminal state `sent-unconfirmed`/`outcome-unknown`, leave the owned-load
capability unverified, and record the limitation.

- [ ] **Implement receipt ordering and active-graph rollback semantics**

Extend the `override-graph` subset to include both request/result pairs,
request persistence coverage, `OverrideSwitch` metadata, provider autoupdate
metadata, the new owner, both schedules, and all three retired child rules. Add
both coupling rules as hash-verified read-only dependencies that apply,
rollback, and reapply are forbidden to mutate. Extend `mainui-ownership` with the four audited pages
and exact Task 2 safety baseline.

Every `override-graph` operation encodes dependency ordering rather than
leaving it to the operator. `apply` performs only these preparation steps:

1. disable both schedules;
2. disable current owner/child rules and recheck stable ingress while the
   downstream coupling rules remain unchanged;
3. restore or install every candidate owner/schedule DTO while still disabled;
   and
4. verify candidate hashes, unchanged coupling DTOs, policy/provider state, and
   post-cursor logs while every candidate rule remains disabled.

Apply exits with the candidate graph fully disabled. One `rehearse` process
keeps both old and new DTO sets disabled through old-disabled restore and
new-disabled reapply, then performs the sole final activation: enable and prove
the intended owner healthy and IDLE first, enable schedules last, then verify
all hashes, states, and post-cursor logs. Rollback restores old owner DTOs
disabled, enables and proves that owner set first, and only then restores old
schedules. Reapply mirrors that owner-first, schedules-last sequence. Coupling
DTOs remain untouched throughout. Old and new owners never overlap, schedules
never run ownerless, and no DTO restore implicitly restores enabled state.

Before any receipt, require an attended window outside both schedules, a valid
owner-committed `OverrideSwitch` ON/OFF runtime state, and fresh ONLINE provider
evidence. If JDBC has prior history, its latest record must match; no history is
allowed only for the exact one-time seed branch above. If `OverrideSwitch` is ON,
dishwasher, Shureflo, and Goat Cam must all be provider-confirmed OFF. If it is
OFF, Shureflo must be
provider-confirmed ON; dishwasher and Goat Cam remain intentionally
unconstrained. Unknown/mismatched state stops the transaction. Reconciliation
is not part of this task and would require separate explicit command approval.
Also require stable `FeederOverride`, no active coupling transition, and no
pending request. The receipt transaction itself never commands
`OverrideSwitch`, a request Item, or a physical load.

- [ ] **Commit exact tested sources before live mutation**

~~~bash
set -euo pipefail
npm test -- tests/openhab/night-load-override-rule.test.js \
  tests/openhab/override-trace.test.js tests/openhab/owned-load-race.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/circadian-rule.test.js tests/openhab/provider-readback.test.js \
  tests/openhab/mainui-ownership.test.js tests/control-catalog.test.js \
  tests/proxy-auth.test.js tests/openhab/rest-safety.test.js
node tools/qa/update-matrix.mjs --task 16 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add openhab/rules/night-load-override.js \
  openhab/rules/living-room-circadian.js openhab/rules/override-schedule-on.js \
  openhab/rules/override-schedule-off.js openhab/rules/goat-cam-coupling-on.js \
  openhab/rules/goat-cam-coupling-off.js openhab/managed-resources.json \
  openhab/mainui/overview-ownership-patch.json \
  openhab/mainui/earthship-ownership-patch.json \
  openhab/mainui/page-fc7fed510c-ownership-patch.json \
  openhab/mainui/page-69e95753c4-ownership-patch.json \
  scripts/openhab-config.mjs src/lib/controls/catalog.js \
  tests/openhab/night-load-override-rule.test.js \
  tests/openhab/override-trace.test.js tests/openhab/owned-load-race.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/circadian-rule.test.js tests/openhab/provider-readback.test.js \
  tests/openhab/mainui-ownership.test.js docs/qa/ui-audit-matrix.csv
git commit -m "feat: consolidate household policy orchestration"
test -z "$(git status --short)"
~~~

Expected: exact-script and race simulations pass from the committed sources;
no household command has been sent, and `night-load-owner-v1` remains explicitly
unverified in every UI/release-mode test.

- [ ] **Apply MainUI first, then the override graph, under two receipts**

Obtain contemporaneous approval for the future/timed-load graph transaction and
an observer for affected equipment. Snapshot and verify both subsets before the
first mutation:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs snapshot --subset mainui-ownership \
  --out-root /tmp --activate-backup
node scripts/openhab-config.mjs verify --subset mainui-ownership \
  --from-active --read-only
node scripts/openhab-config.mjs snapshot --subset override-graph \
  --out-root /tmp --activate-backup
node scripts/openhab-config.mjs verify --subset override-graph \
  --from-active --read-only
~~~

Apply and rehearse the MainUI ownership patch while the old graph remains
healthy, and keep that receipt open:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs apply --subset mainui-ownership \
  --from-active --mode maintenance
node scripts/openhab-config.mjs rehearse --subset mainui-ownership \
  --from-active --mode maintenance
node scripts/openhab-config.mjs verify --subset mainui-ownership \
  --from-active --read-only
~~~

Then execute the single disabled graph transaction and close receipts in
dependency order:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs apply --subset override-graph \
  --from-active --mode maintenance \
  --prerequisite-receipt \
  /tmp/earthship-ui-openhab-active/mainui-ownership.json
node scripts/openhab-config.mjs rehearse --subset override-graph \
  --from-active --mode maintenance \
  --prerequisite-receipt \
  /tmp/earthship-ui-openhab-active/mainui-ownership.json
node scripts/openhab-config.mjs verify --subset override-graph \
  --from-active --read-only \
  --prerequisite-receipt \
  /tmp/earthship-ui-openhab-active/mainui-ownership.json
node scripts/openhab-config.mjs verify --subset mainui-ownership \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset override-graph \
  --from-active --terminal desired
node scripts/openhab-config.mjs close-backup --subset mainui-ownership \
  --from-active --terminal desired
~~~

Require exact hashes/enabled states, healthy owner rules, unchanged healthy
coupling rules, schedules last, no UNINITIALIZED rule, unchanged provider
states, and clean post-cursor logs.

Add a tested `recover-by-log` mode in this task. It requires the exact active
receipt and append-only operation log, proves no mutator process is still
running, and chooses exactly one terminal branch:

- zero mutating calls: canonical live-equals-backup read-only verification,
  then close `unmutated`, with no rollback, rule-enable, PUT, or DELETE;
- one or more mutating calls: dependency-ordered rollback, canonical
  live-equals-backup/enabled-state/provider/log verification, then close
  `rolled-back`; or
- missing, truncated, non-monotonic, ambiguous, or in-flight operation evidence:
  leave the receipt open and emit operator action without another mutation.

A successful terminal branch atomically closes the receipt, emits exactly one
JSON result containing `subset`, terminal `unmutated` or `rolled-back`, and the
receipt/evidence checksum, then exits 0. Every open, ambiguous, approval-waiting,
operator-action, verification, rollback, or terminal-write outcome emits
`receiptOpen: true` and exits nonzero. Tests assert these exit/result semantics,
so `set -e` starts MainUI recovery only after graph recovery is checksum-valid;
an unresolved graph deliberately leaves the MainUI receipt open and untouched
for the emitted operator sequence.

Tests inject failure before the first write and after every MainUI/graph write,
plus crash/write/close failures in both recovery branches. They prove a
zero-write receipt never enters rollback or changes an enabled state.

If either pre-apply snapshot/verify aborts, run `recover-by-log` only for each
exact receipt that was atomically created; both must take the zero-write
`unmutated` branch. On an apply/rehearse/final-verify failure before either
desired close, keep both receipts open and recover the dependent graph before
the MainUI foundation:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs recover-by-log --subset override-graph \
  --from-active --mode maintenance \
  --prerequisite-receipt \
  /tmp/earthship-ui-openhab-active/mainui-ownership.json
node scripts/openhab-config.mjs recover-by-log --subset mainui-ownership \
  --from-active --mode maintenance
~~~

The graph receipt may be zero-write while MainUI is mutated; it closes
`unmutated` before MainUI rollback. MainUI may also be a verified desired no-op
while the graph mutates; in that valid branch the graph rolls back first and
MainUI then closes `unmutated`. If both are mutated, both roll back in the same
order. Graph apply/rehearse/verify record the exact MainUI receipt generation,
checksum, and successful desired-state verification as a prerequisite; missing
or stale prerequisite evidence leaves both open. The next subset never starts
until the prior recovery receipt has a checksum-valid terminal outcome.

When the override receipt is mutated, its rollback proves the old owner set
healthy before restoring schedules and verifies coupling hashes before MainUI
recovery; its zero-write branch proves the untouched graph before MainUI
recovery. A close I/O
failure after both desired verifications does not mutate live configuration:
leave the remaining receipt open, diagnose and rerun only its exact desired
close, and never claim both are open or roll back an already-closed subset.
Never issue a physical reconciliation command without separate approval.

- [ ] **Version circadian separately and enable at most once**

Always snapshot and verify circadian in its own receipt:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs snapshot --subset circadian \
  --out-root /tmp --activate-backup
node scripts/openhab-config.mjs verify --subset circadian \
  --from-active --read-only
~~~

If captured `hex_living_room_circadian` already matches the exact tested
candidate and readback contract, make no live mutation and close the proven
no-op receipt:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs close-backup --subset circadian \
  --from-active --terminal unmutated
~~~

If a change-gated LastResult or readback fix is required, obtain separate
contemporaneous approval before mutation. For a captured-enabled rule, the
recorded scope must cover at most one candidate final re-enable and, only if the
transaction later fails, at most one recovery re-enable of the captured old
rule; either may cause one normal rule-driven bulb adjustment. If that bounded
contingency is not approved, do not begin a mutation.

`record-approval` touches no OpenHAB resource. Before the first write it appends
and fsyncs an entry bound to the exact receipt generation/hash, captured enabled
state, wall and monotonic time, 900-second expiry, approval source, and separate
single-use `candidate-reenable` and `recovery-reenable` counters. Each guarded
rule-enable consumes and fsyncs its matching counter before the REST call. A
flag alone is never authority; apply/rehearse/recovery reject a missing, stale,
expired, wrong-receipt, exhausted, or wrong-scope entry. Run this block only
after the contemporaneous approval is actually received:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs record-approval --subset circadian \
  --from-active --scope candidate-reenable \
  --scope recovery-reenable --ttl-seconds 900 \
  --approval-source contemporaneous-user
node scripts/openhab-config.mjs apply --subset circadian \
  --from-active --mode maintenance \
  --require-approval-scope candidate-reenable,recovery-reenable
node scripts/openhab-config.mjs rehearse --subset circadian \
  --from-active --mode maintenance \
  --require-approval-scope candidate-reenable,recovery-reenable
node scripts/openhab-config.mjs verify --subset circadian \
  --from-active --read-only
node scripts/openhab-config.mjs close-backup --subset circadian \
  --from-active --terminal desired
~~~

If apply/rehearse/verify fails before a proven desired close, run only the
operation-log recovery. Zero writes verify/close `unmutated`. Any mutation
restores the old DTO disabled first and, only when the receipt proves the
captured rule was enabled and the bounded recovery approval exists, re-enables
that old rule exactly once, verifies provider/status/log readback, and closes
`rolled-back`:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs recover-by-log --subset circadian \
  --from-active --mode maintenance --allow-captured-reenable \
  --require-approval-scope recovery-reenable
~~~

A missing/expired approval, enabled-state ambiguity, provider/readback failure,
or recovery enable failure leaves the old source disabled and the receipt open
with `awaiting-recovery-approval` or operator action; it never silently enables
or closes. After new contemporaneous recovery approval, append a fresh
receipt-bound single-use recovery scope and resume only this state machine:

~~~bash
set -euo pipefail
node scripts/openhab-config.mjs renew-approval --subset circadian \
  --from-active --scope recovery-reenable --ttl-seconds 900 \
  --approval-source contemporaneous-user
node scripts/openhab-config.mjs recover-by-log --subset circadian \
  --from-active --mode maintenance --allow-captured-reenable \
  --require-approval-scope recovery-reenable
~~~

`renew-approval` is append-only, is allowed only in the exact
`awaiting-recovery-approval` state, and cannot authorize candidate apply or a
second recovery enable. Tests reject a flag without a receipt entry, wrong
receipt generation/hash or scope, expiry and wall/monotonic-clock rollback,
counter reuse, renewal outside the waiting state, and a second recovery use.
They inject failure before disable, after
disable, after PUT, during rehearsal, after candidate enable, during old-rule
restore/re-enable, verification, and close. They prove the zero-write branch
never calls rollback/enable, the mutation branch never enables without recorded
approval, and no path can close stronger than its operation log. A close I/O
failure after complete desired verification reruns only the exact desired close;
it does not roll back a proven live candidate.

Apply disables first, PUTs and hash-verifies the candidate, and exits disabled.
The single rehearsal keeps old and new sources disabled, then restores the
captured enabled state exactly once at the end; if it was originally disabled,
it never enables. Verify provider readback/status/logs afterward. No manual bulb
command is a proving action. Without approval, close only a genuinely unmutated
receipt and leave the circadian matrix rows `blocked-live`; do not enable the
owned-load capability or proceed to full release.

- [ ] **Enable the owned-load capability only after receipts close**

Only after `override-graph` and `mainui-ownership` are both desired-state
verified and closed, and circadian is closed `desired` or proven no-op
`unmutated`, flip `night-load-owner-v1` from unverified to ready. Any
`rolled-back` receipt is safety recovery evidence, not completion; its live rows
stay blocked and full release is forbidden. Provider health, owner committed
OFF, idle transition, release mode, and freshness gates still apply at runtime:

~~~bash
set -euo pipefail
npm test -- tests/control-catalog.test.js tests/release-mode.test.js \
  tests/proxy-auth.test.js tests/ui/typed-controls.test.js \
  tests/openhab/owned-load-race.test.js
git diff --check
git add src/lib/controls/catalog.js src/lib/releaseMode.js \
  tests/control-catalog.test.js tests/release-mode.test.js \
  tests/proxy-auth.test.js tests/ui/typed-controls.test.js \
  docs/qa/ui-audit-matrix.csv
git commit -m "feat: enable verified owned-load requests"
test -z "$(git status --short)"
~~~

If either receipt remains open, any provider/readback/hash gate is incomplete,
or coupling hashes changed, do not make this commit and do not proceed to a
full release.

- [ ] **Establish the post-graph zero-write rollback floor**

From the still-clean capability commit, build and activate a new immutable
maintenance release. This release understands the new schema but authorizes no
writes:

~~~bash
set -euo pipefail
test -z "$(git status --short)"
GRAPH_SHA=$(git rev-parse --short=12 HEAD)
POSTGRAPH_ID="postgraph-maintenance-$GRAPH_SHA"
RELEASE_ID="$POSTGRAPH_ID" RELEASE_MODE=maintenance \
  node tools/release/build.mjs --reuse-verified
node tools/release/activate.mjs "$POSTGRAPH_ID"
systemctl --user restart earthship-ui-preview.service earthship-ui-pwa.service
curl -fsS http://192.168.1.161:5190/release.json \
  -o /tmp/earthship-ui-postgraph-http.json
curl --cacert /home/sat/.config/earthship-ui/tls/root-ca.crt \
  -fsS https://192.168.1.161:5192/release.json \
  -o /tmp/earthship-ui-postgraph-pwa.json
jq -e --arg id "$POSTGRAPH_ID" \
  '.releaseId == $id and .releaseMode == "maintenance"' \
  /tmp/earthship-ui-postgraph-http.json
jq -e --arg id "$POSTGRAPH_ID" \
  '.releaseId == $id and .releaseMode == "maintenance"' \
  /tmp/earthship-ui-postgraph-pwa.json
node tools/release/verify-policy.mjs --release "$POSTGRAPH_ID" \
  --expect-mode maintenance
~~~

Reprove isolated maintenance write denials plus read-only production
symlink/process ownership and OpenHAB
resource hashes, provider state, and clean logs. `POSTGRAPH_ID` replaces every
older release as the rollback floor. Do not activate full mode until Task 18.
Record exact non-secret evidence in the matrix, then commit only that evidence:

~~~bash
set -euo pipefail
node tools/qa/update-matrix.mjs --task 16 --phase live \
  --receipt /tmp/earthship-ui-openhab-active/override-graph.json \
  --receipt /tmp/earthship-ui-openhab-active/mainui-ownership.json \
  --receipt /tmp/earthship-ui-openhab-active/circadian.json \
  --release-evidence /tmp/earthship-ui-postgraph-http.json \
  --release-evidence /tmp/earthship-ui-postgraph-pwa.json \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add docs/qa/ui-audit-matrix.csv
git commit -m "docs: record household ownership cutover"
test -z "$(git status --short)"
~~~

Expected: device and schedule requests share one serialized owner;
manual/scheduled traces match; provider-driven Goat Cam coupling remains intact;
MainUI is permanently read-only for owned loads; circadian health is truthful;
and the only rollback UI is zero-write.

---

## Task 17: Add PWA shell caching, aged snapshots, and non-flapping dim mode

**Files:**

- Modify: vite.config.js
- Modify: src/App.svelte
- Modify: src/lib/config.js
- Modify: src/lib/ui/Shell.svelte
- Modify: src/lib/charts/historyRequest.js
- Create: src/lib/charts/historyCache.js
- Create: src/lib/pwa/cachePolicy.js
- Create: src/lib/pwa/dimPolicy.js
- Create: src/lib/pwa/register.js
- Create: public/pwa-icon.svg
- Create: public/pwa-icon-192.png
- Create: public/pwa-icon-512.png
- Create: tests/pwa-cache-policy.test.js
- Create: tests/config-offline.test.js
- Create: tests/history-cache.test.js
- Create: tests/dim-policy.test.js
- Modify: playwright.config.js
- Modify: tests/e2e/server.mjs
- Modify: tests/e2e/fixtures/device.js
- Modify: tests/e2e-fixture-contract.test.js
- Create: tests/e2e/fixtures/releaseSwitch.js
- Create: tests/e2e/offline-pwa.spec.js
- Create: tests/e2e/pwa-update.spec.js
- Create: tests/e2e/dim-mode.spec.js
- Modify: `docs/qa/ui-audit-matrix.csv`

- [ ] **Write failing cache/offline/dim tests**

Test that the manifest has exact 192x192 and 512x512 PNG icons (validated by
PNG headers) and that static shell assets are cached under the explicit
`e2e/full` release key while `/config.json`, `/rest/**`, item commands, and pending
control state never enter a service-worker cache. Assert the served manifest,
app build marker, and worker cache key all carry those exact test inputs. Offline reload must show the shell plus timestamped cached
snapshot, disable every control, not replay on reconnect, and make unknown
chart periods unavailable. History-cache tests cover exact item/policy/period
keys, capture/range timestamps, schema corruption, release migration, LRU
eviction, a 32 MiB byte cap, aged labeling, and exact-period hits only.

Dim tests use exact live items:

- Sun_Position_Elevation
- Sun_SunPhaseName
- AmbientWeatherWS2902A_SolarRadiation

Cover dusk/dawn hysteresis, solar-radiation supplementation, missing sources,
no threshold flapping, legible contrast, and alerts staying visible.

- [ ] **Run RED**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T17A-1' -- \
  npm test -- tests/pwa-cache-policy.test.js \
    -t '^\[RED:T17A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T17A-2' -- \
  npx playwright test tests/e2e/offline-pwa.spec.js \
    --project=m9-pwa --grep '^\[RED:T17A-2\]'
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T17A-3' -- \
  npm test -- tests/e2e-fixture-contract.test.js \
    -t '^\[RED:T17A-3\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T17A-4' -- \
  npx playwright test tests/e2e/dim-mode.spec.js \
    --project=m9-browser --grep '^\[RED:T17A-4\]'
~~~

The sole `RED:T17A-3` fixture-contract probe dynamically loads the valid current
Playwright configuration, first proves all three canonical projects are intact,
and emits its sentinel only when the exact `m9-pwa-update` project is absent. A
configuration import/parse error, missing canonical project, or wrong alias is
an unapproved failure and is rethrown unchanged.

`offline-pwa.spec.js` requires the injected standalone profile and skips every
project except `m9-pwa`; an insecure browser project cannot count as an
offline-PWA pass. Release switching is isolated in a dedicated
`m9-pwa-update` project that injects the same frozen `m9-pwa` device/profile,
matches only `pwa-update.spec.js`, and runs that file serially against its own
public port and unique temporary `RELEASE_ROOT`. No other project uses that
server. Update the fixture contract to compare the DOM marker with the resolved
`earthshipDeviceProfile.id`; preserve exact project-name mapping for all three
canonical projects and allow only the explicit auxiliary alias
`m9-pwa-update -> m9-pwa`. Contract tests reject every arbitrary alias.

The update server prebuilds checksummed `e2e-full` and `e2e-maintenance`
releases and uses `releaseSwitch.js` to atomically activate and restart the
release-owned child on the same dedicated public origin. Its controller binds a
separate ephemeral loopback socket, accepts only the process-local synthetic
fixture secret, and never exists in `serve.mjs` or a production release. Every
case starts by activating and verifying `e2e-full`; `afterEach` plus an outer
`finally` restores and verifies `e2e-full` even after an injected failure.
Tests prove the controller cannot load a household token, bind a non-loopback
address, or switch to an unverified release. They run real
`full -> maintenance -> full` transitions and wait for worker/controller/cache
takeover at each boundary.

Expected: FAIL because no service worker/offline shell or deterministic dim
policy exists.

- [ ] **Implement a release-versioned PWA**

Use `vite-plugin-pwa` with injected release ID plus release mode
`safe-compat`, `maintenance`, or `full`, and precache only immutable app assets.
Registration requires `window.isSecureContext`. Production registers on the
trusted 5192 origin in its secure install tab and installed PWA, never on the
5190 HTTP browser surface. On localhost, it additionally requires the frozen
Task 1 QA device ID `m9-pwa`; `m9-browser` and laptop projects stay
service-worker-free even though localhost is a secure context. Tests prove this
origin/profile matrix and reject a query-string-only bypass. The Task 12 release-mode
gate keeps feeder/greywater/override request controls disabled in
`safe-compat` even though the current code understands their schemas. Configure
navigate fallback for the shell and NetworkOnly for `/config.json` and
`/rest/**`. Do not register Background Sync or a command queue.

Use an explicit release-takeover handshake. Every installed worker precaches
and checksum-verifies its release cache. On first registration, when there is no
incumbent active worker or controller, that worker may call `skipWaiting()`;
the page waits for both `navigator.serviceWorker.ready` and bounded
`controllerchange`, then validates the claimed client before continuing. Tests
cover this no-incumbent branch and reject a ready registration without the
matching controller/cache/release.

For an update, the verified worker waits. The page fetches `release.json` with
`cache: "no-store"`, disables all commands during takeover, calls
`registration.update()`, and sends exactly `ACTIVATE_RELEASE:<release-id>` only
when the waiting worker embeds the same release ID as the active manifest. The
worker then calls `skipWaiting()` and claims clients during activation. The page
waits at most ten seconds for `controllerchange`, hard-reloads the same URL, and
re-enables commands only after app marker, controller, cache, manifest, and
active release all agree. Timeout or mismatch leaves commands disabled and
instructs the user to close and relaunch. The old page remains fenced by its
release header throughout. The update E2E injects first-install, install, wait,
message, `controllerchange`, cache, and reload failures and proves every one
fails closed.

`loadRuntimeConfig()` uses a compiled token-free same-origin fallback
`{ openhabUrl: '', apiToken: '', staleBannerSeconds: 90 }` only when
`/config.json` fails or times out. It labels that source
`compiled-safe-fallback`, continues to Task 4 cache initialization immediately,
and lets REST reconcile asynchronously. Offline-with-cache renders aged state;
offline-without-cache renders the shell/unavailable state. Neither path
authorizes commands. Tests cover config rejection before bootstrap, initial
REST timeout, later reconnect, and no replay.

Keep item snapshots in the state cache from Task 4, outside service-worker
runtime caching, with `capturedAt` and cached labeling. Add a native IndexedDB
history cache keyed by schema/release, item ID, normalized series policy, and
one of the exact 4/24/168/720-hour periods. Store only the bounded prepared
typed arrays plus raw-tooltip pairs, range end, capture time, and byte count;
never store response objects, commands, or pending state. Enforce 32 MiB LRU
and corruption/version eviction. Wire successful Task 6 generations to write
it and offline loads to read only an exact key. Unknown/evicted periods render
unavailable, while a hit renders with its aged capture label; every command
primitive gets a shared offline disable reason.

- [ ] **Implement dim hysteresis**

Use a pure state machine with separate enter/exit thresholds. Elevation and sun
phase are primary; solar radiation corroborates but cannot alone cause rapid
toggle. Palette changes may reduce glow/intensity but must keep text/control/
alert contrast at the existing legible floor.

- [ ] **Run GREEN and commit**

~~~bash
set -euo pipefail
npm test -- tests/pwa-cache-policy.test.js tests/config-offline.test.js \
  tests/history-cache.test.js tests/dim-policy.test.js \
  tests/e2e-fixture-contract.test.js
npx playwright test tests/e2e/offline-pwa.spec.js --project=m9-pwa
npx playwright test tests/e2e/pwa-update.spec.js --project=m9-pwa-update
npx playwright test tests/e2e/dim-mode.spec.js
npm run build
node tools/qa/update-matrix.mjs --task 17 --phase automated \
  docs/qa/ui-audit-matrix.csv
git diff --check
git add vite.config.js src/App.svelte src/lib/config.js \
  src/lib/ui/Shell.svelte src/lib/charts/historyRequest.js src/lib/charts/historyCache.js \
  src/lib/pwa/cachePolicy.js src/lib/pwa/dimPolicy.js src/lib/pwa/register.js \
  public/pwa-icon.svg public/pwa-icon-192.png public/pwa-icon-512.png \
  tests/pwa-cache-policy.test.js tests/config-offline.test.js tests/history-cache.test.js tests/dim-policy.test.js \
  playwright.config.js tests/e2e/server.mjs \
  tests/e2e/fixtures/device.js tests/e2e-fixture-contract.test.js \
  tests/e2e/fixtures/releaseSwitch.js \
  tests/e2e/offline-pwa.spec.js tests/e2e/pwa-update.spec.js \
  tests/e2e/dim-mode.spec.js
git add docs/qa/ui-audit-matrix.csv
git commit -m "feat: add safe offline and dim tablet behavior"
~~~

Expected: PWA reload is useful but read-only, no command can replay, and dim
mode is stable and readable.

---

## Task 18: Close the audit, meet performance budgets, and activate the full immutable release

**Files:**

- Create: `tests/e2e/geometry.spec.js`
- Create: `tests/e2e/all-states.spec.js`
- Create: `tests/e2e/chart-performance.spec.js`
- Create: `tests/e2e/accessibility.spec.js`
- Create: `src/lib/qa/TabletMetricsProbe.svelte`
- Create: `tools/qa/collect-tablet-metrics.mjs`
- Create: `tools/qa/validate-tablet-metrics.mjs`
- Create: `tests/tablet-metrics-schema.test.js`
- Create: `tests/tablet-target-navigation.test.js`
- Create: `tools/qa/check-bundle.mjs`
- Create: `tools/qa/check-matrix.mjs`
- Create: `tests/qa-gates.test.js`
- Create: `docs/qa/real-device-signoff.json`
- Create: `docs/qa/release-rehearsal.json`
- Create: `docs/qa/tablet-performance-browser.json`
- Create: `docs/qa/tablet-performance-pwa.json`
- Modify: `src/App.svelte`
- Conditional modify on measured profile drift: `src/app.css`
- Conditional modify on measured profile drift: `src/lib/ui/Shell.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/Tile.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/StatTile.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/HourlyStrip.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/ThermalLoop.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/ChartCanvas.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/HistoryChart.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/HistorySparkline.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/ChartModal.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/CompassRose.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/Header.svelte`
- Conditional modify on measured profile drift: `src/lib/ui/HeaderAlerts.svelte`
- Conditional modify on measured profile drift: `src/screens/Home.svelte`
- Conditional modify on measured profile drift: `src/screens/Energy.svelte`
- Conditional modify on measured profile drift: `src/screens/Weather.svelte`
- Conditional modify on measured profile drift: `src/screens/Earthship.svelte`
- Conditional modify on measured profile drift: `src/screens/Controls.svelte`
- Modify: `docs/qa/ui-audit-matrix.csv`
- Modify: `tools/release/build.mjs`
- Modify: `tools/release/activate.mjs`
- Create: `tools/release/promote.mjs`
- Create: `tests/release-promotion.test.js`
- Modify: `tests/e2e/device-profiles.json`

- [ ] **Write failing aggregate geometry, accessibility, bundle, and matrix gates**

`accessibility.spec.js` checks landmark uniqueness, navigation naming/current
route, visible focus, the header winner full accessible text while its list is
closed, no-alert status, polite/assertive transition rules, native card/button
keyboard activation, modal name/description/focus trap/Escape/return, period
pressed state, chart series/period/state/latest-value descriptions, and
hold-control keyboard/cancel behavior.

`geometry.spec.js` runs Home, Energy, Weather, Earthship, and Controls under
normal, unavailable, stale/offline, pending, failed, `sent-unconfirmed`,
`outcome-unknown`, and long fixtures in all three canonical projects. For
html/body/#app/shell/main and every required card/child/chart/modal/header/rail/
control:

- scrollWidth is at most clientWidth;
- scrollHeight is at most clientHeight;
- child bounds stay within parent bounds;
- required siblings do not overlap;
- every target is at least 44x44; and
- no required text is clipped or omitted.

`check-bundle.mjs` fails if initial JS gzip exceeds 1 MiB or full ECharts/icon
imports remain. Runtime point-cap proof belongs to
`chart-performance.spec.js` and the tablet probe: both assert actual rendered
count never exceeds `floor(4W)` for every series/period. The static checker does
not claim runtime geometry. `check-matrix.mjs --phase automated` fails on a
missing spec family, incomplete or invalid complete RED sentinel inventory,
non-unique ID, empty automated evidence, or open software row, but permits
explicit `blocked-live`/`blocked-device` rows. Default final
mode permits only closed. Aggregate geometry imports `REQUIRED_CONTENT` from
Task 1 and rejects a missing selector instead of maintaining another inventory.
`tests/qa-gates.test.js` owns the two checker sentinels: each probe dynamically
imports exactly one checker, converts only the intended module-not-found result
for that exact path into its sentinel error, and rethrows every syntax, import,
or transitive dependency error unchanged.

- [ ] **Run RED for aggregate gates and promotion recovery**

Each command filters to exactly one structured sentinel probe. A different,
additional, setup, collection, hook, import, timeout, or crash failure—and an
unexpected pass—fails this RED phase.


~~~bash
set -euo pipefail
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T18A-1' -- \
  npm test -- tests/tablet-metrics-schema.test.js \
    -t '^\[RED:T18A-1\]'
node tools/qa/expect-failure.mjs \
  --runner playwright --sentinel 'RED:T18A-2' -- \
  npx playwright test tests/e2e/geometry.spec.js \
    --project=m9-browser --grep '^\[RED:T18A-2\]'
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T18A-3' -- \
  npm test -- tests/qa-gates.test.js \
    -t '^\[RED:T18A-3\]'
node tools/qa/expect-failure.mjs \
  --runner vitest --sentinel 'RED:T18A-4' -- \
  npm test -- tests/qa-gates.test.js \
    -t '^\[RED:T18A-4\]'
~~~

Expected: FAIL for the missing probe, collectors/checkers, aggregate specs, and
fail-closed promotion/recovery implementation.

- [ ] **Implement the aggregate gates and real-app performance observer**

Mount `TabletMetricsProbe` as a read-only observer sidecar only when the normal
app opens with `?qa=performance`; do not replace, strip, or fork the route under
test. It exposes schema v1, build/release IDs, page/worker timestamps,
rendered-point/plot-width counts, `PerformanceObserver` long tasks and Event
Timing, navigation/SSE progress, viewport, DPR, display mode, origin, and safe
area top/right/bottom/left. It has no control method. The collector never
submits a command, but the instrumented application remains the real full app.

`tests/tablet-metrics-schema.test.js` exercises the shared validator with
valid/invalid in-memory fixtures and requires every measurement, unit,
threshold, sample count, mode, collection method, CDP target identity, release
ID, origin, viewport, DPR, and safe-area edge. It does not depend on later
device JSON files. `collect-tablet-metrics.mjs --profile-only` records just the
identity/geometry fields to a caller-supplied `/tmp` output and never accepts
those as performance evidence.

Its separate `--navigate-existing` operation attaches to exactly one existing
CDP target selected by expected origin plus browser or standalone display mode,
records the target ID, calls `Page.navigate` on that same target to the exact
`/?qa=performance` URL, then proves target ID and display mode are unchanged.
It never creates a target. Profile and performance collection require the
resulting target-proof file plus exact `--profile-id` and `--expected-release`;
a missing, duplicate, substituted, or newly created target fails closed.
`tests/tablet-target-navigation.test.js` uses an injected CDP adapter to cover
missing and duplicate targets, origin-plus-mode selection, same-ID
`Page.navigate`, before/after display-mode checks, profile/release/URL proof
binding, stale or substituted proof files, navigation failure, and any attempted
`Target.createTarget`. It asserts the collector never falls back to a new tab.

- [ ] **Implement a fail-closed promotion state machine**

`tools/release/promote.mjs` is an injected-runner state machine. Given safe and
full IDs, it verifies a clean worktree, activates safe, restarts both UI
services, and checks HTTP plus trusted HTTPS endpoints, active
manifest/cache mode, process-owned server paths, isolated forwarding-counter
proxy policy, and read-only OpenHAB health. It never sends a production write.
Only after that gate may it invoke exactly:

~~~text
RELEASE_ID=<full-id> RELEASE_MODE=full node tools/release/build.mjs --reuse-verified
~~~

It then activates full and repeats the server/OpenHAB checks. There is no
second overwrite/build path. Interrupted deterministic reruns use the same
verified-reuse contract.

Emit one machine-readable terminal result:

- `full-verified`, exit 0, only after every full check;
- `full-not-attempted`, nonzero, only when validation failed before any release
  or service mutation and the previously active state was left untouched;
- `safe-recovered`, nonzero, only after a failed promotion and a complete,
  independently verified maintenance recovery; or
- `recovery-failed`, a distinct nonzero with `operatorActionRequired: true`,
  last successful transition, current symlink target, both service states, and
  exact manual recovery commands.

Any failure after mutation makes one bounded recovery attempt: activate safe,
restart both services, and rerun the complete safe gate. If safe activation,
either restart, or any verification fails, never claim safe is active. Fence
writes by selecting the known maintenance symlink when possible; when that
cannot be proven, stop both UI services and report whether stopping succeeded.
Tests inject failures at every primary and recovery step, including activation,
both service restarts, health verification, symlink inspection, service stop,
terminal-report writing, evidence-file write/fsync, and atomic rename. They
assert that no failure path continues to full or reports stronger recovery than
its evidence.

For `--evidence-out`, prepare a candidate `full-verified` record only after all
browser/controller/cache/release, server/proxy, and read-only OpenHAB checks
pass. Refuse an existing destination so a failed or repeated rehearsal cannot
overwrite accepted evidence. Write a sibling temporary file, fsync and close it,
atomically rename it to the requested path, fsync the parent directory, and only
then emit terminal `full-verified`. On interruption or a write/fsync/rename
failure, run the standard maintenance recovery, remove any temporary or newly
renamed candidate, and fsync the parent again. A proved cleanup leaves the
tracked destination absent and unmodified; an unproved cleanup is
`recovery-failed` with operator action. Emit bounded failure evidence to stdout
and `/tmp/earthship-ui-release-rehearsal-failure.json`, never to the tracked
path. Tests prove success-only publication, cleanup and a clean worktree after
each recoverable injected failure, plus operator-required failure when cleanup
cannot be proved. Only this completed atomic sequence may publish
`docs/qa/release-rehearsal.json`.

The default runner validates server/manifest/proxy/OpenHAB state only and emits
`browserProof: "not-requested"`; it never claims to reload a browser or service
worker. `--rehearse-rollback` instead requires CDP plus exact browser and PWA
URLs, attaches to both already-open matching targets, and refuses to create a
normal-tab substitute. Injected CDP tests cover absent, duplicate, wrong-mode,
stale-controller, wrong-cache, and wrong-release targets.

- [ ] **Run complete automated verification and commit the release gates**

~~~bash
set -euo pipefail
npm test
npx playwright test --project=m9-browser
npx playwright test --project=m9-pwa
npx playwright test --project=m9-pwa-update
npx playwright test --project=laptop-1280x720
npm run build
node tools/qa/check-bundle.mjs dist
node tools/qa/update-matrix.mjs --task 18 --phase automated \
  docs/qa/ui-audit-matrix.csv
node tools/qa/check-matrix.mjs --phase automated docs/qa/ui-audit-matrix.csv
git diff --check
if git ls-files | rg '(^|/)(config\.json|openhab\.env|\.env(?:\..*)?)$'; then
  echo "tracked secret or runtime config file detected" >&2
  exit 1
fi
~~~

Expected: all tests pass; no viewport/card scroll or overlap; initial JS is at
most 1 MiB gzip; no secret/config file is tracked; and only live/device matrix
rows remain blocked.

Commit before deriving any release ID:

~~~bash
set -euo pipefail
git add src/App.svelte src/lib/qa/TabletMetricsProbe.svelte \
  tests/tablet-metrics-schema.test.js tests/tablet-target-navigation.test.js \
  tests/e2e/geometry.spec.js \
  tests/e2e/all-states.spec.js tests/e2e/chart-performance.spec.js \
  tests/e2e/accessibility.spec.js tools/qa/collect-tablet-metrics.mjs \
  tools/qa/validate-tablet-metrics.mjs tools/qa/check-bundle.mjs \
  tools/qa/check-matrix.mjs tools/release/build.mjs \
  tools/release/activate.mjs tools/release/promote.mjs \
  tests/release-promotion.test.js tests/qa-gates.test.js \
  docs/qa/ui-audit-matrix.csv
git commit -m "test: add tablet audit release gates"
test -z "$(git status --short)"
~~~

- [ ] **Re-run every automated gate on that exact clean HEAD**

~~~bash
set -euo pipefail
npm test
npx playwright test --project=m9-browser
npx playwright test --project=m9-pwa
npx playwright test --project=m9-pwa-update
npx playwright test --project=laptop-1280x720
npm run build
node tools/qa/check-bundle.mjs dist
node tools/qa/check-matrix.mjs --phase automated docs/qa/ui-audit-matrix.csv
git diff --check
test -z "$(git status --short)"
~~~

Do not derive a release ID unless this post-commit rerun passes. If actual M9
measurement later changes the profile, return to this exact gate after the
profile/layout correction commit and derive new IDs from that new clean HEAD.

- [ ] **Build a zero-write PWA rollback release and promote full**

Build the final service-worker-compatible maintenance release from the clean
hardened HEAD, then delegate activation/gating/full build/fallback to the tested
runner:

~~~bash
set -euo pipefail
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
SAFE_ID="maintenance-$BASE"
FULL_ID="full-$BASE"
RELEASE_ID="$SAFE_ID" RELEASE_MODE=maintenance \
  node tools/release/build.mjs --reuse-verified
node tools/release/promote.mjs --safe "$SAFE_ID" --full "$FULL_ID" \
  --ca /home/sat/.config/earthship-ui/tls/root-ca.crt
~~~

Accept only terminal `full-verified`. On `safe-recovered`, full is not active
and the task stops for diagnosis. On `recovery-failed`, follow the emitted
operator-required recovery evidence; do not continue to install or test a PWA.
No nonzero result is described as verified safe unless the terminal payload is
exactly `safe-recovered` with every safe check attached.

Require healthy affected rules, matching Thing/channel/item/link hashes,
SchneiderTelemetry_Status beginning OK, no unexpected offline Things except
wall-powered bulbs, and no new ERROR/Exception logs. Do not run a rule or
command an item.

- [ ] **Install, launch, and remeasure the real production PWA**

On the M9 with the Task 2 root CA already trusted, open the exact active
`https://192.168.1.161:5192/` full release in Chrome. Verify no certificate
warning, full manifest/app/release IDs, 192/512 icons, standalone scope/start
URL, service-worker controller, and installability. Install it from Chrome,
launch it from the Android home screen, and keep it installed. Assert
`(display-mode: standalone)`, full release ID, controller script release, and
cache key. Open the exact full `http://192.168.1.161:5190/` browser target too.
No insecure flag, certificate bypass, or normal-tab PWA substitute is allowed.

Enable remote debugging only after both real targets exist:

~~~bash
set -euo pipefail
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
FULL_ID="full-$BASE"
adb forward tcp:9222 localabstract:chrome_devtools_remote
node tools/qa/collect-tablet-metrics.mjs --navigate-existing \
  --cdp http://127.0.0.1:9222 --mode browser --profile-id m9-browser \
  --expected-release "$FULL_ID" \
  --url http://192.168.1.161:5190/?qa=performance \
  --out /tmp/earthship-m9-browser-target.json
node tools/qa/collect-tablet-metrics.mjs --navigate-existing \
  --cdp http://127.0.0.1:9222 --mode standalone --profile-id m9-pwa \
  --expected-release "$FULL_ID" \
  --url https://192.168.1.161:5192/?qa=performance \
  --out /tmp/earthship-m9-pwa-target.json
node tools/qa/collect-tablet-metrics.mjs --profile-only \
  --cdp http://127.0.0.1:9222 --mode browser --profile-id m9-browser \
  --expected-release "$FULL_ID" \
  --target-proof /tmp/earthship-m9-browser-target.json \
  --url http://192.168.1.161:5190/?qa=performance \
  --out /tmp/earthship-m9-browser-profile.json
node tools/qa/collect-tablet-metrics.mjs --profile-only \
  --cdp http://127.0.0.1:9222 --mode standalone --profile-id m9-pwa \
  --expected-release "$FULL_ID" \
  --target-proof /tmp/earthship-m9-pwa-target.json \
  --url https://192.168.1.161:5192/?qa=performance \
  --out /tmp/earthship-m9-pwa-profile.json
node tools/qa/validate-tablet-metrics.mjs --profile-only --mode browser \
  --profile-id m9-browser --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  /tmp/earthship-m9-browser-profile.json
node tools/qa/validate-tablet-metrics.mjs --profile-only --mode standalone \
  --profile-id m9-pwa --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  /tmp/earthship-m9-pwa-profile.json
~~~

The navigation proofs show that the exact already-open browser tab and installed
PWA target were reused; collection reattaches by those IDs and never opens a
substitute. Compare viewport, DPR, display mode, origin, and all four safe-area
edges with Task 1 canonical profiles. Any delta stops sign-off and keeps every
affected row `blocked-device`.

For a measured delta, copy only the actual probe values from both raw profile
files into `tests/e2e/device-profiles.json`. Repair layout only in the
conditional Task 18 files listed above. Then run this fail-fast source-candidate
block and commit the profile/layout correction without the matrix:

~~~bash
set -euo pipefail
npm test
npx playwright test --project=m9-browser
npx playwright test --project=m9-pwa
npx playwright test --project=m9-pwa-update
npx playwright test --project=laptop-1280x720
npm run build
node tools/qa/check-bundle.mjs dist
node tools/qa/check-matrix.mjs --phase automated docs/qa/ui-audit-matrix.csv
git diff --check
git add tests/e2e/device-profiles.json src/app.css \
  src/lib/ui/Shell.svelte src/lib/ui/Tile.svelte \
  src/lib/ui/StatTile.svelte src/lib/ui/HourlyStrip.svelte \
  src/lib/ui/ThermalLoop.svelte src/lib/ui/ChartCanvas.svelte \
  src/lib/ui/HistoryChart.svelte src/lib/ui/HistorySparkline.svelte \
  src/lib/ui/ChartModal.svelte src/lib/ui/CompassRose.svelte \
  src/lib/ui/Header.svelte src/lib/ui/HeaderAlerts.svelte \
  src/screens/Home.svelte src/screens/Energy.svelte \
  src/screens/Weather.svelte src/screens/Earthship.svelte \
  src/screens/Controls.svelte
if git diff --cached --quiet; then
  echo "measured profile drift produced no scoped correction" >&2
  exit 1
fi
git commit -m "fix: align layout with measured M9 profile"
test -z "$(git status --short)"
~~~

Bind the two raw profiles to their exact same-target proofs and the measured
full release. The updater must reject a missing Task 18 selector, either raw
profile or target proof, mismatched profile IDs/modes/origins/releases, a
canonical profile that differs from the raw values, any release other than
`full-<HEAD^>` independently confirmed by `.releases/current/release.json`, or
anything short of the complete automated gate:

~~~bash
set -euo pipefail
npm test
npx playwright test --project=m9-browser
npx playwright test --project=m9-pwa
npx playwright test --project=m9-pwa-update
npx playwright test --project=laptop-1280x720
npm run build
node tools/qa/check-bundle.mjs dist
test "$(git log -1 --format=%s)" = \
  "fix: align layout with measured M9 profile"
MEASURED_BASE=$(git rev-parse --short=12 HEAD^)
MEASURED_FULL_ID="full-$MEASURED_BASE"
test "$(jq -r ".releaseId" .releases/current/release.json)" = \
  "$MEASURED_FULL_ID"
test "$(jq -r ".releaseMode" .releases/current/release.json)" = "full"
test "$MEASURED_FULL_ID" = "$(jq -r ".releaseId" \
  /tmp/earthship-m9-browser-profile.json)"
test "$MEASURED_FULL_ID" = "$(jq -r ".releaseId" \
  /tmp/earthship-m9-pwa-profile.json)"
node tools/qa/validate-tablet-metrics.mjs --profile-only --mode browser \
  --profile-id m9-browser --expected-release "$MEASURED_FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  /tmp/earthship-m9-browser-profile.json
node tools/qa/validate-tablet-metrics.mjs --profile-only --mode standalone \
  --profile-id m9-pwa --expected-release "$MEASURED_FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  /tmp/earthship-m9-pwa-profile.json
node tools/qa/update-matrix.mjs --task 18 --phase profile-refresh \
  --profile tests/e2e/device-profiles.json \
  --measured-profile /tmp/earthship-m9-browser-profile.json \
  --target-proof /tmp/earthship-m9-browser-target.json \
  --measured-profile /tmp/earthship-m9-pwa-profile.json \
  --target-proof /tmp/earthship-m9-pwa-target.json \
  --expected-release "$MEASURED_FULL_ID" \
  docs/qa/ui-audit-matrix.csv
node tools/qa/check-matrix.mjs --phase automated docs/qa/ui-audit-matrix.csv
git diff --check
git add docs/qa/ui-audit-matrix.csv
git commit -m "docs: refresh measured M9 profile evidence"
test -z "$(git status --short)"
~~~

Re-run the complete gate on the exact evidence HEAD, then derive and promote
new immutable IDs. A documentation-only evidence commit is still part of the
release ID, so no earlier build may be reused without this rerun:

~~~bash
set -euo pipefail
npm test
npx playwright test --project=m9-browser
npx playwright test --project=m9-pwa
npx playwright test --project=m9-pwa-update
npx playwright test --project=laptop-1280x720
npm run build
node tools/qa/check-bundle.mjs dist
node tools/qa/check-matrix.mjs --phase automated docs/qa/ui-audit-matrix.csv
git diff --check
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
SAFE_ID="maintenance-$BASE"
FULL_ID="full-$BASE"
RELEASE_ID="$SAFE_ID" RELEASE_MODE=maintenance \
  node tools/release/build.mjs --reuse-verified
node tools/release/promote.mjs --safe "$SAFE_ID" --full "$FULL_ID" \
  --ca /home/sat/.config/earthship-ui/tls/root-ca.crt
~~~

Accept only `full-verified`. Drive the Task 17 takeover handshake in the already
installed PWA, relaunch the two exact targets, regenerate both target proofs and
raw profiles, and repeat the measurement from the start of this section. Do not
proceed until both measured modes equal the canonical profile and the complete
updated geometry/profile-refresh gates pass.

- [ ] **Rehearse real browser and installed-PWA rollback, then return to full**

Recompute IDs in this independently runnable block and require both existing
CDP targets:

~~~bash
set -euo pipefail
test -z "$(git status --short)"
BASE=$(git rev-parse --short=12 HEAD)
SAFE_ID="maintenance-$BASE"
FULL_ID="full-$BASE"
adb forward tcp:9222 localabstract:chrome_devtools_remote
node tools/release/promote.mjs --rehearse-rollback \
  --safe "$SAFE_ID" --full "$FULL_ID" \
  --ca /home/sat/.config/earthship-ui/tls/root-ca.crt \
  --cdp http://127.0.0.1:9222 \
  --browser-url http://192.168.1.161:5190/?qa=performance \
  --pwa-url https://192.168.1.161:5192/?qa=performance \
  --evidence-out docs/qa/release-rehearsal.json
~~~

The runner first verifies both matching targets and their browser/standalone
modes. After maintenance activation it drives the Task 17 takeover handshake on
those exact targets, waits for `controllerchange`, preserves both target IDs,
and proves browser app marker plus installed-PWA controller/cache/release mode
all changed to the maintenance release. All commands remain disabled and no
mixed bundle or full proxy write survives. It then returns to full through the
same handshake and repeats manifest/proxy/controller/cache/OpenHAB checks on the
same target IDs. It never opens a target or treats a generic reload as worker
takeover proof.
Accept only `full-verified`. Recovery terminal semantics are identical to the
initial promotion; `recovery-failed` is a critical manual-recovery outcome, not
a rollback pass. Never activate the pre-graph or pre-audit release and never
restore unsafe MainUI toggles.

- [ ] **Collect full performance evidence from both real M9 modes**

With full restored, attach to the same existing targets:

~~~bash
set -euo pipefail
BASE=$(git rev-parse --short=12 HEAD)
FULL_ID="full-$BASE"
adb forward tcp:9222 localabstract:chrome_devtools_remote
node tools/qa/collect-tablet-metrics.mjs --navigate-existing \
  --cdp http://127.0.0.1:9222 --mode browser --profile-id m9-browser \
  --expected-release "$FULL_ID" \
  --url http://192.168.1.161:5190/?qa=performance \
  --out /tmp/earthship-m9-browser-target.json
node tools/qa/collect-tablet-metrics.mjs --navigate-existing \
  --cdp http://127.0.0.1:9222 --mode standalone --profile-id m9-pwa \
  --expected-release "$FULL_ID" \
  --url https://192.168.1.161:5192/?qa=performance \
  --out /tmp/earthship-m9-pwa-target.json
node tools/qa/collect-tablet-metrics.mjs \
  --cdp http://127.0.0.1:9222 --mode browser --profile-id m9-browser \
  --expected-release "$FULL_ID" \
  --target-proof /tmp/earthship-m9-browser-target.json \
  --url http://192.168.1.161:5190/?qa=performance \
  --out docs/qa/tablet-performance-browser.json
node tools/qa/collect-tablet-metrics.mjs \
  --cdp http://127.0.0.1:9222 --mode standalone --profile-id m9-pwa \
  --expected-release "$FULL_ID" \
  --target-proof /tmp/earthship-m9-pwa-target.json \
  --url https://192.168.1.161:5192/?qa=performance \
  --out docs/qa/tablet-performance-pwa.json
node tools/qa/validate-tablet-metrics.mjs --mode browser \
  --profile-id m9-browser --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  docs/qa/tablet-performance-browser.json
node tools/qa/validate-tablet-metrics.mjs --mode standalone \
  --profile-id m9-pwa --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  docs/qa/tablet-performance-pwa.json
~~~

Each run records display mode, viewport, DPR, safe-area edges, origin, URL,
build/release ID, CDP target identity, and service-worker/controller identity.
Use CDP heap before/after the capped 30-day interaction and in-page observers
for at least 20 input samples. Require no chart preprocessing main-thread task
over 50 ms, input response at most 100 ms p95 while loading, worker completion
within 3 seconds after the final page, heap increment at most 64 MiB, rendered
points at most `floor(4W)`, and responsive navigation/SSE. A mode/profile/release
mismatch invalidates the evidence.

- [ ] **Complete M9 and laptop sign-off without physical commands**

On the actual M9 browser and installed PWA, both landscape:

- exercise all five routes with no page/card scroll or overlap;
- read white Outdoor/Indoor temperatures, enlarged Indoor, contained Rain, and
  enlarged Sun/Moon from the household viewing distance;
- exercise 4h/24h/7d/30d modal selection and close/focus;
- inspect the smoothed Outdoor line and correctly scaled compass;
- verify the currently observable AQI source, numeric value, freshness, and
  legibility; cite the automated all-states E2E for stale, unavailable, invalid,
  and above-500 behavior;
- exercise only press-and-hold cancellation before the submit threshold; cite
  isolated all-states E2E for pending, complete, failed, `sent-unconfirmed`, and
  `outcome-unknown` rather than manufacturing those states in production;
- verify owned-load requests are the only interactive paths and maintenance mode
  disables them;
- reload the offline aged snapshot;
- exercise dim mode and SSE interruption/recovery; and
- confirm no hidden required content.

Do not add or enable a production fixture mode for sign-off. Repeat geometry on
a laptop at exactly 1280x720 and at its normal larger viewport. Write viewport,
DPR, display mode, all safe-area edges, origin,
build/release SHA, CDP/target identity where applicable, timestamp, pass/fail,
and notes to `docs/qa/real-device-signoff.json`. Do not mark a row passed from a
screenshot alone.

- [ ] **Close the matrix and commit exact evidence**

Only after every matrix row has post-fix evidence, run the final updater and
checker, then commit the evidence.

~~~bash
set -euo pipefail
BASE=$(git rev-parse --short=12 HEAD)
FULL_ID="full-$BASE"
npm test
npx playwright test
npm run build
node tools/qa/check-bundle.mjs dist
node tools/qa/validate-tablet-metrics.mjs --mode browser \
  --profile-id m9-browser --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  docs/qa/tablet-performance-browser.json
node tools/qa/validate-tablet-metrics.mjs --mode standalone \
  --profile-id m9-pwa --expected-release "$FULL_ID" \
  --device-profile tests/e2e/device-profiles.json \
  docs/qa/tablet-performance-pwa.json
node tools/qa/update-matrix.mjs --task 18 --phase device \
  --signoff docs/qa/real-device-signoff.json \
  --performance docs/qa/tablet-performance-browser.json \
  --performance docs/qa/tablet-performance-pwa.json \
  --release-evidence docs/qa/release-rehearsal.json \
  docs/qa/ui-audit-matrix.csv
node tools/qa/check-matrix.mjs docs/qa/ui-audit-matrix.csv
git diff --check
git add tests/e2e/device-profiles.json docs/qa/real-device-signoff.json \
  docs/qa/release-rehearsal.json docs/qa/tablet-performance-browser.json \
  docs/qa/tablet-performance-pwa.json docs/qa/ui-audit-matrix.csv
git commit -m "docs: record tablet UI release sign-off"
~~~

Stage `tests/e2e/device-profiles.json` only if actual remeasurement changed it;
otherwise `git add` leaves it untouched. Expected: automated/live/device gates
all pass, full is active, real installed-PWA rollback is proven, and the matrix
is closed.

After that commit succeeds, the user-authorized optional memory follow-up may
call exactly the configured Hexmem MCP tool `hexmem_remember` once with a concise
non-secret event containing confirmed active build SHA, M9/laptop sign-off,
maintenance/full rollback rehearsal, and OpenHAB contract outcome. Do not use a
direct database write or an unspecified local fallback, and do not store tokens,
live states, or speculative progress. A Hexmem tool failure is reported
separately and does not undo or block the already-proven UI completion.

---

## Specification coverage map

| Approved contract | Implemented and verified by |
| --- | --- |
| Measured M9 browser/PWA plus 1280x720 only | Tasks 1, 9-11, 18 |
| No route/card scrolling or hidden required content | Tasks 8-11, 18 |
| White Home temperatures and approved type hierarchy | Task 9 |
| Working 4/24/168/720 h selection and contained Outdoor line | Tasks 5-7, 9 |
| Median-3 plus EMA chart-only smoothing and raw tooltips | Tasks 5-7 |
| Point/page/memory/worker/performance limits | Tasks 5-7, 18 |
| Parent-sized compass with external gust/max rows | Tasks 7, 9 |
| Race-free truthful state, freshness, cache, and offline | Tasks 3-4, 17 |
| Header alerts and no BTC header/card sparkline | Tasks 7-8 |
| Numeric current AQI and exact freshness/bands | Tasks 3, 10, 13 |
| North Mass left and South Glazing right | Tasks 3, 11 |
| Typed holds, acknowledgements, outcomes, and no replay | Tasks 12, 17 |
| Safe feeder, greywater, override, and circadian ownership | Tasks 2, 14-16 |
| REST backup/readback/rollback and no unapproved actuation | Tasks 13-16, 18 |
| Immutable compatibility, zero-write maintenance, and full releases | Tasks 2, 16, 18 |
| Canonical audit matrix lifecycle and actual-device sign-off | Tasks 1-18 |
