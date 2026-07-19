# README Screenshots and Git Identity Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish five live tablet-resolution screenshots and a verified service-restart guide in the README, then normalize both published branches so every reachable commit is authored and committed by santyr.

**Architecture:** A focused Vitest contract protects the README copy, screenshot links, and PNG dimensions. A temporary Playwright script captures the five read-only live routes at the primary 1340×800 viewport. Git history is rewritten only after the documentation commit passes verification, using a recovery bundle, an isolated mirror clone, atomic lease-protected pushes, and ref-only synchronization back to the live checkout.

**Tech Stack:** Markdown, PNG, Svelte/Vite live service, Playwright 1.61.1, Vitest 4.1.10, Git 2.43.0, user-level systemd.

## Global Constraints

- Capture exactly five routes: `home`, `energy`, `weather`, `earthship`, and `controls`.
- Capture current live household telemetry at exactly 1340×800 pixels.
- Do not click, press, focus, or issue any household control command.
- Store images as `docs/screenshots/<route>.png`.
- Document `earthship-ui.service` restart, status, logs, and direct Svelte-transform health checks in `README.md`.
- Use `santyr <shane@mr-technical.com>` for every new commit, author, and committer identity.
- Rewrite both published branches: `main` and `build/console-ui`.
- Preserve commit trees, messages, parent topology, author dates, and committer dates.
- Publish rewritten refs only with explicit atomic `--force-with-lease` guards.
- Perform history rewriting in `/tmp`, never in the live Vite-watched checkout.
- Keep the pre-existing untracked `test-results/` directory unmodified, unstaged, and uncommitted.

---

## File Map

- Create `tests/readme-documentation.test.js`: README copy, image-link, PNG-signature, and 1340×800 dimension contract.
- Create `docs/screenshots/home.png`: live Home route at the M9 viewport.
- Create `docs/screenshots/energy.png`: live Energy route at the M9 viewport.
- Create `docs/screenshots/weather.png`: live Weather route at the M9 viewport.
- Create `docs/screenshots/earthship.png`: live Earthship route at the M9 viewport.
- Create `docs/screenshots/controls.png`: live Controls route at the M9 viewport.
- Modify `README.md`: current status, full-width screenshot gallery, and service operations guide.
- Create `/tmp/capture-earthship-readme-screenshots.mjs`: temporary read-only capture utility; never commit it.
- Create `/tmp/earthship-ui-pre-santyr-rewrite-<old-main>.bundle`: temporary recovery bundle; never commit it.
- Create `/tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git`: isolated mirror used for history rewriting; never commit it.

---

### Task 1: Add and Satisfy the README Documentation Contract

**Files:**
- Create: `tests/readme-documentation.test.js`
- Create: `docs/screenshots/home.png`
- Create: `docs/screenshots/energy.png`
- Create: `docs/screenshots/weather.png`
- Create: `docs/screenshots/earthship.png`
- Create: `docs/screenshots/controls.png`
- Modify: `README.md`
- Create temporarily: `/tmp/capture-earthship-readme-screenshots.mjs`

**Interfaces:**
- Consumes: the live service at `http://127.0.0.1:5190`, canonical route names from `src/routes.js`, and Playwright from `/home/sat/earthship-ui/node_modules/playwright/index.mjs`.
- Produces: five tracked 1340×800 PNGs and a README whose asset paths and restart commands are protected by Vitest.

- [ ] **Step 1: Reconfirm the safe starting state and santyr identity**

Run:

```bash
git status --short
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
systemctl --user is-active earthship-ui.service
curl --fail --silent --show-error --output /dev/null \
  http://127.0.0.1:5190/src/App.svelte
```

Expected:

- `git status --short` lists only `?? test-results/`;
- both identities are `santyr <shane@mr-technical.com>`;
- the service prints `active`; and
- the module request exits zero.

- [ ] **Step 2: Write the failing documentation contract**

Create `tests/readme-documentation.test.js` with:

