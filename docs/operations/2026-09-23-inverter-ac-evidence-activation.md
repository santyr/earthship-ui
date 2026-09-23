# Independent inverter-output evidence: live activation

September 23, 2026, approximately 14:54–14:58 MDT. This is an observational
source activation, **not** AC-load or energy-balance publication.

## Preflight and installation

- The live candidate Item and rule were absent. Both inverter and TCP bridge
  Things reported `ONLINE/NONE`. The file-owned JDBC strategy matched the
  canonical SHA256 `39299b96ec22d1e4860ead09f7b85e23f09f89b071e256a6a0609dda575c57a9`,
  including the new Item's automatic-write exclusion and restore-only selector.
  The ownership inventory reported zero issues before installation.
- The new unlinked String Item was installed as the only provider from
  `openhab/file-config/items/inverter-ac-evidence.items`, then read back as
  noneditable. The managed `hex_inverter_ac_evidence` rule was first created
  with **no triggers**, disabled, and only then given the exact reviewed
  triggers and script. Its disabled readback matched before enablement.
  No existing Item, Thing, link, rule or persistence definition was replaced.
- The rule was enabled and returned `IDLE/NONE`. Source and installed Item
  hashes matched. The ownership inventory again reported zero issues; the
  producer's 26 focused tests passed after the canonical-source move.

## Natural receipts and boundaries

Six five-second-spaced live Item reads all showed valid `inverter_output`
evidence with a stable stream epoch, increasing sequences 3–8, and recorded
ages 0.8–1.4 seconds. The rule requires the original `ItemStateEvent` source
for the specific Modbus AC channel, so accepted receipts support natural
provenance qualification without sending synthetic telemetry or commands.
PostgreSQL identity 653 (`public.item0653`) held 16 immutable rows in the
first bounded readback: all 16 passed Solar-PV's separate strict parser,
15 had a valid field and one was an unavailable startup barrier. Sequences
were contiguous 1–16 in one epoch, with no duplicate persistence timestamps.
A subsequent live strict-reader diagnostic over an explicitly finite window
returned 26 intervals and 97.27% coverage over 134.13 seconds. That
diagnostic window is **not** a durable topology policy or a published load
total. The existing `Power_Evidence_JSON` remained live at sequence 16320
during the check. No targeted rule/JDBC exceptions appeared in the checked
OpenHAB log tail.
At the later approximately four-minute check, the new table held 44/44
strict-parser-valid rows, 43 valid fields and one startup unavailable field,
with one epoch, no sequence gaps and no duplicate timestamps. The existing
three-field power stream held 175/175 strict-parser-valid rows in the checked
five-minute window, also with one epoch, no gaps and no duplicate timestamps.
At the later approximately 15:13 MDT read-only check, `item0653` held 213/213
strict-parser-valid rows, 212 valid fields and one startup barrier, one epoch,
no gaps or duplicate timestamps; the table plus index used 122,880 bytes.
This is an early durability/volume sample, not a full-day retention release.

## Remaining gates and rollback

Natural source loss/recovery and a full OpenHAB restart have not been observed;
do not induce an inverter fault or restart solely to test them. Longer-run
durability/volume and raw-observation retention remain to be measured. The
operator reports current inverter-only household topology; no load or balance
publisher was enabled. The existing v3 UI withholding contract is unchanged.
Solar-PV `e36e54f` subsequently added a source-only, strict topology/complete-
local-day policy loader. The operator then chose for the current inverter-only,
no-bypass/no-generator topology to remain valid until they report a change.
Solar-PV `2576222` records that open-ended attestation in the checked-in policy,
beginning at the first durable unavailable AC barrier,
`2026-09-23T20:55:12.284000Z`. It does not backdate September23 or enable a
scheduled consumer; the first possible full local day is September24 after
its 06:00Z September25 end. Each reader request remains finite.
Solar-PV `9b94a2a` then added the read-only day consumer. It resolves both
source Item identities, integrates only qualified inverter-output intervals,
and reports simultaneous MPPT-DC/AC observations with coverage. It does not
subtract DC PV output from AC load or publish a household surplus; the full
analytics suite passed 786 tests. No scheduled job, stored AC daily revision,
v4 UI reader or load publication was enabled.

To stop collection, disable only `hex_inverter_ac_evidence` via its REST
`/enable` endpoint with body `false`; verify `UNINITIALIZED/DISABLED`. The
new Item and its historical rows may be retained for forensics. If removing
the Item, first verify the exact file-owned provider and remove only
`/etc/openhab/items/inverter-ac-evidence.items`; do not alter the existing
three-field power stream or its history. The JDBC exclusion may remain
harmlessly in place. Re-enable only after inspecting the recorded error and
the exact source/runtime state.
