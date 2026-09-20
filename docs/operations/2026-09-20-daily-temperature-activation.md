# Qualified daily temperature learning activation

Activated September20 at2026-09-20T14:52:58.582165+00:00(08:52:58MDT), after
natural thermal training was terminal and its promoted artifact validated.
Release source100219d contains the reviewed e44ecaa daily integration unchanged.

## Transaction and verification

Forecast, shadow and training services were inactive with MainPID0. All three
timers were active before the release. Every installed runtime file matched
the reviewed63529ea baseline; the new daily worker was absent. The live forecast
mode0775 was explicitly preserved in the scoped deployment manifest.

The three timers were briefly paused, idleness rechecked, and current model,
forecast state, service overrides, runtime files and thermal unit files backed
up privately. The receipt-bound installer replaced forecast_intel.py,
thermal_intel.py, weather_temperature_reader.py and weather_temperature_history.py,
and added daily_temperature_runtime.py. All installed runtime bytes and modes
matched the reviewed repository source afterward. No unit/timer definition was
changed. The helper verified unchanged protected-file hashes throughout.

Private release receipt:
`/home/sat/.local/state/thermal-intel/deploy-receipts/daily-temperature-20260920T145258`.
Runtime revision:
`5c9d27b5fcbadf2b2261ecb9270291f47bf1add5527ab13fda2e180046ca86e4`.
The already-executed helper `/tmp/hex-deploy-daily-temperature.py` must not be
replayed: its exact source/baseline/absence preconditions belong to this release.

Installed worker execution used a read-only September19 request. Production
validation accepted the report but not eligibility:covered20576.812587/86400s,
maximum gap65823.187413s, fully_covered=false. Canonical input digest matched the
earlier source-only check:
`363f8015a657b923ad5210babde7f1dad2bf7aed990ac4dd5d903769bd13dee4`.
No temperature score or learned-state write occurred.

New scoped drop-in:
`/home/sat/.config/systemd/user/forecast-intel.service.d/qualified-daily-temperature.conf`.
Effective configuration independently read back:

- DAILY_TEMP_QUALIFIED_ENABLE=1
- DAILY_TEMP_COVERAGE_POLICY=complete_receipt_coverage_v1
- DAILY_TEMP_EVIDENCE_CUTOVER=2026-09-20T14:52:58.582165+00:00
- DAILY_TEMP_DB_CONFIG=/home/sat/.config/hex/weather-temperature-db.json
- DAILY_TEMP_POLICY=/home/sat/.config/hex/weather-temperature-policy.json

Drop-in SHA256:b0e0d64412c80d791e31ef603c83b44c22f54002fd64adf98bd88a79c620fc3f.
Existing hourly opt-in and advisory overrides remained unchanged. All three
timers were restored and independently confirmed active; the three services
were inactive/success at readback. No forecast, training or control rule was
manually triggered. The last observed shadow publication remained07:25 and used
the previous model; new-model natural shadow verification remains outstanding.

Accepted model remained40a48cf6e491054a83b2577c2974a5a65ec37e8c8298f0e36613238ce4201e18.
Forecast state remained4bff3c463e4331c13c02b89a217a62c6300f27fbbdd3e69fd0abd6a8f4ce1059.

## Natural evidence gates and rollback

First normal post-cutover daily origin:September21; first eligible daily
assessment:September22. First day-3 target:September24, assessedSeptember25.
Each still requires complete qualified coverage and correctly captured origins.
These are future gates, not completed model-update claims. Existing bias models
and scored-day markers were preserved; no forecast origin was backdated.

Rollback removes only the newly owned drop-in after verifying its hash, reloads
user systemd and verifies the remaining effective settings. Keep compatible code
and newer learned/model state; do not copy old backup state over later learning.
