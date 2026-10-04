# Energy supporting-source qualification — October 1

## October 4 natural aggregate and UI revision verified

The original daily timer ran at 00:20:56–00:21:00 MDT and exited zero with
both qualified switch and BMS auxiliary readers in its effective arguments.
October 3 snapshot 14 has **21/21 source-quality records `ok`** under their
respective policies; this does not claim zero gaps for every source. Its
canonical payload digest matches the naturally published v4 latest revision:
`c57af3dd5a1c10f415d1bf5d43529ed498b4572129fca315594db33e629ce817`.
The supporting-source natural aggregate/publication gate is now closed.

The observed period is September 20–October 3: **2.4109403678 EFC** over
14 days. October 3 observed PV is **6.3061348186 kWh**. The separate natural
AC day writer exited zero at 00:41 MDT, with revision 13 reporting
**4.8608748661 kWh** at 99.992363% coverage and digest
`bcbeec8d016d1383f3172c3e565558b0321130be82dc36bc6b599e35b89c95dc`.
Unqualified meters and aggregate energy balances remain withheld; the public
Energy status correctly remains partial/degraded despite qualified source health.
No job, control, synthetic value or timer was manually triggered.

The PV badge exposed a separate labeling defect: the producer stores the mean
absolute percentage error of the last seven scored forecasts, not a prediction
interval or necessarily seven consecutive days. The display-only correction
names it `Forecast error`, explicitly marks a missing score unavailable, and
explains its meaning in the title. The numeric producer and forecast
calculations are unchanged. Both reproducing tests failed before the change;
all 17 Energy browser tests and the production build pass afterward.
The actual locally served 1340×800 page renders both battery and PV history
charts and `Forecast error 22%`, with zero page errors, horizontal overflow or
write attempts in a read-only browser probe. No UI or OpenHAB restart was needed.

## October 3 operator acceptance and guarded deployment

The operator accepted the actual-binding fault/JVM qualification in place of a
deliberate physical household outage. The adapter's source release gate is now
open; explicit CLI write authority, the unchanged rehearsed receipt, idle
aggregate/publisher and clear timer window remain mandatory.

The current 136-input receipt below passed fresh verification, then the exact
guarded `apply --allow-apply`. Independent reopening now reports
`installed_waiting_natural_aggregate`. The user service manager confirms all
three expected drop-ins, the exact combined argv and original PYTHONPATH.
Only `zz-qualified-switch.conf` was installed; no job, timer, SQL write,
OpenHAB restart or household control was started or changed. Original power
and temperature readers remain, with the qualified switch and BMS auxiliary
readers added. The existing next natural timer is October 4 at 00:21:01 MDT.
Require that aggregate and subsequent UI publication before claiming end-to-end
completion; partial source days must remain partial and AC-v4 stays separate.

Private receipt:
`/home/sat/.local/state/earthship-energy/deploy-receipts/quality-20261003T093300Z-c10e7482`.
Installed qualification SHA-256:
`8ce0ea2f32ea3f4ee2c612f41264c2f9472fbb00c780ac8993cfbe92d9ce59e1`.
Approved adapter SHA-256:
`62160f4c678ee640c19915f32b1e36bee62b488cbecc6d65b74faab8e63b961d`.
The combined Energy/file-engine/Moon affected suite passes 313 tests without
skips. The following earlier staging sections are historical checkpoints,
not current closed-gate status. Receipt-bound rollback remains available and
refuses later unowned file edits; it needs no apply release gate.

## October 3 refreshed source-pin receipt

The original 135-input point remains retained but stale. A new default-off point
now passes prepare, actual parser/install/interrupted-rollback rehearsal and
read-only verification against **136** current inputs and 18 original private
configuration archives:
`/home/sat/.local/state/earthship-energy/deploy-receipts/quality-20261003T093300Z-c10e7482`.
Its qualification SHA-256 is
`1b4ac6dc89d0da5d2969b0f22bf0ce0afaa144a467f5bd24f9f72056b9ffc91b`.
All **109** affected adapter/file-engine tests pass; temporary fixtures are
removed. Production retains only its two original drop-ins, idle writer,
active daily timer and closed release gate. No job, SQL write or control.

