# Energy supporting-source qualification — October 1

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
