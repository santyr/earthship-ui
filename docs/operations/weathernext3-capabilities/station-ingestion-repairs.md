# Station ingestion repairs — implementation contract

The user authorized fixing all station ingestion issues after reviewing the
installed audit. These repairs extend the existing source/receiver/Item flow;
they are part of the current capability release, not a separate abandoned audit.
The audit supplies the approved problem and correction boundaries. Existing raw
originals, fitted artifacts and historical Item meanings remain replayable.

## Required repairs and integration

1. **Counter state and recovery (AW05/AW06).** Share a pure counter transition
   helper between the strict rain collector and corrected receiver. Never move a
   valid baseline on a single decrease or implausible jump. A fresh natural return
   to the valid baseline clears the suspect candidate without an increment.
   An implausible increase after a gap longer than receipt validity requires two
   consecutive consistent natural readings to establish a new baseline, with
   a new source epoch and an unknown-gap barrier. A substantial counter reset
   also needs two consistent readings and a new phase. A still-plausible reading
   after a gap starts a fresh phase immediately, with no assigned gap increment.
   No accumulation is
   assigned to the unobserved gap. Keep the short-interval 0.5-inch spike guard;
   increasing it alone does not repair recovery. Clock rollback and restart clear
   pending confirmations. Old v1 originals must still replay unchanged.
2. **Rain products (AW02/AW03).** Use aware UTC observation clocks and the site's
   IANA timezone for local periods. Separate last-hour depth from ten-minute
   depth multiplied by six. Use Sunday-to-Sunday weeks and complete local
   calendar months/days. Implement the documented 24-hour event criterion; do
   not use one dry hour as a storm boundary. Track incomplete windows and counter
   discontinuities explicitly. A missing window is unavailable or a labeled
   partial lower bound, never a measured zero or falsely complete total. Give
   corrected products versioned identities; preserve original history.
3. **Identity and field freshness (AW04).** Pin outdoor 206, indoor WH32B 235,
   and the already configured WH31E identities 193/223 from the reviewed local
   temperature policies. Preserve actual WH31E channel metadata. Validate finite
   values, units, duplicates and ranges per field. Missing/invalid fields cannot
   refresh cached values or model-wide completeness. Forward independently valid
   fields even when an unrelated optional UV/light/wind field is absent. Expose
   per-field observation/expiry and a degraded initial/partial/stale state. Do
   not fill missing humidity or wind with invented constants in derived products.
4. **Pressure (AW01).** Expose raw station pressure under an absolute/station
   identity and correct consumer labels. Do not invent sea-level pressure or copy
   an unknown console offset. Mark or retire the historically misnamed alias,
   without rewriting its old readings. Make any custom pressure trend's method
   and actual time support explicit; a cold short history is not “steady.”
5. **Solar (AW07).** Keep lux and the manufacturer-supported 126.7 conversion.
   A new v2 proxy can cover the documented 200,000-lux range (1578.53 W/m²), with
   a 1600 W/m² envelope matching downstream physical input limits. Preserve the
   v1 1200-bound conversion for literal old receipts and incumbent numerical
   packages. Add a separately identified field/profile before migrating readers;
   never feed changed watts into old electrical coefficients under the same
   artifact identity. The estimate remains a lux-derived proxy, not independently
   calibrated irradiance.
6. **Derived fields and transport.** Check every current relay/receiver field
   while repairing its shared validation path. Retain correct dew-point and
   wind-chill units. Fix the unreachable low-humidity heat-index adjustment using
   the primary NWS method, and withhold derived values missing their required
   current inputs. Reject malformed/nonfinite decoder JSON without restarting
   healthy RF capture. Treat radio decode, HTTP receipt and sensor measurement
   times distinctly. Keep console gain/offset availability explicit; the pending
   user answer is not assumed to be factory defaults.

## Implementation and release sequence

Use regression-first changes in this existing worktree. Start with the pure
counter helper and both its consumers. Bring the corrected receiver into a
maintained, explicitly enabled adapter for the existing Flask application rather
than an unversioned live-file rewrite. Existing temperature/rain/radiation receipt
hooks must still observe original requests before a corrected response replaces
legacy processing. Disabled means the old application remains available; an
explicitly enabled bad configuration must expose unavailability, not silently
claim corrected ingestion.

