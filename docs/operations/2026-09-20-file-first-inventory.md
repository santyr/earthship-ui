# File-first migration inventory boundary

Live registry read on September 20, 2026, after the first Item transfer:

| Resource | Managed | Non-managed | Verified file-owned |
| --- | ---: | ---: | ---: |
| Items | 427 | 1 | 1 |
| Things | 84 | 0 | 0 |
| Rules | 35 | 0 | 0 |
| Item/channel links | 261 | 0 | 0 |

`openhab/scripts/config_inventory.py` reproduces this registry graph through GET
requests only. The first run found no duplicate identities, unresolved Item/group,
Thing/bridge or Item/channel link references, or discrepancies against the current
ownership manifest. This is structural evidence, not proof of control safety.
Six unit tests cover omission of sensitive values, graph references, provider
ambiguity, ownership drift, duplicates and absent declarations.

## Remaining migration scope

1. Review each observational Item's metadata, link profiles, state restoration,
   writer and consumers before selecting further transfers. A String Item is not
   inherently safe: it may carry safety observations or operator commands.
2. Inventory Thing configuration and binding-specific secret dependencies before
   generating text definitions. Preserve UIDs, channels, bridges and polling
   parameters. Do not combine Modbus bridges as an incidental migration change.
3. Inventory rule scripts, triggers, dependencies and runtime/cache ownership.
   Registry graph checks cannot resolve code-generated Item names. Preserve pump
   timing and fail-closed controls; qualify restore/restart/rollback before moving
   protected resources. No duplicate active rule or competing timer is acceptable.
4. Inventory persistence strategies, transformations, UI pages, add-ons, exec
   scripts and external systemd publishers. Determine the supported declarative
   source or reproducible managed exception for each. Existing registry totals
   do not include these resources and must not be called a complete inventory.
5. Establish protected backups for credentials, userdata, PostgreSQL history and
   learned models, then rehearse clean-system restoration. Git definitions alone
   cannot recover the running installation. Temporary cutover receipts are not
   a substitute for durable backups.

No additional live provider transfer occurred during this inventory. Task 82
remains held; feeder work owned by another agent is not included in this change.
