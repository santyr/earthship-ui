# BatteryIcon file-provider staging

`BatteryIcon` is a UI icon value, but its managed definition has custom
`stateDescription` metadata: value is one space and pattern is
`"Battery Icon [%s]" <iconify>`. A plain `String BatteryIcon` declaration would
lose that format. The staged `openhab/file-config/items/battery-icon.items`
preserves the exact value and pattern; it is **not installed** on production.

On September 29, an isolated, networkless OpenHAB 5.2.1 file-provider run
matched the live Item's name, type, label, category, tags, Groups, metadata
value/config and REST state-description. The sole DTO difference was
`metadata.stateDescription.editable`: `true` for the live managed Item and
`false` for the isolated file-owned Item. This is an ownership change, not a
format change. The owned container and tmpfs were removed after the test.

The live `BatteryIcon` is still REST-managed, unlinked and ungrouped. Its
unique JDBC mapping is Item 31, with 136,507 rows and a current/persisted
`iconify:mdi:battery-70` state at the read-only check. The
`UpdateBatteryIcon` rule runs every 30 seconds; its script SHA-256 was
`834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f`.
That same rule also updates `BatteryChargingStatus`, so disabling it during
icon migration could interrupt another live status signal. Do not do that.

Before a production transfer, prepare and test a guarded adapter that keeps
the writer running, handles a natural state/history update during the handoff,
preserves exact Item 31 history, and restores managed ownership on any
failure. Exercise provider withdrawal, rollback and restart in a disposable
OpenHAB/JDBC instance. After an attended handoff, retain the private rollback
receipt and require a natural `BatteryIcon` writer update plus new Item 31 row
before declaring file ownership verified. No synthetic production icon update
is acceptable to satisfy that gate.