Exact candidate-flag restricted dry runs for September 30 and October 2 succeed.
October 2 returns 21 source-quality records: 17 `ok`, four `partial`. These are
per-source policy results, not proof of a fully continuous day. Both optional
switch loads correctly retain null ON-hours and energy with
`withheld_incomplete_switch_evidence`. Qualified observed PV input/output are
11.461099274/11.032701699 kWh; these are actual observations, not reconstructed
forecast inputs. The independent snapshot balance still withholds qualified
AC load and does not replace the separately qualified AC-v4 publication.
The physical-fault qualification decision and natural post-release aggregate/UI
checks remain required before activation; completed grants must not be reasked.

## October 3 earlier source-pin follow-through

The later forecast-fetch source/instrumentation changes invalidate the earlier
135-input receipt below. Its read-only `verify` now correctly refuses with
`ValueError`; no supporting-quality target was installed. The release gate
remains off. Preserve the old recovery point, but prepare/rehearse a **new**
receipt under current source pins after the outstanding qualification decision.
The earlier result below is historical, not a current live-apply authorization.

## October 2 prepared daily-quality handoff and rollback

The default-off `scripts/energy-quality-files.py` adapter is now implemented
and qualified. Its only production target is the user drop-in
`/home/sat/.config/systemd/user/energy-daily-aggregate.service.d/zz-qualified-switch.conf`.
It reuses the existing secure, no-follow, journaled file-transaction engine;
there is no second deployment engine, new timer, SQL write, OpenHAB request or
household control. Apply/restore/recover require `--allow-apply`, an idle daily
aggregate and publisher, an active existing timer and at least a 90-second
clear timer window. Apply additionally requires the **still-false** source
release flag and a successfully rehearsed receipt. CLI authority alone cannot
open that gate.

The exact live baseline, FragmentPath, two original drop-ins, full effective
argv and PYTHONPATH were independently verified. The private staged receipt is
`/home/sat/.local/state/earthship-energy/deploy-receipts/quality-20261003T043300Z-40b305ea`.
It pins 135 actual source/configuration inputs by hash and mode and privately
backs up 18 original unit/policy/connection files with explicit original path
identities. Python source is fingerprinted, not needlessly duplicated; no code
is installed by this handoff. Its frozen candidate hash remains `6a12658f...`.
The separate exact file manifest records the new target as originally absent.
Receipt directories are owned mode 0700 and private files mode 0600; secrets
and original private configuration are not printed or committed.

The actual user-systemd parser accepted temporary copies of the original,
installed candidate and restored original. Actual journaled interruption after
file replacement then recovered the absent target and unchanged original
bytes/modes. This is a **temporary-target** install/rollback rehearsal, not an
attended production cutover or service-manager activation. All **53** affected
adapter/adjacent file tests pass without skips, including drift, missing or
corrupt archives/manifests, wrong effective argv, failed parser/readback,
interrupted recovery, later unowned edits, busy/imminent jobs and both CLI/source
gates. A deterministic archive-order regression was fixed before private
staging. All owned test/parser storage, including the initial failed-test
fixtures, is removed; the intentional private recovery receipt is retained.

A fresh read-only aggregate using the **exact candidate flags** again qualifies
September 30: **21/21** unique source-quality checks are `ok`, qualified-power
accounting is preserved, and pinned inputs/receipt remain unchanged. Its output
SHA-256 is `5fd4c0410b80cebcae7450116e50f1a5302e103996f3335252952ebd3b179b2a`.
No historical aggregate or snapshot is rewritten. The final adapter SHA-256 is
`4d8e74467dbc8dafe5bfc5848598ae0a0856821be9864f56dfa7c366468e3050`;
private qualification SHA-256 is
`86d2b97f48e692be2ab1082082945d2a8bdeb4f7240884ad82c27be710a2a323`.

