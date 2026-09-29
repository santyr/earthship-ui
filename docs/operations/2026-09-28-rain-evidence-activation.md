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

## September 29 raw-counter spike diagnosis and collector correction

At the first local midnight, 226 persisted rain snapshots showed one receiver
epoch and three paired counter-jump/drop latch increments since activation.
The fault counts increased again at 00:02:28 MDT even though the held accepted
counter remained 102.7497945 inches. Filtered `weather.service` logs show the
underlying cause: at 23:18, 23:34 and 00:02 the source supplied the same
121.358025-inch counter, an impossible +18.61-inch jump. The existing weather
app rejected those packets and kept its baseline. The new observational
collector, however, briefly treated each spike as valid and moved its baseline,
then counted the normal return as a drop. This is a real source-data anomaly,
not change-only JDBC staleness. The strict rain day reader correctly refuses
the affected period; no precipitation error was qualified or scored.

Commit `e74132b` makes the collector match the existing physical jump guard:
an increase greater than 0.5 inch in one packet becomes an invalid
`counter_jump` barrier, increments the fault latches, and **does not** replace
the last accepted counter. The next normal packet can recover without an
artificial drop. The full weather test slice passed 186 tests with two
optional skips. It does not relax the day reader's refusal of faulted days.

With all three temperature streams valid, `weather.service` active under the
verified sat-owned Gunicorn master PID 1607215 and the installed collector
matching old SHA-256
`aaf8bfff3db82465cfd95a1ede9bfe9479f71b2ee99298134d3b3a83e3c82986`,
the tested module was installed atomically. Its private exact rollback copy
is `/home/sat/.local/state/weather-rain-spike-6sbHuB/`; source and installed
SHA-256 match
`d47a6a9e038e78f4ca492fe35dc2420a2123edf5431b2c596e36c3acdaee23f4`.
One HUP retained the master and booted a new worker. Natural packets restored
valid outdoor, indoor, north-wall and rain receipts. JDBC retained a deliberate
new-epoch startup-null rain snapshot at 00:09:28, then strictly parsed valid
natural rows at 00:10:28 and 00:10:58 with zero new fault counts. The startup
barrier and earlier spikes make September 29 unqualified. A future full day
still needs zero unresolved source faults, both midnight brackets, continuous
coverage, the exact Item 657 SELECT grant and a strict day-reader pass. No
weather legacy state, forecast coefficients or protected control was changed.

### Temporary source-attribution diagnostic — September 29, 00:20 MDT

`rtl_weather.service` retains no accepted raw packet history, and no foreign-ID
message coincided with the three repeated spikes. Commit `0748891` adds a
diagnostic only on rejected jumps: it emits bounded differences in source
temperature, humidity and solar radiation, plus model, approved sensor ID,
rain delta and battery-status transition. It never logs a full request URL or
alters acceptance. It logs each distinct spike value at most once per worker
epoch (maximum eight) and stops automatically at September 30 00:00 MDT.
The full weather slice passed 187 tests with two optional skips, including
callback failure and expiry behavior. Remove the diagnostic code after the
cause is resolved; no permanent packet logger is intended.

With all temperature streams valid and the same sat-owned master active, the
tested collector module was atomically installed from exact preimage
`d47a6a9e038e78f4ca492fe35dc2420a2123edf5431b2c596e36c3acdaee23f4`.
A private mode-0600 rollback copy is in
`/home/sat/.local/state/weather-rain-anomaly-6e07jW/`. Installed/source
SHA-256 is
`c1b3cb8f15794307dd05b9a305efe17396a93a543d1853d2bc6e4e8db23ea381`.
One HUP kept Gunicorn master PID 1607215 and booted a new worker. Natural
outdoor, indoor, north-wall and rain packets all restored valid; the rain
epoch had zero new fault latches at the 00:20 readback. This resets the
observational rain epoch, so September 29 remains unqualified. The next
actual rejected spike and its bounded metadata—not this deployment—must
inform the root-cause decision.

