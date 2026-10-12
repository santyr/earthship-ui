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
