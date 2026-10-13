# UI availability investigation - 2026-10-12

At approximately 11:37-11:43 America/Denver, earthship-ui.service was active,
with no service restart recorded. HTTP checks against loopback, the LAN address
and hostname returned 200 for the page, public configuration, compiled app
module and OpenHAB event stream. A capped fresh browser session at the LAN
address rendered Home and reported the OpenHAB connection as live, with no
page errors or Vite error overlay, before and after the change below. These
checks do not establish whether an existing household device had a stale tab,
DNS or network failure; the reported client symptom has not been reproduced.

The Vite watcher did have an independently reproduced defect: builds under
.worktrees caused live page reloads, including build outputs at 11:13, 11:19,
11:30 and 11:39. Repeated stylesheet HMR updates were also logged. Creating a
harmless private HTML probe under a worktree triggered a live page reload.

The narrow fix excludes .worktrees and .superpowers directories from the
running Vite watcher. Repeating the same probe after the fix produced no page
reload. The config change caused Vite's normal in-process server reload;
OpenHAB and ML consumers were not restarted or changed.

Validation: two existing proxy/release test files, 34 tests passed; actual
browser rendered Home with a live connection and zero page errors. Browser
and tests used bounded scopes. The UI service itself remains an existing
uncapped development server; its memory was about 1.2 GiB before and 1.7 GiB
after Vite dependency reoptimization. No service memory limit was changed in
this investigation.

A repeat check at about 13:12 America/Denver again confirmed HTTP 200 and an
active service. The bounded fresh browser rendered Home at the LAN address
with a live OpenHAB connection, no error overlay and zero page errors.

A repeat at about 14:40 America/Denver confirmed the service active/running with
NRestarts=0, HTTP 200 from loopback, LAN and hostname, HTTP 200 for the
compiled app module, and HTTP 200 with received data from the OpenHAB event
stream. These were lightweight HTTP/service checks, not a new browser run.
No later watcher-triggered worktree reload appears in the bounded service log.
The original device-specific offline symptom remains unreplicated.

A new investigation at approximately 19:40-19:44 America/Denver confirmed
that earthship-ui.service was active/running, NRestarts=0, and still listening
on 0.0.0.0:5190. Host available memory was about 6.6 GiB and memory pressure
averages were zero. No UI, OpenHAB, or ML service was restarted.

Loopback, LAN address 192.168.1.161, and hostname ogsatoth all returned HTTP
200 for the page, public configuration, main frontend module, battery state,
and item snapshot. The sanitized things endpoint and Earthship/Weather paths
also returned 200. A bounded event-stream observation received three actual
ThingStatusInfoEvent messages.

A fresh LAN browser rendered Home, completed loading, and reported the actual
accessible badge as "openHAB connection: live". It recorded zero page exceptions,
zero failed network requests, and no Vite error overlay. The browser ran under
CPUQuota=20%, MemoryMax=256 MiB, MemorySwapMax=0, TasksMax=96, idle I/O and a
55-second outer timeout, then exited. The first probe used incorrect DOM
selectors; it established rendered Earthship content but could not inspect the
connection badge. A corrected probe established the Home and badge result above.

A preliminary regex-based module crawl also matched imports inside dependency
comments and source maps, producing invalid synthetic paths. Those 404s are
not treated as application failures; the real browser recorded no failed requests.

These host-local LAN checks still do not establish accessibility from the
reported household device. Its exact URL and browser symptom remain pending.
No root cause for the reported offline appearance has been established.
