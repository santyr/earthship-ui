# Astro Moon Thing: staged exact file-provider candidate

Status: **the accepted, attended October 3 hot handoff is complete. Moon is
verified file-owned and ONLINE, with managed rollback exercised and all 28
original histories preserved. The one-shot live mutation gate is re-locked.**
Production whole-JVM restart recovery is not claimed or authorized.

## October 3 attended production handoff and natural JDBC verification

The operator confirmed current physical attendance and both pumps OFF. Fresh
output readback also showed both OFF, BMS comms OK and qualified Schneider
telemetry. The exact adapter then captured a new private original preimage and
completed **file-1 → original managed rollback → file-2**. Every phase verified
the exact full provider descriptor, all dependent definitions, source/consumer
guards, new distinct native Moon/Sun events and all 28 original JDBC prefixes.
No Item/link migration, synthetic state, SQL write, household command or
OpenHAB restart was performed. File ownership is now declared only after actual
independent readback; site/cadence and full source bytes match the candidate.

Private original recovery point:
`/home/sat/.local/state/openhab-config-migration/astro-moon-yr3s8zaj`.
Its original 28-history baseline contains **1,090,404 rows / 53,989,970 COPY
bytes**. Thirty-file preimage manifest SHA-256:
`0306f3837e7cb2e208988acf8acfbaa1554ce769cb6bef86ee9da12626ec4255`.
The three phase receipts and separate `jdbc-natural.json` remain private beside
the original preimages. An independent process reopens every preimage, restores
typed ISO cutoff timestamps for the strict comparator, and verifies all 28
original prefixes after the final cutover. The first diagnostic passed raw
JSON strings to the typed comparator and correctly refused; explicit timestamp
rehydration fixed that diagnostic without changing the comparator or history.

At 14:19:01Z, original native Moon illumination at **14:16:17.930Z** matches
Item 41's new JDBC row at **14:16:17.932334Z**. Native Sun elevation at
**14:18:55.279Z** matches unchanged Item 16's JDBC row at
**14:18:55.281324Z**. Both numeric values are compared, not just timestamps;
held states alone cannot pass. Moon is solely noneditable/ONLINE and Sun remains
managed/ONLINE. The one-shot live gate is false; metadata acceptance stays true.
Final adapter SHA-256:
`c5ddc55471699127f2f470a234cf30f490f42874d69706faa09ba454b72fcd57`.

This qualifies the actual hot handoff, managed rollback, final provider and
natural JDBC continuity. Earlier isolated JVM recovery retains its exact scope;
no later production restart or global dynamic-consumer closure is inferred.
Private recovery data must be retained; only owned disposable tests are removed.
Final inventory has zero issues (86 Things: 79 managed/seven non-managed).
All 313 affected transaction tests and 14 ownership-inventory tests pass.
OpenHAB remains active at PID 1696, both pump outputs OFF, BMS comms OK and
Schneider telemetry fresh. No new ERROR line appears in the bounded log scan
since 08:15 MDT. Three old rules report UNINITIALIZED/DISABLED, not a new
provider failure; their disabled posture is preserved and they are not started.

## October 3 accepted metadata decision

`METADATA_DEVIATION_APPROVED` now records the operator's acceptance of exactly
27 generated tag lists, 11 explicit false `forceEvent` defaults and one age
description. Every other descriptor comparison remains exact; neither the
full comparator nor the independent live gate is weakened. The contained
qualification harness requires the live gate closed regardless of metadata
approval. A new regression test proves it still refuses an open live gate.

Fresh GET/read-only SQL preflight passes all 28 histories: 1,090,377 rows,
53,988,642 COPY bytes, original-prefix digest
`87f6eb1bb103ab246515b35fb8d69ca44472f1384f555cc036892f4b9850efbb`.
Its output explicitly reports metadata approved, live release false, zero
production writes. The affected combined suite passes 313 tests without skips.
Adapter SHA-256:
`fe0f38b8b06c88c669df1ec4bbb02838ba07ca6f14732a4e4b177294c87fc101`.
Harness SHA-256:
`e6d71b246bccf67e76d316533ed3c5e679026d1e9ab4ac20da291b04ebed8e50`.
Older source pins and pending-choice statements below retain their historical
scope. The subsequently attended hot handoff and original-history/natural-JDBC
checks are complete in the section above. No production restart was performed.

## Exact current scope

