# Fixed thermal weather-forcing attribution

Observed October 18, 2026. This completes one diagnostic increment of Task 7, not thermal qualification or provider cutover.

## Contract and API review

Google's current [Earth Engine guide](https://developers.google.com/weathernext/guides/earth-engine), [collection catalogues](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p05deg), [dissemination schedule](https://developers.google.com/weathernext/guides/dissemination), [authentication scopes](https://developers.google.com/earth-engine/guides/auth#details_on_scopes) and [`getRegion` reference](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-getregion) were reread against the current code. The existing corrected storage scope and explicit original image-clock validation remain appropriate. Targets use cross-checked `end_time` and lead hour; initialization and actual acquisition availability remain separate. A metre-scale approximate query is not native-cell equivalence. See the [API compatibility findings](2026-10-18-weathernext-api-compatibility.md).

No additional acquisition rewrite is justified by this check. The remaining model migration requires downstream evidence; successful API access alone does not establish predictive skill.

## Comparison implementation

`weather_learning.thermal_shadow.compare_fixed_thermal` first replays the original household energy/plan receipts under a freshly computed manifest of the **actually executing original numerical sources**. It restores their original prepared thermal context, model artifact, coefficients, initial air/mass state, actions, horizon and native solar geometry. It changes only hourly station temperature and GHI, using a retained Google snapshot whose original source bytes rederive and whose acquisition completed before the original forecast origin.

The comparison preserves the control's linear hourly interpolation on its exact five-minute grid. Google's GHI remains identified as a trailing-hour mean derived from native J/m²; this fixed-processing comparison does not assert that hourly energy is instantaneous irradiance. Direct radiation, wind and invented weather codes are not inputs to this thermal comparison. No extrapolation, missing-value substitution, model fitting or release authority is added.

The first actual replay exposed a stale model-family assumption in the new adapter: the installed current artifact uses the newer 14-parameter irradiance/shade family, while the older synthetic fixture uses the 10-parameter installed-shade family. The initial replay refused rather than producing a result. The adapter now uses the original runtime's `fit_profile` selector and verifies its rule against the retained prepared model. Older runtimes lacking that selector support only their explicitly matching original model rule. No installed thermal code or parameters were changed or copied into the migration checkout.

The Google result has a separate attribution schema. Modified forcings are not resealed as an original prepared projection or model artifact. Original and attribution source manifests are checked again before return. Actual completion controls prospective eligibility: only an entire hourly outcome interval starting after completion can qualify as prospective. Measured outcomes remain null and `NOT_SCORED`.

## Actual retained-source replay

- Original origin: **2026-10-18 20:15:15 UTC**.
- Original energy document: `80e0a846e61b3da80add98f08030890232b78d2e8eb1c344b3416ff27d4e6f83`.
- Original plan document: `69c47d5b614c5d2d69d4405cd566505624f7ac440c68de358258f531414912df`.
- Original model artifact: `1ccff0a33a9b0b2474c70da9d8af81c6384a58f34e26e7d36b871d83b317b275`.
- Executing fixed numerical runtime: `97b850d80329234e94e24be98e6ec2afceb09f90c6b96867983234606510ebc1`.
- Unchanged geometry series: `3339f13892c87376009f0f1f94f94afa513ae60660b9dc96aec814f7390ff66f`.
- Google source: `ad52a362ec0b4952b5d8550a9a75671443b3d267c4decc9ba70c2215eea45247`, initialized 06:00 UTC, actually available **19:35:48.221224 UTC**.
- Comparison completed **20:45:45.200854 UTC**, **0.947 seconds**, **103,384 KiB peak RSS**.
- Separate immutable report: `d6ea182571343401024e91729badcb40db972602eb205aee97355beb3743a853`.

Both trajectories contain 24 identical hourly target instants. The original coefficients, initial state, action context and geometry match exactly. The actual context preserves outdoor shades absent and the retained venting/indoor-shade snapshot; it does not fabricate per-zone shade telemetry or later action confirmation. Hour 1 had already started and is not prospective. Complete hourly windows 2–24 were still future at comparison completion. This does not score an outcome, prove constant future ventilation, or qualify a regime.

The report and original forecasts remain private, with immutable report objects mode 0600 under the execution evidence directory. No forecast, credential or private sensor receipt is committed or added to public assets. No cloud request, database query, fitting, service restart, publication or actuator operation occurred. Existing shared admission/resource safeguards are unchanged.

## Verification and remaining work

The new comparison initially failed because it did not exist. A model-family mismatch regression then failed against the initial implementation and passed after using the retained runtime's selector. Tests exercise real native original-source fixtures, original replay parity, unchanged nonweather inputs, actual completion clocks, missing/future/historical/tampered Google sources, runtime drift, nonconstant hourly interpolation and absence of provider/database access.

The final relevant thermal/native-weather run passed **46 tests**. The complete pinned WeatherNext suite passed **152 tests in 4.356 seconds**. The actual installed-model replay above additionally exercises its newer family, independently of the older checkout fixture.

This temporary incumbent-control adapter must be detached from the active project at retirement. It does not authorize importing old weather-trained weights into a new production model. Qualified local thermal outcomes, prospective regime comparisons, fresh Google/local weather-dependent fitting, daily energy consumer migration, existing qualification intervals, production-provider integration and complete Open-Meteo removal remain unfinished. See [readiness](weathernext-readiness.md) and [retirement](openmeteo-retirement.md).
