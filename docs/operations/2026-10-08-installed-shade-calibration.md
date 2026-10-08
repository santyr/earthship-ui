# Installed-shade uncertainty calibration

The installed-outdoor-shade candidate has a separate development calibration
contract, `earthship-installed-shade-calibration/v1`. Outdoor shades remain
installed until the operator reports a change. This path refuses removed or
unknown outdoor-shade origins, and retains the existing November no-vent default.

Calibration learns symmetric temperature bands from original as-issued residuals.
`build_calibration` verifies the original native-v2 training snapshot and numerical
candidate proof, then rereads and replays original issued captures, their persisted
publication payloads, exact native outcomes and original recent-cycle receipts.
Residual summaries and pass flags cannot substitute for these sources. Every pair
must match the same base candidate, runtime and sensor hardware phases.

Coefficient fitting and base-candidate creation must precede the separate
calibration interval. Both issue and outcome must fall inside that interval;
outcomes must be mature before calibration creation. A later calibrated candidate
must include the calibration end in its learning cutoff and be frozen before
untouched release evaluation. Calibration outcomes must never be counted as final
holdout or prospective release evidence for the resulting candidate.

The numerical rule is fixed and versioned:

- Required horizons are 1, 6, 12 and 24 hours.
- Select UTC non-overlapping windows, then the first issue per Denver local day.
  Declared regime samples are subsets of that same selected daily sample.
- Require the existing statistical support floor of 35 independent days and
  windows for each horizon and every declared regime.
- For `n` selected residuals, choose the one-based absolute-residual order
  statistic `ceil((n + 1) * 0.90)` as the symmetric radius. Do not interpolate,
  trim, cap or clip that learned radius to a release threshold.
- Insufficient cells retain their raw and independent counts and expose no
  usable radius. One complete cell cannot qualify the other cells.

The finite-sample order-statistic recipe follows the split-conformal construction
in [Angelopoulos and Bates](https://arxiv.org/html/2107.07511v6). Thermal time-series
samples are not established to be exchangeable; independent-window accounting
alone does not establish that assumption. The record therefore explicitly denies
a coverage guarantee. Later untouched and current prospective evidence must still
pass the predeclared coverage, width, bias and paired baseline-skill gates.

`write_calibration` retains original training inputs, candidate/fit proof, original
issued captures and the complete source-packet index before saving the calibration.
Files are immutable, content-addressed 0600 members in an existing owned 0700
directory. `read_calibration` requires an independently expected runtime binding,
checks the private index and source addresses, and replays the original numerical
and issued evidence. A rehashed summary does not become valid evidence.

This is development learning, not activation authority. Original uncalibrated
candidate/forecast/capture schemas remain closed and retain unavailable intervals.
A separately versioned calibrated candidate and issue runtime must bind and issue
these bands before their actual coverage can be release-scored. No historical
uncalibrated publication may be relabeled to contain them. Production, action
advice and automatic actuation remain subject to their existing separate gates.
