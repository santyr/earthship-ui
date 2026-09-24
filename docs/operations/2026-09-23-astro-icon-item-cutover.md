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
