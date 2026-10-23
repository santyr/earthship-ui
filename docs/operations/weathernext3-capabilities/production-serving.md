# Selected production forecast integration

Step 11 replaces the active methods after the integrated release is reviewed.
The selected-product adapter, publication boundary, version-three UI reader and
confirmed-output scoring functions are implemented. The production configuration,
bounded evaluator scheduling and dependent PV/thermal replacements remain to be
connected before installation. This document does not certify a live cutover.

`production_forecast.prepare_production_forecast` consumes original provider
selections, the current measured-target contexts and explicitly registered fitted
models. It neither ranks challengers nor fits weights. Every selected point keeps
its original forecast, measurement/grid/lead cohort, model, bundle and admission
identity. Missing current measurement context, unsupported native statistics,
expired models and unsupported lead ranges use named target-specific raw
fallbacks. Owner refusal remains fatal. The short and extended provider sources
are independent: short-range hourly overlays do not change the source used for
extended daily summaries.

The ten-day forecast uses version 3. Version 1 raw forecasts and version 2 legacy
adjustments remain readable. Corrected temperature points reach both the JSON
products and numeric OpenHAB Items. Daily high/low values are extrema of hourly
point forecasts, with complete future local days and an explicit remaining-hours
scope for today. They are not distributions of daily extrema. Local dates retain
23/25-hour daylight-saving boundaries. A missing required future hour withholds
the summary instead of manufacturing a complete day.

The original native instantaneous wind remains in `windMph`; the separately
fitted local station hourly mean uses `windMeanMph`. Version-three UI readers
prefer that local estimate when available and retain the original wind and its
statistical meaning. The first already-started interval remains native. The
chart separates native fallback markers from the hourly-mean curve, and hover
text names the quantity. These local wind estimates do not replace native wind
in physical PV cooling calculations. Radiation, precipitation and native source
originals remain literal inputs. Local ranges and distribution parameters are
retained privately; no probability or coverage qualification is inferred.

The writer requires paired preparation, prepublication retention and current
owner checks. It retains the original before any forecast PUT, verifies all
owned states and commits the detail Item last. A separate confirmed emission
binds the original state bytes and successful readbacks. A failure after that
publication preserves its actual success and immutable originals. A prepared
object keeps `issued=false`; its new emission has its own identity. Old shadow
records are never relabeled.

Production issue capsules losslessly compress the complete original product,
including literal sources, contexts, fitted values and predictions. Reloading
verifies both the capsule and decompressed original identities. Decompression
retains the existing 16 MiB object bound; capsules and emissions count toward the
existing shared 2 GiB/10,000-object limit. Repeating retention preserves the
original bytes and clocks. The actual preview's 6,699,341-byte original retained
as a 2,144,422-byte capsule. An hourly 28-day projection for those issue capsules
alone is 1,441,051,584 bytes; existing data, emissions, observations, scores and
index growth must also be budgeted before enabling the recurring writer.

Only hourly rows actually present in confirmed published states enter the new
scoring population. A fixed set of at most 48 temperature/wind targets per issue
samples the published horizon. Native instantaneous wind does not become an
hourly-mean observation target. Observations must be mature, actually acquired
and replayable; a changed sensor epoch is reported as incompatible. Scoring uses
retained predictions and original measured targets without fitting or consulting
a current selector. Scheduling this work under the shared evaluator's existing
budget remains part of the deployment integration.

`production-serving-results.json` records scoped test and real-data preview
results. Private originals and source files are retained separately. A preview
uses a frozen prepared selection for read-only evaluation, not an installed
production owner. Its UI exercise uses a captured real OpenHAB Item inventory
with the prepared forecast values overlaid locally. It performs no OpenHAB state
writes. Final release review, permanent original/source export, source and
selector installation, rollback, actual deployed UI readback and natural-cycle
verification remain required by Step 11.
