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

## Optional receiver integration — isolated verification

`weather_temperature_receiver.py` now supplies an optional Flask extension.
Only literal enabled=True plus explicit1–3named policies registers a raw GET
/weather before-request hook and additive GET /temperature_evidence endpoint.
Disabled mode registers neither and does not inspect configuration. Existing
endpoint collisions refuse installation before modifying the app.

Each process owns a new UUID and initially null records (unknown, never restored
fallbacks). PID changes also invalidate a preloaded/forked collector. A locked
snapshot checks both aware wall time and monotonic elapsed time: expiry at the
exact deadline is irreversible until another valid packet arrives. Clock
rollback clears the epoch and all observations. Polling does not refresh receipt
timestamps, and snapshots are copies rather than mutable internal references.
No-store responses prevent HTTP caches presenting old evidence as current.
Capture failures clear evidence and preserve legacy request handling; endpoint
clock failures return a constant503 error rather than stale measurements.

The collector still reports receiver receipts, not cryptographically authenticated
sensor measurements. Policy matching cannot prove physical ownership or protect
an unauthenticated receiver from deliberately forged HTTP input. Production
deployment must preserve/verify the trusted relay ingress boundary. Capture and
the evidence endpoint accept loopback peers only (127.0.0.1/::1), ignoring
forwarding headers in the current unproxied Flask app. Nonlocal weather requests
retain legacy behavior but cannot populate evidence; nonlocal evidence reads
return404. Local processes and WSGI peer metadata are the trust boundary, not
proof against a hostile same-host process or a future misconfigured proxy.
This implementation adds no
credential, arbitrary URL, file write, learning or control surface.

Verification:67focused tests total (38builder,21collector/Flask,3actual-receiver
comparisons,5existingcharacterizations). The actual installed weather.py is
loaded twice with disposable state, blocked requests.Session traffic, dummy auth
and fixed receiver time. Disabled/enabled/forced-capture-failure modes produce
identical legacy HTTP bodies, diagnostics, health, full previous_data state and
saved JSON bytes across outdoor rain/temp, missing/invalid temp, indoor,
north-wall and foreign-ID packets. Evidence independently rejects fallback and
foreign overwrite. These tests do not send anything to production.

Not yet installed: relay ID forwarding, actual service import/configuration,
production identity/range/TTL/ingress qualification, natural expiry/restart
records, OpenHAB atomic persistence and scoring reader cutover. The isolated
integration closes the adapter implementation/equivalence step only.

## Optional startup wrapper and policy loading

`weather_evidence_wsgi.py` exports the existing `weather.app` and invokes the
configuration adapter. The existing gunicorn service still uses weather:app;
neither its command nor installed sources were changed. A future switch to
weather_evidence_wsgi:app alone does not enable capture.

Only WEATHER_TEMP_EVIDENCE_ENABLE exactly equal to string1 reads
WEATHER_TEMP_EVIDENCE_POLICY. That variable must name an absolute path to an
owned regular file not writable by group/others. Reading uses a no-follow,
nonblocking file descriptor (rejecting symlinks, FIFOs and directories), checks
size and reads at most8193bytes with an8192byte limit. JSON duplicate keys,
nonfinite constants, unknown fields and implicit policy values are rejected.
The exact document shape is version=1 plus streams mapping names to model,
sensor_id, minimum_f, maximum_f and validity_seconds. There is no installed
production policy, default identity or default acceptance range.

Disabled mode performs no policy read or app mutation. Invalid enabled
configuration emits a constant sanitized warning and retains the legacy app
without an evidence endpoint. Collection still requires reviewed identity,
range/expiry and ingress decisions; malformed settings never fall back to
wildcard collection. Endpoint/policy errors cannot authorize learning.

The23new configuration/wrapper tests plus67previous cases pass (90total).
They cover exact enable semantics, strict schema/size/duplicate/nonfinite
rejection, unsafe file kinds/permissions, sanitized startup failure, and the
actual WSGI entrypoint with an isolated app in enabled/disabled modes. These
checks do not qualify a production policy or constitute service deployment.

## Outdoor identity forwarding — installed September10

The existing relay's WH65B/WH24 filter already rejects station IDs other than
206. Its forwarded outdoor payload now includes id=data["id"] from that same
filtered packet. No expected ID is invented downstream. Reproducible patch:
`openhab/patches/rtl-weather-forward-outdoor-id.patch`.

Five tests execute the actual relay main AST using fake subprocess/RF lines,
fake sleep and captured sends; they perform no real RF or HTTP operation. Both
outdoor aliases failed solely for missing ID before the patch, then passed with
every weather value unchanged. Foreign207, missing ID and wrong-type string206
remain filtered. The full focused evidence/receiver suite passes95tests.

The current script including the temporary WH32B survey was backed up to
`/home/sat/bin/rtl_weather.py.before-outdoor-id-forward-20260910`, originalSHA256
`d2af9e4e621f611e783227e696adaac3daf659c3aee1a3d8b02c3af5ac7fc928`.
Syntax and whole-source AST comparison proved the only change is the added
outdoor id expression. ReplacementSHA256:
`9f034f9d0ed5912ad5495136bcb6414c20bccb3cb24d1c09622a16c29c9e2777`.
rtl_weather.service was restarted; it and weather.service read back active.
The preexisting systemd disk/loaded-unit drift was not daemon-reloaded. Receiver
source and rain state were not edited, and the temporary indoor survey retains
its original expiry. No temperature evidence endpoint or learning was activated.
The new optional receiver still requires its separate policy and deployment.
Read-only receiver health after restart reports outdoor packet receipt
19:18:59MDT, age1second and aggregateok. That confirms normal packet reception,
not field-qualified evidence or an end-to-end persisted identity record.
