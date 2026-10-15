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
required. Deployment and natural-score evidence remain pending. Full PR #3 remains incomplete and actuator requests stay disabled.
