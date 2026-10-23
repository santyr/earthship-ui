# Raw temperature range sidecar

The supplemental `earthship-weathernext-capabilities/v1` product retains the
original native mean and available quantiles. Mean and median remain separate;
an absent median stays absent. A crossed range is withheld while the original
mean remains usable. Each hour identifies its own source, initialization,
actual acquisition completion, native grid hash and actual band signature.
Near-term and extended segments are selected independently. A refresh never
extends the original source's 24-hour eligibility lifetime.

The fixed GET-only `/api/weather-capabilities` route reads one private file,
with the existing ownership, permission, symlink, mutation and closed-schema
guards. Its 256-KiB limit is separate from existing routes' unchanged 32-KiB
limit. No query-selected paths or browser cloud access are supported. A missing,
stale or malformed sidecar leaves the existing deterministic forecast working.

The detail chart shows the raw range as a purple band and raw mean as a dashed
line, separately from the orange displayed temperature. Accessible cards retain
the percentile values, actual median when present, and source-age information.
The label is “WeatherNext p10–p90; local coverage not yet verified.” Mean-only
sources instead explicitly say that the percentile range is unavailable.

## Explicit staged publication

Run the following from the reviewed source, under the existing shared resource
launcher. Use an absolute archive path and an explicit private shadow namespace.
Omitting `--apply` prepares a digest without creating state. The worker reads
the authoritative OpenHAB site configuration; it never acquires cloud data,
fits/selects a model, writes Items, installs services or commands equipment.

```sh
PYTHONPATH=openhab/scripts python3 scripts/run-household-job.py \
  --minimum-mib 256 --preferred-mib 512 --tasks 24 --seconds 45 -- \
  /usr/bin/python3 -m weather_learning.capability_worker \
  --archive /absolute/path/to/archive \
  --state /absolute/path/to/shadow/google-local-v2
```

`--apply` explicitly retains the immutable original, prepares bounded scoring
work, atomically writes the display cache, then confirms publication. A failed
cache write cannot create issued-score support. A process interrupted after
cache publication is recovered from that original cache before replacement or
assessment. Preparation and confirmed publication remain distinct states.
No production timer or producer pin has been changed by this source work.

## Original-issued verification

The separate `earthship-capability-performance/v1` diagnostic scores only
confirmed original ranges at predeclared offsets 1, 3, 6, 12, 24, 48, 72, 120,
168, 240 and 336 from the first future native hour of each retained issue. This
is sampled lead coverage, not every emitted row or complete history. The
contract digest binds those offsets, metrics and weighting policy.

After target maturity plus two minutes, the existing qualified outdoor receipt
adapter supplies the outcome. Missing, wrong-epoch or invalid observations are
withheld rather than treated as zero. Original observation availability must be
within seven days of the target; late discovery can still score that timely
original after a restart. Existing scores and forecast values are not rewritten.

Metrics are original-mean absolute error, p10/p90 pinball loss, 80% interval
score, inclusive coverage and width. Coverage uses the contracts' 1e-9 Celsius
numerical tolerance at endpoints. Weighted interval score is available only
when the original includes an actual median. No CRPS or joint probability is
inferred from these marginal statistics.

Summary weights give equal weight to local target dates, then targets, then
issued forecasts for each target. Grid, sensor epoch, observation policy and
evaluation contract define separate cohorts. Independent target/date counts
remain distinct from issued row counts. The report covers 28 target days,
summarizes at most 10,000 rows and explicitly reports truncation. All retained
scores remain durable, including outside the summary window. No small-sample
coverage result grants local-calibration, release or actuation authority.

The evaluator hook is absent unless this optional issue index exists. At most
eight observation attempts share the existing 64-attempt job budget with core
temperature, solar, rain and correction work. Optional failures keep their full
reservation consumed when partial read accounting is unknown; global deadline,
memory and admission stops propagate. Preview uses a disposable database copy.
Legacy v2 reports and old score semantics are unchanged.

Capability originals count toward the existing shared 10,000-object/2-GiB
shadow-file cap. The new score index has a smaller 64-MiB ceiling and keeps
32 MiB of free disk headroom. Capacity denial withholds this optional product;
it never raises limits, prunes original evidence or breaks the core pipeline.
