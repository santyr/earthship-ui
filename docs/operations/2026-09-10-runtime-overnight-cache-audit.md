# Runtime estimator overnight-cache defect

Read-only live review September 10. Rule `hex_bms_ttd_smooth` is IDLE and
triggered by BMS_TimeToDischarge_Min updates. Its action SHA-256 remains
`b5b80aa90ca0dbea4b03cd4c7b62eb73d2ee938d7df2b7940a21a29ba5d543a2`.

The exact live `overnightW` function selects yesterday 20:30 through today
06:00 regardless of the current time, then caches the result under today's
date. If called before 06:00 it queries an unfinished interval. The cache is
not invalidated when that interval completes, so the partial result can remain
the overnight load basis through the rest of the day. Query failure similarly
caches the numeric fallback for the day under the existing policy.

An isolated Node harness executed the function extracted from the hash-verified
live action. At 00:30 a mocked persistence API returned 100 W for the partial
window; after the clock advanced to 06:05 it would return 200 W if queried.
Observed result: early=100, completed=100, query count=1, first query end=06:00
in the future, cache={day:2026-09-10,w:100}. No live rule was invoked or state
written. These are controlled reproduction values, not measured household watts
or proof of a particular historical runtime error.

The intended narrow correction is to select the most recent completed local
06:00 boundary: before 06:00 use the prior day's completed night; at/after
06:00 use today's completed night. Derive 20:30 start from that end and key the
cache by the completed window's date. Use a single clock snapshot and exact
second/subsecond boundaries. Test midnight, 06:00, restart and DST dates before
installing anything. Keep existing averageBetween weighting, fallback, floors,
current thresholds, dwell, median, EMAs and output contracts unchanged.

Do not replace averageBetween with an arithmetic mean of change events: the
previous API investigation found time-weighted LEFT integration. Independent
power-source freshness qualification is still a separate unresolved audit item;
repairing the cache does not establish source coverage.

Read-only live registry search found these output names only in their producing
rule. Repository consumers include Home/Energy displays and sanity checking.
That limited inventory does not prove the absence of external consumers. No
estimator or household control was changed. A tested source patch and managed
installation remain unfinished.
