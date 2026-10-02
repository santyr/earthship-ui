# Astro Moon Thing: staged exact file-provider candidate

Status: **source/parser, isolated managed baseline and managed rollback
qualified; file descriptor gate refused; uninstalled; production remains
managed**. This is the next migration candidate, not a completed provider
handoff or authorization for a whole-OpenHAB restart.

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
