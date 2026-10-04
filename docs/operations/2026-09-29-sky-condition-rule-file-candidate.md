# Sky-condition control-input rule: verified live file handoff

The sky writer is now file-owned. The latest receipt below describes the
October 4 approved production handoff; older dated sections retain their
original candidate/precondition snapshots.

## October 4 approved live handoff and natural evaluation verified

The operator authorized this exact reviewed sky handoff. The attended one-shot
invocation opens only `deploy-sky-control-input.py`'s in-memory gate; its disk
gate and the generic engine's sky gate both remain **false**. All four inspected
source pins match the qualified versions listed below. The transaction performs
actual **file -> exact original managed rollback -> final file**, without a
production restart, forced cycle, Item write or pump request.

A read-only watcher first refused the expired cooldown. Native charge rose
from 87% to 90%; sky temporarily changed to OVERCAST (98% eligibility), then
returned to CLEAR. The original automatic policy started the east pump at
**09:06:00.385 MDT** and completed its ordinary fifteen-minute cycle. Both
output Items were OFF at **15:21:06.963304Z**; actual native safety/remaining-
cooldown preflight qualified at **15:21:07.045262Z**. No cycle was induced to
obtain this window. The native radiation receipt then had snapshot SHA
`4ab03e3fdd62d9ae5a56c17ae16db542e974cce0bb8e18b86434200a32bd2aa1`.

The final file was published at **15:21:37.304994Z**:
`/etc/openhab/automation/js/sky-condition-calculator.js`, SHA-256
`6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320`,
regular/non-symlink mode 0644, owned device/inode **64512/6723384**. Independent
readback at 15:21:54Z and again at 15:23:54Z verifies the unique noneditable
IDLE/NONE rule and all five original trigger contracts. It also verifies:

- Exact managed pump consumer `4c34780e...`, its two triggers and metadata.
- All 41 unrelated rule definitions, 26 related Item definitions/links,
  native Sun definition and six other JS sources, unchanged.
- Original OpenHAB PID **1696**, fresh native inputs and both pump Items OFF.
- Original sky JDBC identities **172/173/540/541** and the entire fixed
  October 3 API history prefixes: **75/77/1032/1090** rows.
- Continuity SHA `d2ed72bb77ececef5d5a6d3d254110c40ce5a0ac15e8c700927f513f81b997bd`.

These are explicit bounded previous-day prefixes, not a full-table export or
physical-relay certification. Exact original managed action SHA remains
`d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`
in the private recovery point:
**`/home/sat/.local/state/sky-rule-7et2pcub`** (0700). Its
`managed-rule.json`, `continuity.json` and actually withdrawn first file
`withdrawn-1.js` are 0600; the withdrawn source hash is exact.

### Original natural file-writer receipt

After the conservative completed readback clock **15:21:53.856101Z**, the
original natural event at **15:22:55.279Z** explicitly identifies
`org.openhab.automation.jsscripting$file:sky-condition-calculator.js` as the
writer of `SkyCondition_LastEval`. Its changed value is
`2026-10-04T09:22:55.279-0600`. Exactly one new original JDBC row persists that
value at **15:22:55.282Z** (ID 540), with one corresponding diagnostic row at
the same millisecond (ID 541):

```text
condition=CLEAR,reason=ratio,weatherStatus=OK,weatherAgeSec=11,weatherFresh=true,actual=230,theoretical=288,ratio=0.80
```

The fixed JDBC query uses `serviceId=jdbc`,
`starttime=2026-10-04T15:21:53.856101+00:00`,
`endtime=2026-10-04T15:23:05.870158+00:00`, `boundary=false`.
`SkyCondition` remained CLEAR and its sunny icon remained unchanged; their
zero new rows are expected under the preserved change-only policy. No manual
rule invocation or synthetic update was used.

Only after independent provider and natural-JDBC readback was the file/verified
ownership declaration added. The final live inventory at 15:23:54Z has **zero
issues**, 35 managed/seven non-managed rules, and unchanged other counts.
The full corrected pinned-environment Python suite passes **4,052 tests**,
with 10 explicitly gated integration skips and 91 passing subtests; all 201
focused dependency/signer cases pass. The earlier exact isolated transaction
and independent code review remain the qualification for these unchanged pins.

