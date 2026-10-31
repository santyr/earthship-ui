# Disposable browser verification

`npm run test:e2e -- --list` selects maintained fixtures. `npm run test:e2e:sensors -- --list` selects the separate, nonempty opt-in sensor integration suite. Both block service workers and use one worker; compiler pools and Chromium raster/process settings stay bounded within the original resource limits.

General fixtures create ephemeral loopback Vite servers through `fixture-server.js`, with test caches under `.superpowers/test-cache`. Shared browser routing admits only those owned origins. Unstubbed REST/report reads are unavailable; permitted fixture mutations are the in-memory shade preview and explicitly intercepted advice feedback. No household credential or proxy target is inherited. Use the existing household resource launcher for browser/build jobs; do not raise task limits to start a browser.

The `sensors` project retains actual authenticated OpenHAB REST/SSE and synthetic MQTT transitions at both supported tablet sizes. It requires `SENSOR_INTEGRATION=1`, an existing Python environment with the pinned dependencies in `services/lorawan/requirements.txt`, and the disposable `deploy/lorawan/compose.test.yaml` stack including its `chirpstack` profile. Set `SENSOR_TEST_PYTHON` to that environment's absolute interpreter path (default `/tmp/earthship-sensor-test-venv/bin/python`). The harness always adds `-B` and disables Python bytecode.

Restore/provision and start that stack only as a separate explicitly isolated integration qualification. `services/lorawan/provision.py` creates private synthetic configuration under this checkout's `.superpowers/lorawan-private`; it refuses to rotate an existing fixture. Both integration entrypoints share a Python ownership preflight covering MQTT, PostgreSQL, ingestion, OpenHAB, Redis and ChirpStack, all current-worktree bind mounts, exact published loopback endpoints and the rendered simulator configuration. Ownership is revalidated before HTTP/MQTT effects and lifecycle/database cleanup; Docker lifecycle/exec actions target inspected container IDs, and a replacement stack requires a new qualification. A foreign/production stack or missing opt-in fails closed. The fixture token stays private and server-side. Browser screenshots go to Playwright's output directory.

`fixture` coverage of the sensor component is additional synthetic transport/freshness/geometry coverage. It does not qualify the MQTT/PostgreSQL/OpenHAB integration, radio hardware or physical enrollment. The retired application route remains retired.


The general fixture project builds the complete app in both original release modes before Chromium starts,
then serves its assets from disposable loopback servers with the same backend
isolation and in-memory shade preview. Compiler/browser heaps run sequentially
inside the original 1 GiB cap. No routes, assertions or resource limits are reduced.
Custom sensor harness plugins retain their owned Vite server and sensor-only
qualification does not add a general-app build. Both server paths close only
connections accepted by their own listener.
