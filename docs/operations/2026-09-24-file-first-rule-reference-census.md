# File-first rule-reference census — September 24, 2026

`python3 openhab/scripts/config_inventory.py --rule-references --summary`
now adds a read-only literal Item-name census of live rule trigger, condition
and action configuration. It scans values only in memory and emits recognized
Item names and rule IDs, never script bodies, raw configuration values, Item states or
credentials. Thirteen focused inventory tests pass, including a redaction
check. This is a migration review aid, not a dependency proof or release gate:
dynamically constructed Item names and external systemd publishers are outside
its scope, and a mere rule mention does not identify read versus write access.

At 17:02 MDT the live inventory had 386 managed and 46 non-managed Items,
246 managed and 17 non-managed links, 36 managed rules and zero structural
ownership issues. Rules mentioned 179 Item names literally. Ninety-three
managed Items had no channel link or Group membership; after excluding
literal rule mentions and Group types, only 17 remained. Sixteen are
Lightning Goats canary/held-canary acknowledgement, hold, override, fault,
journal or remote-enable surfaces. They are not safe batch-migration
candidates merely because the OpenHAB rule list does not mention them.
`Thermal_Advisory` is the seventeenth: it is published by
`forecast-intel.service`, gates its prediction receipt and feeds the UI alert
contract, so it also requires a targeted provider, persistence, rollback and
post-publication review.

Do not interpret the 17-name list as an allowlist. Review external publishers,
consumers, protected-control semantics, metadata, links, history and restart
behavior for each resource. The same exclusions apply to Items that do have
literal rule mentions; this census only helps prioritize manual review.
No provider, rule, Item state, control or service changed in this audit.

## September 29 protected-overlap warning

The sky-rule provider rollback exposed an indirect control-input dependency:
the sky rule writes `SkyCondition`, which the live greywater controller reads.
The read-only `--rule-references` census now reports exact Item names mentioned
by the known `hex_southoutlet_cycle` controller *and* other rules. At the live
check it found five shared names: `BMS_Comms_Status`, `BMS_SOC`,
`DCData_Voltage`, `SkyCondition` and `Sun_Position_Elevation`. In particular,
`SkyCondition` is shared with `sky-condition-calculator`.

These are **review warnings**, not inferred read/write edges or migration
approval: `UpdateBatteryIcon`, for example, reads `BMS_SOC` without producing
it. The known-control set is deliberately incomplete, dynamic Item names and
external publishers are not found, and an empty overlap would not clear a
candidate. A live downstream-consumer review remains mandatory before any
rule is classified display-only or moved to a file provider. Fourteen focused
inventory tests pass; the live redacted inventory reported zero ownership
issues and five known-control overlaps. No production rule or Item changed.
