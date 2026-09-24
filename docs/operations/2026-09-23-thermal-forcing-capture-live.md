# Thermal shadow forcing capture: live activation

On September 23, 2026, the existing two-hour `thermal-model-shadow.service`
was given a default-off observational capture directory. The installed v4
publisher received only the capture hook and decision-timestamp backport;
the separate source v5/journal changes were not deployed. No model was promoted
out of shadow, and no actuation authority changed.

- Private archive root: `/home/sat/.local/state/thermal-intel/forcing-captures`
  (owner `sat`, mode `0700`); month directories are `0700`, immutable archive
  files `0600`. The user-service drop-in
  `thermal-model-shadow.service.d/forcing-capture.conf` sets
  `THERMAL_SHADOW_CAPTURE_DIR` to that root. The pre-capture installed v4
  publisher backup is
  `/home/sat/.local/state/thermal-intel/runtime-backups/thermal_intel-v4-pre-capture-20260923.py`
  (mode `0600`). Neither private capture data nor this backup is in Git.
  The helper and drop-in now have Git-owned deployment sources in the fixed
  thermal manifest; unit installation creates the private capture root.
- The natural 09:48 MDT run published successfully but recorded a capture gap:
  `generatedAt` had been truncated to seconds, preceding the actual
  post-input decision time by less than one second. The publisher now retains
  full decision-clock precision in `generatedAt`. A fractional-second
  regression test covers that contract.
- After the fix, 160 focused publisher/capture/deployment tests passed. An attended
  09:50 MDT shadow run exited `0` and wrote one 8,770-byte archive. Its
  verifier accepted the private file and all four content digests. The archive
  contains 240 raw Open-Meteo forecast hours and 240 normalized rows.
  `inputs_available_at` and `decision_at` were both
  `2026-09-23T15:50:54.866271+00:00`; publication followed at
  `15:50:57.111209+00:00`. The captured output digest matched the live
  `Thermal_Model_JSON` state exactly. The output remains `shadow` and
  low-confidence. No archive was fabricated for the 09:48 gap.
- Installed publisher SHA-256 after the fix:
  `e0b79aae4887af8502697bfeb813b6c8d9868374e8deaf337957c00897388b45`.
  Installed capture helper SHA-256:
  `73e8afb340bf8b3100528f5ba1c48aaf3e63b1731982bd234d3f02af1ba1d24c`.

Future thermal qualification must use the exact per-publication forcing archive,
qualified action/outcome receipts, and scored shadow forecasts. This archive
alone does not demonstrate a useful model or justify leaving shadow mode.

The next **natural** thermal shadow timer ran at 11:51:12 MDT on September 23
and exited successfully at 11:51:16. Its private 8,686-byte archive records a
17:51:14.111111Z decision and 17:51:16.392209Z publication. The capture
verifier accepted all four content digests and 240 exact forecast rows. The
output remained low-confidence shadow with no candidate because minimum
modeled improvement was not met. Its 1-hour and 24-hour outcomes were not yet
due at this checkpoint; no accuracy or graduation claim follows from capture.

The next eligible strict one-hour audit ran after the selected 13:00 MDT target
and five-minute maturity margin. This exact 11:51 forcing capture scored one
qualified indoor outcome: model absolute error **2.801°F** versus same-origin
persistence **1.620°F**. The published 10.414°F-wide interval covered the
outcome. Its archived outdoor forcing was **1.14°F cooler** than the qualified
outdoor observation. The earlier captured 09:50 publication scored 1.541°F
versus 0.540°F persistence, with outdoor forcing 5.12°F warmer than observed.
Together the two mature, capture-qualified one-hour points have model MAE
**2.171°F** versus persistence **1.080°F**; both remain low confidence. The
09:48 legacy publication remains a missing-capture gap. Opposite outdoor
forecast error signs alongside two indoor underpredictions do not prove a
specific physical-model cause. Neither 24-hour captured target is mature,
and no shadow graduation, tuning or advisory change follows from two points.

Later September 23, the existing read-only strict scorer was rerun after the
13:51 MDT captured publication's one-hour target matured. Across three
non-overlapping one-hour pairs from one revision, model MAE was **2.162°F**
versus same-origin persistence **0.840°F**, with signed model bias −2.162°F.
All three broad intervals covered their outcomes; mean width was 10.414°F.
The exact-forcing outdoor forecast had MAE 3.4933°F and bias +2.7333°F on
those same three targets. This adds evidence of indoor underprediction, not a
qualified correction or weather-causality finding.

The first captured six-hour target also matured: one model error was −6.529°F
versus −3.420°F for persistence. Its 10.414°F interval missed the qualified
outcome, while the same target's outdoor forcing error was +1.26°F. This
single case points to a high-priority physical-model diagnosis but cannot
identify a coefficient or regime correction. The strict 24-hour scorer found
five publications with outcomes not yet due and zero capture-qualified scores.
The model remains in shadow; no tuning, release gate or advice was changed.

