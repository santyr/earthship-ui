# README Screenshots, Service Operations, and Git Identity Design

**Date:** 2026-07-19

## Goal

Bring the repository landing page up to date with the running Earthship Console:

- show every user-facing route with a current live screenshot;
- document the supported service restart and diagnosis commands;
- replace the stale design-phase status; and
- normalize all published commit authorship and committer identity to the
  repository owner's `santyr <shane@mr-technical.com>` identity.

## Screenshot Set

The canonical set contains one PNG for each route in `src/routes.js`:

| Route | Asset |
| --- | --- |
| Home | `docs/screenshots/home.png` |
| Energy | `docs/screenshots/energy.png` |
| Weather | `docs/screenshots/weather.png` |
| Earthship | `docs/screenshots/earthship.png` |
| Controls | `docs/screenshots/controls.png` |

Each screenshot will:

- use the primary Lenovo Tab M9 landscape viewport, exactly 1340 by 800 pixels;
- come from the live household service at `http://127.0.0.1:5190`;
- show current live telemetry after the route has settled;
- capture the viewport rather than a scrolling full-page image;
- contain no open modal, pressed control, debug overlay, or browser chrome; and
- be accepted only when the route produces no page error, console error,
  failed request, or HTTP response with status 400 or higher.

The capture process is read-only. It will not activate, press, or send commands
to any household control.

## README Presentation

Add a `Screenshots` section near the top of `README.md`, after the project
summary and current status. Use one subsection per route with a full-width
Markdown image. Each image will link to the same PNG so GitHub readers can open
the original 1340 by 800 asset.

The README status will describe the five-screen console as implemented and
running rather than in design phase. Existing configuration guidance remains
intact.

## Service Operations

Add a `Service operations` section to `README.md` documenting the supported
user-level systemd workflow:

```bash
systemctl --user daemon-reload
systemctl --user restart earthship-ui.service
systemctl --user status earthship-ui.service --no-pager -l
```

The section will also include:

- `journalctl --user -u earthship-ui.service -n 100 --no-pager` for recent
  logs;
- a `curl` request to `http://127.0.0.1:5190/src/App.svelte` as the direct
  Svelte-transform health check; and
- an explicit instruction to restart and verify the service after branch
  switches, fast-forwards, or other tree-wide checkout changes.

## Commit Identity and Published-History Normalization

Set the repository-local Git identity to:

```text
santyr <shane@mr-technical.com>
```

All new commits for this work will use that identity. After the README and
screenshot commit is verified, rewrite every commit reachable from `main` so
both author and committer are `santyr <shane@mr-technical.com>`. Preserve each
commit's tree, message, parent topology, author date, and committer date.

The rewrite covers both published branches:

- `main`; and
- `build/console-ui`, mapped to the rewritten equivalent of its current tip.

No tags currently exist. Before rewriting, fetch the remote, record exact
remote object IDs for lease checks, and create a recovery bundle outside the
repository under `/tmp`. Perform the rewrite in an isolated temporary clone so
the running Vite watcher never observes a tree-wide rewrite. Publish both
rewritten branches using explicit `--force-with-lease=<ref>:<old-object-id>`
guards, never an unguarded force push.

After the remote update, move the local branch refs to their rewritten object
IDs without rewriting the identical checked-out files. Restart and verify the
live service if any watched working-tree file changes during synchronization.

The pre-existing untracked `test-results/` directory is user-owned and must
remain unmodified and uncommitted.

## Verification

Completion requires fresh evidence that:

1. all five PNGs exist, decode successfully, and are exactly 1340 by 800;
2. each captured route rendered with no browser, network, or HTTP error;
3. every README image target resolves to its tracked PNG;
4. the restart commands and health-check URL match the installed service;
5. the documentation diff contains no secrets or unintended live-control
   actions;
6. every commit reachable from both rewritten local and remote branches has
   author and committer `santyr <shane@mr-technical.com>`;
7. local and remote branch tips match their intended rewritten object IDs;
8. the live service remains active and a clean browser can render the Home
   route without errors; and
9. `test-results/` remains the only pre-existing untracked path and is not
   staged.