At 00:22:17 MDT the next natural packet repeated the exact 121.358025-inch
value. The bounded diagnostic identified approved sensor ID 206 and model
`Fineoffset-WH24`; temperature, humidity and solar-radiation deltas from the
last accepted packet were all zero. The rain conversion in `rtl_weather.py`
is a direct `rain_mm * 0.03937`, so this report is consistent with an isolated
raw rain field anomaly, not a temperature-driven unit conversion or a
foreign-ID packet. The diagnostic cannot distinguish RF decoding from the
station's transmitted counter; do not label either as the cause yet. The
collector rejected the jump, subsequently returned to a valid receipt and
reported one jump, zero drops and one invalid packet in the new epoch. Keep
the strict day-quality gate; the affected September 29 day is unqualified.

A bounded read-only query of Item 657 confirms how this particular fault
appears in durable history: 00:21:28 and 00:21:58 were valid at
102.7497945 inches with zero faults; 00:22:28 was explicitly invalid with
`counter_jump`, null counter and the paired `invalidPackets=1`,
`counterJumps=1`; 00:22:58 and later were valid again at the unchanged
102.7497945-inch counter, with `counterDrops=0`. Thus the strict reader's
whole-day refusal is intentional under v1, not a failure to persist the
quarantine. A possible future recovery-qualified policy must be separate and
tested against persisted invalid rows as well as latched jumps between polls:
prove bounded valid coverage on both sides, unchanged or monotone accepted
counter, exact paired jump/invalid increments, no drops/restarts/other invalid
reasons, and no midnight ambiguity. Do not enable it merely because the live
weather app kept its legacy daily accumulator stable.

A source-only, default-off candidate implementation now lives in
`openhab/scripts/weather_rain_day_recovery.py`. It preserves the original v1
reader as production authority. The candidate accepts only exact
`counter_jump` quarantines (including jumps latched between persistence
polls) whose invalid/jump counts advance together, whose preceding and
following accepted counters are identical, whose valid receipts overlap in
time, and whose incident is away from both midnight boundaries. It refuses
other faults, resets, replay, a changed accepted counter, unbracketed jumps
and more than 16 recovered incidents per day. It has no JDBC or forecast
caller and does not alter live scoring. The adjacent rain and forecast test
slice passed 159 tests with one optional skip; three older forecast tests
were made independent of today's PV/rain cutover dates rather than changing
their production behavior. A real completed source day, restricted reader
grant, observed fault/recovery chain and release review remain prerequisites
before any candidate-to-production scoring cutover.

At 00:42:33 MDT the same impossible 121.358025-inch source value recurred.
The live collector reported two jumps, two invalid packets, zero drops and a
valid unchanged 102.7497945-inch accepted counter. In Item 657 history,
00:42:28 was valid with latch counts 1/1 and 00:42:58 was also valid at the
same counter with latch counts 2/2: this rejected packet occurred *between*
persistence polls, unlike the explicit invalid row at 00:22. Both naturally
observed shapes therefore exist. Repeated faults also mean the candidate's
16-incident daily ceiling may refuse this source even if each incident is
locally recoverable; that is deliberate until the underlying repeated source
anomaly is understood, not a reason to silently raise the ceiling.

The default-off candidate now also has a separate restricted JDBC assessor,
`fetch_candidate_recovered_rain_day`; the forecast worker still calls only
the unchanged strict `fetch_qualified_rain_day` entry point. Both share the
same exact-Item, bounded, read-only repeatable-read transport. Focused unit
tests pass, and an isolated PostgreSQL test proved real SQL candidate recovery,
strict-reader refusal of that same faulted history, and candidate refusal
after SELECT revocation. Its disposable container and volumes were removed by
the fixture; no production database, writer or publication state changed.

### Expanded bounded source diagnostic — September 29, 00:50 MDT

The first natural metadata sample showed unchanged temperature, humidity and
solar radiation, but those fields alone cannot distinguish a counter-only
decode fault from a same-ID station. Commit `881b4ca` adds bounded differences
for wind direction, average/gust speed and UV, and correctly interprets the
stringified battery boolean. It retains the same once-per-distinct-spike,
eight-value and September 30 00:00 MDT expiry limits; collector acceptance,
fault latches and publication policy are unchanged. Seventy-one adjacent
weather evidence tests passed.

