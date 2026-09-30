# Bitcoin polling Thing: file-provider candidate — September 30

## Current scope and ownership

`exec:command:BTC_Price` remains REST-managed and ONLINE. Its existing file-owned
`BTC_USD_Price` and `BTC_Output_Receipt_JSON` Items/output links are separate
resources. This candidate transfers only the polling Thing, not the price Items,
their JDBC history, Group, percentage rule, script, credentials or whitelist.
It does not restart OpenHAB or change any hardware/control resource.

The staged definition is
`openhab/file-config/things/bitcoin-price.things`. It preserves the exact live
label `BTC_Price`, command `/etc/openhab/scripts/bitcoin.py`, 30-second interval,
15-second timeout, and `autorun=false`. The Thing has no Bridge or location.
Its seven channels have their existing identities, types and empty configuration;
only `output` is linked, to the two existing file-owned output Items. Neither
`input` nor `run` has a control link.

Source SHA-256:
`becb9ed6081f7a5780dc943a055217bed3907ec0bc55fc3793aa0ec401fff26a`.
The read-only live DTO digest before and after qualification is unchanged:
`8bd83ac857fc0d61359a9c42bceaad6383f39cc7ecc7282636f64bf2fe2723f1`.
No ownership declaration was changed and the source is **not installed**.

## Actual qualification

The installed OpenHAB 5.2.1 grammar parser accepted the one-Thing definition
and rejected malformed syntax. The shared parser keeps its existing default
three-declaration OpenMeteo check; that real check also passed. This is syntax
evidence, separate from the runtime checks below.

The corrected `scripts/qualify-bitcoin-exec-provider.py` run passed against the
cached OpenHAB 5.2.1 image and installed Exec binding. Its one owned container
(`85c061b0855d`) had no network, host mounts, published ports, devices or private
configuration; root was read-only, user 9001, all capabilities dropped, one CPU,
and 1.5 GiB memory with no extra swap allowance. Its temporary script at the
same command path was the checked-in **synthetic** fixture, returning 12345.67.
The real Bitcoin script and its private credential file were never copied or
executed. No database or household OpenHAB was part of the test runtime.

The test verified:

- Managed-to-file ownership with exact configured Thing metadata, all seven
  channel contracts and the two unchanged file-owned output link definitions.
- A new synthetic polling timestamp and expected numeric price, rather than
  assuming a held state proves execution.
- Actual server JVM exit and a different JVM after restart, with the file Thing,
  output links and a new synthetic poll intact.
- File withdrawal, exact managed recreation and another synthetic poll.
- Ownership-checked removal of the container and its temporary filesystems.

Earlier fixture attempts terminated at bundle readiness or managed creation;
none was claimed a pass. The corrected bootstrap stages the binding after
core startup, handles transient CLI reads without relaunching that JVM, accepts
the console's Unicode separators, starts a resolved binding explicitly, waits
for its type registry and uses the minimal creation DTO rather than copying
enriched read-only channels/properties. Fifty-three focused offline tests pass,
including config/link drift, resource isolation and immutable synthetic-script
guards. This does not qualify the real credential-backed feed or JDBC recovery.

At `2026-09-30T09:14:52Z`, independent read-only preflight still found the exact
managed live Thing and unchanged output links. The global inventory returned
zero issues (81 managed / 4 non-managed Things). No container with the owned
qualification label remained. Production writes were zero.

## Next guarded live handoff

Before any live provider withdrawal, implement/review a bounded transaction
that rechecks this exact baseline, script/whitelist identity and fresh successful
price receipt. Retain a private managed Thing/registry/link preimage and a
fixed-cutoff Item 34 history proof; do not commit credentials or raw registry
backups. Preserve both Item identities, Group and existing link configurations.

Withdraw only this managed Thing and install only the staged `.things` file.
Require one noneditable ONLINE Thing with the same effective configuration and
channel/link contracts. Then require a **new real successful output receipt**,
matching current price and continued Item 34 history; a timestamp alone or the
synthetic test price cannot close this gate. A brief polling gap is possible
and must not be backfilled or described as uninterrupted collection.

On failure, remove only the owned file before recreating the saved managed
Thing; verify its exact configuration, links and real polling recovery. Record
file ownership only after successful production readback, retaining the private
rollback preimage. The isolated JVM restart above does not authorize or qualify
a whole-production OpenHAB/protected-control restart.

Read-only preparation and isolated qualification commands:

```sh
python3 scripts/preflight-bitcoin-exec-thing.py --syntax
python3 -m pytest -q scripts/test_preflight_bitcoin_exec_thing.py scripts/test_qualify_bitcoin_exec_provider.py scripts/test_preflight_bitcoin_price_item.py scripts/test_qualify_bitcoin_price_provider.py
python3 scripts/qualify-bitcoin-exec-provider.py
```
