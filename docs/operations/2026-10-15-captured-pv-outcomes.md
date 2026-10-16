# Captured-PV outcome comparisons

The operator approved a bounded extension of the existing scheduled outcome
scorer. It compares the original captured-DC storage scenarios with qualified
`Power_Evidence_JSON:pv.output_power_w` history, separately from potential array
production. The latter remains unscored: curtailed controller output does not
measure how much the array could have produced.

The new `earthship-household-captured-pv-outcome/v1` binds the external original
energy forecast and v6 plan, and the original learned-load scenario when present.
It replays these originals before scoring. Its target is reported controller DC
output after acceptance. Scenario losses, charging acceptance and usable battery
energy remain assumptions, so these comparisons are provisional and do not
qualify physical calibration or causal effects.

At 1-, 6-, 12- and 24-hour leads, the target is the **hour ending at that lead**.
The original cumulative captured energy supplies each frozen hourly mean; the
original current controller output supplies a persistence reference. Both are
integrated over the identical qualified observed duration. This is explicitly an
hour-mean comparison, not a claim of retained subhour captured-power predictions.
A learned-load scenario is compared only when its original receipt is available;
its model identity is retained rather than backfilled from a later model.

Each source packet retains original persistence times and raw observations, the
actual activation policy/cutover, item mapping, acquisition clocks and digest.
The existing strict power parser preserves invalid barriers, expiry, ordering and
epoch checks. A changed power stream withholds the old-origin comparison. At least
99% coverage is required for accuracy; missing time is never zero generation.
Valid observed zero remains a measurement. UTC elapsed hours preserve DST folds.

Full original scores are compressed and content-addressed under
`~/.local/state/household-intel/captured-pv-outcomes`. Compact verified admissions
pin those originals, retain predictions/coverage/errors and check their arithmetic.
Rolling reports verify the compressed original bytes without repeatedly parsing
a week of raw measurements. The separate `captured-pv-performance.json` reports
per-model paired counts, independent Denver origin days, bias, MAE, RMSE and
persistence skill. It does not pool lead times or claim independence from dense
rows. Each model's persistence comparison uses that model's exact matched pairs.

The existing battery opportunity runs the optional producer after the existing
battery, solar/SoC and learned-load scorers. It handles one due hour per opportunity,
reuses their original hourly sample selection, retains a bounded seven-day index,
and preserves the existing overall deadline and forecast margin. Failures defer
only this new domain. No timer, database permission, fitting, forecast equation,
existing score schema, physical owner or actuator transport changes.

`household_pv_outcomes.py --receipt ... --energy ... --plan ... [--profiled ...]`
replays a full saved score offline against the exact external originals and
executing runtime. Files are private and bounded; changed inputs refuse. It does
not read live history, issue a forecast or fit a model.

The broad household/backend verification passes 1,701 tests. After the single
review correction, all 56 focused cases pass, including genuine older and later
originals with a shared solar cohort but different captured-PV eligibility. Tests cover meter-plane distinctions, same-duration arithmetic, valid zero,
missing coverage, cutover, DST, stream changes, original/runtime tampering, learned
scenario binding, compact admissions, file-only replay and optional-job isolation.
The final review found one Important admission issue, now fixed: a solar cohort
does not bind original current-PV availability or its stream epoch. Ineligible
chosen originals are excluded before queue admission, preserving their original
selection and allowing later valid comparisons to advance. No repeat review is
required. Deployment and natural-score evidence follow. Full PR #3 remains incomplete and actuator requests stay disabled.

Source `dd16b98` activated at 2026-10-15T23:51:39.876899+00:00 as deployment
`33bf61cfe8559ed10fc627510af49529c64e29db2c98cef2164acfebfc0c26c7`. All five owned definitions, three timers,
both scoring calendars and HTTP endpoints pass effective readback. The complete
thermal artifact `188a42a8` and daily service unit remain unchanged. The clean idle
daily source is advanced without starting its job. No fit, manual forecast,
qualification probe or service restart occurred.

The normal 2026-10-15T23:58:26.424973+00:00 opportunity retained the original
2026-10-15T15:50:15+00:00 forecast's first captured-PV comparison. Qualified
controller output was 2.511182 kWh over
3599.710 seconds (99.9919% coverage); the
frozen constant-load scenario predicted 2.846700 kWh and current-PV
persistence predicted 2.474801 kWh over that same
duration. Exact activated CLI replay matches the full saved score, and all
external original files remain unchanged. This is one origin/day, not established
general skill. The learned-load model remains on its ordinary morning schedule.


The operator also approved a read-only accuracy table in the existing Earthship
monitoring panel. The fixed GET `/api/household-captured-pv-performance` serves
only the curated `captured-pv-performance.json`, using the existing owned,
private, bounded cache transport. Query parameters and mutation methods are
refused. Schema validation rejects extra fields, duplicate keys, incompatible
meter scope, nonfinite or inconsistent metrics, invalid clocks and authority
flags. No raw source packets or private receipt paths are exposed.

The table separates constant-AC and learned-AC captured-PV scenarios at each
1/6/12/24-hour lead, showing paired model/persistence MAE in kWh, RMSE skill,
qualified-pair versus mature counts, and independent Denver origin days. Empty
metrics remain collecting; zero baseline error leaves skill unavailable. Only
hours with at least 99 percent qualified coverage enter the metrics, and both
predictions use the same observed intervals. The original report update and
last measured target remain visible; the display clock marks the report stale
at its original expiry. Transport failure shows unavailable. Potential array
yield remains unscored. The table remains below existing Earthship content and
contains no controls.

All 2,489 frontend tests pass, including 34 focused parser, transport and rendered
panel cases; the production build succeeds. An actual naturally issued producer
report is admitted by the new parser. This presentation change does not alter
models, scoring, training schedules, database permissions or physical authority.

The single final review found one Important empty-report admission issue:
malformed non-null last-target data could compare equal to the absence of a
measured target. The correction requires exactly null for all-empty reports;
nonempty reports still require the exact valid latest timestamp. Parser and real
HTTP regressions reproduce the original issue and reject nested private bytes.

UI source `032b12c` deployed at
2026-10-16T01:05:45.464635+00:00. Only four matching frontend files changed in the
live checkout; unrelated overlays remain preserved. Vite loaded the endpoint
without an explicit service restart. The fixed GET returns HTTP 200 with the
actual scheduled report, and laptop (1280×800) and tablet (1340×800) render all
eight lead/scenario rows beneath existing content, without outer overflow,
page errors or mutation requests. Report expiry continues to use the original
producer clock. This verifies presentation and transport, not scientific skill
or completion of the full architectural program.