The verified old module SHA-256 was
`c1b3cb8f15794307dd05b9a305efe17396a93a543d1853d2bc6e4e8db23ea381`.
With `weather.service` active under sat-owned Gunicorn master PID 1607215 and
all three temperature streams valid, an exact private rollback copy was saved
at `/home/sat/.local/state/weather-rain-wind-04wnDX/`. The new module was
installed atomically, source/runtime SHA-256 both equal
`102cfaeb18e4a65722534df0c0226619d421b15a55ec86f886fae28c51f2aa4c`,
and one HUP retained the same master. Natural packets restored valid indoor,
north-wall, outdoor and rain receipts; the new rain epoch had zero jump/drop
latches at readback. The next rejected spike's expanded metadata is still
pending. This reload adds another September 29 source-epoch barrier; no rain
day is newly qualified and the temporary diagnostic must be removed later.

At 01:01:45 MDT the expanded diagnostic captured the same 18.608-inch rain
spike from ID 206/`Fineoffset-WH24`. Relative to the previous accepted
packet, temperature was −0.18°F, humidity and solar radiation unchanged,
wind direction +2°, average/gust speed +2.67/+2.73 mph, UV unchanged and
battery status unchanged. The collector rejected it and recovered to the
unchanged 102.7497945-inch accepted counter with one jump, zero drops.
Those ordinary wind variations do not identify a second transmitter or prove
an RF decoder fault. The normal receipts canonicalize the model name, so the
previous *raw* model was not retained for comparison.

Commit `30a11c4` adds only `previous_model` to the same bounded, expiring
diagnostic; 28 adjacent receiver tests passed. After confirming all three
temperature streams and rain valid, the exact prior module SHA-256
`102cfaeb18e4a65722534df0c0226619d421b15a55ec86f886fae28c51f2aa4c`
was copied privately to
`/home/sat/.local/state/weather-rain-model-AROhZG/`. Atomic installation and
one HUP kept Gunicorn master PID 1607215. Source/runtime SHA-256 now both equal
`b62895777adbab63642311ddf18eddfed09792b73b36e9725e44ae600cf38d51`;
natural indoor, north-wall, outdoor and rain receipts are all valid with zero
new rain fault latches. The next natural spike is needed to compare raw model
names. This is another deliberate observational epoch reset, not a daily
rain-qualification or production learner cutover.

### Root-cause match and radio-adapter correction candidate

