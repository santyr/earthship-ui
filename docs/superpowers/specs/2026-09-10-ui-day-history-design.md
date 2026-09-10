# Current-day temperature history boundaries

## Approval and scope

Sat approved the combined UI midnight rollover and historical carry correction
on September 10, 2026 (Hexmem event 8686). This records that approved approach
for written review. The separately approved BMS event/timestamp-link adjustment
remains a separate implementation in its existing worktree.

Correct Home's indoor and outdoor current-day high/low calculation. Preserve
the existing layout, current temperature presentation, independent freshness
alerts, six-hour charts, Bitcoin candles and rolling-24-hour Item contracts.
No OpenHAB controls, persistence settings, notifications, learned state or
telemetry producers change. Task 82 remains held.

## Verified defects

The current REST history request includes only changes inside the requested
range. It omits the state already in effect at midnight. The September 4
two-minute outdoor probe contained only 65.3 F; its known start state was
65.48 F. Including that state changes the helper's maximum. This does not
establish that the sampled full-day extrema were wrong.

OpenHAB 5.2.1 boundary mode supplies a start carry but also moves the first
post-window value back to the query end. Both synthetic timestamps lose the
original observation time. Enabling that mode globally would introduce
look-ahead and must not be used as a source-freshness repair.

Home also stores temperature arrays without their day identity. Its minute
clock tick does not invalidate them. A replay using the actual refresh
coordinator confirms that a pre-midnight request can commit afterward and
leave yesterday's 95 F maximum alongside today's 65 F current reading.

## History contract

Add an explicitly opt-in state-window request to the existing bounded OpenHAB
client. Existing getHistory callers retain their current behavior. Only Home's
two current-day temperature histories opt into this contract in this change.

The opt-in path requires finite, explicit start and end instants with end after
start. It requests native boundary data, then retains only rows whose finite
timestamps fall in [start, end). Discard every end-boundary row, even when it
could be an actual event: the historical interval is deliberately half-open.
Never request itemState=true or substitute the current Item value at an old
boundary. A zero-duration midnight window yields no history without a request.

Treat a row at the start as historical state-in-effect only. Native boundary
data cannot distinguish an exact-start change from a synthetic carry, so do
not claim either has a verified original observation timestamp. Keep this
path separate from sensor update metadata and all source-health calculations.
Preserve unavailable values as unavailable; never search past an invalid latest
state for an older valid value. Existing finite-value extrema handling remains
responsible for excluding nonnumeric values from maxima/minima.

Retain existing response byte/row limits, abort propagation and malformed-body
errors. Failure provides no fabricated carry. Home may retain a previously
successful result only while it belongs to the same local day. Current numeric
values remain part of the existing high/low presentation; they are not used to
reconstruct earlier history or establish historical coverage.

## Day ownership and rollover

Store each successful temperature history result with its requested local-day
start identity, derived by local calendar arithmetic, not a fixed 24-hour
subtraction. Accept completion only if that identity still matches the actual
current local day and the request is still the latest generation.

At the first existing minute clock tick after a day change, invalidate old-day
temperature histories and start a fresh daily request. Check again on tab
visibility restoration, so a sleeping tablet does not wait for its next
five-minute refresh. Derived extrema must ignore results whose day identity
does not match the displayed clock's day. Before valid new history arrives,
use the existing current-value-only or unavailable presentation, never
yesterday's extrema. Remove any added listener on component destruction.

Keep the existing five-minute refresh for normal within-day operation. Reuse
latest-request cancellation; day ownership is an additional condition, not a
replacement. The six-hour indoor chart must retain its separate rolling-window
meaning even though its fetch currently shares the temperature refresh batch.

## Other history consumers

This repair does not redefine power integration, gust statistics, or chart
interpolation. They remain explicit work in the broader change-only audit:
power needs an integration/coverage contract, and irregularly sampled charts
need time-axis and gap handling. Do not silently route them through a temperature
extrema helper. Weather and Earthship's existing rolling-24-hour Items remain
unchanged. Completing this spec is not completing the whole project.

## Verification and release

Before implementation, add failing tests for missing start carry, future end
boundary removal, unchanged default requests, invalid ranges, unavailable carry,
request failure and cancellation. Preserve bounded-body regression coverage.

Use fake clocks and deferred responses to cover a request that crosses midnight,
old-day success after new-day success, failures after rollover, current-only
fallback, visibility restoration and component destruction. Cover Denver's
23-hour and 25-hour days and a non-DST day without changing the host clock.

Run an isolated browser fixture against actual Home at 1340x800, with intercepted
read-only data, to demonstrate midnight rollover and late-response rejection.
No screenshots are required. Verify labels, absence of page errors and overflow,
and absence of attempted control writes. Run affected tests, the full UI suite
and build; obtain independent task and branch review before integration.

After approved integration, verify live read-only request parameters and clipped
results against the known boundary contract. Do not present a fake-clock fixture
as a real overnight observation. Record source revision and evidence in the
canonical tracker and Hexmem. Rollback is a source revert; no database restore,
persistence change or history deletion is needed.