Publish reader-compatible Item/report schemas before enabling producers. Add
field expiry/backstop behavior and update Home/Weather/current consumers to use
corrected products and truthful unsupported states. Inventory all affected
consumers before retiring aliases. Preserve the old raw files/state and exact
rollback package; do not seed new measurement freshness from the legacy cache.
Keep natural original receipt history under its existing persistence owner.

Run isolated numerical and Flask tests with network/production writes blocked,
actual installed decoder offline frames, native receipt/history regressions,
old-producer replay, frontend/browser tests and release migration/rollback tests.
Only then deploy the scoped reviewed release under the user's existing merge/
deploy authorization. Read back source hashes, effective flags, Item meanings,
source epochs, field units and natural fresh packets. View the actual UI. Do not
stimulate rain buckets, change station calibration, or actuate hardware.

Task 9 still needs its complete rain target/collection/experiment/queue gates;
Tasks 10 and 11 remain required. Receiver repairs must be integrated before the
final completion claim. Unknown physical calibration and genuinely immature
windows are finite evidence dependencies, not reasons to leave software undone.

## Receiver implementation progress (2026-10-22)

The independently releasable counter repair is PR #45. Its final fresh-context
review found a confirmation-boundary issue: a pre-gap spike could count as the
first post-gap confirmation. A RED→GREEN regression now requires withheld at
128 seconds and recovery at 144 seconds for 100@0 → 101@112 → 101@128 → 101@144.
All 61 release tests pass. Exact old/new receiver bytes and helper-first apply /
receiver-first rollback are staged and rehearsed. This entry does not claim
production installation; the deployment receipt must establish that separately.

The maintained adapter and relay changes are implemented locally with 50 focused
passing tests. They are not wired into the production WSGI entry point yet:
consumer schema, expiry behavior, migration tests and release verification remain.
The adapter starts with no cache-derived freshness, pins the surveyed identities,
expires individual fields, preserves actual WH31E channels, rejects duplicate
values and replayed decode clocks, and withholds unsupported derived values.
Existing raw temperature/rain/radiation hooks still execute before its response.
The legacy solar field remains capped at 1200; the separately named v2 lux proxy
reaches 1578.53 W/m² at 200000 lux. No incumbent electrical coefficients consume
that new profile. Field receipt and radio decode clocks remain distinct; neither
is called a sensor measurement timestamp.

The user separately reported pressure always displaying steady. The installed
implementation keeps only 12 readings and treats insufficient history as steady.
The corrected local adapter requires continuous three-hour support, uses a
boundary bracket at the exact three-hour start, and classifies only when the
possible change agrees with a 0.01 inHg threshold. Cold, interrupted, stale or
threshold-ambiguous history is unavailable. This is an explicitly local three-hour
trend, not a claim to reproduce the console's own pressure bar graph. Tests place
the entire pressure change in the first hour, leave the final hour flat, and prove
rising/falling/steady classifications independently of the old twelve-reading
failure. Do not seed this support from the legacy cache during deployment.

The event product is a local reconstruction. It first requires a complete known
quiet 24-hour interval under 1 mm, then retains event accumulation until a complete
quiet 24-hour interval after that event has at least 24 hours of history. This
avoids the legacy one-hour reset and prevents a small new event being erased
immediately by a pre-event dry window. Unknown start/gap coverage stays unknown;
console micro-timing equivalence and physical gauge calibration remain unproven.

Heat-index validation follows the NWS preliminary/simple estimate averaged with
ambient temperature, followed by the Rothfusz equation and low/high humidity
adjustments when applicable. Source:
https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
No default humidity or wind is substituted into derived values.

## Station v2 release preparation

The rain-counter-only repair is now deployed through merged PR #45; see
`station-counter-deployment.json` for natural packet progression and actual
Home/Weather screenshots. That release intentionally does not claim pressure or
all station issues fixed. The maintained station v2 release is prepared next.