The repeated accepted 102.7497945-inch counter is 2,609.85 mm, exactly
10,275 tips at 0.254 mm/tip. Every rejected 121.358025-inch packet is
3,082.5 mm, **the same 10,275 tips** at 0.3 mm/tip. The upstream
[`rtl_433` Fine Offset decoder](https://github.com/merbanan/rtl_433/blob/master/src/devices/fineoffset.c)
uses precisely those WH65B/WH24 tip factors and also uses 0.51/1.12 wind
factors. The rejected packets are labeled `Fineoffset-WH24`; the site array
was surveyed as the WH65B/WS-2902 family with approved ID 206. This exact
integer-tip equality across both scales explains the 18.608-inch apparent
jump far better than physical rain, a battery reset or a chance same-ID
station. It is still useful to inspect the next bounded `previous_model`
diagnostic before closing source attribution.

The live 226-line `/home/sat/bin/rtl_weather.py` was copied byte-for-byte
into Git at `openhab/scripts/rtl_weather.py` before editing; no credential is
in the source. The candidate adapter now recovers the integer tip count from
either decoder label, refuses ambiguous/nonfinite counts, and emits the same
WH65B 0.254-mm tip and 0.51 wind scale for this filtered station. Other IDs
remain excluded. Thirty-eight radio/receiver tests pass, including parity of
both labels at 10,275 tips and fail-closed ambiguous values. No live radio
service has yet been restarted at this source-only checkpoint. Keep the
rain collector's physical spike guard and strict day reader in place after
deployment; do not score a day until the next complete, fault-free local day.

### Guarded live radio-adapter cutover — September 29, 01:10 MDT

Commit `b74e83a` became the Git-owned canonical adapter. The installed prior
file was verified as SHA-256
`deaf48dc9e35dabb06c93bbd484c8750479f25cc9b3e50f7ea0acebb2df7ade6`,
and a mode-0600 rollback copy was saved under
`/home/sat/.local/state/rtl-weather-wh65b-3knU2P/`. `rtl_weather.service`
was active under sat-owned PID 1974092, with `Restart=always` and the exact
`/usr/bin/python3 /home/sat/bin/rtl_weather.py` entrypoint. Since unattended
`systemctl restart` required a password, the tested source was installed
atomically and only that verified main process received SIGTERM. Systemd
restarted it as PID 1954630 and relaunched its `rtl_433` child. The new
source/runtime SHA-256 both equal
`31a574cc30ebc83c6aa1b69856405707ceb4a8d26da615894261827807352808`.
The downstream `weather.service` was not restarted.

Natural outdoor and rain packets after the cutover were valid at 01:11:37
MDT; the accepted counter stayed 102.7497945 inches with zero new jump/drop
latches. Indoor and north-wall receipts were also valid after the radio
restart; no adapter warning appeared in the bounded service-log check. This
closes restart and ordinary-packet recovery, **not** yet the natural
misclassified-WH24 packet gate. The temporary collector diagnostic remains
expiring and the physical spike guard remains active. September 29 is still
unqualified because of its earlier faults and evidence-epoch resets; the
first possible full local source day is September 30 if continuity and both
midnight brackets pass.

The first expected recurrence window after the radio cutover passed by
01:22:41 MDT. The unchanged downstream collector epoch had accepted 65
packets with zero invalid packets, jumps or drops, and remained valid at the
same 102.7497945-inch counter. Bounded logs contained no new impossible
rain jump and no radio-adapter ambiguous-unit refusal. Before the cutover,
the wrong-scale value recurred at 00:42:33 and 01:01:45 MDT, about 19–20
minutes apart; this first clean window is meaningful but not a proof that a
raw WH24-labeled packet was received, because the normal weather receipt
canonicalizes its model label. Continue observing later windows and the
first complete local day. No rain score or quality gate was relaxed.

### Superseded recovery candidate cleanup

The default-off recovered-jump day reader and its separate JDBC assessor were
never production callers. They were a contingency for unexplained source
spikes; after the exact WH24/WH65B tip-scale cause was corrected upstream,
keeping a second policy that can tolerate faulted days would add complexity
without addressing the source. The two candidate-only modules/tests and the
candidate JDBC branch were removed; they remain recoverable from Git history.
The original strict day reader, restricted transport and forecast call path
are unchanged. Focused radio/rain/forecast tests passed 135/135, the strict
transport passed its disposable PostgreSQL test, and the fixture left no
container. The next full, fault-free local source day still has to pass before
any rain-learning score is released.

### Temporary anomaly logger removed — September 29, 01:31 MDT

The same exact-tip proof and first clean natural recurrence made further
source-difference logging unnecessary. Commit `63e1b41` removed the temporary
metadata parser, callback, one-time log state and expiry constant while
retaining the >0.5-inch physical jump guard and fault latches. Seventy focused
radio/rain/weather tests passed. With all three temperature streams and rain
valid, the prior installed module SHA-256
`b62895777adbab63642311ddf18eddfed09792b73b36e9725e44ae600cf38d51`
was saved privately at
`/home/sat/.local/state/weather-rain-cleanup-HcimWY/`. The logger-free source
was installed atomically and one HUP retained Gunicorn master PID 1607215.
Source/runtime SHA-256 both equal the previously tested guard-only value
`d47a6a9e038e78f4ca492fe35dc2420a2123edf5431b2c596e36c3acdaee23f4`.
Natural indoor, north-wall, outdoor and rain receipts all returned valid;
both weather and radio services remained active, and the new rain epoch had
zero jump/drop latches. This final cleanup adds a September 29 epoch barrier,
not a new qualified day. No temporary packet logger remains installed.

### Second post-fix recurrence check — September 29, 01:42 MDT

The logger-free receiver's new epoch had 43 natural rain packets by 01:42:17
MDT, a valid accepted counter still at 102.7497945 inches, and zero invalid,
drop or jump latches. A bounded `weather.service` journal read since the
01:30 worker reload contained no impossible rain jump or counter regression.
This passes another interval in which the wrong-scale value had previously
recurred, but the downstream canonical receipt still does not reveal whether
a WH24-labeled raw packet occurred. September 29 remains disqualified by the
earlier faults and restarts; the first complete clean-day and restricted
Item 657 read gates remain open. No scoring or control changed.