Retained proof hashes:

| Receipt | SHA-256 |
| --- | --- |
| Final independent live proof (`/tmp/earthship-sky-live-proof.json`) | `c70284064e4a32e9a0402f6a995ff39004e5f69c44f95db6a8b0045a28853526` |
| Natural original evaluation (`/tmp/earthship-sky-natural-proof.json`) | `7b3ccd77c503dd4a71f642f6fd2262f36035e6cbe5dcc8fbea0e59ac72586200` |
| Actual transaction output (`/tmp/earthship-sky-live-handoff.log`) | `738c4df1589514fb8fc6dcce23680e16f2a7b23198d7cdc8fd7a472c3b8b1596` |
| Final live inventory (`/tmp/earthship-sky-final-inventory.json`) | `931cf9deb6c74fd4c05215f945a16df8876af44f19f3233d502f430d0d7206e9` |

### Retained guarded recovery and remaining scope

For a later attended rollback, use the exact reviewed transaction code and
original private receipt above. Recheck every source pin, native protected
OFF/freshness window and saved continuity. Instantiate `Transaction` with the
saved original rule/receipt and that guard. Verify the retained
`withdrawn-1.js` is the exact regular, non-symlink 0600 first withdrawal and
that `withdrawn-2.js` is absent, including any symlink. Seed `owned_identity`
with **(64512, 6723384)** from the actual final receipt and **`withdrawals=1`**
to resume the completed round trip's counter, then call `to_managed()`.
The next withdrawal is `withdrawn-2.js`; never overwrite the retained first
withdrawal. This verifies the watched source/inode, privately withdraws only that owned
file, verifies the moved inode/hash before chmod and restores complete original
managed fields only after file-provider withdrawal. Refuse drift or lost
ownership; do not adopt a replacement file or retry unknown recovery. Verify
exact managed metadata and original history prefixes before removing this
rule's file ownership declaration. Never create a managed/file duplicate or
edit JSONDB for recovery.

This closes the approved live provider transfer, actual managed round-trip
and natural writer/JDBC gate. Production whole-JVM recovery, deliberate native
input faults and physical hardware signoff are separate gates; the inspected
isolated experiment does not close them. Task 82 and broader protected-control
boundaries remain unchanged.

## October 4 exact protected transaction qualified in isolation

The final independently reviewed transaction passes the **actual** inspected,
networkless OpenHAB 5.2.1 provider experiment. It runs the same `Transaction`
class and actual `os.link`, inode checks and `Path.rename` against the watched
container filesystem through an explicitly injected isolated REST client.
The deployment adapter and generic sky release gate both remain **false**.

The completed experiment proves:

- A real registered file followed by injected first-readback failure returns
  the exact original managed rule, including `visibility`/`configuration`.
- Actual exclusive file -> original managed rollback -> final file succeeds,
  retaining exact source and inode ownership.
- The actual server JVM exits and is replaced; original file rule/trigger and
  consumer definitions return. A saved inode receipt then permits exact
  post-restart managed restoration through the same transaction code.
- Hot-file, restarted-file and managed-rollback phases each reject missing/
  expired native SoC evidence and stale communications with both synthetic
  pumps OFF and no transient ON command. Each phase also executes one fresh
  unlinked positive control, then the safety path returns both outputs OFF.
- The labelled container and ephemeral volumes are removed; final exit is zero.

All **105** affected Python tests pass without skips. Independent source review
has no remaining critical/important findings. Reproducing regressions identified
and fixed staged-inode adoption at publication, a withdrawal inode substitution,
and automatic restore after that substitution. Ownership now comes from
`fstat` before publication and is checked again on the withdrawn file before
chmod or managed restore. Once ownership verification fails, both transfer
paths permanently refuse further mutation in that transaction. An unexpected
file already moved during a concurrent rename is retained for inspection;
this is not a claim that pathname races can prevent every filesystem move.

The real fixture initially exposed an `EXDEV` mismatch between its separate
conf/userdata tmpfs mounts. Production's watched directory and private backup
root both have device ID **64512**. The isolated recovery directory now lives
outside watched automation under the same conf mount; the adapter additionally
refuses different device IDs **before any provider withdrawal**. No production
layout or source was changed. The isolated consumer copy preserves its real
managed metadata rather than accepting invented defaults.

