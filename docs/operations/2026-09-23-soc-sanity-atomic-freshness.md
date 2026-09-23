# OpenHAB sanity: atomic BMS SoC freshness

September 23, 2026. The external observational sanity checker no longer treats
`BMS_SOC_LastUpdate` as proof of validated SoC acquisition. That scaler
heartbeat can advance before raw SoC validation. Instead, its `fresh:bms`
check requires the independent `BMS_SOC_Evidence_JSON` v1 receipt to have a
valid source-checked status, finite bounded SoC, exact 120-second expiry,
non-future acquisition/publication timestamps, and a recent publication.
An unchanged SoC with fresh atomic receipts remains fresh even when JDBC has
no new value-change row. A fresh scaler heartbeat cannot mask invalid or
expired atomic evidence.

Focused tests: 16/16 passed, including unchanged-value recovery, stale
heartbeat suppression, fresh-heartbeat/invalid-evidence rejection, future and
expired timestamps, malformed identity and duplicate JSON keys. A read-only
evaluation against the live OpenHAB snapshot reported no problem keys; it
disabled notifications and state/log writes. The live atomic receipt passed
the new pure validator before deployment. No Item, poller, persistence rule,
protected control, or notification rate was changed.

Source commit `d4358fe` was pushed to `origin/main`. The existing installed
script matched the tracked pre-change source exactly (SHA-256
`0e796c07b9d828aab579c77bea9f4bbb9ca33ed617f2c029e1533d9180e866f4`).
The naturally scheduled 12:46 MDT sanity check exited 0 with all checks
passing. While the service was inactive and its next timer roughly ten minutes
away, the one script was staged and atomically replaced. Installed and tracked
new SHA-256 match:
`8f1b2b2ede369a3cc725a898f6e177aad5126fd42d2811bd9e36d50841b805af`.
The installed mode remains 0775. The exact prior file is retained privately at
`/home/sat/.local/state/openhab-sanity/release-nzUSiz/original.py`
(directory 0700, file 0600). Timer remains enabled; no manual sanity run or
test DM was issued. The first natural run under the new script started and
finished at 12:56:38 MDT with exit 0 and `OK (all checks passed)` in the
sanity log. The next timer remained active for 13:07 MDT.
