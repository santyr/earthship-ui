# Thermal shadow score with non-overlapping forecast windows

The read-only persisted-shadow scorer now reports a deterministic
`nonoverlap:overall` group and per-revision non-overlap groups alongside its
original all-pairs metrics. It sorts scored windows by issue time and retains
the next only when its issue is at or after the preceding selected target.
This avoids counting several overlapping two-hourly 24-hour publications as
independent 24-hour windows. It does not prove statistical independence or
action benefit. The original overlap-aware groups remain unchanged.

At approximately 13:26 MDT on September 23, a bounded read-only audit of
persisted 24-hour shadow trajectories found 33 mature qualified pairs from
46 publications. All 33 were low-confidence, across three model revisions.
The overlapping overall MAE was 2.5145°F for the model versus 2.0236°F for
same-origin persistence; nominal interval coverage was 87.88%. The selected
three non-overlapping windows had MAE 2.5417°F versus 1.5600°F, with 66.67%
interval coverage. Per-revision non-overlap counts were one, two and one;
these revision groups can overlap each other and must not be added together.
The aggregate non-overlap result cannot be attributed to one stable model.

The separate exact-forcing, capture-qualified one-hour audit still had only
two mature pairs. Their windows were non-overlapping, with model MAE 2.171°F
versus persistence 1.080°F. No capture-qualified 24-hour target was due.
The current shadow model therefore remains unqualified for graduation.
Twelve focused scorer tests pass, including a three-window regression proving
that an overlapping middle window is omitted. No model, advice, control,
OpenHAB state, or production history was changed by this audit.