Station v2 now preserves battery measurements and their expiry, requires actual
day-start receipt coverage for daily extrema, invalidates same-decode-clock
conflicts, and applies source-age expiry to rain products. Pressure trend uses the
separate `WeatherStation_PressureTrendV2` identity; the misleading old alias is
retired rather than mixing its twelve-sample history with the three-hour method.
A 1e-9 inHg comparison tolerance prevents binary rounding at exactly 0.01 inHg
from becoming a false rising/falling classification. Both reader and producer
have RED→GREEN threshold regressions.

The UI validates each current field's own evidence. A missing/expired v2 report
masks old current values; derived values require their current inputs. Both
screens use a five-second expiry clock. New report/pressure/rain Items retain
separate identities and old history. Existing historical/current legacy mode is
available only when the v2 Item does not exist, including a deliberate rollback.
The default-off generic adapter is explicitly activated in the reviewed WSGI
release entry point after all raw receipt hooks; setting its enable flag to zero
restores the legacy handler. Bad enabled configuration exposes unavailability.

`openhab/weather-station-v2-resources.json` prepares eleven read-only channels
and Items, initially disabled, with 90-second expiry. It adds no commands or
rules and reuses the existing JDBC wildcard policy. A densely populated receipt
snapshot measured 8306 bytes (1860-byte legacy flat response); the full-report
binding has a 16384-byte buffer. The installation should conservatively increase
the legacy response buffer from 2048 to 4096 for valid longer numeric values.
Deploy schema/readers before activating the producer; preserve literal old
files, Item/Thing/link configuration and source hashes for rollback. Preserve
old cache files but never seed new freshness from them.

Current local verification: 242 backend tests and 192 focused frontend tests
pass; six Weather/Earthship browser cases passed after the current-field masking
change. The production build must be repeated on the final release sources.
Remaining release gates are the isolated branch review, migration/rollback
rehearsal, live installation, natural readbacks and actual UI inspection. Neither
this preparation entry nor a passing fixture constitutes deployment evidence.
The non-radiation transition-range apparent-temperature formula is documented by
https://www.bom.gov.au/info/thermal_stress/index.shtml .


### Whole release review corrections (2026-10-22)

The independent review of release c2f4a13 found four integration defects. All
four have failing regression evidence followed by passing tests in one fix pass:
withholding rain coverage now preserves the counter's confirmation sequence;
the UI gates every rain product and partial on the original counter field's
freshness; calendar rain and daily extrema carry the site's explicit period
expiry, including 23/25-hour DST days; and malformed decoder measurement fields
remain contained within their record instead of restarting healthy RF capture.
Invalid owned receipts still break counter confirmations. A confirmed new phase
never assigns rain to the unknown gap. Server snapshots clear expired calendar
values and partials before the next packet; cached UI reports apply the same
period deadline without relying on the browser timezone.

Verification after corrections: 225 backend tests and 194 frontend tests passed.
The first frontend run exhausted its own 32-task test scope before assertions;
a single-worker, two-CPU run within a 64-task scope passed. Shared household
limits remain unchanged. Production installation and live verification remain
required; these results describe source tests only.


### Deployed release (2026-10-22)

PR46 merged as `aba39486fec030078e7771f36c5e9e89cb065d4c`; all fourteen CI
checks passed before activation. The source release is
`41636b173d6f33a2e16b9c922442018098a17f0e`. The receiver, relay, schema and both
UI readers are installed, with exact original files and REST configuration
retained outside the plan workspace. See `station-ingestion-deployment.json`
for hashes, readbacks, tested rollback and the migration/recovery record.

Natural readbacks show all four sensor roles fresh and twenty fresh fields.
The corrected Thing is ONLINE; natural raw rain packets advanced from 6 to 10.
Both actual Home and Weather screenshots were inspected: 23.84 inHg absolute
station pressure and a three-hour trend unavailable during warm-up, with no
page errors or mutation requests. No synthetic weather receipts were used.
Pressure trend now requires three hours of continuous observations instead of
the old twelve-reading cap and missing-history steady default. Incomplete rain
periods also remain unavailable. The installed report measured 9261 bytes,
within its 16384-byte response buffer. The legacy response buffer is 4096 bytes.

This closes the deployed software repairs identified in the station audit.
Console calibration and independent physical gauge/irradiance calibration remain
unknown; this release supplies no such qualification. WeatherNext capability
Tasks9–11 still require their separate experiment, integration and final gates.
