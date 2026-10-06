# Sun calendar and eclipse Item migration

The next attended file-first batch contains exactly eight observational Sun
Items and their original single, empty-profile channel links. Their identities,
labels, Point tags, Sun membership, units, binding-derived formatting and
semantics remain unchanged. The live registry has no literal rule references to
these names; this bounded census does not prove absence of dynamic or external
consumers.

| Item | JDBC ID | Type |
| --- | ---: | --- |
| Sun_Spring | 80 | DateTime |
| Sun_Summer | 81 | DateTime |
| Sun_Autumn | 82 | DateTime |
| Sun_Winter | 83 | DateTime |
| Sun_RingEclipse | 89 | DateTime |
| Sun_TotalEclipse | 86 | DateTime |
| Sun_PartialEclipse | 87 | DateTime |
| Sun_Eclipse_PartialElevation | 88 | Number:Angle |

The Sun Thing/Group, elevation, daylight-start/sunset bounds, phases, radiation
and countdown inputs remain outside this batch. No new astronomical calculation
or household rule behavior is introduced. In particular, the planter fan's
current daylight policy is unchanged.

Canonical candidate: `openhab/file-config/items/sun-calendar.items`.
Frozen secret-free contracts: `openhab/file-config/sun-calendar-migration.json`.
Closed guards: `scripts/sun_calendar_items.py`. Only original Item and link
DELETE/PUT definitions pass its mutation guard; state, command, metadata, Thing,
rule and protected daylight-input writes are rejected.

## Qualification checkpoint

All eight production Items and links remain managed; the candidate is not
installed and has no file-ownership declaration. Twenty-one closed contract
tests were exercised RED before implementation and then pass GREEN. A separate
restart-header regression was later exercised RED/GREEN, bringing the affected
contract suite to **22 passing tests**. Fresh combined guards, including adjacent
fan, diagnostic and weather-health contracts, pass **99 tests**.

The full repository run passes **4,256 tests**, with **10 skips** and **91
subtests**. The subsequently added header regression passes separately, giving
**4,257 unique passing tests** across these runs. Source and correction reviews
are clear; final receipts are reviewed before local integration.

The native provider round trip passes five exact phases: original managed
startup, file handoff, file cold restart, original managed rollback and final
file handoff. The cold process changes from host PID **2821379** to **2838173**.
Every phase validates complete descriptors, semantic metadata, formatting,
degree units, exact empty-profile links and the closed fixture scope. The
runtime contains only these eight display Items/links and their managed Sun
Group/Thing, current cached Astro bundle and private API users. It has no rules,
hardware/device endpoints, production mounts or external network.

Two initial fixture failures are retained separately. The clean image had no
JSONDB directory before its first JVM startup; a clean-image probe confirmed the
cause, and staging now creates the directory. The next attempt passed the first
three phases but lost its temporary request header during Docker restart.
An owned tmpfs probe confirmed that behavior. Each isolated definition mutation
now restages its private header before curl; a regression covers this exact
failure. All failed and successful owned containers/volumes were removed.

The separate JDBC fixture passes managed rollback, hot-file state/history
restoration and full JVM restart using eight synthetic DateTime/degree values
only in owned isolated OpenHAB/PostgreSQL containers. Degree values are compared
as exact decimals in the original Item unit; DateTime values preserve native
instants. Both containers are removed. This synthetic-history scope does not
prove binding fetch or original production-history migration.

At **03:16:15Z October 6** (21:16 MDT October 5), independent production readback
verifies all eight original mappings and **6,994 recoverable original history
rows**, all 58 installed-source pins, every Item/link/Thing/rule definition and
unchanged PID **1696**. No binding freshness properties changed. All eight
production Items/links remain managed, and the candidate file is absent.

Private provider, JDBC and production-preservation evidence is retained under:

- Provider round trip: `/home/sat/.local/state/openhab-config-migration/sun-calendar-provider-20261005-tx2tvmj6`
- Synthetic JDBC recovery: `/home/sat/.local/state/openhab-config-migration/sun-calendar-jdbc-20261005-it1xa5y6`
- Original histories and production preservation: `/home/sat/.local/state/openhab-config-migration/sun-calendar-preflight-20261005-krnhf6q_`

These private capsules retain source contracts, native proofs, terminal logs and
recoverable prefixes. Private API users and Sun configuration remain outside Git.
The candidate is qualified in isolation; its exact attended production transport
and live original-managed rollback are the next stage. Stable calendar/eclipse
outputs will retain their separate natural-change gates after transfer.
Production whole-JVM qualification still requires host authentication for the
already-approved service restart.

## October 6 live transfer and change of focus

The live file/original-managed/final-file round trip completed before the
operator redirected work to machine learning. All eight Items and links are now
file-owned. At 13:26:02Z, independent readback confirms their managed disk records
are absent, all 6,994 original history rows are preserved, and all eight current
values match their latest JDBC values. There are 21 additional rows; stable
calendar/eclipse changes remain future observation gates. PID1696 is unchanged,
and the Sun semantic representative is unchanged. Prior 58 source pins and all
unrelated definitions, rule health and disabled states passed each checkpoint.
The ownership manifest now adds exactly sixteen declarations for this batch;
installed source paths total59. No household state, command or rule call occurred.

The exact transport passed owned native managed/file/managed/file and cold
recovery. Review-driven delayed-withdrawal, directory-durability and rule-health
regressions pass. Verification covers 4,283 full-run passes plus two later
durability regressions (10 skips,91 subtests); all50 affected guards pass.
The final source review and preparation/evidence review are clear.

Current recovery capsule:
`/home/sat/.local/state/openhab-config-migration/sun-calendar-handoff-20261006-uo8orcd3/`.
It retains fresh original managed definitions, users/configuration, eight
recoverable histories and three attended phase receipts. The current restart
baseline still pins58 sources/44 prefixes and needs refreshing before a later
production qualification. That refresh and further migration work stopped at
the operator's October6 instruction to focus on machine learning. Production
restart qualification remains open.