GET-only production inspection on October 2 verifies `astro:moon:local`, label
`Moon`, type `astro:moon`, managed and ONLINE/NONE. Its only configuration keys
are the already committed site `geolocation` and integer `interval=300`.
There is no bridge, location or Thing property override. All channel offsets
are default zero. The staged declaration preserves those values and relies on
the version-matched binding to recreate its **34** channels.

Source: `openhab/file-config/things/astro-moon.things`.
SHA-256: `bc347fa716e7b959ceefc363b9e83b9d929da5354e1215ebef886d02f7b6310e`.
Intended destination: `/etc/openhab/things/astro-moon.things`, currently absent.
Do not install while the managed Thing exists. No ownership declaration is
added before an actual guarded provider transfer and independent readback.

There are **28** distinct linked Items across **27** channels, with seven
unlinked channels. Three links are file-owned (phase, illumination and phase
icon); the other 25 remain managed. The Moon Group is also managed. A Thing
handoff must preserve every existing Item/link, including profiles and units;
this scope does not transfer those 25 links or recreate Item history identities.

## Consumer qualification so far

Home reads phase name and phase icon. The live rule-reference census finds
the phase icon in `sky-condition-calculator`, whose condition is a greywater
eligibility input. Thus an apparent display dependency must not be dismissed
just because the Thing is astronomical or has no hardware-command channel.

The actual live sky script matches the reviewed source SHA
`d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
Its Moon read changes only the nighttime icon; condition selection depends on
Sun phase and qualified weather/radiation, not Moon state. The exact live
script was executed privately in a no-hardware VM for **90** cases: three Sun
phases, three radiation ratios, two weather-health states and five Moon inputs
(valid icon, NULL, UNDEF, empty, missing Item). The eligibility condition never
changes with Moon input; unavailable nighttime Moon input selects the existing
weather-night fallback. Only the four existing sky display/diagnostic outputs
are allowed, and equipment commands are forbidden.

Those 90 cases are also retained in the staged sky-rule tests. The targeted
sky-rule/icon suite passes **96 tests in 181 ms**, with cache disabled.
The original sky rule remains managed and its migration apply gate remains
closed. These tests qualify this particular Moon-to-sky value path, not all
protected-control restart behavior. The literal census also identifies generic
dynamic Item lookups; it is not a complete transitive safety classification.

## Parser qualification and remaining release gates

The existing `HexOpenMeteoThingsParse.java` grammar probe, with declaration
count `1`, accepted the new source using the installed **OpenHAB 5.2.1** Thing
parser. It reported ThingModel, one declaration, zero syntax errors and rejected
its malformed-input negative control. No binding or provider was started by
that syntax probe. Do not confuse syntax acceptance with effective channel,
handler, Item-state or history recovery.

### October 2 isolated provider fixture: not yet qualified

The new GET-only-production probe
`scripts/qualify-astro-moon-thing-provider.py` uses a clean, pinned OpenHAB
5.2.1 container with no network, host mounts, ports, devices, household rules
or database. Its sole fixtures are the Moon definitions and cached Astro/MAP
bundles. Memory and memory-plus-swap are both capped at 1,536 MiB; the observed
runtime used about 484 MiB. It removes its ownership-labelled container and
tmpfs in `finally`; all attempts recorded here were cleaned up.

Concrete findings before any file handoff:

- Creating the managed Thing from site/cadence alone regenerated **39**
  descriptor fields: default tags, missing `forceEvent` defaults and one
  description. This is a fresh managed-fixture difference, **not** a completed
  file-provider test. Do not quietly normalize those channel changes away.
- Posting all original channels at creation returned HTTP **400**. Inspection
  of the installed `ThingResource.create` and `ThingHelper.addChannelsToThing`
  confirms that supplied channels are added to factory channels and duplicate
  UIDs are rejected. The probe now creates without channels, then uses the
  supported update/merge path to restore the original writable descriptors.
  `ChannelDTO` has no `linkedItems` field; only that read-only enrichment is
  removed from the recovery DTO, while links are restored separately.
- The corrected managed fixture then matched the full Thing/channel and link
  definitions. Its initial Item differences were three length units and the
  Group's derived semantic configuration. GET-only inspection confirmed
  production's `en`/`US`/`America/Denver`/`US` regional settings. Reproducing
  those settings removed the unit differences.
- The remaining observed mismatch was `Moon.metadata.semantics.config`.
  Trying to register production's selected `hasPoint` Item last did not fix
  it; that ineffective registration-order workaround was removed. The installed
  semantic provider iterates the Group's member **Set** and writes a single
  `hasPoint` value. Its representative must not be mistaken for the entire
  membership. Exact member/tag/parent relations and a justified cross-runtime
  comparison remain to be qualified; the current probe still refuses on this
  mismatch instead of dropping semantic metadata.

The targeted provider/preflight regression suite passes **105 tests** without
cache. This is source-contract coverage, not a successful isolated provider
rehearsal. No file-transfer, full-JVM or managed-rollback runtime gate passed,
and no production history recovery was tested by this fixture. Production
remains active at PID 1696 with the Moon Thing managed and the destination
absent. Resolve the fixture boundary before attempting a live adapter.

### October 2 23:53Z: semantic fixture resolved, actual file difference and rollback

The installed `SemanticsMetadataProvider.processHierarchy` iterates a Group's
member Set. `processMember` overwrites a single `hasPoint` representative;
`added(Point)` recomputes the Point, not its parent Group. Thus Group-first
fixture creation can retain the initial empty Group metadata. Reinitializing
**only the isolated semantic bundle** after all 28 members exist resolves that
fixture-cache issue; no production bundle or service was restarted.

The revised comparison validates the representative against the actual Point
members and compares the complete sorted membership/Point relation instead
of insisting on a Set's arbitrary last member. It requires all **28** members,
all **27** Point-to-Moon parent bindings, no duplicates/extras, and a valid
Equipment/derived-provider identity. Every other metadata field, Item tag,
parent, unit and provider flag remains exact. Nine new regression cases cover
valid alternate representatives and broken references, membership or parents;
the complete targeted suite passes **114 tests** without cache.

Actual runtime outcomes, with no household rules or hardware:

1. The original managed baseline passes all 34 full channel definitions,
   all 28 Item/link definitions, the complete semantic relations and a **new
   source-attributed natural Astro update**.
2. The actual file-provider handoff then differs in exactly **39** descriptor
   fields. These are 27 default tag lists (legacy empty, current binding
   Calculation/Duration/Timestamp/Info/Status variants), 11 explicit
   `forceEvent` defaults, and the `phase#age` description. The age text changes
   from “The age of the moon in days” to “The age of the moon”. The pinned Astro
   XML declares `forceEvent=false`; its compiled channel-config constructor
   also defaults that primitive to false. No other descriptor difference is
   observed. Current type-registry GETs independently confirm all 27 tag changes;
   shared eclipse type wording is not used as a factory-description comparator.
