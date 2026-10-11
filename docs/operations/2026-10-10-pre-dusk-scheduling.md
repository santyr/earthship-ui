# Pre-dusk lock scheduling

On October 10 the only eligible half-hourly check, at 17:30 Denver time,
collided with the new thermal publisher holding the shared consumer lock
from 17:29:45 through approximately 17:30:30. Nonblocking flock returned 75,
which the old drop-in treated as success. No October 10 pre-dusk issue exists.
The original morning forecast and the October 9 pre-dusk receipt remain intact.

The timer now checks every ten minutes at minutes 02, 12, 22, 32, 42 and 52,
at second 45, between 14:00 and 20:59 in America/Denver. These checks avoid the
thermal preparation and delivery interval and provide three opportunities in
each 30-minute eligible sunset window. The worker still issues at most once
per day, requires fresh atomic SoC and the same-day morning record, and refuses
anything outside 60 to 90 minutes before the original Astro sunset.

The existing capped service waits at most 20 seconds for its original shared
lock, within its unchanged 45-second timeout. Lock exhaustion is a visible
service failure and the next scheduled check retries. CPU, memory, swap, task
and I/O caps remain unchanged. The worker obtains its actual issue clock and
inputs after acquiring the lock; no forecast is backdated or regenerated for
a missed day. Lock contention can still withhold a forecast if every eligible
attempt is blocked; it no longer disappears as a successful run.
