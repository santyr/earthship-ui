# Sky diagnostic Item file handoff

`SkyCondition_Diagnostic` (String, JDBC541) and `SkyCondition_LastEval`
(DateTime, JDBC540) are now live and file-owned, with their state-description
metadata. Both remain unlinked members of `gWeatherHealth`. Labels, empty
category/tags, single-space metadata values, `%s` and `%1$tF %1$tT` patterns,
read-only/options semantics and original history identities are preserved.
Source `items/sky-diagnostics.items` SHA-256 is
`3c6e43fbb3d6d03723341efa425c4dfb5143722fb2cdbcd0fe42ba43561ebca3`.

The existing file-owned `sky-condition-calculator` remains the sole publisher;
its source, triggers and primary outputs are unchanged. It posts the primary
condition/icon before handling diagnostics, and catches missing diagnostic
Items. Actual-source Node execution verifies the same primary outputs for
night, overcast, partly cloudy, clear and stale-weather cases with either or
both diagnostics absent. LastEval retains its existing diagnostic posting
interval. `SkyCondition`, health status and outdoor age remain managed.

## Native and attended evidence

The native rehearsal passes nine phases: managed diagnostic baseline, file
handoff, cold restart, original managed rollback, final file handoff, followed
by resulting four-file-member Group transfer, cold restart, managed rollback
and final Group file transfer. All six original prefixes totaling **1,672,266
rows** remain byte-exact. Existing age Items, links and metadata stay file-owned;
protected health/outdoor-age members stay managed. The fixture has two inert
age channels, no HTTP handler or endpoints, no executable rules and no hardware
links. Both owned containers and their anonymous volumes are removed.

The sealed native capsule is
`/home/sat/.local/state/openhab-config-migration/sky-diagnostic-items-20261005-ofc7div4/`,
with 40 mode-600 evidence files plus its manifest inside a mode-700 directory.
It qualifies provider/history recovery; binding fetch and household cold
recovery remain separate scopes.

The attended hot handoff preserves all **1,672,289** original rows in six
recoverable histories, every unrelated definition and all 57 prior source
pins. Both Items and metadata entries are file-owned; there are no diagnostic
channel links. The new source makes **58** declared source paths. No production
state, command, rule-execution or service RPC occurs, and PID **1696** is unchanged.
The reviewed one-shot adapter waits for managed withdrawal before publishing
the sole file, verifies full registry/history recovery, and retains owned-inode
rollback, foreign-file refusal and directory durability barriers.

Its mode-700 recovery capsule is
`/home/sat/.local/state/openhab-config-migration/sky-diagnostic-handoff-20261005-shno1ece/`.
Original records/metadata, current configuration, private users, six compressed
CSV prefixes, source snapshots, operation receipts and review evidence remain
outside Git. The existing Hex token is reused.

## Natural writer and resulting Group layout

At **02:40:23Z October 6** (20:40 MDT October 5), both original JDBC tables have
natural writes at 02:38 and 02:40. Diagnostic values report the original NIGHT
classification with weather age 2 then 10 seconds. LastEval values are the
publisher's 02:38:00.351Z and 02:40:00.351Z timestamps. No synthetic production
state is posted. Persisted managed Item/metadata records are absent.
The live inventory reports zero issues: 350 managed/95 non-managed Items,
with unchanged links, Things and rules.

A fresh current-layout bootstrap independently starts with **three** managed
records (Group and two protected members) and **four** file-owned members,
restores all six histories (**1,672,372 original rows**) and removes its owned containers. This is additional
to the nine-phase rehearsal. The first probe retained a transport failure while
the owned container was still running; a bounded Item-census readiness retry and
regression address the observed startup REST transition. The successful capsule
is `/home/sat/.local/state/openhab-config-migration/sky-diagnostic-current-group-20261005-dtisy80q/`.
Production Group ownership remains managed and its file remains uninstalled.

## Verification and pending restart

The frozen full run passes **4,234 tests**, with **10 skips** and **91 subtests**.
The subsequent startup-readiness regression passes separately, covering **4,235
unique passing tests**. All 76 focused Group/age/diagnostic guards pass. Source
and handoff reviews are clear; final receipts are reviewed before integration.

The refreshed restart capsule is
`/home/sat/.local/state/openhab-config-migration/restart-20261005-sky-diagnostics-qfk5_4lu/`.
Its 55 mode-600 evidence files plus manifest cover **58** source pins and **44**
recoverable prefixes. All sources match the configuration archive; all **95**
JSONDB documents parse and archived managed diagnostic records are absent.
Fresh sparse-preserving archives total **1,801,758,720 bytes**. The retained
qualifier points to the diagnostic worktree and checks all 44 prefixes.
`/tmp/openhab-restart-directory` selects this capsule; the previous baseline is
retained. Capture is live and non-atomic; production restore/restart remain
unqualified and still require host authentication for the approved service action.
