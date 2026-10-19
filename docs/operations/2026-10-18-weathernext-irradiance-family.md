# Preserve the installed irradiance/shade model for WeatherNext

Observed October 18, 2026. Task 8 preparation; this is not production activation, source/model qualification or completed Open-Meteo retirement.

The migration branch had an older ten-parameter thermal model while the installed system uses the corrected fourteen-parameter irradiance/shade family. A WeatherNext cutover must preserve that correction rather than restore the earlier low-sun amplification. The branch now carries the installed family and its fitting, candidate, receipt, projection and UI interfaces. No installed fitted weights were promoted or inherited by a new model.

## Physics and model identity

The preserved model rule is `earthship-native-irradiance-shade-dynamics/v4`. Its heat input uses W/m² directly, with the original native geometry masking solar at nonpositive elevation. It does not divide weak low-elevation radiation by a clear-sky estimate. Four indoor/outdoor shade regimes retain monotone gain constraints, existing stability/temperature/vent limits and analytic fourteen-parameter sensitivities.

The equations and physical shade configuration preserve the installed implementation. The irradiance module differs only by removal of a trailing blank line; the private comparison retains both original and ported source hashes. The configuration preserves the operator's nominal 65% cloth rating and three exterior zones: kitchen, living room, and combined bedroom/bathroom. The rating remains a provisional prior, not measured building attenuation. Mid-to-late May 2027 reinstallation remains subject to operator confirmation; no automatic reinstallation is enabled.

Generic numerical/history readers still understand earlier native families before cutover. Explicit Google production configurations, however, now require the preserved v4 irradiance candidate before collection, geometry preparation, scoring or staging. Google staging also requires all irradiance/joint/context source pins. Unknown or older candidates refuse rather than silently downgrade. The existing scheduled fitter explicitly selects `joint=True, irradiance=True` and fit-evidence v4, matching the installed fitter; its schedule, guards and activation policy are unchanged.

## Complete consumer path

Fresh candidate v4 validation retains original local data, native geometry, fitting/runtime evidence, full loss/support/conditioning replay and immutable source hashes. A genuinely executed bounded synthetic fit tests this path; it is not real-site skill evidence or an admitted production artifact. Tests also admit that fresh fourteen-parameter candidate through the actual receipt helper and prove byte-equal full/receipt Google captures.

Removed outdoor shades are accepted only by the appropriate native family. Native capture, frozen thermal projection and the versioned Google weather context agree on that action domain. Frozen projection performs no filesystem reads. Google originals and their existing causal/unit/unknown-value checks remain intact.

Outcome scoring previously stamped every native pair with the oldest native rule, including the installed newer model. New pairs now carry the verified capture's actual rule; one artifact cohort cannot mix model rules or runtimes. Original retained records are not rewritten. Serving and operational helper pins are updated to the reviewed bytes. Bounded report reuse recognizes only the explicit reviewed current/prior/installed score implementations and their exact helper identities; original entry/final binding checks, chronology, source-inventory verification, scoped cache bounds and unknown-helper fallback remain.

Complete-package tests exposed two exporter gaps: a remaining 72-source staging cap and omission of `thermal-shade-context.json` from both the Git archive request and member selection. Staging now uses the same bounded 96-source constant as capture/archive retention, and explicitly retains the declared shade context. The full 83-file fitted base plus the separate native family/configuration closure round-trips. Changing the staged shade context refuses verification. Per-file/archive byte bounds, interpreter/ownership checks, process resources and operational deadlines remain unchanged. Package-only test metadata is not numerical qualification.

The UI parser now matches the already signed-off live parser: it recognizes native joint/irradiance rules and removed shades for those families, while retaining the original family's installed-only domain. All authority, expiry, geometry, physical, confidence and graduation checks remain. Live UI files were not edited.

## Retained real-data parity

A read-only comparison created at **2026-10-18T23:30:07.922001+00:00** and completed at **2026-10-18T23:30:08.640245+00:00** used the actual retained 2026-10-18T20:15:15+00:00 model origin, its original fourteen coefficients, initial state, action context, native geometry and origin-eligible Google snapshot. The new implementation reproduced all **288 five-minute forcings and 24 hourly air/mass trajectory rows exactly**, including canonical output bytes, in **0.718 seconds / 92544 KiB peak RSS**.

Private immutable receipt: `3a5e101c87bca4d15ccc3c272f29d7f12742fe81e57ffe55bd685208ff17a164`. This is `RETAINED_ORIGIN_COMPARISON_ONLY`. Old coefficients were used solely to verify the port. It was not a fresh forecast, model fit/admission, measured outcome or production publication. Originals remain private (mode 0600; Vite filesystem HEAD returned 403).

## Verification and remaining work

New tests first failed on missing model modules/fitting interfaces, removed-shade rejection, incorrect score labels, stale serving/operational pins, older-family production admission and incomplete deployment source packaging. Each was diagnosed before correction. Existing data-address, receipt/deployment-pin, source and fitting validators were preserved.

Final relevant Python execution/model/receipt/staging/daily-fitting suite: **125 passed in 49.51 seconds**, using CI's exact Solar_PV dependency. After the trailing-newline cleanup, all nine irradiance-family tests passed again in 3.32 seconds, including fresh source-bound fitting and actual receipt/full-capture parity. Full pinned WeatherNext suite: **175 passed in 5.877 seconds**. Full frontend suite: **2,598 passed across 172 files in 43.37 seconds**; build passed in **1.53 seconds**, with the existing chunk-size warning. The earlier broader native physical/fit/artifact/forecast/scoring checks passed 150 tests; bounded report reuse and genuine-model integration checks passed together in 21 cases, including original-mutation rejection and caller isolation.

Production units and their matching overrides still execute sealed-stage sources, not the edited worktree source tree. No service configuration, installed candidate/receipt, provider selection, current shade/vent state, resource policy, notification or equipment authority changed.

Prepare the final Google-only removal/source closure before actual release fitting. Detach all incumbent controls, old pending weather targets and provider state; preserve qualified local histories and physical configuration. Complete the required variable/regime/outcome and prospective qualification, release ownership/retained attempts, attended cutover, natural serving/degraded verification and final whole-branch review. Fresh source-bound fitting is still required; this preservation increment does not qualify the incumbent weights or complete the migration.
