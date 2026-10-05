# WeatherNext sources and verification ledger

**Verified on:** October 5, 2026. These links identify primary sources; access, pricing, schema, licensing, and availability must be rechecked before production promotion. WeatherNext access has been requested and approval/live data access remain pending.

## Google

- **S1 — WeatherNext GCS/Zarr guide.** https://developers.google.com/weathernext/guides/gcs
- **S2 — Cloud Storage Requester Pays billing semantics.** https://docs.cloud.google.com/storage/docs/requester-pays
- **S3 — Earth Engine noncommercial tiers.** https://developers.google.com/earth-engine/guides/noncommercial_tiers
- **S4 — WeatherNext terms overview and historical-data transition.** https://developers.google.com/weathernext/guides/disclaimers
- **S5 — GDM Real-Time Weather Forecasting Experimental Data Terms, modified 2026-09-03.** https://storage.googleapis.com/weathernext-public/terms-of-use.pdf
- **S6 — WeatherNext 3 surface data catalog and units.** https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p1deg
- **S7 — WeatherNext 3 station-head data catalog.** https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p05deg
- **S8 — WeatherNext dissemination schedule.** https://developers.google.com/weathernext/guides/dissemination
- **S9 — WeatherNext access quick start.** https://developers.google.com/weathernext/guides/access-forecast
- **S10 — Creating service accounts.** https://docs.cloud.google.com/iam/docs/service-accounts-create
- **S11 — WeatherNext access-request form.** https://docs.google.com/forms/d/e/1FAIpQLSeCf1JY8G78UDWzbm0ly9kJxfSjUIJT5WyMR_HiNqCm-IHIBg/viewform
- **S12 — WeatherNext 3 model and historical coverage.** https://developers.google.com/weathernext/guides/models

## Repository evidence

Earthship files below were inspected at `8a5a4ddb95917c64b19454d9277a656d4b599757`; they are repository/operations evidence, not independent live-server verification.

- **R1 — Forecast worker, source policy and current gates.** https://github.com/santyr/earthship-ui/blob/8a5a4ddb95917c64b19454d9277a656d4b599757/openhab/scripts/forecast_intel.py
- **R2 — Prediction-learning review and qualified-data limitations.** https://github.com/santyr/earthship-ui/blob/8a5a4ddb95917c64b19454d9277a656d4b599757/docs/operations/2026-09-29-prediction-learning-review.md
- **R3 — Forecast payload parser.** https://github.com/santyr/earthship-ui/blob/8a5a4ddb95917c64b19454d9277a656d4b599757/src/lib/weather/forecastDetail.js
- **R4 — Project architecture and UI constraints.** https://github.com/santyr/earthship-ui/blob/8a5a4ddb95917c64b19454d9277a656d4b599757/README.md
- **R5 — Solar_PV system and safety ownership.** https://github.com/santyr/Solar_PV/blob/main/README.md — pin its current commit during implementation.

## Corrections carried into the plan

WeatherNext 3 history is not assumed to extend to 2022: current documentation lists 2026 and says 2024/2025 are being backfilled. Long horizons apply to the four main runs; interim runs have shorter horizons. Public availability is delayed relative to model initialization. [S8, S12]

A historical forecast archive is not the same as a mature, source-qualified household training set. Existing qualification cutovers and release gates remain authoritative. [R1, R2]

Displayed p10/p90 values are not locally calibrated probabilities until evaluated, and summing hourly marginal quantiles does not produce a daily-energy quantile.

## Execution-time checks still required

Confirm Google identity approval, live metadata/schema, direct-read transfer size/memory/latency/billability, variable-specific historical overlap, qualified household measurement counts, installed services/grants, permitted operational use, and incremental out-of-sample forecast skill.
