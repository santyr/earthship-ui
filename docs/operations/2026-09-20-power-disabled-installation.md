# Power evidence: disabled installation

September 20, 2026, 09:02:38 MDT. Installed from clean main `d336876`.
This is a configuration-installation receipt, not live acquisition qualification.

## Installed and verified

- Four String Items from `power-observation-resources.json` and
  `power-evidence-resources.json`, all still `NULL`.
- Three read-only Modbus data Things, reusing existing pollers. Each was created
  unlinked and immediately disabled; disabled status and exact requested read
  configuration verified before linking. No write configuration exists.
- Three default-profile links, installed using the add-only managed provider.
- `hex_power_evidence`, created triggerless, disabled, then assigned its reviewed
  three acquisition triggers and expiry timer. Disabled status and complete
  rule definition verified after the update. No observer run was requested.

Rule source SHA256:
`9aa838239b70ace10e8c96e97b88a6f65bf57c3ec87d13bd14d06727b3664329`.
Installer source SHA256:
`27eaac812a93e81baeadc819a12984f2ad8ec5f95b29c99878cba374ddd89592`.

Fresh log receipts confirmed exactly four Item additions and three link
additions. Both temporary installer rules were removed and verified absent.
Existing rule definitions, Thing definitions (excluding runtime status and
properties), and JDBC persistence configuration matched before/after snapshots.
The installation log contained no new error. No OpenHAB restart, control command,
poller change, global persistence change or existing resource replacement occurred.

Private receipt: `/tmp/hex-power-disabled-nlf76x6_` (directory0700/files0600).
It contains before/after definitions and installed-resource readbacks; this
temporary receipt is not a durable disaster-recovery backup.

## Remaining gate

All three new Things and the observer remain disabled. Before continuous
collection, qualify actual binding-origin events, invalid/expiry behavior,
persisted records, restart boundaries and storage rate. The Solar_PV accounting
branch remains source-only; no existing energy history or published totals were
changed. Do not replay the add-only installer against these now-existing IDs.

The approved file-first policy change and migration remain ordered after the
in-flight power-evidence work. This installation does not transfer configuration
ownership or weaken protected-control migration gates.

## Bounded live acquisition qualification

At 09:05 MDT a 40-second observation enabled only the new observer and three
new data Things. Cleanup disabled all four again and verified their disabled
readbacks. No existing poller or control was changed.

PostgreSQL created `item0648` for `Power_Evidence_JSON`; input tables are
`item0647` (PV output), `item0649` (PV input), `item0650` (battery).
Exactly 24 output records persisted between
`2026-09-20T15:05:22.557696Z` and `2026-09-20T15:06:01.402689Z`.
All passed the staged production `parse_power_evidence` validator using original
persistence timestamps. One epoch, contiguous sequences1–24, maximum486bytes.
The production interval builder accepted all three field histories, producing
7battery/8PV-input/7PV-output qualified segments in the bounded window.

Battery evidence included one naturally unchanged watt reading with a newer
acquisition receipt. That establishes unchanged-value receipt renewal for this
field; neither PV field happened to repeat during this short probe. The
observer's strict original-event source checks accepted actual binding events.
No new observer error was found. Sampled REST states are retained privately at
`/tmp/hex-power-live-probe-dq7rwkcn`; the authoritative history is PostgreSQL,
not the subsampled REST receipt.

This is not continuous-collection activation or lifecycle/expiry qualification.
Current Item states retain the last probe record; consumers must respect its
embedded expiry and must not treat disabled collection as fresh telemetry.
All new acquisition Things and the observer remain disabled. Persisted probe
history is retained and must not be represented as a full-day coverage result.
