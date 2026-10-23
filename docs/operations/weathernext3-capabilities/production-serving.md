# Selected production forecast integration

The selected methods are installed as the active production defaults. Current
source-role pins, original model/fit/admission identities, actual operation,
rollback and scientific limits are in [the release readback](production-release.json)
and [release operations](production-release.md). Source pins are intentionally
split by compatible owner; historical preview measurements below remain dated.

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
originals remain literal inputs. Distribution parameters remain in the private original. A sanitized fixed GET
view publishes the original local point/range and model/training support only
after complete production confirmation. No probability or coverage qualification
is inferred.

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
a current selector. The existing monitor now reserves at most 48 of its unchanged global 64 label
attempts for production outputs, with all legacy queues using the remaining
budget. It uses the same native read-only target readers and retains the actual
first acquisition. No extra scheduler, shadow producer or observation allowance
is introduced.

`production-serving-results.json` records scoped test and real-data preview
results. Private originals and source files are retained separately. A preview
uses a frozen prepared selection for read-only evaluation, not an installed
production owner. Its UI exercise uses a captured real OpenHAB Item inventory
with the prepared forecast values overlaid locally. It performs no OpenHAB state
writes. Those preview-stage prerequisites were subsequently completed; the current release readback records installation, export, rollback, actual UI and natural cycles.


The v2 publisher configuration pins the exact selected-profile bytes, original
model/admission files, actual native temperature configuration, release source
closure and user deployment policy. Default preflight reads no observations and
publishes nothing. Explicit publication uses the real owner at every transport
boundary; profile edits, source changes and used-model expiry refuse transport.
Unavailable target inputs use their named raw fallback. Original admission and
fit clocks are never renewed. A failure after successful publication exits
nonzero while preserving the actual published result and its original emission.

Confirmed output registers immediately in a private SQLite work index, capped
at 256 MiB with a 2 MiB page cache. Recovery rotates over eight original
emissions per run. Prepared originals never enter the score population; repeat
confirmations cannot inflate support. A seven-day deadline constrains actual
observation arrival, with later discovery allowed when the original timely
capture exists. Missing originals and incompatible sensor cohorts remain named
diagnostics. Preview uses a disposable index and changes no retained values.

Production performance groups ordinary refits by the registered procedure,
training/numerical policy, measurement/grid cohort and scalar scoring runtime.
Each fitted artifact also keeps its own diagnostics. Metrics weight local target
dates, then targets, then original origins/versions equally. Matched and
fallback-inclusive results remain separate. Native boundary-mean wind is an
hourly approximation, not a native hourly distribution. Scientific comparison
criteria remain descriptive and do not veto the authorized experimental cutover.

The full 28-day, 48-row/hour workload has 32,256 records and 224 daily-refit
artifacts. Its complete comparison report measured 563,317 bytes against the
former 512 KiB cap. The cap is now 640 KiB, preserving all diagnostics; the
verified report is 563,401 bytes and aggregates in 20.3 seconds under the
512 MiB test envelope. A second database test includes the full per-score producer manifest and scalar
runtime provenance. Eager loading exceeded the 512 MiB job limit. The owner now
streams literal records and retains only validated aggregation metadata; the
same complete workload passes under a 256 MiB hard limit with 212,844 KiB peak
RSS, a 160,190,464-byte database and a 564,391-byte complete performance report
in 25.45 seconds. The database remains capped at 256 MiB. These are synthetic
capacity checks, not observation or forecast-accuracy evidence. Retention caps do not grant
unlimited runway; final deployment must budget all existing state and originals.

The fixed /api/weather-production route serves only a bounded 512 KiB sanitized
view with a 4 KiB immutable confirmation receipt bound to the literal cache
bytes. It refuses private fields, unsafe files, missing receipts and stale or
mismatched identities. The expanded forecast details additionally require the
view issue to match the core OpenHAB forecast. The component starts its fixed
GET only while expanded and aborts when closed. It shows actual selected means
or medians, original native values, local p10–p90 ranges and finite training
support, with no local coverage qualification. New production details do not
subscribe to the old shadow comparison products.


A live read-only check at 01:36 UTC on October 23 confirmed the deployed Home
shows 0.16 inches / 279 estimated gallons today and 0.30 inches / 523 gallons
for the week, with no partial text. Station absolute pressure was 23.77 inHg.
Its trend correctly remained unavailable: the original report contained only
9,240 seconds of continuous pressure support against the required 10,800.
The Weather page still chose the short partial-bound display even though the
original report also retained 0.16/0.30-inch recorded totals. This release fixes
that display to prefer validated recorded totals and uses the recorded daily
series for its chart. Qualified complete interval values remain separate; the
live receiver and original scientific bounds are unchanged.
