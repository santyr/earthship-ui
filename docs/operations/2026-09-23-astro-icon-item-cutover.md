# Astro icon Item file-provider cutover

On September 23 MDT (September 24 05:00Z), the exact Git source
`openhab/file-config/items/astro-icons.items` (SHA-256
`e4ac1e2f889b5ba6be4e770ca76aeb324e0b38fac7e81ac39e05f1f2847e134b`)
became the sole production provider for `SunPhaseIcon`, `MoonPhaseicon` and
their existing Astro `phase#name` MAP-profile links. The installed `astro.map`
matched its Git source byte-for-byte before transfer. The two Astro Things
were online; their parent Sun and Moon Groups were not transferred.

Before production, a disposable networkless OpenHAB rehearsal passed exact
file Item/link readback on first boot and full restart, then provider
withdrawal and managed rollback. It removed the owned container. The
read-only production preflight confirmed expected managed definitions,
links, states, online Things and JDBC IDs 90/60 with 2,863/995 history rows.

The attended transfer saved a private managed-definition, JSONDB and JDBC-row
rollback bundle under
`/home/sat/.local/state/openhab-config-migration/astro-icons-20260924T050009Z`.
It withdrew only the two managed links and Items, then installed the tracked
file. Live REST readback independently confirmed both Items and links
noneditable/file-owned, unchanged labels, categories, groups, states and
MAP-profile link configurations. `SunPhaseIcon` remained
`iconify:mdi:weather-night`; `MoonPhaseicon` remained
`iconify:mdi:moon-waxing-gibbous`. JDBC identities 90/60 and every pre-transfer
history row were preserved. Production OpenHAB was not restarted and no
hardware Item was changed.

This proves provider and historical-prefix continuity, not a natural binding
update after transfer. The next natural Sun transition and Moon-phase change
must be checked against the Item state and JDBC history separately; the Moon
phase can take days to change. Do not claim that gate from hot-load state
restoration alone.

## Natural Sun follow-up and MIDNIGHT map correction — September 24

After the transfer, Astro naturally reported `MIDNIGHT` at 00:56:33 MDT.
`SunPhaseIcon` changed with source `astro:sun:local:phase#name` and JDBC
`public.item0090` retained the transient value; at 00:57:37 it returned to
`iconify:mdi:weather-night`, again with a matching JDBC row. This proves a
post-transfer Sun channel-to-Item-to-JDBC update, but exposed a real mapping
gap: the existing `astro.map` lacked `MIDNIGHT` and OpenHAB logged four
transformation warnings during that phase. Available logs contained 106
`MIDNIGHT` map warnings and no other unmapped Astro phase names.

The canonical map and focused regression now map `MIDNIGHT` to the existing
monochrome night icon. The one focused test passed. A guarded, atomic
deployment replaced only `/etc/openhab/transform/astro.map` after checking its
old SHA-256 `25f76f802ab403d97bcf4608ffce41529455a1de79a7964fd805ba7d8f8dc7ad`;
the installed file matches Git at
`54b74cc4a17a96890e5d4594321516c40afa4832742da55ef26e3f6c64dc04c4`
and retains `openhab:openhab` ownership and mode 0664. No Thing, Item, link,
service, command, or hardware state changed. The archived initial map remains
an exact recovery snapshot, not the current deployed version. A future natural
`MIDNIGHT` transition must still verify that OpenHAB hot-loads the new map;
the Moon-phase natural-change gate also remains open.

## Post-fix natural source verification — September 28

Read-only JDBC inspection found `Sun_SunPhaseName` (Item 49) changed to raw
`MIDNIGHT` at 06:56:04Z September 25, 06:55:48Z September 26,
06:55:32Z September 27 and 06:55:00Z September 28. The corrected Git and
installed `astro.map` still match SHA-256
`54b74cc4a17a96890e5d4594321516c40afa4832742da55ef26e3f6c64dc04c4`.
The mapped `SunPhaseIcon` retained `iconify:mdi:weather-night` across those
transitions. Its change-only JDBC table does not add a row when `MIDNIGHT`
maps to the already-held night icon; that absence is expected, not a failed
update. The continuous OpenHAB application log from the September 24 restart
through this check contains no later `astro.map` transformation warning,
whereas the four earlier September 24 warnings are retained before the fix.
This closes the natural post-fix `MIDNIGHT` transform gate without claiming a
new icon-history row for an unchanged value.

`Moon_MoonPhaseName` (Item 59) changed among `WANING_GIBBOUS`, `FULL`, and
`WANING_GIBBOUS` from September 25–27. `MoonPhaseicon` (Item 60) has matching
mapped JDBC changes at the same three instants, including
`iconify:mdi:moon-full` and `iconify:mdi:moon-waning-gibbous`. Live REST still
reports both icon Items noneditable/file-owned with their expected states;
authenticated link readback confirms each raw/mapped pair shares its exact
Astro `phase#name` source channel.
This closes the natural Moon channel-to-mapped-Item-to-JDBC gate; it does not
transfer ownership of the parent Sun or Moon Groups.
