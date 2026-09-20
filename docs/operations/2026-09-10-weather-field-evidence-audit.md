# Weather field evidence and isolated receiver tests

September10 read-only runtime/source review plus isolated characterization.
weather.service runs one gunicorn worker, weather:app, from /home/sat/bin on
port5000. rtl_weather.service is active. These scripts are not in a Git checkout
at /home/sat/bin. Neither service, source nor live state was modified.

The installed hourly scorer still chooses the closest temperature change within
15minutes of a target and consumes it. The prior September5 reproduction already
established that post-target changes can be selected and healthy constant values
can be missed. Repeating that probe is not additional completion evidence.
The missing prerequisite remains per-temperature field freshness and identity.

## New executable characterization

Five tests in openhab/scripts/test_weather_receiver_characterization.py execute
the actual installed receiver source with a separate Flask client. Before module
initialization, they redirect its __file__-relative state into pytest tmp_path,
seed only disposable values, provide dummy auth, force OPENHAB_WRITE=0, block all
requests.Session network traffic and forbid access to production previous_data.
No HTTP request is sent to the real receiver or OpenHAB.

The tests establish current behavior, not desired acceptance criteria:

- An empty sensor map reports aggregate health ok without any observation.
- Missing and invalid outdoor temperatures refresh packet health while a seeded
  70F fallback remains the exposed temperature.
- The string nan converts to a nonfinite temperature in receiver state while
  refreshing the model update time.
- Two arbitrary indoor IDs overwrite the same WH32B temperature slot; its health
  record does not retain the ID.

All five tests pass in0.15seconds. Those inputs are synthetic; this does not
prove live contamination, nonfinite measurements or a specific learned error.
The existing /home/sat/bin/tests/test_weather_app.py was NOT run: its loader
imports the live module and its request handlers can save production
previous_data.json. It lacks the isolation above. No production state was used
as a fixture or overwritten.

## Required next contract

Packet health alone must not qualify temperature scoring. A receiver evidence
record needs the exact field value, validated finite/range status, explicit
sensor identity, receipt/observation time and restart epoch together. Missing or
invalid fields must not acquire a fresh temperature timestamp from another
field's packet. Do not assign a new observation time to restored values.

The RTL outdoor path filters ID206 but omits that ID from its forwarded payload.
The indoor relay forwards IDs but does not pin one, and the receiver drops that
identity. Confirm the intended indoor identity before selecting it; do not infer
one from an aggregate health label or overwrite legacy consumers silently.
Any new evidence interface should be additive and default-off for learning.
Preserve existing display data, rain accumulators, everyChange persistence and
learned state while qualifying the new evidence stream.

Only after that contract is reviewed and verified should hourly learning use
the valid state in effect at the target, with independent freshness, rather
than the nearest change event. The old learned history must not be relabeled or
reset, and no retrospective synthetic origin can count as validated training.
Temperature outcome attribution and the broader all-algorithm audit remain open.

Subsequent correction: the operator-approved indoor ID-only survey observed
WH32B235, still awaiting physical ownership confirmation. Outdoor206 ID
forwarding is now installed in the relay with the original filter and all
weather values preserved. The optional temperature evidence collector and
startup wrapper are implemented and tested but not selected by the live service.
See [temperature evidence contract](2026-09-10-temperature-evidence-contract.md)
for exact source hashes, isolated tests and the current deployment boundary.
These follow-ups do not repair or qualify the legacy receiver's fallback/health
semantics characterized above.