Read-only verification:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/energy-quality-files.py verify \
  --receipt /home/sat/.local/state/earthship-energy/deploy-receipts/quality-20261003T043300Z-40b305ea
```

The result is `rehearsal_passed`, `release_ready:false`; the production target
remains absent, the daily job inactive and OpenHAB active at PID 1696. Do not
open the gate without the outstanding qualification decision and evidence
review. After eligibility is established, the exact attended apply must verify
the effective service-manager command and roll back its owned file on failure;
then require the next **natural** previous-day aggregate and subsequent UI
publication. Natural partial days must remain partial; September 30's clean
qualification does not turn later gaps into complete coverage. Publisher live
BMS-health opt-in, AC accounting and household controls stay separate. An
emergency receipt-bound restore/recover uses `--allow-apply` but does not need
the apply release flag; it refuses later unowned edits rather than deleting
them. No start/restart/enable is part of either path.

## October 2 actual BMS Modbus transport qualification

`scripts/qualify-bms-transport.py` exercises the cached **5.2.1 Modbus binding
and transport**, original native uint32 channels, exact eight collector
triggers, unchanged BMS auxiliary collector and actual JDBC. Before allocation,
the exact four live Thing configurations must match the read-only source
contract. The actual production collector hash and trigger list were also
independently checked and match. Unlike the faster HS103 fixture, this run
preserves production's **30,000-ms** refresh, 34 holding registers starting at
64, unit 190, three read attempts, unchanged-value updates, connection defaults,
120-second receipt TTL and 60-second publication interval. Only host/port change
to loopback `127.0.0.1:1503` instead of the household gateway's port 503.

The isolated Java peer accepts only that unit/function-3/register-block read;
there is no write implementation. Its MBAP framing, response register values
and transaction/unit identities pass an offline self-test against the exact
embedded `net.wimpi.modbus` protocol classes. Wrong protocol, length, unit,
function, address, quantity and truncated requests are refused. Both owned
containers share only an otherwise networkless namespace, with no host mounts,
devices, published ports, household routes or production credentials. OpenHAB
memory+swap is capped at 2 GiB and PostgreSQL at 384 MiB; OpenHAB's root is
read-only and its caps are dropped. Cleanup is ownership checked. No production
write or household command occurs.

The actual October 3 run qualified eight strictly ordered original JDBC rows:

| Checkpoint | UTC |
| --- | --- |
| Both native values first valid | 2026-10-03 04:12:00.045 |
| Unchanged values renew the periodic envelope | 2026-10-03 04:13:10.043 |
| Real TCP failure; both source barriers persisted | 2026-10-03 04:13:30.413 |
| New native reports recover both fields | 2026-10-03 04:14:30.418 |

During the three actual failed TCP reads, the real poller became OFFLINE, but
the numeric Items **remained 320 Ah and 29315**. Those held values were not
treated as fresh: both original evidence fields became `source_unavailable`
with null value, observation time and expiry. Recovery after restoring the peer
requires new original channel receipts after the barrier, not parent health or
retained numbers alone. The epoch and consecutive sequence are preserved.
The peer recorded nine requests, three faults and **zero forbidden requests**.

Original ordered row-list SHA-256 (compact sorted-key JSON):
`9dd52e5434b8ca5024748d84251dab94f82794871d06d3d6a89ebbcc21077e15`.
Binding SHA-256:
`8563c9d3e5852873470225fc80722e0ba5556579b8e4c862d2fd0bc4d2993884`.
Transport SHA-256:
`cd95c445719a33a658c6d948bb8f8ad37c6ec6056896ace1eb82220a5f57533b`.
Unchanged collector SHA-256:
`c57778dceca6f78c3db41a05605918e1bd9db3ad10aea13579ea453587391618`.
All **70** focused harness/parser/history tests pass, with no skips; the actual
JVM/transport/JDBC run also exits zero. Both finalizers and independent Docker
queries confirm no task containers remain. Production OpenHAB retains PID 1696.

Repeat with `PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-bms-transport.py`.
This closes the tested actual transport/collector/persistence path, **not an
observed physical household outage** or all possible connection failures. It
does not activate the supporting quality flags or change aggregate snapshots,
temperature scaling, the battery estimator, pumps or watchdogs. The operator
has been asked whether these actual-binding tests together with the already
verified production JVM recovery may substitute for waiting on a physical
outage. Until that decision, retain the physical-source gate; exact guarded
rollback, complete-day qualification and natural aggregate/UI verification are
still required even if the substitution is approved.

## October 2 actual-binding disconnected transport qualification

`scripts/qualify-tplink-transport.py` now exercises the cached **5.2.1 HS103
binding**, original switch observation Items/JS transform, exact six collector
triggers, unchanged v2 collector and actual JDBC persistence. The two peers
listen only on `127.0.0.1` and `127.0.0.2:9999` inside an owned networkless
PostgreSQL/OpenHAB namespace. They accept only the binding's exact read-only
`get_sysinfo` query; every other command is refused and counted. There are no
household routes, published ports, host mounts/devices, production credentials
or production writes. Container memory equals memory+swap limits; cleanup is
ownership guarded in success and failure finalizers.

The Java peer's frame encoder/decoder is checked against the actual binding's
`CryptUtil`, including zero/negative/oversized and truncated frame refusal.
The successful October 3 03:14–03:15Z run proves:

- Unchanged OFF reports acquire new original receipt clocks and renew the
  periodic persisted envelope after 60.142 seconds. This is not freshness
  inferred from a change-only numeric Item.
- Each plug independently suffers a real TCP read failure. The real handler
  reports OFFLINE, its peer records the fault, and the original collector
  persists `source_unavailable` with null value/source time/expiry. The other
  plug remains valid.
- The binding actively publishes **UNDEF** on this failure. Its JS acquisition
  wrapper obtains a new host timestamp, but that unavailable channel update
  does not become a valid switch observation. Initial fixture assumptions
  that the Item would necessarily retain OFF were corrected; no production
  collector/parser behavior was changed or weakened.
- Restoring the read-only peer produces a new native OFF observation after
  the barrier. The stream epoch and consecutive sequence remain intact; exact
  original checkpoints are found in strictly ordered JDBC history.

| Field | Persisted fault (UTC) | New native recovery envelope (UTC) | Rows inspected |
| --- | --- | --- | ---: |
| Dishwasher | 2026-10-03 03:15:26.310 | 2026-10-03 03:15:30.327 | 7 |
| Cistern Pump | 2026-10-03 03:15:32.323 | 2026-10-03 03:15:36.337 | 10 |

Original ordered row-list hashes (compact sorted-key JSON) are respectively
`56bc2bad89b9b6fa6c0bdd892f1174ecd67863d54271b1c1e8b2139bbb314013`
and `98ba089af6c5cb8c3f2f4dd8f31aef86c78d5b9dda9a6e35cac012bdb060c538`.
Binding SHA-256 is
`96adea67cf034952a1d4d19b14f809089ca5e0b46662451f1e564e35f3318999`;
unchanged collector SHA-256 is
`40b34d9b2afa3ce9451aecdf5b26aef3f46a85adda402cb6a0f7f6106f4466d9`.
All **40** affected harness/evidence/history/deployment tests pass, no skips.
Both finalizers and independent Docker queries confirm all task containers
were removed; failed predecessor runs were removed as well. Production
OpenHAB remains active under PID 1696.

Repeat with `PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-tplink-transport.py`.
This fixture intentionally polls every **1 second**, not production's
30-second cadence; the original 95-second TTL and 60-second publication bound
are unchanged. It qualifies the actual binding transport/collector/JDBC path,
**not an observed physical household outage**, every timeout mode, or a live
consumer release. Keep the independent physical-source gate, guarded user-unit
handoff/rollback and next natural aggregate/UI gates separate. Neither staged
quality flags nor permanent collector units were installed or activated.

## October 2 combined daily-unit source candidate

The trusted Solar_PV repository's existing, **uninstalled**
`deploy/systemd/user/energy-daily-aggregate.service.d/zz-qualified-switch.conf`
now adds both BMS auxiliary arguments as well as both switch arguments. It
preserves current power/temperature flags, separate aggregate writer and
restricted evidence reader, source paths, original lock and previous-day
selection. SHA-256 is
`6a12658f41ba8e6b32e6543681cfd05676f5c4830a6e6f20f62b4f9b40d5a5e5`.
Two regressions reproduced missing BMS arguments, then passed. All 84 affected
unit/scheduled/CLI/source-quality/reader tests pass, plus two actual disposable
producer/SQL/grant-withdrawal integrations. Their simulated faults do not
qualify a physical household outage.

Temporary copies of the actual daily unit and its existing two drop-ins pass
the user-systemd parser in original/candidate/restored phases. Original copied
bytes and live files remain unchanged; no daemon reload, service/timer start,
database snapshot write, publisher opt-in or physical action occurred. Test
storage and containers are removed. This closes combined source-unit syntax
and argument forwarding, not a production cutover or natural writer gate.

Independent physical-source fault qualification and exact private rollback/
guarded live handoff remain. Keep the prior full-day/parity and October 2
actual JVM recovery evidence below, preserve partial days, then verify the
next natural aggregate/UI output after any eligible release. Publisher BMS
live-health opt-in is separate; qualified AC/EFC accounting is unchanged.

## Scope

Read-only completed-day qualification at `2026-10-01T19:05:14.338649Z` closes
the first complete post-cadence BMS auxiliary and v2 TP-Link day checks for
**September 30**. This is not a live quality release, a history rewrite,
physical network/JVM recovery qualification or control authorization. Existing
grants were used; no new grant is needed for these reads.

The dedicated `energy_power_reader` accessed exact evidence Items 658 and 656
through bounded repeatable-read transactions. Denver's day is
`2026-09-30T06:00:00Z` through `2026-10-01T06:00:00Z`. The BMS cutover remains
`2026-09-29T05:14:44.776000Z`; the switch policy retains its original stream
cutover `2026-09-28T16:36:40.989000Z`. The v1/v2 parser preserves their distinct
TTLs and restart barriers. Neither September 28 nor September 29 is relabelled.

## Actual complete-day results

| Supporting field | Coverage | Gaps / unavailable barriers | Observed result |
| --- | ---: | --- | --- |
| Remaining Ah | 100% | 0 / 0 | `ok`, 1,447 auxiliary receipts |
| Native BMS temperature | 100% | 0 / 0 | `ok`, same 1,447 auxiliary receipts |
| Dishwasher switch | 100% | 0 / 0 | `ok`, 1,441 switch receipts, 0 observed ON seconds |
| Cistern Pump switch | 100% | 0 / 0 | `ok`, same 1,441 switch receipts, 43,200.046 observed ON seconds |

The BMS Fahrenheit scaler separately passes **seven actual native-temperature
changes**, with zero mismatches and zero skipped transitions. Its status is
`observed_consistent`; this is not merely an unchanged-temperature carry test.
The observed switch ON duration is not pump water volume, electricity or a
greywater-cycle label. Dishwasher's zero change-only rows do not mean stale
OFF: its independent native switch receipts cover the entire day.

## Exact reader bindings

| Module | SHA-256 | Actual audit source |
| --- | --- | --- |
| `bms_aux_evidence.py` | `09c5e213213368fbb2e9240cb2e6b9bd335c220dec9d6e1d7e7d42da19cf6617` | Installed `/home/sat/openhab/scripts` |
| `bms_aux_history.py` | `acfebbff8ee49c3f8d7ba24f43c68825ca199c33f23b2a0fd73733194441d218` | Installed |
| `bms_temperature_parity.py` | `76abe84969fc8692a6447218dd20dc7e5e54dfb36804c9c752b0277fe0030d48` | Installed |
| `tplink_switch_evidence.py` | `1e9354d9ca4beb153b704e91a5eb50625a006128a7b8a3854807d24b35f576fa` | Repository `openhab/scripts` |
| `tplink_switch_history.py` | `86a6461c639fce3ed66d9e53bb7e0137adbe803b91568a427b36da5520c8a67a` | Repository |

All three installed BMS files match the repository byte-for-byte. Switch
libraries were explicitly selected from the repository, not claimed installed
in `/home/sat/openhab/scripts`. An initial import-only attempt correctly stopped
because that installed directory lacks the switch library; the subsequent
audit prints and verifies its explicit source binding. No implicit fallback
was added to a production process.

## Combined dry-run and isolated recovery

The existing Energy `aggregate --date 2026-09-30 --dry-run` command was evaluated
under `energy_power_reader`, retaining its current qualified-power and
temperature-policy flags. Current flags yield **19/21 `ok`** supporting rows:
only dishwasher and Cistern Pump are `freshness_unverified`.

Adding the existing paired switch policy/reader and BMS auxiliary policy/reader
flags yields **21/21 `ok`**. Both auxiliary rows then cite
`BMS_Aux_Evidence_JSON`, not held `BMS_DevicePresent`; both switch rows cite
`TPLink_Switch_Evidence_JSON`, not numeric Item timestamps. Battery/PV power
accounting identity and efficiency coverage remain unchanged. The separate AC
balance reason remains `ac_load_evidence_unqualified` in this power snapshot;
this dry-run does not merge independent AC observations into a new balance.

A separate disposable PostgreSQL test copied only the 1,441 original switch
rows, read under the restricted household role. Their ordered
`[(timestamp.isoformat(), original_text), ...]` compact-JSON SHA-256 is
`68e828303b7ee698507c1f902ed26c360ff9a2885f9ef4f32319eb1418d702e4`.
The existing strict SQL reader:

- reproduces both full-day `ok` results;
- refuses after SELECT withdrawal and reproduces the identical result after
  SELECT restoration;
- isolates a simulated unavailable barrier to its affected field;
- refuses a malformed original record;
- marks both fields partial after a simulated new unavailable restart epoch;
- reproduces the identical baseline after exact original-row restoration.

All mutations above are **only disposable test data/grants**, not household
records or physical actions. The container and volumes were removed in the
harness's finalizer; independent readback finds no remaining `advisory-test-`
containers. Original observations and operational backups are retained.

The existing focused Python integration slice passes **113 tests in 5.03
seconds**, including actual JS BMS producer → restricted PostgreSQL → current
health/UI consumers and read-grant withdrawal. The three JavaScript producer
files pass **39 tests**. An initial test command named an absent parity test
file and collected nothing; the successful command uses the actual
`test_bms_aux_history.py` suite. No product/test code was altered to make these
checks pass. Owned pytest fixtures are removed after terminal verification.

## Live state and remaining release boundary

The actual v4 Energy Item at `2026-10-01T19:05:29.091326Z` is still degraded
with reason `daily_source_quality_not_ok`. Its separately qualified September
30 AC observation is already live: **5.2808896114 kWh**, coverage
**99.9964086%**, snapshot ID 10, SHA-256
`11a2e95f91e1368982193ff766643bff0a82bf21ca94fc53e5a4adbda3debdc2`.
That AC publication is not broken or withheld by the two optional switch rows.

The daily service still has only `qualified-power.conf` and
`qualified-temperature.conf`; the publisher retains its qualified-power and
qualified-AC drop-ins. No switch/BMS auxiliary opt-in, timer change, ad-hoc
aggregate write, OpenHAB restart, equipment command or DM occurred.

This checkpoint closes the previously future-only completed-day/scaler and
combined read-only integration gates. Physical-network/full-JVM recovery,
an exact reversible user-unit quality release and its next natural
aggregate/publisher readback remain separate. Do not silently waive those
gates, suppress the current warning, rewrite older snapshots or request the
already-successful grants again. Keep the current qualified AC/EFC accounting
and source identities intact during any later release.

## October 2 actual JVM recovery and October 1 day follow-through

The existing production OpenHAB JVM started at 07:25:20 MDT on October 2.
Read-only restricted SQL checked the original persisted restart window: 17 BMS
auxiliary and 16 switch receipts. Both streams persist their new-epoch,
sequence-1 all-unavailable barrier at `2026-10-02T13:25:34.977000Z`.
Both BMS fields recover with native post-barrier observations at
`2026-10-02T13:25:40.579000Z`; both switch fields recover at
`2026-10-02T13:26:04.887000Z`. Each original field observation is after the
barrier, not a restored numeric Item or collector-health timestamp. BMS strict
successor checks pass throughout the inspected window. Item mappings remain
658 and 656, and live producer sources match their repository hashes:

- BMS auxiliary: `c57778dceca6f78c3db41a05605918e1bd9db3ad10aea13579ea453587391618`.
- Switch: `40b34d9b2afa3ce9451aecdf5b26aef3f46a85adda402cb6a0f7f6106f4466d9`.

This closes the actual JVM barrier/fresh-recovery gate without inducing another
outage. It does not qualify every physical-source/network failure. Independent
Modbus connection-timeout logs exist around October 1 03:57 MDT, but no
independent TP-Link OFFLINE/network-fault log was found. A coincident switch
freshness gap is not proof of its physical cause.

The newly complete October 1 Denver day is
`2026-10-01T06:00:00Z` through `2026-10-02T06:00:00Z`:

| Supporting field | Coverage | Gaps / unavailable barriers | Strict result |
| --- | ---: | --- | --- |
| Remaining Ah | 99.9971157% | 1 / 0 | `partial`, 1,478 auxiliary receipts |
| Native BMS temperature | 99.9971157% | 1 / 0 | `partial`, same receipts |
| Dishwasher switch | 99.9183553% | 1 / 2 | `partial`, 1,442 switch receipts |
| Cistern Pump switch | 99.9173866% | 1 / 1 | `partial`, same receipts |

All 30 actual native-temperature changes pass parity, with no mismatches or
skipped transitions. BMS coverage has a 2.492-second durable-publication gap:
the prior expiry is 09:58:28.448Z and the next envelope persists at
09:58:30.940Z. Its original field observations at 09:58:14.275/276Z precede
expiry, but a later persisted receipt cannot retroactively fill the gap.
Switches persist an `input_stale` barrier at 09:58:00.875Z and recover from
original source events at 09:59:07.421/423Z. No TTL or polling cadence was changed.

The existing aggregate command for October 1 passed a restricted-reader
`--dry-run` with the paired switch/BMS options and existing power/temperature
flags. It preserves these partial quality results and withholds load ON-hours
and load energy as `withheld_incomplete_switch_evidence`; raw observed ON
duration is not electricity or water volume. Qualified power observations remain
6.697226403 kWh PV and 5.861595155 kWh load. The independent power-snapshot
balance remains `ac_load_evidence_unqualified`, not a replacement for the
separate qualified AC v4 publication.

No snapshots were written, optional live flags enabled, history rewritten,
physical fault induced or household control executed. September 30's clean
qualification remains historical evidence, not a substitute for October 1.
Physical-fault qualification and the exact reversible user-unit release remain
open; the actual JVM recovery requirement above is now satisfied.
