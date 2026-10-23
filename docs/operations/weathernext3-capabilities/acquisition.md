# Optional native statistics acquisition

The collector keeps its existing default twelve-band core and v1 result when
no optional profile is supplied. Optional acquisition requires explicit
`--collect`, a reviewed 48/360-hour horizon, and repeatable
`--capability-profile` arguments. The approved profiles are `uncertainty-v1`,
`atmosphere-v1`, and `rain-uncertainty-v1`. Their frozen definitions and hashes
remain in [profile-contract.json](profile-contract.json). Production service
arguments and credentials have not been changed by this implementation.

Core full/interim collection runs first. Optional groups run in priority order
under the same collector lock, initialized SDK, transfer counter, EE request
counter and acquisition clock. There is no new transport per group and no
larger policy: 32 EE requests, 8 MiB of responses, 75 seconds, and the existing
native-point limit. The original noncommercial preflight remains mandatory for
actual SDK initialization. Paid access, full ensembles, Requester Pays and
account changes remain disabled. EECU balance and actual account tier remain
unknown; request and byte counts are not EECU measurements.

Each query preserves its collection's native projection and one nearest native
cell. Station and gridded cells stay separate. Hourly solar/rain intervals and
all raw/normalized units remain explicit. No percentile interpolation or local
downscaling is introduced. Full and interim coverage remains relative to source
initialization. Rain uncertainty is requested only for full runs; an interim-only
job reports `full_run_only` deferral rather than silently omitting the profile.

Profiles retain separate immutable originals rather than changing the old
snapshot schema or core original. A valid grid received before another grid's
failure is retained, with incomplete-profile status and exact missing bands.
Core requests remain strict. Partial optional originals can support only the
statistics actually delivered and cannot satisfy a complete expanded cache hit.
A mean-only source cannot become a quantile profile. Consumers must preserve
the original identity of each statistic when joining separate profiles; current
raw-temperature v1 rows do not borrow p50 from a different snapshot.

Expanded cache reuse checks requested statistics, units through original replay,
native grid/cell, authoritative site, original run, full requested coverage and
actual source availability. It validates the original rather than trusting an
index's run label. Malformed candidates cannot hide a valid later candidate.
Warm reuse keeps original first-seen/completion clocks; it never renews source
availability or claims a fresh provider revision.

The opt-in v2 collector result reports collected/cached, unavailable, rejected
and deferred groups, normalization status, requested-profile hash, actual-band
signature, source identity, missing fields and retry time. `consumed` remains
false at this acquisition boundary; declared consumer names are not evidence of
downstream use, local skill, calibration or serving admission.

Retries are scheduled, never slept/polled inside a job. Each profile/run/horizon
gets at most two attempts, with a fifteen-minute cooldown after missing or
rejected delivery. The private, atomically replaced backoff file is at most
16 KiB and six current slots. It is mutable operational state, separate from
immutable forecast/outcome history. Quota restriction stops lower-priority
remote work and persists 1/6/24-hour bounded cooldowns. Only allowlisted Google
error-status codes enter diagnostic traces; arbitrary messages stay private.
Global cancellation, admission and memory stops propagate. Even optional cache
work stops when the shared acquisition clock is spent.

All core/interim/optional writes share the existing 10,000-object/16-GiB archive
cap, 8-MiB normalized-object cap and free-disk reserve. No original or pending
outcome dependency is evicted. Per-group preflight reserves the existing
worst-case object bound before another request. The result exposes current
objects/bytes, maximum new objects and archive growth per cycle, and conservative
remaining complete cycles. It does not invent days of runway without a measured
schedule/growth rate or infer cloud quota from local disk capacity.

Offline fixtures exercise both native grids, every enabled statistic and full/
interim coverage through the actual bounded HTTP bridge and normalizer. The
pinned SDK profile separately binds all point queries to the real API signature
with outbound sockets blocked. Cold/warm replay, staging retention and the
actual JS public reader run under existing host admission; these are software
and resource proofs, not live cloud-access or physical/statistical qualification.


## Self-contained uncertainty original

Task 10 adds `uncertainty-complete-v1` as an explicit alternative to the frozen
`uncertainty-v1` quantile-only profile. The original profile identities and
originals remain unchanged. Only one uncertainty variant may run per collection
cycle. The new profile retains the six temperature statistics together and the
mean/p10/p50/p90 solar and wind statistics on each variable's own native grid.
This gives the existing temperature detail and marginal adapters the companion
means they require without combining statistics from separately acquired
originals or borrowing an older original's availability clock.

The new profile requests fourteen bands instead of nine within the same two
native queries per run. It retains the existing 32-request/8-MiB/75-second owner
budget and maximum new objects per cycle. Extra response columns consume that
shared transfer budget; they do not justify a larger limit. A warm cache must
satisfy the exact new profile, not the legacy quantile-only original. Missing
one native grid preserves the usable other grid and the independent core.
The same two mutable uncertainty retry slots change with an explicitly selected
variant; unrelated cooldowns and the global quota cooldown remain intact. No
forecast original or pending scoring dependency is pruned.

Solar marginal quantiles refer to the original hourly radiation energy/mean.
Wind endpoint quantiles are retained statistics but do not become quantiles of
an hourly averaged wind target. Rain hourly quantiles likewise do not become
calendar-day or rolling-24-hour quantiles; the occurrence/amount challenger uses
its separately defined target and measurement threshold. These mathematical
limits explain intentionally unconsumed statistics in the capability matrix.
No production profile is enabled by adding this source option.
