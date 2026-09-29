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
grant has been requested. At this collection checkpoint, the pure day reader
and JDBC adapter were unconnected to production forecast scoring. September 28 began before
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

## Forecast scoring guard installed before the next natural run

Commit `c0dd094` adds a dated rain-learning cutover at the first persisted
receipt, `2026-09-29T04:12:48.122Z`. September 28 is explicitly partial and
withheld. From September 29 onward, both same-day and day-3 precipitation
errors require the exact restricted, complete-day source-bound counter reader;
neither falls back to `max(RainFallDay)`. The worker records bounded score
provenance and preserves retryable forecast targets when evidence is absent.
The existing rolling precipitation-error arrays are retained as historical
legacy values; they were not reset or relabeled as qualified. Adjacent
forecast/weather/SoC validation passed 332 tests with two optional skips.

The forecast service was inactive when the exact worker and four read-only
rain modules were installed. Installed/source worker SHA-256 is
`866bd4c2344e0895470818bd5d5cd25b33ad567946caa7e7caa4943f91c491e5`;
the prior exact worker SHA-256
`af54be82936fd8808dea0002117ef40064c27e42e8cf7858b6bca603624129a7`
is retained privately at
`/home/sat/.local/state/forecast-intel/rollback-rain-qKXNyO`. An installed
fresh-process import refused September 28 as `evidence_cutover_partial_day`.
The timer remained enabled for September 29 06:40 MDT; no manual forecast run
occurred. The learned PV coefficients (`k_res=1.3`, `d_direct=5.40326272`)
and existing precipitation-error arrays were unchanged at installation.
The first natural writer readback, restricted SELECT grant and first complete
rain day remain open. Until they pass, qualified precipitation error scoring
is withheld; numerical weather forecasts and unrelated learners continue.

At 22:28 MDT, a read-only JDBC persistence query returned 32 natural rain
receipts since activation. They share one stream epoch; packet counts advanced
from 5 to 60 and all observed invalid-packet, counter-drop and counter-jump
latched counts remained zero. This extends the initial continuity observation,
but is still a partial day and does not qualify a daily total. A separate
read-only connection as `energy_power_reader` confirmed the unique Item 657
mapping and `SELECT=false`, `INSERT=false` on `public.item0657`. The exact
table SELECT grant remains pending; no privilege or scoring state was changed.
