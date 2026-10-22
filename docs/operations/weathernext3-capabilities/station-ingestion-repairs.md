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
   After a gap longer than receipt validity, two consecutive consistent natural
   readings within the original increment bound establish a new baseline, with
   a new source epoch and an unknown-gap barrier. A substantial counter reset
   also needs two consistent readings and a new phase. No accumulation is
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