3. A stable descriptor difference ends this isolated file attempt after 30
   seconds, rather than consuming another five-minute observation window.
   The probe verifies its installed source SHA, withdraws only that file,
   then creates and updates the original managed definition. **Managed rollback
   passes** the full original channels/Items/links/relations and another new
   source-attributed natural update. The file gate remains failed; recovery
   success does not turn it green.
4. Full isolated JVM restart was **not attempted** after the file gate failed.
   The ownership-labelled container and tmpfs are removed. Production remains
   active at PID 1696; the managed Thing and absent destination are unchanged.

An explicit operator choice is pending: qualify the current binding's generated
metadata as a named migration deviation, or require literal legacy descriptors.
Do not silently replace the full-channel comparator with UID-only checks. Any
accepted deviation must still qualify exact intended file descriptors, effective
behavior, existing Item/link/unit/history preservation, JVM recovery and managed
rollback before a live handoff. No production adapter or gate is enabled.

Before a live cutover:

1. Finish the dynamic-consumer and upstream/shared-binding review against
   current live rule/script definitions; keep exact source pins in preflight.
2. Use the existing clean, networkless, no-host-mount runtime harness and pinned
   Astro bundle to qualify managed-to-file transfer, full isolated JVM restart,
   file withdrawal and managed rollback. Compare all 34 full channel definitions,
   exact Item/link/Group semantics and native binding updates, not just two
   displayed Moon readings. Do not copy household control rules into that test.
3. Qualify complete original Item/history identities and available ordered
   prefixes for all 28 dependents. Handle expected enriched read-only metadata
   loss during absent-provider withdrawal explicitly; final metadata must match.
4. Prepare a narrowly bounded, default-off attended adapter with private recovery
   preimages, exclusive installation, overlapping-execution protection, guarded
   rollback and no Item command, synthetic state, SQL write or production restart.
   Unexpected provider/source/Item/link drift must refuse overwriting.
