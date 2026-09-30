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

## Guarded adapter qualification

`scripts/migrate-bitcoin-exec-thing.py --check` now verifies the reviewed real
feed and receipt-transform bytes, existing whitelist, exact managed Thing,
file-owned dependent Item definitions, Group/member semantics and a fresh
successful price receipt. It streams a fixed-cutoff, read-only Item 34 prefix;
the September 30 03:39 MDT preflight found 1,106,136 rows / 40,035,792 CSV bytes
before `2026-09-30T09:37:33.433529Z`, SHA-256
`f98d1801e9aec4088ba002c8974c92e4f0eca9ed366120e1fb991967ef91880b`.
This digest is a preservation proof, **not a new JDBC recovery archive**.

The release-gated apply path retains a private mode-0700 managed REST/prefix
and Thing/link JSONDB preimage, rechecks the baseline, withdraws only this
Thing, and publishes the file atomically without overwriting an existing
definition. It requires exact provider/full-channel-metadata readback, unchanged
Item/Group/source definitions, a new real success receipt matching the current
price, persistence of that same original receipt, and the identical fixed price
history prefix. No direct SQL/Item/link write or OpenHAB restart is included.
Rollback withdraws only its own unchanged inode/file before recreating the
minimal managed Thing; it also requires a new successful durable receipt and
unchanged history. Foreign/changed files require manual recovery, not removal.

Eighty-six focused tests pass, including backup privacy/failure cleanup,
non-overwrite publication, both provider states, metadata preservation,
scoped REST mutations and transfer/receipt/history failure rollback. The actual
networkless provider/full-JVM-restart/managed rollback was rerun with the full
channel labels/descriptions/properties comparison, and passed; its owned
container was removed. The live apply gate remains off at this checkpoint.

Exact live plan: run a fresh guarded preflight and private backup, perform this
single-Thing handoff with its existing 30-second polling/15-second timeout,
verify the required real durable receipt and Item 34 prefix, then independently
read back file ownership/source and all dependent definitions. Declare only
this Thing in the ownership manifest after verification, and turn the one-shot
apply gate off again. On a failed gate perform the adapter's guarded rollback
and report the retained private recovery path. A brief Bitcoin-card update gap
is possible; no pump, BMS, forecast, collector, signer or other resource will be
changed, and no whole-OpenHAB restart is planned.

## First live withdrawal and verified rollback

The first guarded production attempt withdrew the managed Thing but refused
before installing its file. Its Item comparison included OpenHAB 5.2.1's
rolling `lastState`, `lastStateChange` and `lastStateUpdate` observations;
a normal quote update was therefore mistaken for definition drift. Independent
path-only comparison found only those observation fields differed. The managed
Thing was recreated with its exact full definition, both output links and a
new successful persisted real-price receipt; the fixed Item 34 history prefix
was unchanged. No file Thing was installed, and no OpenHAB restart occurred.
The complete private rollback backup was retained.

The comparison now excludes rolling observations while retaining static Item
identity, ownership, label and metadata. Its regression verifies that normal
state/timestamp changes pass but changed labels still refuse. Static failure
phase receipts identify any later failed gate without exposing private data.
All 86 focused tests and a fresh read-only live preflight passed with the
one-shot apply gate off; the existing history contained 1,106,202 rows before
`2026-09-30T10:12:32.619262Z`. A retry still requires a new private preimage and
the original strict metadata, receipt and history gates.

## Exact empty-provider Item contract

The next attempt also refused before file installation and verified managed
rollback, a new durable real receipt and unchanged price prefix. The restored
static Items, Group and source bytes matched the private preimage. A dedicated
networkless synthetic withdrawal/rollback probe reproduced the only temporary
differences: `stateDescription.readOnly` on both linked output Items. The Exec
binding supplies this read-only property while its channel exists; without the
Thing it becomes false, then returns to true after recreation. This is not an
Item-definition edit.

The corrected boundary checker requires the Thing to be absent, all existing
output links unchanged, and every Item/Group/member definition unchanged except
this exact Boolean true-to-false transition on those two linked Items. It does
not exempt labels, patterns, metadata, ownership or other read-only transitions.
Both final file-provider and rollback checks still require the full enriched
Item contract, including restored read-only values. Focused regressions also
prove a changed link or unrelated definition refuses, and a boundary refusal
restores managed polling without installing a file. The one-shot gate remains
off pending the corrected isolated transfer qualification and fresh preflight.

The corrected actual isolated run subsequently passed the exact scoped
empty-provider comparison, file ownership/full-channel contract, a new
synthetic poll, full server-JVM exit/different-JVM restart and managed rollback
with another synthetic poll. The owned container/tmpfs was removed. All 97
focused regressions pass. This is isolated provider evidence, not a real-feed
or production JDBC result; the guarded live gates still have to pass.
