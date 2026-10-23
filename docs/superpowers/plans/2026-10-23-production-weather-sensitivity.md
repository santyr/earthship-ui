# Production Weather Sensitivity Integration Plan

> Execute this remaining Task 8/10/11 integration using the existing inline, test-driven workflow. The user has already authorized implementation and deployment after the required checks pass.

**Goal:** Make the three predeclared deterministic weather cases available as read-only production guidance, separately from unqualified joint probabilities.

**Architecture:** Reuse the frozen scenario protocol and original-producer bridge. Read the completed current household energy/plan and its verified native model/environment. Publish a bounded original and a curated, confirmed cache through the existing fixed-report server. Show the cases in an expandable Earthship detail, leaving the weather modals' requested text cleanup intact.

**Tech stack:** Existing Python source-bound projection, managed resource pool, immutable private state, Svelte/Vite fixed GET reports, pytest/Vitest/Playwright.

**Spec:** [Approved capability plan](weathernext3-capabilities-20261021.md), Tasks 8, 10 and 11. This closes an installation/consumer gap found during the completion audit; it does not add another model search.

## Design decisions and constraints

- Keep central, half-solar, and +3 C/1.2-times-solar cases exactly as predeclared. Keep load, initial state, capacity and actions fixed. Use the retained thermal model and environment, with central thermal trajectory parity within 1e-9 F.
- Display component PV before its electrical correction and conditional nominal storage as their actual quantities. These sensitivities are separate from the active calibrated central forecast. Do not borrow its gain or claim measured usable capacity, action benefit or risk probability.
- Support the confirmed-production temperature context explicitly. Preserve its original selected points and initial-state interpolation; apply declared constructed temperature deltas to those points and retain original raw solar interval semantics. Legacy conditioning remains replayable.
- Existing source/binary/admission/clock guards stay enforced. New adapters remain outside fitted numerical closures; verify those closures byte-for-byte before deciding whether a genuine refit is needed.
- The actual v1 scenario child currently returns a v2 reply after a package import shadows its request-type flag. Reproduce and repair that protocol bug before using the adapter.
- No new cloud acquisition, observation query, fit, actuator call, provider or host-resource allowance. Use only existing retained household originals. Joint outputs stay withheld without their eight qualified template dates and physical targets.
- The actual report measured 7,649,716 bytes; naive gzip is 3,845,063 bytes. Reuse source-package chunks once per source generation and byte-pinned parent energy/plan originals already retained in native evidence. A measured factored payload is about 171.8 KiB per issue before final reference metadata, plus 3.73 MB per source generation. Reconstruct the exact original bytes on replay. Parents must remain retained; introduce no eviction or cleanup.
- Use an optional 256 MiB original-storage ceiling and reserve 384 MiB of the existing shared 2 GiB/10,000-object namespace for core work. Check every write and disk reserve. Hourly generation is the target only if final measured bytes/runtime fit; missing fresh originals or capacity means explicit unavailability without changing core services. Final writer measurements remain required.
- Fixed GET only; private paths, source capsules and raw household extracts stay private. Missing/stale/withdrawn data must not break the existing Earthship page.

## Tasks

- [x] **Original-producer compatibility.** Add normal failing tests for v1/v2 protocol separation and confirmed-production conditioning. Fix the request-type shadowing and add the explicit conditioning branch without changing legacy outputs. Run affected native/scenario/component replay tests and the actual frozen production input probe. Preserve central parity and original fit clocks.
- [x] **Bounded production writer.** Select completed current originals and their verified interpreter; reuse the original-input scenario worker. Add original/confirmed-view retention with exact readback, no-op repeated issue behavior, private path ownership, expiry and shared/optional capacity checks. Measure actual bytes/runtime and test failures, source changes and interrupted publication.
- [x] **Fixed report and Earthship consumer.** Add strict typed public parsing and an existing-pattern fixed route with bounded receipt verification. Add a collapsed Weather sensitivity detail with the three cases and their quantities. Test source identity, stale/absent/malformed/zero values, no probabilities or mutations, keyboard behavior and both console sizes.
- [ ] **Review and release.** Verify normal affected Python/frontend/build/browser/SDK and original-producer checks; review the new immutable patch once and fix findings. Publish/merge after required CI, install only the new sidecar and UI reader, verify current source/environment/rollback, actual generated cases and real UI. Preserve existing production models and all originals.
- [ ] **Finish the original goal.** Update the per-model/capability/delivery records and all 70 checklist requirements, 13 recommendations, 30 regressions and global constraints against current evidence. Export the late evidence delta, publish the final documentation and complete the goal only after this audit passes.

Local verification: 80 affected Python tests, all 3,037 frontend tests (199 files), build and four browser cases passed. The actual 17:45:15 household issue produced three confirmed cases in 51.01 s at 197,464 KiB peak RSS in a private integration namespace. Exact repeat replay took 44.50 s and retained its first report/cache/generation/confirmation identities. Measured retention is 175,591 bytes per issue plus 3,736,880 bytes per source generation, about 121,734,032 bytes for 28 days hourly. This is not yet an installed production timer or UI deployment.