```js
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const README_URL = new URL('../README.md', import.meta.url);
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const ROUTES = [
  ['home', 'Home'],
  ['energy', 'Energy'],
  ['weather', 'Weather'],
  ['earthship', 'Earthship'],
  ['controls', 'Controls'],
];

function pngDimensions(buffer) {
  expect(buffer.subarray(0, 8).equals(PNG_SIGNATURE)).toBe(true);
  expect(buffer.subarray(12, 16).toString('ascii')).toBe('IHDR');
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

describe('README documentation', () => {
  const readme = readFileSync(README_URL, 'utf8');

  it('describes the implemented five-screen console', () => {
    expect(readme).toContain('**Status:** implemented and running');
    expect(readme).toContain('## Screenshots');
  });

  it.each(ROUTES)('links the %s screenshot and preserves M9 dimensions', (route, title) => {
    const relativePath = `docs/screenshots/${route}.png`;
    expect(readme).toContain(`[![${title} page](${relativePath})](${relativePath})`);

    const image = readFileSync(new URL(`../${relativePath}`, import.meta.url));
    expect(pngDimensions(image)).toEqual({ width: 1340, height: 800 });
  });

  it('documents the supported service recovery workflow', () => {
    expect(readme).toContain('## Service operations');
    expect(readme).toContain('systemctl --user daemon-reload');
    expect(readme).toContain('systemctl --user restart earthship-ui.service');
    expect(readme).toContain('systemctl --user status earthship-ui.service --no-pager -l');
    expect(readme).toContain('journalctl --user -u earthship-ui.service -n 100 --no-pager');
    expect(readme).toContain('http://127.0.0.1:5190/src/App.svelte');
    expect(readme).toContain('branch switches, fast-forwards, or other tree-wide checkout changes');
  });
});
```

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
npm test -- tests/readme-documentation.test.js
```

Expected: FAIL because the README has the stale design-phase status and the five screenshot files do not exist.

- [ ] **Step 4: Create the temporary read-only screenshot capture utility**

Create `/tmp/capture-earthship-readme-screenshots.mjs` with:

```js
import { chromium } from '/home/sat/earthship-ui/node_modules/playwright/index.mjs';

const routes = ['home', 'energy', 'weather', 'earthship', 'controls'];
const outputDirectory = '/tmp/earthship-ui-readme-screenshots-history/docs/screenshots';
const browser = await chromium.launch({ headless: true });
const results = [];