5. Obtain/confirm the exact live handoff authority after those gates. Require
   independent readback, a new natural Astro update, unchanged histories and
   protected inputs before declaring provisional ownership. A later actual
   production JVM can qualify restart recovery; do not restart solely to make
   the migration status look complete.

Post-check production remains active at PID **1696**. The Moon Thing is still
managed; the destination is absent and no managed object, Item, link, history,
runtime, privilege, collector or control was changed. The earlier
source/parser/VM checks created no container or private backup; later isolated
provider attempts created only disposable containers, all removed afterward.

### October 3 05:14Z: all 28 original live history baselines verified

The existing provider qualifier now has a separate, strictly read-only mode:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-astro-moon-thing-provider.py --check-history
```

It pins the exact linked names and original JDBC IDs (39–45 and 50–70),
including the three already file-owned Items. Mapping verification refuses
missing, duplicated, remapped or aliased identities. PostgreSQL collation can
order names differently from Python; the comparison preserves multiplicity
without treating that ordering as an identity change. This concrete initial
refusal has a regression test; no descriptor or history normalization was added.

Each transaction independently confirms server-side `read-only` and
`repeatable read`, then streams the original ordered `(time,value)` COPY bytes
into a digest. Duplicate rows remain part of the digest; no observation values
are printed or retained. The second snapshot uses each original maximum
timestamp, allowing genuine later appends without expanding or rewriting the
original prefix. Empty history, invalid timestamp contracts, changed original
prefixes or definition/link/dependent drift refuse qualification. Queries have
20-second statement and three-second lock limits; streamed data is bounded to
32 MiB per table and 128 MiB total per snapshot. No write transaction, synthetic
state, fixture/container or private backup is created.

Actual final assessment at `2026-10-03T05:14:42.578906+00:00` verifies all
**28 Items**, **1,089,408 original rows** and **53,941,693 original COPY bytes**
in each independent snapshot. Aggregate original-prefix manifest SHA-256 is
`a27901e98a0317c8e3106c0f47527f1ba2e3dbe22cfd6e039f494cf66fe71c76`.
Final qualifier source SHA-256 is
`78c8aba43a5c7a990e787a64a663e2eb77376c1e787c7ab31d8117b5dbec99b2`.
The affected provider/history/adjacent migration slice passes **94 tests in
0.19 seconds**, without skips. Task-owned temporary pytest directories and
generated bytecode were removed; no live worker or diagnostic remains.

This establishes the complete **current original-history baseline**, not
production history recovery or preservation across a provider cutover. Those
outputs remain explicitly `not_tested`. A future guarded adapter must capture
fresh original prefixes and prove them unchanged after handoff and rollback.
The 39-field descriptor decision, dynamic/shared-consumer review, isolated
file/restart qualification and exact attended authority remain open. Production
OpenHAB is still active at PID **1696**, Moon is managed, and the watched file
destination is absent. Do not repeat the selected-reading-only baseline checks
or infer a broader migration release from this result.

### October 3 05:35Z: exact binding-metadata alternative passes isolated recovery

The operator choice is now supported by a separate actual-runtime candidate,
not an ignored-field or UID-only comparison. The default no-argument probe
still requires the literal original descriptor and would refuse the previously
recorded 39 differences. This explicit alternative is isolated-only:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-astro-moon-thing-provider.py --qualify-binding-metadata-candidate
```

The expected alternative is constructed **before fixture allocation** from
the original descriptor and the independently byte-pinned Astro 5.2.1 XML.
It permits exactly 27 channel default tag lists, 11 explicit boolean
`forceEvent=false` defaults and the one `phase#age` wording change. The pinned
XML independently requires offset zero and false force-event defaults. Current
GET-only channel-type checks also match the XML tag ordering and age text.
Missing/extra/duplicate channels, type/UID drift, existing nonempty tags,
nonzero offsets, an existing force-event override, other age wording or a
different change count refuse before allocating the fixture. All other full
Thing/channel fields remain in the exact comparison; managed baseline and
rollback always use the unmodified original descriptor, never this alternative.

