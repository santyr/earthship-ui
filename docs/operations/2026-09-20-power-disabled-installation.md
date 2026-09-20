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
