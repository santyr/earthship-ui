# Native model monitoring continuity

Read-only inspection found 134 delivered native forecasts across five artifact
IDs and no completed native score records at the time of inspection. The shared
latest-native report described historical model `62323d7c` with zero observations,
while the selected model was `d0b0d9c8`. Legacy monitoring's 256 scores are separate
and do not establish native accuracy.

Three concrete continuity defects are corrected:

- Packaging changed model creation time even when the original fitted evidence
  and exact model runtime were unchanged. Model IDs `8cee08fa` and `d0b0d9c8`
  shared runtime `1e819157` and the same fit. Deployment-only packaging now
  reconstructs and verifies the same candidate with its original creation time.
  Changed runtime or original evidence creates a new candidate. Corrupted prior
  candidates are rejected; identity is not preserved by trusting cached fields.
- Native workers shared one latest-report file. A historical worker replaced the
  current model's report, which the publisher correctly rejected as the wrong
  model. Reports now also have artifact-specific files. Publication prefers that
  file and only falls back to the old filename when no artifact file exists.
  Model, future-time and fifteen-minute age validation remain unchanged. Failed
  source reconciliation removes the affected scoped report as well as the legacy
  latest file; a bad scoped report cannot be masked by the fallback.
- Every retained deployment reduced the current model's share of scoring slots.
  Seven selections meant one current opportunity every seventy minutes; at the
  existing 31-history bound it would be every 320 minutes. Current scoring now
  receives alternate native opportunities, every twenty minutes. The other half
  continues rotating all explicitly retained selections. This does not delete
  historical work or change the separate legacy schedule.

Four identity regressions, four initial report/storage regressions and the
scheduling regression failed before implementation. The first affected batch
passed 46 tests in 13.08 seconds. Twelve final integration checks passed in 23.82
seconds, including publication after a different model's report refresh, existing
report-age checks, receipt scoring and historical model association.

The fifteen-minute report-validity window is shorter than the twenty-minute
current scoring interval. A report can still expire between refreshes. This
change prevents displacement and unbounded scheduling dilution; it does not
claim continuous monitoring availability, statistical graduation or a measured
accuracy improvement. Original chronological outcomes and baseline comparisons
are still required. Old frozen workers with fifty-second internal deadlines also
remain a limitation for their own historical backlog.

The report reader/writer changes the optional serving runtime, so this deployment
requires a newly bound candidate using the unchanged fit. Subsequent changes that
leave both that runtime and original evidence unchanged preserve its model ID.
Activation and natural-cycle verification are recorded separately below.

## Activated and serving

Source `b6a5e87`, deployment `2b8aab1b`, model `52dd5d12` activated after the
previous forecast completed. All five owned files, exact service limits and pins,
and three active timers matched. Activation peaked at 56.9 MiB with no memory
limit events. The daily production checkout is clean at this same source.

The normal geometry preparer succeeded. The first scheduled forecast completed
in 43 seconds with exit 0, verified delivery, 12.585 CPU seconds, 81.9 MiB peak
memory and zero swap. Its 19:15:15 UTC household snapshot was shadow, with no
expired qualified sources at verification. At 19:15:30.311 the HTTP200 endpoint
exactly matched the cache and selected model, before the 19:15:35.112 expiry.

This verifies serving after deployment. The new current-model scoring opportunity
and artifact-specific report write still require natural execution. No native
completed scores existed at this readback. The next native current opportunity
is 19:21 UTC; its first 19:15 forecast cannot have a mature one-hour outcome until
20:20:15 UTC. Neither an empty report nor legacy score counts establish accuracy.
Private deployment and normal-cycle evidence is retained in the serving-receipt
QA directory under `actual-monitoring-continuity-20261014`.

At the natural 19:21 UTC opportunity the scorer exited 0 and created the current
model-specific report, assessed at 19:21:15.800053 UTC, with zero mature outcomes
at every horizon. Current report production is therefore verified. The
`historical_model_selection_unavailable` pending reason concerns older deliveries;
it did not prevent the current report write. Mature scoring and accuracy remain
unverified. See `2026-10-14-astro-native-serving-acceptance.md` and the canonical
tracker's `current_model_report_natural_execution` record.
