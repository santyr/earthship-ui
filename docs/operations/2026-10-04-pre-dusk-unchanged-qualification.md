# October 4 unchanged pre-dusk forecast qualification

The October 4 natural pre-dusk issue predicts **74%**, the same numeric value
as October 3. The read-only qualification gate incorrectly required one new
same-day numeric JDBC row. This Item uses `everyChange`, so the successful
unchanged Number publication legitimately leaves no new numeric row.

## Evidence contract and fix

The existing publisher first PUTs `Predicted_SoC_Trough_PreDusk`, then publishes
its immutable issue receipt after the Number PUT succeeds. Its receipt carries
the current issue clock, linked morning issue and original atomic SoC digest.
The qualifier now accepts either its existing single matching same-day write,
or, with no same-day changes, the latest matching original numeric change
before that day. Receipt timing, sunset lead, derived integer prediction,
morning linkage and exact restricted-reader SoC qualification still apply.

The lookup requests JDBC history with `boundary=false`; it retains the actual
old persistence timestamp and reports `numeric_state_basis` as
`unchanged_persisted_value`. OpenHAB's `boundary=true` returned a 74% row stamped
at the requested day's midnight rather than the actual change time, so that
response cannot establish an original numeric write. The checker does not use
that interpolation or a current Item state.

One bounded lookback GET covers 31 local calendar days and at most 64 numeric
changes, under the existing 32,768-byte transport budget. Missing, malformed,
conflicting, duplicate, oversized or out-of-range histories withhold the issue.
Both the standalone qualifier and the experimental comparison reader use the
same bounded local REST adapter. An anchor older than the read budget remains
unqualified; the budget is not a
claim that an old numeric sample became fresh. No DB privileges are added.

## Original October 4 qualification

Two native CLI runs agree at **October 5 00:29:45Z**:

| Evidence | Original timestamp or result |
| --- | --- |
| Linked morning issue | October 4 12:40:57.827890Z |
| Natural pre-dusk issue | October 4 23:30:00.923128Z |
| Immutable receipt persisted | October 4 23:30:00.926000Z |
| Atomic SoC source persisted | October 4 23:29:49.183994Z |
| Last numeric change | October 3 23:30:00.936000Z |
| Qualified prediction | 74%, unchanged persisted value |
| Completed-night check | Pending; no outcome read or score yet |

Private proof files are durably staged with mode 0600 under the mode-0700
`/home/sat/.local/state/thermal-intel/qualification-receipts/pre-dusk-unchanged-20261004/`
directory. Original working copies remain in `/tmp/earthship-pre-dusk-unchanged-20261004/`.
`qualified.json` and `repeat.json` match, SHA-256
`c8bfb0328f173ad0e2bdff8011021a413cc054ebac50fb8457a9595a5da337fb`.
`night-pending.json` preserves the same qualified original issue, awaiting the
October 5 11:00 America/Denver outcome boundary. Browser rendering is not
claimed by these CLI reports. A separate live **1340×800** browser read at
**00:39:02Z** verifies exactly one `Estimated trough 74%` label with title
`Pre-dusk estimate for Oct 4 night; not a measured minimum.`, with zero page
errors. The browser allowed only local Vite GETs, blocked mutation/external
requests and closed without screenshots. Its `display.json` proof is in the
same private directory.

This change affects the repository's qualification and experiment readers.
The live publisher, its calculations, Items, persistence configuration and
runtime source installation are unchanged. No forecast job, equipment action,
training run, receipt, or synthetic numeric write was triggered.

## Validation

The original affected baseline passed 25 tests. Before production changes, two
new behavioral regressions failed because unchanged-value issues were refused.
The focused source/history/qualification checks then passed 50 tests, including
original SoC integrity and rejection of contradictory or missing evidence.
Independent review identified one benchmark caller using an unbounded REST
adapter. Four real-CLI transport regressions failed before correcting that
caller; all receipt/numeric archive reads now use the existing bounded adapter.
The final affected checks pass **108 tests**. Independent re-review approves
with no remaining blockers. A native historical charge-profile check retains
the October 3 reported-full result, 99% at sunset and its original source digest
under the corrected reader (`charge-reader-compatibility.json` in the same
private proof directory). The complete Python suite on the final reviewed code passes **4,085 tests**,
with **10 skipped** and **91 passing subtests**, exit zero in 385.82 seconds.
The run uses the installed Solar-PV/Primal dependencies and pinned NIP-04 stdin
NAK binary. The final log is `/tmp/earthship-pre-dusk-unchanged-final-tests.log`.
`git diff --check` passes. This verifies the read-only correction; seasonal
forecast skill, genuinely confirmed actions and unfinished future targets
remain separate gates.

## October 4 natural charge-to-sunset target closed

After the actual **00:40:34.220Z** sunset, a restricted read-only charge-only
assessment at **00:41:01.651098Z** qualifies October 4 under the corrected
bounded reader. The original weather issue is 12:40:57.827890Z; its distinct
atomic SoC assessment is 12:40:57.840Z, with 87% at that origin. The bank first
reported 100% at 16:04:16.538195Z and is 98% at sunset, with 99.9855% source
coverage. The original source and target digest are retained in
`oct4-charge-outcome.json`; target digest is
`e7769e2332d2fcfd218940e2751f57d6a07ce05a0cf13327e608683eab50bb9f`.
This is reported-full evidence, not a calibration or physical capacity claim.
The completed full-day PV and overnight targets are not available yet, so
October 4 is not added to the three completed joint PV/charge/night days.
No learned correction, automatic job or equipment action was run.
