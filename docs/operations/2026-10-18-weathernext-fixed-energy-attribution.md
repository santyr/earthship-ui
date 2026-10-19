# WeatherNext fixed-model PV and storage attribution

Observed 2026-10-18. Task 7 increment, using the existing physical array/storage scenarios as fixed controls. It is not fresh model fitting, a production-provider selection or a completed energy qualification report.

## Model and source boundary

`weather_learning.energy_shadow.compare_fixed_energy` replays an original retained energy receipt and its original household plan through the **actual original numerical runtime**. The runtime manifest is freshly computed from executing source files and must match the retained closure. Supplying saved hashes as though they were the executing source is not allowed. The current outside-model attribution code has its own source manifest; both manifests are checked again before return. Original receipts, curves and identities remain unchanged.

The comparison holds array inventory/orientation, physical model assumptions, native five-minute geometry, terrain profile, initial battery state, declared bank capacity, efficiencies, topology and load inputs fixed. It changes only GHI, station temperature and wind to original WeatherNext values already available at the household origin. Native hourly solar means keep their trailing-interval semantics; temperature and wind use the existing integrator's interpolation policy. Native direct radiation is not substituted into this Erbs-based control: changing decomposition simultaneously would confound the provider attribution. Direct-solar diagnostics remain separate.

The optional original learned AC profile is replayed with its actual retained model/runtime/admission evidence and held fixed for the corresponding Google scenario. Local-only demand learning is not an imported weather-trained model. No daily `k_res`, Kalman state, weather-dependent coefficients, backfill, pending target or error history enters a new Google model. The physical assumptions remain provisional; reusing them here does not qualify usable capacity, electrical losses or action effects.

Potential array DC, modeled captured DC and modeled unaccepted energy remain separate. Missing or origin-ineligible Google weather yields no Google scenario while preserving the verified control. Missing storage evidence does not discard independently valid array potential. Measured available PV, harvested PV, full-charge, evening SoC and overnight trough outcomes remain explicitly absent/NOT_SCORED until their qualified readers supply actual matching outcomes. Harvested PV cannot be relabeled as unconstrained available solar resource.

## Actual retained-input execution

The actual energy control originated at **20:15:15Z / 2:15:15 PM MDT**. Its document SHA256 is `80e0a846e61b3da80add98f08030890232b78d2e8eb1c344b3416ff27d4e6f83`, with bound plan `69c47d5b614c5d2d69d4405cd566505624f7ac440c68de358258f531414912df`. The matching original profiled-load receipt is `d506afe8df2c5c271dcdfe8ce7f2b7f1cf79e6a9539e79946e1e48e9d09a2cdc`.

The selected Google snapshot was `ad52a362ec0b4952b5d8550a9a75671443b3d267c4decc9ba70c2215eea45247`, initialized at 06Z and actually archived at **19:35:48.221224Z**, before that origin. A later acquisition cannot replace it in this original comparison. Its site and all required hourly GHI/temperature/wind values rederived from original native rows.

The fixed runtime digest was `97b850d80329234e94e24be98e6ec2afceb09f90c6b96867983234606510ebc1`; native geometry series `3339f13892c87376009f0f1f94f94afa513ae60660b9dc96aec814f7390ff66f` remained unchanged. Initial SoC, nominal bank capacity, constant AC load, source-evidence pins and storage assumptions matched exactly across providers. The profiled alternative retained the identical 24-hour load forecast `6571ac249f07e005082cac4575fa5ef01e3c0cd0c05c0daf2ea189e31889c2af` and hourly AC assumptions.

The comparison completed at **20:27:51.587040Z**, producing both constant-load and original-profiled-load 24-hour Google trajectories in **1.674 seconds / 114,268 KiB peak RSS**, under unchanged shared 256–512 MiB / 24-task / 120-second admission. Report SHA256: `35cd8d4b33473aa960f9f13bfc32b547286446ad9946ad66e779137647495203`. Original reports are retained as separate immutable private objects, not overwritten scientific issues; a latest audit summary is only an index.

Actual completion time governs prospective exposure eligibility. The first ending-hour interval had already started when this comparison finished, so it is explicitly ineligible. Ending-hour intervals **2–24** had not started yet; the first begins at **21:15:15Z** and ends at **22:15:15Z**. This is not a claim that the Google scenario was delivered at the earlier 20:15 origin. No outcome score or skill result is implied by a future trajectory.

The audit made no cloud request, PostgreSQL query, fit, Item publication, grant, resource-policy change or actuator call. Original control receipts and numerical source files were read only. The installed collector/shadow/training release remains f5775f8; this is a separately executed research adapter.

## Verification and limits

- New fixed-energy cases plus original energy/profiled-model/storage regressions: **39 passed in 49.79 seconds**.
- Full pinned WeatherNext suite: **152 passed in 4.523 seconds**.
- Tests exercise original-curve reproduction, unchanged battery/load/geometry/assumptions, source/runtime changes, actual completion time, late/historical/missing/wrong-site Google data, independent unavailable storage, learned-load preservation and resource-versus-harvest separation.

The working checkout's group-writable files correctly failed the original immutable-source validator. Tests therefore ran from an isolated Git export with the exact pending source patch and normal non-group-writable source permissions; live/working-tree permissions and safeguards were not changed. The real audit then used the installed original source closure and actual retained files. A mistaken unused fixture key was removed before behavioral checks; it was not a production contract change.

This increment does **not** satisfy all of Task 7. Actual qualified energy/charge/night outcomes, paired errors/regimes, fixed thermal attribution, fresh weather-dependent Google/local fitting and every still-required daily energy consumer remain unfinished. In particular, this physical scenario comparison does not replace the remaining legacy daily-learner migration or pretend its rounded retained gain is an exact original fitted coefficient. Existing release gates remain unchanged.

This adapter is **temporary pre-cutover control analysis**. Task 9 must detach/archive its incumbent replay path and tests outside the active project at complete Open-Meteo retirement, while preserving provider labels and original historical evidence. It adds no dormant fallback or post-cutover comparison collector.
