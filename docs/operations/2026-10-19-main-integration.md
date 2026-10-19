# Main integration — October 19, 2026

The operator requested merging all completed work into remote main. The combined WeatherNext PR retains the histories of PR #33 (shade-regime/hallway-high correction) and PR #34 (manual/Lightning-only feeder scope), alongside PR #35's Google-only migration and forecast closure.

The newer WeatherNext implementation already contained the completed production behavior from the two earlier branches. Their remaining differences were historical rollout documents and regression coverage. Conflicts retain the Google-only source readers, the trailing-hour irradiance correction, original source/runtime guards and manual/Lightning-only feeder display policy. No production source or deployment definition changes relative to verified release `fdf198a7934c8eb313b34173cdaffea817e8c8c9`.

Restored pre-cutover deployment tests now check the current contract: Google admission requires the preserved irradiance model family, and a separately verified fresh Google runtime need not import a previous model's runtime. Original package/source checks remain covered. Historical rollout records retain their original dates and provisional accuracy limits.

Validation of the combined tree:

- All 2,573 frontend tests across 170 files passed.
- All 61 affected shade math, fit, artifact, forecast, deployment and handoff regressions passed.
- Production build passed with the existing bundle-size advisory.
- Every production file matches the previously qualified release; its full hosted checks, including all three OpenHAB shards, forecast ML, receipt integrity and GitGuardian, passed.
- The earlier [forecast closure](2026-10-19-forecast-closure.md) retains complete baseline verification and live deployment evidence.

The live root checkout and immutable production worktrees are preserved. This source integration performs no fitting, deployment, restart or actuation.