Exact qualified SHA-256 pins:

- `deploy-sky-control-input.py`: `5d3791fc8ac6d2478e03dcff531c6a7460a4791dcdb5990609c4ba4e4dad6d24`.
- `qualify-season-rule-provider.py`: `e9c722f61cca1d3483cd5ed09cc017c0e6ac79587729956e557d8dc23cd41947`.
- `isolated-sky-transaction.py`: `5b40aa0151c845dc21aec23863f0adf5126afc3e4ba001616c129e2653261950`.
- `migrate-season-countdown-rule.py`: `066efd3641a4983a3bb5442c93600f5fc852b0a801a83fd2d560f3ad726ddf31`.
- `sky_control_probe.py`: `b77b6b543f010531eaa8908f14a0e4ab9c23a74a64fa905528989197e10b05c4`.

Qualification output SHA-256: `6210115a3e09d9ca9a941a7cab343cafb02e885f53591146a9cf5d59cffb4c1a`.
Run the exact experiment with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-season-rule-provider.py \
  --kind sky --restart --sky-control-probe --protected-transaction
```

The added mode refuses any other scope before production reads. Its cached
standalone Python runtime enters only the inspected disposable container's
userdata via tar stdin, with no production mount, network, device, port or
channel link. The short-lived container API token travels to the runner over
stdin and is neither retained nor printed. The unwatched private recovery
receipt preserves ownership across the isolated JVM replacement.

Independent repeated **read-only** production continuity matches original SHA
`d2ed72bb77ececef5d5a6d3d254110c40ce5a0ac15e8c700927f513f81b997bd`:
41 unrelated rules, 26 related Items/links, six other JS files and all four
original October 3 JDBC prefixes (75/77/1032/1090 rows). OpenHAB PID remains
**1696**, both original production rules remain managed with exact action pins,
both pump Items are OFF and the watched sky file is absent. The ownership
inventory has zero issues. Final candidate read-only safety preflight still
refuses **`15-minute cooldown window required`**; OFF alone does not qualify.

This closes exact isolated transaction qualification, not native production
telemetry/history protection, physical actuation safety, actual-JDBC pump
recovery or whole-production JVM recovery. The real guard retains those native
checks. Next obtain specific fresh handoff authority/physical attendance and a
qualifying protected timing window, then perform independent live readback
before ownership declaration. No production release or restart was performed.

## October 4 specific protected transaction — source only

`scripts/deploy-sky-control-input.py` implements the proposed guarded
**file -> exact managed rollback -> final file** protocol, reusing the existing
display engine's provider predicates, backup, REST and wait helpers. It does
not open the generic display gate. Its own `RELEASE_READY` is **false**, and
`--apply` additionally requires fresh `--attended --physical-pumps-off` flags.
Default invocation is read-only and creates no backup or runtime file.
Candidate SHA-256:
`0160efbdfde35b9259d74fcfdb932eda205762972b160d1a777f1f66ef2e8e20`.

Before each mutation, it requires the exact repaired managed pump consumer,
fresh native SoC, healthy Schneider/BMS inputs, both output Items OFF and
verified current native v2 radiation evidence from the restricted reader. The
native Sun Thing must be ONLINE. It requires at least **15 minutes** before
possible pump eligibility: a remaining daytime cooldown or an actual upcoming
native sunrise. A past sunrise is never advanced by an invented day. Neither
held numeric SoC nor collector health alone qualifies freshness. Naturally
changing sky outputs are not written back or frozen to force equality.

Continuity compares all 41 unrelated rule definitions, 26 related Item
definitions/links, native Sun definition, six other watched JS sources,
OpenHAB PID and exact JDBC identities **172/173/540/541**. The original
previous-complete-local-day history is an explicit bounded prefix check,
**not a full-table history export**. Two read-only October 4 snapshots match
SHA `d2ed72bb77ececef5d5a6d3d254110c40ce5a0ac15e8c700927f513f81b997bd`;
October 3 row counts are 75/77/1032/1090 respectively. No SQL writes or new
grants are needed. Apply would privately retain its exact managed preimage,
continuity receipt and withdrawn owned files. It never changes the ownership
manifest automatically; declaration still follows independent live readback.

File installation publishes an atomic, no-overwrite hard link from an unwatched
temporary filename. Withdrawal/completion verifies both exact bytes and the
owned inode, refusing symlinks, unexpected files or same-byte replacements.
Managed rollback preserves `visibility` and `configuration` as well as original
action/triggers/descriptive fields. Any unowned continuity or protected-input
drift can refuse rollback; retain the private recovery point and require
attended inspection rather than overwriting unknown ownership.

All **102** affected Python cases pass without skips, including 26 new
transaction/preflight cases. The first real read exposed an adapter-only health
casing mismatch (`ok`); two reproducing tests failed before matching the
existing sky producer's uppercase normalization. The corrected read-only
preflight qualifies native receipts but **refuses the current expired cooldown**.
Do not call it a passed complete live preflight or bypass that window because
the pumps happen to be OFF. No production mutation has occurred.

The actual container proof below qualifies the current source and original
provider/JVM/rollback paths, not this new exclusive-install transaction code.
Next exercise that exact transaction in the inspected isolated provider, then
review its final immutable pin and obtain separate fresh protected-release
authority/attendance. No production restart or test pump cycle is included.

## October 4 repaired consumer requalified in isolation

The qualifier now explicitly selects `consumer_revision='durable-recovery'`,
pinned to the deployed pump action
`4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b`.
The original default remains pinned to `e697e262...` for the historical repair
adapter; no arbitrary hash, automatic "latest" revision or live release gate
is accepted. It also checks the exact copied consumer payload before each
probe phase, including after actual JVM replacement.

Seven new revision-selection cases failed before implementation; an additional
post-restart payload case failed before its guard. All **76** affected Python
cases now pass without skips. The existing command below then passed actual
**file-hot -> full JVM replacement -> original managed sky rollback** with
the repaired consumer. Every phase kept both synthetic pumps OFF for missing
and expired native SoC evidence and stale BMS communications, verified no
transient ON command, and exercised one unlinked positive control followed by
safety OFF. This is sky-provider/consumer evidence, not a replacement for the
separate actual-JDBC interrupted-ledger qualification already completed.

Harness SHA-256:
`8d6dbc73a09223b95059e3e644c866bb9c17fd919db4e81b60ca680a21deb7a2`.
Probe SHA-256:
`b77b6b543f010531eaa8908f14a0e4ab9c23a74a64fa905528989197e10b05c4`.
The owned networkless container and ephemeral volumes were removed. Independent
13:20Z readback confirms original managed sky action `d99c01c1...`, five
triggers, repaired managed pump action and two triggers, both IDLE/NONE,
both pump Items OFF, absent watched sky file, zero ownership issues and
unchanged OpenHAB PID 1696. No production write, test cycle or restart occurred.
`RELEASE_READY['sky']` remains false. The specifically guarded handoff below
still requires its own reviewed authority and fresh physical attendance/OFF.
Earlier action-pin/refusal checkpoints below are historical.

## October 3 later recovery finding — handoff held

The subsequent interrupted-ledger fault tests exposed an automatic-start
durability defect in the copied live pump source. The correction
is now in `southoutlet-cycle-current.js`; its separate actual-JDBC/JVM rehearsal
subsequently passed; the exact managed recovery repair is now deployed after
operator approval and physical attendance (October 3 19:16 MDT). Keep this sky
handoff held pending requalification of that repaired consumer and separate
protected-provider release authority; the earlier missing/expired/comms experiment below
does not cover the defect. Its action pin remains `e697e262...` and intentionally
refuses the new source rather than silently qualifying a different candidate.
See [exact candidate, tests and next release boundary](2026-09-23-greywater-timer-watchdog.md#october-3-interrupted-ledger-durability-repair--source-only).

## October 3 isolated consumer/restart/rollback qualification

Production remains **managed**, and `RELEASE_READY['sky']` remains false.
The extended, networkless provider harness now includes the exact current
`hex_southoutlet_cycle` consumer rather than classifying the sky output from
its name. Both live action pins were independently checked:

- Managed sky action: `d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
- Pump action at that experiment: `e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18`,
  then identical to `openhab/rules/southoutlet-cycle-current.js` (now advanced
  by the later source-only repair above).