for (const route of routes) {
  const context = await browser.newContext({
    viewport: { width: 1340, height: 800 },
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => {
    errors.push(`pageerror: ${error.message}`);
  });
  page.on('requestfailed', (request) => {
    const reason = request.failure()?.errorText ?? 'unknown';
    errors.push(`requestfailed: ${request.method()} ${request.url()} ${reason}`);
  });
  page.on('response', (response) => {
    if (response.status() >= 400) {
      errors.push(`response: ${response.status()} ${response.url()}`);
    }
  });

  const response = await page.goto(`http://127.0.0.1:5190/#/${route}`, {
    waitUntil: 'domcontentloaded',
    timeout: 20_000,
  });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(3_000);

  const rendered = await page.evaluate((expectedRoute) => ({
    appChildren: document.querySelector('#app')?.children.length ?? 0,
    hash: location.hash,
    width: innerWidth,
    height: innerHeight,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    openDialogs: document.querySelectorAll('[role="dialog"]:not([hidden])').length,
    errorOverlay: Boolean(document.querySelector('vite-error-overlay')),
    expectedRoute,
  }), route);

  if (response?.status() !== 200) errors.push(`document: ${response?.status()}`);
  if (rendered.appChildren < 1) errors.push('render: #app is empty');
  if (rendered.hash !== `#/${route}`) errors.push(`route: ${rendered.hash}`);
  if (rendered.width !== 1340 || rendered.height !== 800) {
    errors.push(`viewport: ${rendered.width}x${rendered.height}`);
  }
  if (rendered.horizontalOverflow) errors.push('layout: horizontal overflow');
  if (rendered.openDialogs > 0) errors.push(`dialogs: ${rendered.openDialogs}`);
  if (rendered.errorOverlay) errors.push('vite: error overlay visible');
  if (errors.length > 0) {
    throw new Error(`${route} failed verification:\n${errors.join('\n')}`);
  }

  const path = `${outputDirectory}/${route}.png`;
  await page.screenshot({ path, fullPage: false, type: 'png' });
  results.push({ route, path, ...rendered });
  await context.close();
}

await browser.close();
console.log(JSON.stringify(results, null, 2));
```

- [ ] **Step 5: Capture all five live routes**

Run:

```bash
mkdir -p docs/screenshots
node /tmp/capture-earthship-readme-screenshots.mjs
```

Expected:

- exit code zero;
- five JSON result objects;
- every result reports `1340x800`, no overflow, no dialogs, and a non-empty app; and
- exactly five new PNGs appear under `docs/screenshots/`.

- [ ] **Step 6: Inspect each screenshot visually**

Open each generated file with the local image viewer:

```text
docs/screenshots/home.png
docs/screenshots/energy.png
docs/screenshots/weather.png
docs/screenshots/earthship.png
docs/screenshots/controls.png
```

Expected for every image:

- the route title and navigation state match the filename;
- the complete 1340×800 console viewport is visible;
- live values have settled;
- no modal, pressed control, debug overlay, clipping, or browser chrome appears; and
- no secrets or credentials are visible.

- [ ] **Step 7: Update the README**

Replace the stale status line with:

```markdown
**Status:** implemented and running on the household LAN. Five tablet-first
screens provide live monitoring and safety-gated controls.
```

Add this section after the status:

```markdown
## Screenshots

Captured from the live household console at the primary Lenovo Tab M9
landscape viewport (1340×800).

### Home

[![Home page](docs/screenshots/home.png)](docs/screenshots/home.png)

### Energy

[![Energy page](docs/screenshots/energy.png)](docs/screenshots/energy.png)

### Weather

[![Weather page](docs/screenshots/weather.png)](docs/screenshots/weather.png)

### Earthship

[![Earthship page](docs/screenshots/earthship.png)](docs/screenshots/earthship.png)

### Controls

[![Controls page](docs/screenshots/controls.png)](docs/screenshots/controls.png)
```

Add this section before `## Config (not committed)`:

````markdown
## Service operations

The household runtime is the user-level `earthship-ui.service`, which serves
the Vite application on port 5190.

Reload the installed unit definition and restart the service:

```bash
systemctl --user daemon-reload
systemctl --user restart earthship-ui.service
systemctl --user status earthship-ui.service --no-pager -l
```

Inspect recent logs:

```bash
journalctl --user -u earthship-ui.service -n 100 --no-pager
```

Verify that Vite is transforming Svelte modules:

```bash
curl --fail --silent --show-error --output /dev/null \
  http://127.0.0.1:5190/src/App.svelte
```

Restart and verify the service after branch switches, fast-forwards, or other
tree-wide checkout changes. Vite hot reload is not a deployment substitute for
those operations.
````

- [ ] **Step 8: Run the focused test and verify GREEN**

Run:

```bash
npm test -- tests/readme-documentation.test.js
```

Expected: one test file passes with seven passing cases: one status case, five route cases, and one service-operations case.

- [ ] **Step 9: Run documentation and repository safety checks**

Run:

```bash
git diff --check
git status --short
git diff -- README.md tests/readme-documentation.test.js
git diff --stat
git grep -n -E '(gho_|ghp_|OPENHAB_TOKEN=|Authorization: Bearer|api[_-]?token)' \
  -- README.md docs/screenshots tests/readme-documentation.test.js
```

Expected:

- no whitespace errors;
- only README, the documentation test, and five screenshots are new or modified;
- `test-results/` remains untracked and unstaged; and
- the secret-pattern scan returns no matches.

- [ ] **Step 10: Run the full verification suite**

Run:

```bash
npm test
npm run build -- --outDir /tmp/earthship-ui-readme-build
node /tmp/capture-earthship-readme-screenshots.mjs
systemctl --user is-active earthship-ui.service
```

Expected:

- all Vitest files and tests pass;
- the production build exits zero;
- the second live capture refreshes all five PNGs with zero route errors; and
- the service prints `active`.

- [ ] **Step 11: Commit only the documentation deliverable as santyr**

Run:

```bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git add README.md tests/readme-documentation.test.js \
  docs/screenshots/home.png docs/screenshots/energy.png \
  docs/screenshots/weather.png docs/screenshots/earthship.png \
  docs/screenshots/controls.png
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: add console screenshots and restart guide"
```

Expected:

- both identities are `santyr <shane@mr-technical.com>`;
- the staged-name list contains exactly seven intended files;
- `test-results/` is not staged; and
- the commit succeeds.

---

### Controller Integration Checkpoint

After Task 1's implementer and reviewer both approve the deliverable, the
primary agent fast-forwards `main` to `docs/readme-screenshots-history` from
the live checkout. Verify that only documentation, test, and screenshot files
change, that `test-results/` remains untouched, and that the live service stays
healthy. Task 2 begins only after `main` contains the reviewed documentation
commit.

---

### Task 2: Rewrite and Publish All History as santyr

**Files:**
- Create temporarily: `/tmp/earthship-ui-pre-santyr-rewrite-<old-main>.bundle`
- Create temporarily: `/tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git`
- Modify: local refs `refs/heads/main` and `refs/heads/build/console-ui`
- Modify remotely: GitHub refs `refs/heads/main` and `refs/heads/build/console-ui`

**Interfaces:**
- Consumes: the fully verified documentation commit from Task 1, remote branch object IDs, and the approved identity `santyr <shane@mr-technical.com>`.
- Produces: two local and two remote branch refs whose complete reachable histories use the santyr author and committer identity.

- [ ] **Step 1: Fetch and record immutable pre-rewrite state**

Run:

```bash
git fetch origin
git status --short
git rev-parse refs/heads/main
git rev-parse refs/heads/build/console-ui
git rev-parse refs/remotes/origin/main
git rev-parse refs/remotes/origin/build/console-ui
git rev-list --count refs/heads/main
git rev-list --count refs/remotes/origin/build/console-ui
git shortlog -sne refs/heads/main
gh auth status
```

Record these exact values for later commands:

```text
OLD_LOCAL_MAIN
OLD_LOCAL_BUILD
OLD_REMOTE_MAIN
OLD_REMOTE_BUILD
MAIN_COMMIT_COUNT
BUILD_COMMIT_COUNT
```

Expected:

- only `test-results/` is untracked;
- the active GitHub account is `santyr`;
- `main` contains the new documentation commit; and
- the shortlog still reports the pre-rewrite mixture of Hex and santyr.

- [ ] **Step 2: Create and verify the recovery bundle outside the repository**

Run with the recorded main object ID:

```bash
git bundle create \
  /tmp/earthship-ui-pre-santyr-rewrite-${OLD_LOCAL_MAIN}.bundle \
  refs/heads/main refs/remotes/origin/build/console-ui
git bundle verify \
  /tmp/earthship-ui-pre-santyr-rewrite-${OLD_LOCAL_MAIN}.bundle
```

Expected: bundle verification reports both refs and completes successfully.

- [ ] **Step 3: Create the isolated mirror and pin its two rewrite inputs**

Run:

```bash
git clone --mirror /home/sat/earthship-ui \
  /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git \
  update-ref refs/heads/main "${OLD_LOCAL_MAIN}"
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git \
  update-ref refs/heads/build/console-ui "${OLD_REMOTE_BUILD}"
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git \
  remote add github https://github.com/santyr/earthship-ui.git
```

Expected: the isolated `main` matches the local documentation tip, while the
isolated `build/console-ui` matches the current published build branch.

- [ ] **Step 4: Rewrite author and committer identity in the isolated mirror**

Run:

```bash
env FILTER_BRANCH_SQUELCH_WARNING=1 \
  git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git filter-branch \
  --force \
  --env-filter '
export GIT_AUTHOR_NAME="santyr"
export GIT_AUTHOR_EMAIL="shane@mr-technical.com"
export GIT_COMMITTER_NAME="santyr"
export GIT_COMMITTER_EMAIL="shane@mr-technical.com"
' \
  -- refs/heads/main refs/heads/build/console-ui
```

Expected: both refs are rewritten successfully and the live checkout remains untouched.

- [ ] **Step 5: Prove the rewrite preserved content and topology**

Run:

```bash
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git diff --exit-code \
  refs/original/refs/heads/main refs/heads/main
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git diff --exit-code \
  refs/original/refs/heads/build/console-ui refs/heads/build/console-ui
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git rev-list --count refs/heads/main
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git rev-list --count \
  refs/heads/build/console-ui
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git log \
  --format='%an <%ae>|%cn <%ce>' \
  refs/heads/main refs/heads/build/console-ui | sort -u
```

Expected:

- both diffs exit zero;
- commit counts equal `MAIN_COMMIT_COUNT` and `BUILD_COMMIT_COUNT`; and
- the identity output contains exactly:

```text
santyr <shane@mr-technical.com>|santyr <shane@mr-technical.com>
```

- [ ] **Step 6: Confirm remote leases immediately before publishing**

Run:

```bash
git ls-remote https://github.com/santyr/earthship-ui.git \
  refs/heads/main refs/heads/build/console-ui
```

Expected:

- `refs/heads/main` still equals `OLD_REMOTE_MAIN`; and
- `refs/heads/build/console-ui` still equals `OLD_REMOTE_BUILD`.

Stop without pushing if either object ID differs.

- [ ] **Step 7: Atomically publish both rewritten branches with explicit leases**

Run:

```bash
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git push github --atomic \
  --force-with-lease=refs/heads/main:${OLD_REMOTE_MAIN} \
  --force-with-lease=refs/heads/build/console-ui:${OLD_REMOTE_BUILD} \
  refs/heads/main:refs/heads/main \
  refs/heads/build/console-ui:refs/heads/build/console-ui
```

Expected: both forced updates succeed in one atomic remote transaction.

- [ ] **Step 8: Synchronize local refs without rewriting watched files**

Read the rewritten IDs:

```bash
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git rev-parse refs/heads/main
git -C /tmp/earthship-ui-santyr-rewrite-${OLD_LOCAL_MAIN}.git rev-parse \
  refs/heads/build/console-ui
```

Record them as `NEW_MAIN` and `NEW_BUILD`, then run:

```bash
git fetch origin \
  +refs/heads/main:refs/remotes/origin/main \
  +refs/heads/build/console-ui:refs/remotes/origin/build/console-ui
git update-ref refs/heads/main "${NEW_MAIN}" "${OLD_LOCAL_MAIN}"
git update-ref refs/heads/build/console-ui "${NEW_BUILD}" "${OLD_LOCAL_BUILD}"
git status --short
```

Expected:

- local and remote-tracking refs update;
- the checked-out tree and index remain identical;
- no tracked file is modified; and
- only `test-results/` remains untracked.

Stop and diagnose instead of resetting if any tracked-file change appears.

- [ ] **Step 9: Verify all local and remote history and identity invariants**

Run:

```bash
git rev-parse refs/heads/main refs/remotes/origin/main
git rev-parse refs/heads/build/console-ui \
  refs/remotes/origin/build/console-ui
git log --format='%an <%ae>|%cn <%ce>' \
  refs/heads/main refs/heads/build/console-ui | sort -u
git rev-list --count refs/heads/main
git rev-list --count refs/heads/build/console-ui
git config --local --get user.name
git config --local --get user.email
git status --short
```

Expected:

- each local branch ID equals its remote-tracking branch ID;
- the only history identity is santyr for both author and committer;
- commit counts equal the recorded pre-rewrite counts;
- local defaults are `santyr` and `shane@mr-technical.com`; and
- only `test-results/` is untracked.

- [ ] **Step 10: Run final repository and live-service verification**

Run:

```bash
npm test
npm run build -- --outDir /tmp/earthship-ui-post-rewrite-build
systemctl --user is-active earthship-ui.service
curl --fail --silent --show-error --output /dev/null \
  http://127.0.0.1:5190/src/App.svelte
node /tmp/capture-earthship-readme-screenshots.mjs
git status --short
```

Expected:

- all tests pass;
- the build exits zero;
- the service is active;
- the Svelte module health check exits zero;
- all five browser routes recapture with no errors at 1340×800; and
- only `test-results/` remains untracked.

- [ ] **Step 11: Record the verified durable outcome**

Store a private Hexmem event containing:

- the new `main` and `build/console-ui` object IDs;
- both remote lease-protected force updates;
- exact author/committer identity verification;
- screenshot paths and 1340×800 dimensions;
- test, build, and clean-browser outcomes; and
- confirmation that `test-results/` remained untouched.

Expected: Hexmem returns a stored event reference.
