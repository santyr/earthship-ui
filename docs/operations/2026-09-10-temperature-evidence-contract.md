# Temperature receipt evidence foundation

Scope: additive evidence for change-aware hourly temperature scoring and later
thermal outcome attribution. Existing display/fallback/rain behavior, learned
state, schedules, controls and packet-health Items remain untouched. The helper
is not wired into production or any learning consumer.

## Source and identity

The operator-approved ID-only relay survey observed WH32B235 on September10
18:32:12MDT; a later bounded journal check found no additional surveyed IDs.
That is an observed identity, not proof of physical ownership or exclusivity.
Outdoor WH65B/WH24 is filtered to206 by the relay; its current forwarded payload
omits the ID. North-wall WH31E193 is explicit in live OpenHAB. New accepted
outdoor evidence must require the actual forwarded ID, not inject206 in the
receiver merely because it expects that station.

The pure `weather_temperature_evidence.py` helper requires a canonical supported
model, numeric expected ID, finite ordered Fahrenheit acceptance bounds and an
explicit1–300second validity policy. There is no implicit production policy or
indoor-ID selection. Test bounds/expiry are fixtures, not manufacturer ranges
or activated household settings. WH24 aliases canonical WH65B; protocol/ID
matching remains mandatory. Known other IDs/models produce no event for this
configured stream; missing/ambiguous identity on the expected model produces
an invalid barrier. No wildcard sensor acceptance is allowed.

## Atomic record

Exact fields: version, streamEpoch, recordedAt, model, sensorId, field, status,
reason, receivedAt, validUntil, temperatureF. Version1 concerns this temperature
receipt contract, not the distinct BMS atomic schema. sensorId identifies the
configured stream; only a valid record attests a matching received identity.

An adapter supplies raw request fields before fallback or conversion, an aware
server receipt clock, and a new canonical UUID epoch for each receiver process.
The helper has no disk, network, environment, saved-state or learning access.
Request-supplied timestamps are ignored. receivedAt is receiver arrival time,
not a radio-device measurement timestamp. Valid records bind the value and
expiry to this exact receipt. Repeated unchanged values receive distinct new
receipt times; no periodic persistence is added to disguise change-only data.

Missing/ambiguous/invalid temperature or identity emits status=invalid with
receivedAt, validUntil and temperatureF null. Invalid temperature values include
nonfinite numbers, booleans, malformed text and values outside explicit policy.
Duplicate HTTP id or temperature fields cannot silently select a value.
Unrelated humidity cannot refresh temperature. Saved display fallback values
are never inputs. This deliberately treats an incomplete expected-sensor packet
as a qualification barrier; it does not declare the physical temperature zero.

## Integration and acceptance still required

1. Confirm intended sensor ownership and production range/validity policy.
2. Preserve the actual filtered outdoor ID in the relay payload. Add the helper
   before receiver fallback with a process epoch and an additive evidence
   endpoint. Restore no evidence from legacy previous_data.json. The new path
   must be optional and isolated from legacy request handling failures.
3. Verify installed helper/source hashes, legacy request/display/rain equivalence,
   known-ID routing, same-value heartbeat and restart invalidation using isolated
   fixtures first, then bounded natural live records. Do not send synthetic
   weather to production or count fixtures as learned outcomes.
4. Persist each complete record together through additive OpenHAB String Items.
   Preserve everyChange persistence. A consumer enforces expiry at the target,
   rejects future receipts, incompatible epochs, invalid barriers and missing
   coverage. It must not equate current packet age with past field validity.
5. Only after verified end-to-end field history exists should hourly scoring
   select the qualified state in effect at the target, never the nearest
   post-target change. Preserve old learned state; record any assessment-policy
   cutover explicitly. Bandit/reward/threshold activation remains separate.

Verification:38pure helper tests cover closed atomic shape, finite/range checks,
missing fields, malformed/foreign IDs, unchanged-value receipts, ignored request
timestamps, no saved fallback, outdoor alias/ID requirement, duplicate fields,
explicit epochs/timezones and policy bounds. No production source, service,
Item, persistence or learned-state change was made by this foundation.