Intended provider-neutral full-descriptor SHA-256:
`3c4b60e6d22f3e8b452b1e2834d02d6cf5f1b12bcd3745563d330209adf90595`.
Executed qualifier source SHA-256:
`17a17c8f3d4992b5a83d567d3d606530d93fe0203cff5dc46ffced3cc1e45301`.
The affected provider/history/adjacent-migration tests pass **107 cases in
0.20 seconds**, without skips; 13 cases specifically cover the new alternative.

The actual owner-labelled fixture `e7e192742ab8` completed these checkpoints:

1. Exact original managed baseline, all 34 channel descriptors, 28 linked
   dependents and a new source-attributed native Astro update.
2. Exact alternative file provider, unchanged original Item/link/unit and
   complete membership/27 Point-parent semantic comparisons, and a new native
   update. No dependent Item or link ownership was transferred.
3. Full isolated JVM stop/start, a different sole JVM PID, the same exact file
   descriptor/dependent comparisons and a new post-restart source-attributed
   illumination change. During the initial logging gap, a valid numeric state
   alone did not pass; the same original process waited for the native event
   at the preserved five-minute cadence, without retrying the entire run or
   forcing a new binding state.
4. Verified withdrawal of only the exact file, original managed creation/update,
   full original comparisons and another new source-attributed update.
5. Owner-checked container/tmpfs removal; independent Docker census is empty.

Containment stayed networkless, read-only-root, no host mounts/ports/devices,
no household rules or database. Memory and memory-plus-swap were both 1,536
MiB, CPU limited to one; observed usage was about 269 MiB, with no OOM kill.
No new test directory, diagnostic or fixture remains. Production OpenHAB
remains active at PID **1696**; the Moon Thing remains managed and its watched
file remains absent. No production REST/SQL write, restart, Item command or
synthetic state occurred.

The final output explicitly reports `qualification_target=binding_metadata_candidate`,
`production_deviation_approved=false` and `production_history_recovery=not_tested`.
This is successful qualification of the named **alternative**, not acceptance
of a production metadata deviation or completion of live cutover/history
recovery. Await the operator's descriptor choice; then finish dynamic/shared
consumer review and the fresh, exclusive, rollback-backed attended adapter.
The already verified all-28 original-history baseline must be captured fresh
and checked after both live handoff and rollback, rather than treated as that
future proof. No whole-production restart is authorized by this fixture.

### October 3 06:29Z: named consumer review and read-only drift guard

Fresh GET-only inspection covers all 42 registered rules' module configurations.
Acorn parses all 29 managed JavaScript action bodies and the five installed
file-rule sources without executing them. The remaining managed script is the
933-byte `mppt60_native_status_mapper` Rules DSL action, not failed JavaScript;
manual review confirms a fixed charger-code switch from
`MPPT60_Native_ChargerStatusCode` to `ChargerStatus`. No script-bearing
conditions or triggers occur in this snapshot. The only literal Moon input
found in those sources is the already VM-qualified sky rule's `MoonPhaseicon`.
Literal absence is not proof that an arbitrary computed/external consumer
cannot exist.

The live greywater and night-load scripts match their canonical source bytes.
The greywater `getItem(name)` helpers receive fixed CFG fields or its two-pump
list; its astronomical gate is `Sun_Position_Elevation`, and its eligibility
input is `SkyCondition`. The night-load device lookup validates keys with
`hasOwnProperty` against its fixed three-device map. No registry-wide Item
selection is introduced by these reviewed paths. The five installed file
scripts match their canonical bytes; their fixed temperature, Bitcoin and
seasonal helpers do not select Moon Items. The astronomy forecast publisher
selects `astro:sun:local` for both Thing and actions. Its OSGi service lookup
is the read-only timezone provider, not a Moon-dependent action dispatcher.

Installed Astro/core bytecode independently confirms per-handler scheduler
maps and locks, new Sun/Moon handler instances, and Moon disposal cancelling
only its own scheduled futures and clearing its own cached Moon. Astro actions
have prototype service scope and an instance handler reference. Core service
registration/removal is keyed by that Thing UID; removing Moon does not remove
the Sun's registered action set. This is a **compiled-source lifecycle review**,
not a two-Thing runtime fault/recovery test or proof of all shared services.
No production bundle, scheduler or service was restarted.

