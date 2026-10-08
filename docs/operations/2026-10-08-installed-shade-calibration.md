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

## Calibrated candidate and original-issued contract

`earthship-installed-shade-candidate/v2` aggregates the original core candidate,
its original runtime binding, the calibration address and band metadata, and the
calibrated runtime binding. Its learning cutoff includes the calibration end;
creation follows calibration creation. The new runtime must retain every
original source hash, dependency version, interpreter and observer pin, and bind
the explicit calibration/aggregate/issued modules. A changed numerical core or
original environment cannot inherit old residual calibration under this contract.

Public build, preparation, private storage and reading replay original core and
calibration inputs. The aggregate file is written after its private original
source archive. Its compact band metadata is compared with the replayed
calibration; a new outer checksum cannot make an altered radius valid. Shape-only
checks and mathematical test fixtures are not source preparation or release proof.

New original publications use `earthship-installed-shade-forecast/v2` and captures
use `earthship-installed-shade-origin/v2`. Bands are actually issued at the exact
1/6/12/24-hour targets using the declared origin regime, with explicit nominal
coverage and calibration identity. Incomplete calibration or an undeclared origin
regime refuses issuance. Other trajectory hours receive no fabricated/interpolated
bands. Learned radii are not clipped to release limits or physical temperature
bounds; the numerical trajectory remains subject to its unchanged physical checks.
Nonfinite uncertainty is refused. These issued observations remain shadow and
unqualified until the separate production publication path verifies release gates.

`earthship-installed-shade-source-scored-pair/v2` first checks the actual persisted
v2 output, then measures its original band width and later native outcome coverage.
An internal numerical view reuses unchanged weather/native/physical/recent-cycle
checks; returned hashes bind the actual v2 capture and publication, never a
fabricated original v1 publication. Older readers refuse the new namespaces.

## Explicit calibrated qualification

The calibrated registration receipt is
`earthship-installed-shade-policy-registration/v2`, with candidate namespace v2.
Its development baseline archive may contain original installed-domain v1 or v2
captures, each through its exact typed reader/scorer; those forecasts retain their
original schemas and identities. Only source-derived persistence/recent-cycle
baselines set the numerical thresholds. Release scoring requires v2 observations
of the one frozen aggregate candidate, runtime and hardware phases.

The report is `earthship-installed-shade-qualification-report/v2`. It replays the
original calibration/candidate, registered thresholds, archived runtime and issued
source packets. Conditioning, independent-day refit stability, 35-day/window
horizon/regime support, positive paired skill against both baselines, coverage,
width, bias, current prospective monitoring and freshness requirements retain their
existing values. Calibration availability alone does not pass these gates.

Use the explicit calibrated command:

```sh
python3 scripts/qualify-installed-shade.py --contract-version 2 \
  --registration "$private_registration" --candidate "$private_candidate" \
  --runtime-bundle "$private_runtime_bundle" --original-pairs "$private_pairs" \
  --output-dir "$private_report_directory"
```

Omitting `--contract-version` preserves the original uncalibrated v1 command.
The assessment clock is actual UTC; there is no date or activation override.
Exit zero means a report was written, including honest unavailable reports.
Read its stage and individual gates. The private JSON and Markdown retain matching
frozen cutoffs, evaluation intervals, thresholds, numerical-fit diagnostics,
calibration metadata, independent support, baseline/error/coverage statistics,
current monitoring, expiry and original source hashes. Reports remain caches;
production must requalify the original references before using an active state.

Natural native-v2 acquisition, a genuinely useful/stable frozen model, actual
registration and sufficient later outcomes remain necessary. No synthetic source
fixture, calibration record or cached report constitutes that release evidence.
Production publication/UI integration and the live entry point remain separate
unfinished work. No service or household control is changed by these APIs.
