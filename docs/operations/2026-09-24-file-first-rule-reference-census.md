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