- Staged sky file: `6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320`.

Run the scoped experiment with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-season-rule-provider.py \
  --kind sky --restart --sky-control-probe
```

The flag refuses any other rule scope or omission of `--restart` before live
reads. The cached OpenHAB 5.2.1 image is run read-only, networkless, unprivileged,
with no production mounts, devices, ports or channel links, a 2-CPU/2-GiB cap
and no container swap. Only copied rule definitions and synthetic Items enter
the container; its ephemeral administrator token is never printed.

The actual October 3 experiment passed **file hot load -> full JVM process
replacement -> original managed rollback**. In each phase, held numeric SoC
100 and calculated CLEAR sky did not bypass missing source evidence, expired
source evidence or stale BMS communications: both synthetic outputs stayed OFF
and the command log contained no pump ON event. Each phase also passed a
fresh-receipt positive control (receipt SoC 95): the exact action started only
one **unlinked** synthetic pump, with an actual ON command trace, then the
real missing-evidence safety path immediately returned both outputs OFF.
This prevents a disabled/broken action or absent logger from passing vacuously.

All **43** affected Python provider/probe/handoff tests and **148** focused
sky/current-pump/daylight/recovery JavaScript tests pass. Qualified harness SHA:
`e1bbc6062cfe7a28cf567bbf705d788d7eab4f2e606bcfd7c88027bd4c24033f`;
probe SHA: `822a73ee3f450e3299c5566045e08768f76e04e5d39a5d8f497661e802713386`.
The labeled container and its ephemeral volumes were removed on completion;
the previously cached image remains. At 22:22:04Z the production inventory has
zero issues, both original actions remain managed/IDLE/NONE with exact pins,
the watched sky file is absent and OpenHAB PID remains 1696.

This qualifies the stated cold/missing/expired/comms and positive paths only.
It does not prove restored interrupted-ledger/orphan-device recovery, JDBC
recovery, physical feedback/transport, all protected controls or a production
whole-JVM restart. Existing broader control-recovery requirements remain.

### Proposed attended control-input hot handoff

This scope needs specific operator review; it is not released by the successful
isolated test. No production whole-OpenHAB restart is included.

1. Recheck exact sky/pump actions, five sky triggers, single managed provider,
   absent watched file and committed source; confirm operator attendance and
   both pumps **physically** OFF immediately before any mutation. Require fresh
   source-bound SoC, healthy Schneider/BMS telemetry and weather input evidence,
   and a cooldown window clear of the next eligible pump transition.
2. Take a private, mode-0700/0600 current managed-rule/source recovery point.
   Pin all unrelated rule and relevant Item/link definitions, output JDBC
   identities 172/173/540/541 and original history prefixes. Treat naturally
   changing telemetry as data, not configuration drift; never replay old values
   into live control inputs to force equality.
3. Use an individually guarded transaction to withdraw only the managed sky
   rule, atomically install only its exact file, verify one healthy original UID
   and all five triggers, exercise original managed rollback, then return to the
   exact file provider. The pump rule/commands and all other owners stay untouched.
4. Independently verify unchanged definitions/history/PID and fresh controls.
   Require a natural source-attributed file timer/output and matching JDBC receipt;
   do not run the production rule manually or fabricate telemetry/pump activity.
5. Declare file ownership only after readback. On failure, withdraw only the
   exact owned file before restoring the private managed original. Refuse unowned
   edits, duplicate providers and unsafe rollback; retain the qualified backup.

The generic adapter stays default-off. A specific tested guarded transaction,
remaining protected-recovery checks and fresh reviewed attendance must precede
execution. Later production whole-JVM recovery stays a separately approved gate.

At the September 29 05:23 MDT live preflight,
`sky-condition-calculator` was REST-managed (`editable=true`, `IDLE/NONE`).
Its 4,677-byte JavaScript action had SHA-256
`d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
It has four Item-state-change triggers on `Sun_SunPhaseName`,
`Sun_TotalRadiation`, `AmbientWeatherWS2902A_SolarRadiation` and
`WeatherData_HealthStatus`, plus `0 0/2 * * * ?` as a two-minute fallback.
It writes only the SkyCondition/Icon and rate-limited diagnostic display Items;
it does not command hardware.