The scorer now offers opt-in `--include-pairs` only with `--require-capture`.
It reports bounded issue/target times, signed indoor and outdoor errors,
interval inclusion and non-overlap selection; the default aggregate output is
unchanged. Thirteen scorer tests pass. The three one-hour model errors were
−1.541°F, −2.801°F and −2.144°F; the paired outdoor forcing errors were
+5.12°F, −1.14°F and +4.22°F. The six-hour error was −6.529°F with a +1.26°F
outdoor error. Consistent indoor underprediction across mixed outdoor-error
signs supports investigating the thermal dynamics and mode/action assumptions,
but is not a causal attribution or a justified fitted offset from this tiny
sample. The actual installed v4 shadow model was not modified.

At 18:25 MDT the same read-only strict scorer found a fourth matured,
non-overlapping one-hour pair from the accepted revision: model error
−1.599°F versus same-origin persistence +0.180°F. Across all four pairs,
model MAE was 2.0213°F versus persistence 0.6750°F; all published intervals
covered their targets but averaged 10.414°F wide. The four paired outdoor
forcing errors had mixed signs (+5.12, −1.14, +4.22 and +2.90°F), while all
indoor model errors were low. A second six-hour target also matured: model
error −6.530°F versus persistence −2.880°F, outside its 10.413°F interval.
It overlaps the first six-hour target, so two misses are not two independent
days; the greedy non-overlap selection still contains only the first. Both
six-hour outdoor errors also have opposite signs. No coefficient, threshold,
artifact, control authority or advice was changed on these diagnostics.

The next natural shadow timer completed successfully at 19:51:52 MDT. A
read-only strict rescore after its preceding one-hour target matured found
five capture-qualified, non-overlapping one-hour pairs from the same accepted
revision: model MAE 1.8656°F versus same-origin persistence 0.6480°F, model
bias −1.8656°F and nominal interval coverage 5/5 with 10.4138°F mean width.
The two overlapping six-hour pairs remain model MAE 6.5295°F versus
persistence 3.1500°F, both outside their intervals; only one is independent
under the greedy non-overlap rule. Fourteen captured 24-hour targets are not
yet due and none is scored. The current model therefore remains in shadow.

At 21:37 MDT a fresh read-only strict score found six forcing-captured,
non-overlapping one-hour pairs for revision `c87551f92f02`: model MAE
**1.731°F** versus same-origin persistence **0.660°F**, model bias −1.731°F,
with 6/6 interval coverage at 10.4138°F mean width. The newly matured point
itself erred −1.058°F versus +0.720°F persistence. Three overlapping six-hour
targets now score model MAE **5.9513°F** versus persistence **2.3400°F** and
interval coverage 1/3; the third model error was −4.795°F versus +0.720°F
persistence, with a paired outdoor forcing error of +8.38°F. Only the first
six-hour target is selected by the non-overlap rule (model 6.529°F versus
persistence 3.420°F). All seven 24-hour targets in this bounded audit
were still not due. These mixed-sign outdoor errors and persistent indoor low
bias justify further physical-model diagnosis, not a fitted offset or shadow
graduation.

At 22:17 MDT, a further read-only strict score found the same six independent
one-hour pairs (model MAE 1.731°F versus persistence 0.660°F) and one
additional matured six-hour target. Four six-hour targets now have model MAE
5.4265°F versus persistence 2.2500°F, with 2/4 interval coverage. The new
target at 04:00Z erred −3.852°F versus +1.980°F persistence, and its exact
archived outdoor forcing was +5.62°F warmer than the qualified observation.
These six-hour targets overlap; the greedy non-overlap set still contains only
the first. All eight captured 24-hour targets in the bounded audit were not
yet due. This is evidence against early graduation, not a validated thermal
coefficient change. The read-only scorer, action-as-of and operational-origin
contracts passed 26 focused tests; no live model or advice was changed.

At September 23 23:05 MDT, the next captured one-hour target at 05:00Z
had matured. The bounded strict rescore now has seven non-overlapping
one-hour pairs for revision `c87551f92f02`: model MAE **1.6211°F** versus
same-origin persistence **0.6429°F**, model bias −1.6211°F, and 7/7 broad
interval coverage at 10.4139°F mean width. The new point erred −0.962°F
versus +0.540°F persistence. The six-hour captured set remains four
overlapping pairs (model MAE 5.4265°F versus persistence 2.2500°F), only one
non-overlapping pair. No captured 24-hour target was scored. These are
observational, not independent action outcomes or evidence for promotion.

At September 24 03:54 MDT, the next natural timer invocation exited 0 after
four seconds. Its 09:54:53.209493Z decision produced a private archive with
240 forecast rows; the archive verifier accepted its complete digest set and
the archived output matched the live `Thermal_Model_JSON` exactly. The Item
remained `shadow`, low confidence, with no candidate schedule. A read-only
strict rescore now has nine non-overlapping, one-hour pairs from the current
revision: model MAE 1.4667°F versus same-origin persistence 0.5800°F, with
negative model bias and 9/9 broad interval coverage (mean width 10.4139°F).
Six overlapping six-hour pairs remain at model MAE 4.7023°F versus persistence
2.4300°F; only two are non-overlapping (4.9995°F versus 3.1500°F). All eleven
capture-qualified 24-hour targets in the bounded audit were not yet due.
This is verified natural publication and another unfavorable short-horizon
score, not action compliance, model tuning or grounds to leave shadow mode.
