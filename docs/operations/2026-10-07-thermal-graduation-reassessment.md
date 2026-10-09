# October 7 thermal graduation reassessment

PR [#2](https://github.com/santyr/earthship-ui/pull/2) merged as
`68364dd63d649f8777368282e73305ac759be9a6` after all four CI checks passed.
This continues the existing forecast-ML goal; PR #3 household-planner
architecture remains deferred.

The [machine-readable development report](2026-10-07-thermal-graduation-reassessment.json)
is assessed at **2026-10-07 15:54:12 UTC**. It verifies 26 original publications,
85 mature source-bound horizon pairs, and 589 captured native receipt queries.
Receipt counts include repeated queried targets and are **not** independent
observations. Original captures, native outcome receipts and recent-cycle
comparators are preserved privately. A network/database-disabled repeat produced
the same scores and source hashes. Every public metric is stratified by the full
artifact digest; errors retain the original scorer's 0.001°F precision.

The newest published artifact in this checkpoint, `f5b7d7532291…`, has one mature
1-hour pair and zero mature 6/12/24/48-hour pairs. That single 1-hour error is
0.670°F, versus 0.540°F persistence and 0.180°F recent-cycle. It establishes no
release-quality skill. The preceding `366e01fe2868…` artifact has only one
non-overlapping 24-hour window: 0.450°F error versus 1.260°F persistence and
1.800°F recent-cycle. Its 12 independent 1-hour windows have 0.745°F model MAE
versus 0.345°F recent-cycle MAE; four independent 6-hour windows have 1.774°F
versus 1.125°F. A single good 24-hour result does not override missing support
or losses at other horizons. Local independent-day counts are also reported.

The earlier pooled descriptive comparison had two disjoint 24-hour windows,
but pooled changing artifacts is not a release test. No dates inspected in this
reassessment may subsequently be called an untouched final holdout.

## Blocker dispositions

| Existing blocker | Disposition | Evidence and next requirement |
| --- | --- | --- |
| Historical 24-hour loss to baselines | still_blocked | Current legacy v4 backtest still reports model MAE 2.179°F versus persistence 1.690°F and recent-cycle 1.834°F. This is conditional historical evidence, not exact operational qualification. |
| Low-confidence operational forecasts | still_blocked | All scored outputs report low confidence; short-horizon losses and limited interval support remain. New publication must separate forecast confidence from action-label confidence. |
| Insufficient independent operational windows | still_blocked | Newest artifact has no mature 24-hour pair; earlier individual artifacts have at most one independent 24-hour window in this checkpoint. |
| Mixed artifact revisions | still_blocked | Metrics are now stratified; a frozen single-candidate untouched/prospective release test still does not exist. |
| Missing confirmed action outcomes | required_for_advisory_stage | Not required solely to enable Stage A forecasting; genuine qualified action-response outcomes remain necessary for Stage B. No reconstructed state is promoted. |
| Action-label confidence limits | not_required_for_forecast_stage | An action-only confidence penalty must not veto independently qualified temperature forecasting. It still limits action advice. |
| Unset graduation thresholds | still_blocked | The shadow contract still has no numerical production thresholds. A new versioned policy must be fixed before final holdout inspection. |
| Prospective evidence outside fit artifact | still_blocked | This immutable capsule closes reproducible development scoring, but a versioned release binding must include qualified prospective evidence. |
| Incomplete seasonal/regime coverage | still_blocked | The short October checkpoint does not establish winter or general seasonal skill. Qualification must declare and measure its supported regimes. |
| Conditioning/stability absent from current artifact | still_blocked | Hardened fit code is merged, but the installed legacy artifact does not carry a fresh independent-day assessment under that code. No manual fit was run on the household host. |
| Initial source epochs not bound at issue | still_blocked | Legacy v2 captures preserve values/timestamps/expiry, but not complete original initial-receipt epoch identities. Do not invent them later. |
| Publication runtime not bound at issue | still_blocked | Acquisition-time source was frozen and reproduced; artifact training revision alone does not prove original publication-runtime identity. The new capture must bind it at issuance. |

Forecasting and action advice retain separate gates. The outcome of this report
is **keep shadow**, not a declaration that the engineering or whole goal is done.
Remaining work follows the [approved-scope implementation plan](../superpowers/plans/2026-10-07-thermal-graduation.md).

## Reproduction and host limits

The private capsule is under
`/home/sat/.local/state/thermal-intel/qualification-receipts/thermal-graduation-20261007/thermal-qualification-20261007`.
It contains no copied credential configurations. The following reads only saved
code/evidence and does not query services, fit models or publish Items:

```sh
systemd-run --user --scope --quiet \
  -p CPUQuota=25% -p MemoryMax=768M -p MemorySwapMax=0 \
  -p TasksMax=48 -p IOWeight=10 \
  nice -n 15 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$PWD/scripts:$PWD/openhab/scripts" \
  python3 scripts/thermal_qualification_evidence.py \
  --capsule /home/sat/.local/state/thermal-intel/qualification-receipts/thermal-graduation-20261007/thermal-qualification-20261007
```

After the operator reported a host hard reset, local work was limited to one
small check at a time under verified cgroup CPU/memory/task limits. Forty-five
focused evidence/comparator tests passed under the resource limits.
Full suites run in CI. Subsequent operator approval removed the off-host
execution requirement: small serial local fits are permitted with verified
resource limits and host preflight. No production service, forecast equation, actuator,
notification policy or credential was changed by this reassessment.


## October 8 live-entrypoint engineering update

The installed-domain publisher now has a bounded private CLI, real source
collector and telemetry/JDBC transport, serial issue lock, immutable attempt
markers, and two-receipt capture orchestration. The existing mass observer
provides the initial thermal state while original sensor receipt metadata is
retained. Send-time checks follow metadata lookup and request pacing. Failure
withdrawal requires actual JDBC confirmation before it is called verified.
Service/timer and separate numeric String Item templates await actual integration.
See the [live entrypoint runbook](thermal-model-graduation.md#bounded-installed-domain-live-entrypoint).

The previous committed milestone `8d578245b66263f34694439649f8b94e61f9c767`
passed all three hosted workflows: CI `37865825960`, Forecast ML `37865825924`,
and Thermal delivery `37865825904`. That result applies to that exact commit;
new live-entrypoint changes require their own full hosted verification. These
engineering checks do not change the October 7 statistical scores above.
No new household candidate has qualified and no production cutover is claimed.
The operator reconfirmed that outdoor shades remain installed.
