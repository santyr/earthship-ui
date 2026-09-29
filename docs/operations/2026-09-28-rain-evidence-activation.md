# Rain-counter receipt collection: guarded live activation

September 28, 2026, about 22:11–22:14 MDT. This activates observational
raw outdoor rain-counter receipts only. It does not change the legacy weather
adapter, precipitation forecast scoring, a thermal model, or any control.

## Preflight and receiver reload

The `weather.service` master was active as user `sat`, PID 1607215, and all
three existing temperature receipt streams were valid. The exact new rain
Item/Thing names, receiver modules, private policy and root-owned rain
systemd drop-in were absent. The existing WSGI preimage SHA-256 was
`f4056c28f8b49eda30a59005d52e1818f66e340cf22ed5cc929ce46123b5e684`;
the existing temperature config and receiver modules matched repository
sources. A mode-0600 copy of only that WSGI preimage is retained privately at
`/home/sat/.local/state/weather-rain-rollback-BuHwR8` for exact rollback.

The reviewed rain evidence, collector, config, private policy and WSGI files
were installed byte-for-byte from Git. The policy is mode 0600, owner
`sat:sat`, and was parsed successfully from its installed path. The
root-owned systemd drop-in could not be installed without sudo and was not
altered. Instead, the reviewed WSGI entrypoint explicitly enables rain
capture using that private policy and honors
`WEATHER_RAIN_EVIDENCE_ENABLE=0` as an opt-out. This is a deliberate
source-level release, not an implicit policy-file-presence activation.

After a final PID and temperature-health check, exactly one `HUP` was sent to
the sat-owned Gunicorn master. The master PID stayed 1607215, the old worker
exited and a new worker booted. The `/rain_evidence` endpoint appeared with a
new epoch; natural sensor-206 packets made it valid with zero invalid-packet,
counter-drop and counter-jump latches. The existing outdoor, indoor and
north-wall temperature receipts also returned valid. No whole OpenHAB or
weather-service stop/restart was used.

## File-owned OpenHAB collection

The exact `weather-rain-evidence.things` file was hot-loaded first. REST
readback found `http:url:weatherRainEvidence` file-owned (`editable=false`),
`ONLINE/NONE`, pointed only at the local `/rain_evidence` GET endpoint, with a
String `snapshot` channel configured `READONLY`. The two standard HTTP
last-success/last-failure channels were unchanged binding-generated metadata.

The exact `weather-rain-evidence.items` file was then hot-loaded. REST found
one file-owned String `Weather_Rain_Evidence_JSON` Item and exactly one
file-owned link to `http:url:weatherRainEvidence:snapshot`. The first four
natural JDBC rows, from `2026-09-29T04:12:48.122Z` through
`04:13:58.363Z`, all parsed under the strict source-bound receipt schema:
one epoch, increasing packet counts, stable zero fault latches and a maximum
observed source interval of 32.505 seconds. This is bounded post-activation
continuity, not a complete local day or fault/restart qualification.

The OpenHAB PostgreSQL `items` registry maps the new Item uniquely to ID 657,
`public.item0657`. The restricted `energy_power_reader` currently lacks
SELECT on that table. No database privilege was changed; an exact-table
grant has been requested. The pure day reader and JDBC adapter remain
unconnected to production forecast scoring. September 28 began before
collection and cannot qualify; September 29 is the first possible complete
local day, assessable after September 30 local midnight and only if every
coverage, source, fault and midnight-bracket gate passes.

## Recovery boundary

If the weather extension fails, restore the exact private WSGI preimage and
send one HUP to the verified current sat-owned Gunicorn master; recheck all
three temperature receipts. The three newly installed rain Python modules and
private policy may then be removed only after exact-path/hash validation;
historical JDBC evidence must be retained. If OpenHAB collection fails,
withdraw only the two new exact file-owned rain definitions after checking
their hashes, and recheck the existing temperature Thing/Item. No forecast
state, established sensor Item, motor, pump, inverter or protected rule should
be modified in rain rollback.
