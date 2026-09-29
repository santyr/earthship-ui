# Temperature extrema display writer: file-provider handoff

At the September 29 preflight, `temp-highlow-24h` was one healthy managed
JavaScript rule with a single `0 0/15 * * * ?` timer. Its 1,146-byte action
had SHA-256
`a499269f5aabf7a82de55f9fbc168d7c281c3155d07d91321a2259199b7072db`.
It reads the two indoor/outdoor temperature Items' 24-hour persistence and
posts only `IndoorTemp_24h_Low`, `IndoorTemp_24h_High`,
`OutdoorTemp_24h_Low` and `OutdoorTemp_24h_High`. A live literal-rule census
found no other rule referencing those four outputs; the Earthship page uses
them for display. This is a manual review of known consumers, not a proof
about uninspected external applications.

The exact file equivalent is
`openhab/file-config/automation/js/temperature-highlow-24h.js`, SHA-256
`4c6c32a4847c93792f9748028ad8d53ac7116bc837a385544b7523fcd5c62297`.
Three no-hardware VM tests cover UID/timer, the four 24-hour extrema and
withholding one source with missing persistence. An owned, networkless
OpenHAB 5.2.1 rehearsal loaded the same UID with `editable=false`, withdrew
the file and restored the managed rule; its container and volumes were
removed. Seven offline handoff/rollback tests passed across the season, sky
and extrema configurations. The sky control-input release gate remains off.

## Guarded live handoff

Read-only `scripts/migrate-season-countdown-rule.py --kind extrema --check`
passed the exact live script, source hash, six input/output Item types and
states, timer, one managed provider and active OpenHAB. The guarded
`--apply` saved the exact managed DTO privately at
`/home/sat/.local/state/extrema-rule-vghvrx7g/managed-rule.json`
(directory 0700, file 0600), withdrew the managed rule, atomically installed
only the Git JS file and armed managed rollback for failed readback.
Independent verification found one `temp-highlow-24h` rule with
`editable=false`, `IDLE/NONE`, the exact 15-minute timer and installed source
hash. All four output states were retained and OpenHAB remained active. No
OpenHAB restart, fabricated temperature update or control change occurred.

The natural 06:00 MDT timer run posted all four extrema. `openhab.log` records
both calculations under `jsscripting.file.temperature-highlow-24h.js`; the
four `ItemStateUpdatedEvent`s are in `events.log`, and the changed outdoor
low explicitly attributes its `ItemStateChangedEvent` to
`org.openhab.automation.jsscripting$file:temperature-highlow-24h.js`.
OpenHAB remained active. The natural-writer gate passed, but ownership remains
`file`/`provisional` until a later full-restart check. Keep the private managed
DTO until that gate passes.
