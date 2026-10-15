# Terrain horizon and retained irradiance diagnosis

Checkpoint: October 15, 2026. This is a descriptive research result for the
existing PR #3 solar-input work. No fitting, new production forecast, deployment,
actuation or database write was performed.

## What the location adds

A digital elevation model can estimate the visible skyline in each azimuth
direction. Comparing that static skyline with the seasonal Sun path predicts
mountain blockage without needing a full year of local observations first.
[PVGIS documents terrain horizons](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-tools/horizon-profile_en)
using terrain cells approximately 90 m across; it does not resolve nearby trees
or buildings. [USGS 3DEP](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services)
offers finer elevation products; coverage and the useful resolution at this
site still need checking. Do not download or process a national raster for
this local calculation.

A bounded request to PVGIS 5.3 `printhorizon`, using the operator-provided site
coordinates, returned 48 unique directions at 7.5-degree spacing plus the
repeated north endpoint. Retrieval was at 15:03:44Z. Original response SHA-256:
`284643f993d60d48165cb01ea77475dcfd1bc5836ec4d119780e76806d900846`.
Exact coordinates and the complete request/response are retained privately.
The returned 2,037 m elevation is a DEM estimate, not a surveyed sensor height.

| Direction | Skyline elevation above horizontal |
|---|---:|
| Northeast | 6.5 degrees |
| East | 4.2 degrees |
| Southeast | 1.9 degrees |
| South | 6.5 degrees |
| Southwest | 8.4 degrees |
| West | 8.8 degrees |

These values are **unvalidated map estimates**, not observed sunlight times.
The source azimuth uses south as zero, increasing westward; research converts
it to clockwise from true north with `(source_azimuth + 180) % 360`.
The array's approximately 165-degree azimuth remains the operator's provisional
estimate. Do not adjust it to compensate for a mountain or station obstruction.

## Actual history checked

Read-only, indexed, day-bounded SELECTs examined October 3–14: **33,953 original
receipt rows** including daily boundary carry/closing evidence. The existing
reader selected **3,453 of 3,456** five-minute as-of points. Seven days pass its
strict full-day v2 transport/coverage checks; the other five retain their
original rejection reasons. A complete receipt day establishes coverage, not
clear skies or calibrated physical irradiance.

Radiation is the station's original lux-derived proxy. It is not a calibrated
pyranometer measurement. The current receipt table starts on October 2; the
verified v2 cutover is `2026-10-02T20:00:09.206165Z`. Older numeric series, if
used later, must carry weaker provenance and must not be silently combined
with this source-qualified period.

For this descriptive comparison only, pvlib 0.16.1 SPA supplies geometric Sun
positions at the retained observation grid. It is isolated under `/tmp`, with
no production dependency change. The map predicts morning direct-beam access
roughly 15–20 minutes after the Sun center crosses zero geometric elevation,
and loss roughly 50 minutes before the evening zero crossing on these dates.
These five-minute-grid differences are **not** differences from native Astro's
refracted sunrise/sunset event definition or measurements of actual exposure.

The largest low-Sun five-minute morning increases occurred at Sun elevations
from 0.6 to 10.9 degrees. Their variability makes a largest-jump detector an
unreliable horizon estimator: clouds, diffuse light and receiver-specific
obstructions remain confounded. Seven clean transport days do not qualify a
physical horizon, clear-sky classification or annual validation. No new
horizon was fitted from these changes.

Private originals and replayable descriptive results are under
`.superpowers/sdd/2026-10-12-household-common-cycle/pv-trajectory-20261015/`:
`pvgis-horizon-original.json`, `pvgis-horizon-retrieval.json`,
`terrain-history-diagnosis.json`, `analyze-terrain-history.py`, and daily
compressed original receipt files. A restricted-reader attempt to access the
historical native elevation table was denied; no privilege change was made.
This research SPA calculation does not replace the retained native geometry
used by the production model.

## Apply within the existing model

Use the terrain skyline as a separately versioned, source-bound provisional
input shared by PV and thermal solar-resource calculations. Retain its original
response, coordinate convention and uncertainty. Reuse it across serving cycles
rather than fetching maps for each inference. Keep receiver-specific tree,
building, panel and window obstructions separate.

Compare repeated low-cloud irradiance profiles at matching solar azimuth and
elevation, retain source gaps, and evaluate any inferred correction on later
days. Station radiation is primary evidence for sunlight timing. PV output can
corroborate it only when telemetry and battery/controller limiting status
permit; curtailed generation does not prove shade. Annual seasonal validation
remains incomplete until the relevant solar paths have observations.

Block direct beam below the skyline while preserving diffuse sky radiation;
[PVGIS describes this separation](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/data-sources-calculation-methods_en).
A finer model can account for sky-view reduction of diffuse radiation too.
Do not set all irradiance or generation to zero merely because a mountain
blocks the solar disk. Avoid applying terrain loss twice to irradiance that
already includes the same local obstruction.

Preserve Astro's event times and owner daylight rules. The effective direct-sun
window is a model-layer result, not a replacement for astronomical sunrise or
sunset. The initial array prototype assumed an unobstructed horizon. The later
October 15 deployment now requires the source-bound provisional map profile
for its new PV/storage observer, withholds that projection if the profile is
missing or unusable, and retains exact original receipts. See the
[verified deployment](2026-10-15-pv-forecast-practice.md#verified-deployment--october-15).
The map is still unvalidated; existing thermal forecasts, daily PV predictions
and actuator authority remain unchanged.