The repeatable guard is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/preflight-astro-moon-consumers.py
```

It verifies three named managed script hashes/languages/providers, the five
installed file-rule sources/providers, the current canonical Astro MAP, and
the pinned Astro 5.2.1/core-Thing binaries. A second independent rule/Sun read
must match the first full definitions; only live rule execution status is
excluded. Every unknown definition field remains compared. Production passes
with all 42 rules, unchanged managed ONLINE Sun, and no inventory issues.
The rule-graph digest is
`b1ac9ecbe6cf7b763cf00837d018a9894ea5436de5bc4329dfb64e65db178c53`;
source-pin digest is
`ce5578f79282d40143f268fd0c2c36fcc89fb6fbeb8941a86cb1fda2120309b2`.
The guard/provider/adjacent preflight regression slice passes **147 tests in
0.20 seconds**, with no skips; 22 cases exercise the new guard's drift/refusal
and read-only contracts. Test fixtures and their temporary directories are
removed after verification.
Exact individual pins are maintained in the guard, not inferred from collector
health. Its output explicitly reports `all_consumer_closure=false`,
`atomic_snapshot=false`, `apply_available=false`, and zero production writes.

This closes the named current consumer/shared-binary source review and gives
the future adapter a repeatable drift check. It does not waive fresh private
preimages, original-history/cutover/rollback verification, unexpected registry
drift, independent natural Moon/Sun updates or the pending exact descriptor
choice and attended live authority. No guarded live adapter is released.

### October 3: default-off handoff adapter and original CSV recovery point

`scripts/migrate-astro-moon-thing.py` now implements the guarded provider
round trip, but both `LIVE_RELEASE_READY` and `METADATA_DEVIATION_APPROVED`
remain **false**. It is an uninstalled/unreleased candidate, not live-cutover
authority. Its supported safe paths are:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/migrate-astro-moon-thing.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/migrate-astro-moon-thing.py --prepare
```

Check uses only GET and server-confirmed read-only/repeatable-read SQL.
Prepare additionally retains private mode-0700/0600 original Thing, Item,
link and source definitions plus all 28 exact original ordered CSV prefixes.
The qualifier's default digest-only behavior is unchanged; its new optional
writer hook archives the same bounded COPY stream, without a third SQL scan.
Each recovery point has an exclusive, fsynced 30-file preimage manifest.
Independent reopening refuses extra/missing files, symlinks, unsafe modes,
changed definitions, source bytes or original CSV digests. A permanent small
private flock file prevents overlapping prepare/apply executions; it is an
intentional operational lock, not a leftover worker.

The actual backup-only run retained
`/home/sat/.local/state/openhab-config-migration/astro-moon-y363q6hk`:
**1,089,603 rows**, **53,951,135 original CSV bytes**, all 28 original mappings.
Independent process reopening verifies all 30 files and the original source.
Manifest SHA-256:
`af9d6449122165ab6cbb1e1cbae929c4b11dfa4d2426b539b2d31d361b9f7091`;
snapshot SHA-256:
`06354e287a3f81d122eb3c45fc925f374b70a46ad8336d2672bb70ca23a0f9a0`.
The bounded native-event reader also accepts distinct recent production
Moon-illumination and Sun-elevation events. That qualifies its current log
reader, **not** post-cutover natural recovery. No observation values or private
definition bodies were printed or committed.

The dormant apply flow requires both pumps' output Items OFF immediately
before planned withdrawal, then checks the exact alternative file descriptor,
all dependent definitions and original histories. It requires new, distinct,
source-attributed Moon and Sun events at the preserved cadence. It exercises
original managed rollback and the same checks before installing the final file.
Only exact Moon Thing DELETE/POST/PUT is supported; no Item/link mutation,
household command, SQL write or production restart exists. Installation never
overwrites a destination; owned-inode/source checks guard withdrawal. Lost
DELETE responses still enter recovery, and ownership is retained before a
later directory-sync failure. Unexpected provider drift refuses an overwrite
and retains the private recovery point for attended manual recovery.

The affected guard/provider/Bitcoin/seasonal regression slice passes **240
tests** without skips. These are offline transaction/refusal tests, not an
actual runtime execution of the new adapter's whole round trip. The new
source hashes are adapter
`d0f96210e15ead1c17bdd1a5d2d3f8a49b6b797c999ddbae97bdbc192364c0f8`
and qualifier
`0e17fef9b748b2db87aeb3e9402f95043d82d1795bd5548800718c55f15ae460`.
Earlier isolated outcomes remain evidence for their recorded source pins;
they are not relabeled as a runtime qualification of this new apply flow.