The source-only JS Scripting file
`openhab/file-config/automation/js/sky-condition-calculator.js` preserves
that UID, trigger set, action logic, weather-freshness boundary, moon-phase
night icon and change-only/rate-limited output behavior. Its SHA-256 is
`6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320`.
Five no-hardware tests cover the triggers, partly-cloudy icon, nighttime moon,
stale/degraded weather and unchanged output. The post-stage full JS suite
passed 1,850 tests in 125 files.

The existing networkless OpenHAB 5.2.1 rule-provider harness was generalized
to accept this candidate. In an owned, disposable container it created a
managed copy, withdrew it, loaded the exact Git file, observed UID
`sky-condition-calculator` with `editable=false` and all five exact triggers,
then removed the file and restored the managed definition. The labeled
container and volumes were removed. Production readback remained
`editable=true`, `IDLE/NONE`, with five triggers; the watched sky file was
absent. No production output or control changed.

## Guarded live handoff — 05:32 MDT

The existing display-rule handoff adapter was parameterized for exact sky
identity, source hashes, all five triggers, eleven input/output Item types and
the two stable output states. Four offline success/rollback tests pass for
both display rules. Its read-only sky `--check` passed against the managed
production rule. The guarded `--apply` saved the exact managed JSON at
`/home/sat/.local/state/sky-rule-vxz_cwr2/managed-rule.json` (directory
0700, file 0600), removed the managed provider, and atomically installed the
Git file. Independent REST readback found one `sky-condition-calculator` rule
with `editable=false`, `IDLE/NONE`, all four Item-change triggers and the
unchanged two-minute cron, exact installed SHA-256 and active OpenHAB. The
display remained `TWILIGHT` with the current sunrise icon, consistent with
`Sun_SunPhaseName=ASTRO_DAWN` and theoretical radiation zero. The ownership
manifest is provisionally file-owned. No whole-OpenHAB restart, fabricated
Item event, or control change occurred.
Restricted read-only JDBC registry lookup still maps `SkyCondition` to Item
172, `SkyConditionIcon` to 173, `SkyCondition_LastEval` to 540 and
`SkyCondition_Diagnostic` to 541. No Item was recreated by this rule handoff.