An attempted closed-gate CLI check of the apply interface was rejected by the
execution safety reviewer before any command ran because live authority and
the exact metadata choice are outstanding. It was not retried or bypassed;
the independent backup/log verification ran separately, read-only. Production
still has its original managed Moon Thing, no watched Moon file, and OpenHAB
PID 1696. Retain this private recovery point; remove only disposable test
fixtures. Next: qualify the new adapter's actual isolated round trip including
Sun continuity and withdrawal metadata, obtain the exact descriptor/live-plan
decisions, then capture a fresh preimage during the attended handoff. Source
green, a backup or this one-shot negative check must not open either live gate.

### October 3 07:47Z: actual contained adapter round trip qualified

`scripts/qualify-astro-moon-handoff.py` now executes the adapter's **same
transaction core**, with explicit contained capabilities rather than the
production `--apply` interface. Both live gates remain false. The original
private manifest above is pinned and reopened; all 28 typed CSV histories
(1,089,603 rows) are restored into disposable PostgreSQL 16. A SELECT-only
fixture role independently reproduces every original prefix before the
OpenHAB fixture starts and at each transaction boundary.

Both containers have no network access or published ports. OpenHAB has no
host mounts, devices or household rules. PostgreSQL's only host mount is an
owned, private temporary Unix-socket directory, not production data/config.
Docker is Snap-installed and cannot see host `/tmp`; the first socket attempt
failed before importing history. The corrected socket directory is created
under the workspace, owner-checked and removed on exit. Database creation
reports only safe failure categories, never credential-bearing arguments.

The first actual withdrawal exposed an incomplete guard: channel-derived
patterns and option lists disappear as well as read-only flags. Installed
`ChannelStateDescriptionProvider` skips missing channels; the default core
provider supplies type-derived patterns. The corrected comparator requires
the **exact** fallback pattern, `readOnly:false` and empty options. It refuses
explicit state-description metadata, formatted labels, unreviewed types or
descriptor fields before planned withdrawal. All links, Group relationships,
units, providers and persistent metadata remain exact; normal provider phases
retain full original/intended descriptor comparisons. Nothing is normalized
away. The reviewed default-provider core binary is now also pinned by the
GET-only consumer guard; its fresh source-pin digest is
`81223186eb62fe65a26f0c224e302755934511c024ccba539d398043fe99d569`.

The corrected actual run passed **file-1 → original managed rollback →
file-2**, requiring new distinct source-attributed Moon illumination and Sun
elevation events, full dependent definitions and all 28 original history
prefixes in every phase. The shared Sun retains its original site, cadence and
full definition except the explicitly different single fixture probe link.
Household pump Items are absent, not simulated OFF; the real production OFF
gate is separately regression-tested. The test's container-local file transport
qualifies transaction logic, not the production filesystem's atomic-link
implementation, which retains its own interruption/ownership tests.

All **284 affected regression tests pass**, without skips. The source pins are:

- Adapter: `d336992e9a13f553197cb57221a3a873e3ac543341018c368401d4d0852a5daa`.
- Provider qualifier: `0790ddad7a11679a90b1320c2c5d8b55cb2be32162c7a647ed5eb1dd216e2aa6`.
- Actual handoff harness: `c2dbd5dc40398bce0bc4dd89c212810f2637b9d21b1ab92636650bcdfb1591b3`.
- Expanded consumer guard: `89c7b52107b855d094b47dfc58da71e0950379c83f0226c7b3dffb5585c3759a`.

Every owned test container, socket directory and disposable test fixture is
removed; the original private recovery point is deliberately retained.
Production remains managed, with no watched Moon Thing file and unchanged
OpenHAB PID 1696. No production REST/SQL write, restart or household command.
The final 07:50Z read-only production preflight also passes the new withdrawal
provenance guard and both snapshots of all 28 current prefixes (1,089,702 rows,
53,955,969 bytes). The independent configuration inventory reports zero issues.

This closes actual new-adapter transaction/withdrawal/Sun-continuity and
original-prefix recovery qualification. It does **not** test a natural JDBC
writer in the fixture, a production filesystem handoff, a new adapter JVM
restart or global consumer closure. Earlier JVM evidence retains its recorded
source scope. The exact 39-field metadata choice and attended live plan remain
pending. Only after those decisions may a fresh private preimage and guarded
live rollback/readback establish production cutover and new natural JDBC
receipts. Do not open either live gate from this isolated pass.