The 05:32 `SkyCondition_LastEval` post preceded the file's 05:32:41 install;
it was **not** proof of the file rule executing. The natural 05:34 timer then
posted `SkyCondition_LastEval` at 05:34:00.254, and `events.log` attributed
that state change and the rate-limited diagnostic change specifically to
`org.openhab.automation.jsscripting$file:sky-condition-calculator.js`.
The unchanged `TWILIGHT` condition and sunrise icon were correctly not
reposted. The rule remained `IDLE/NONE`. This closes the natural post-file
timer/diagnostic gate; a later full restart still needs verification. Retain
the private managed rollback until that check passes.

## Safety reclassification and managed rollback — 05:40 MDT

The earlier description of this rule as display-only was wrong:
`SkyCondition` is also the live `hex_southoutlet_cycle` greywater eligibility
input. Read-only inspection of that **live** rule found two `SkyCondition`
references and the `CLEAR` gate; this is not inferred only from a Git source
candidate. Although the exact file rule ran correctly, a change to its provider
is therefore a protected-control *input* migration. Its isolated provider
test and one natural timer are insufficient to qualify control recovery after
a whole-OpenHAB restart. No restart was attempted.

With both `SouthOutlet_Outlet2_Switch` and
`East_Bed_Socket_Outlet_2_Power` reporting OFF and `SkyCondition=TWILIGHT`,
`scripts/rollback-sky-condition-rule.py` verified the exact private original
and installed hashes, withdrew only the sky JS file to
`/home/sat/.local/state/sky-rule-vxz_cwr2/withdrawn-file.js`, then restored
the managed DTO. Independent readback found exactly one rule under the
original UID, `editable=true`, `IDLE/NONE`; the watched sky JS file is absent.
Both pumps remained OFF, `SkyCondition=TWILIGHT`, the sunrise icon and active
OpenHAB remained unchanged. The file-ownership manifest claim was removed.

The source candidate and isolated rehearsal remain useful, but **production
sky-rule ownership is managed**. Do not reapply the file cutover until the
protected-control restart/rollback behavior and a specifically reviewed
control-input migration plan are qualified. The distinct
`SkyConditionIcon` *Item* remains file-owned; this rollback did not alter it
or its natural Item 173 history.
