# Recurring thermal confirmations: approved policy and qualified candidate

## Authority and current state

On October 3 the operator selected **automatic questions after recorded thermal
recommendations, at most once daily**, with five-minute inbox polling. This is
approval for observational collection, not actuator access, model promotion,
inferred compliance, or new thermal advice. No further policy approval is needed
for this scope; the remaining work is implementation and release qualification.

**Deployed October 3 at 10:26 MDT; relay degradation remains.** The user timer is
enabled with five-minute completion-based polling. Its first invocation selected
`followup_status=idle`, sent no question, and retained the authentic trial.
It exited 3 because Damus required explicitly approved NIP-42 authentication.
Read-only relay probes independently verified that nos.lol returned two events
and relay.primal.net was readable with zero events. Authentication remains off;
an operator decision is pending. Do not describe this as all-relay healthy or
proof of a new automatic question/reply. The timer continues retrying without
overlap. See [the trial evidence](2026-10-01-primal-compatibility-candidate.md).

The sections below retain dated preparation evidence. Their inactive/unchanged
SQLite statements describe those earlier checks, not the current deployment.

## Exact recovery and release — October 3

The new activation boundary is `2026-10-03T15:57:16.140816+00:00`.
Under the shared state lock, only the approved SQLite reservation/configuration
metadata was added. Activation, bank epoch, collector and operator are durably
pinned; zero automatic questions existed at release. The original authenticated
shade reply and original acknowledgement ciphertext were independently checked
after offline dependency rebuild and cold reopening.

The original read-only PostgreSQL archive restored into an owned disposable
PostgreSQL database. Idempotent acknowledgement authorization exercised exact
journal readback there, with no relay publication. All original rows and digests
matched before/after: 5 message receipts, 11 action events and 4 mode events.
Production table proofs also remained unchanged. The disposable container and
temporary rebuild directory were removed before qualification was recorded.

Docker's Snap launcher cannot operate inside the parent unit's address-family
restriction: it failed with missing `cap_dac_override`. Adding AF_NETLINK did
not resolve it. Only the disposable-container **orchestrator** ran without that
restriction/NoNewPrivileges. The actual cold consumer and production collector
both retained NoNewPrivileges and AF_UNIX/AF_INET/AF_INET6 restrictions.
No system-wide permissions or production hardening were relaxed.

The retained private recovery root is
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-10-03-primal-recurring-v3`.
Its five-file v6 data manifest is
`35fd3320685a76d671a2fff58d2648bc375e0f96c2b78f160c1b28c69ce60b74`;
the completed cold qualification is
`c0f014c94ee43c6269d01fbcd57f0afff3f7cfb20cccaf0b53be3c8e8bb75420`.
The final 33-file outer bundle includes exact code, requirements/hash-pinned
wheels, signer, credentials, policy/routes, original SQLite/journal data,
qualification, release profile, rendered units and final orchestrator. Its
manifest is
`53edb033c0b1008829ba8f4c880f386743ea6ba0ebc819c9341bb76c579f5145`.
Off-host copying remains explicitly deferred.

The active private profile is
`/home/sat/.config/hex/thermal-primal/recurring-v3-profile.json`, SHA-256
`a714bfedc5195eac83dc694991564a165eb0da34e6c2f131effa3612ae44efe8`.
The profile pins the separately installed launcher/verifier, frozen 12-file
closure, interpreter, credentials, identities, signer, policies/routes and cold
qualification. It refuses drift before importing application code or enabling
collection. Generic repository/frozen source gates remain false; only this
profile opens Primal, automatic-follow-up and v2 journal gates process-locally.
It accepts no arbitrary command or transport override, and currently no relay
authentication override.

The exact installed launcher passed `--check-release` under production unit
restrictions with zero messages/journal writes. All 25 release tests passed,
including tampered code/config/proofs, unsafe paths/permissions, identity drift,
closed check mode and fixed run arguments. Unit syntax verification passed.
Effective live ExecStart uses the pinned profile and v3 code, the dedicated
eight-field environment, 192 MiB limit and the reviewed restrictions.

The combined release/stager/follow-up/CLI regression passed **110 tests, no
skips, in 33.32 seconds**. The former poll-only unit assertion was updated to
verify the approved pinned recurring entrypoint, exact closed argv, retained
restrictions and byte-equivalent rendered template, not weakened or removed.
Two actual timer invocations (10:26:29 and 10:31:43 MDT) both selected idle;
the second respected the persisted refusal retry delay. Read-only comparison
after both runs proves every original ledger/configuration/reservation row
unchanged and all three production journal table digests exactly equal to the
cold-recovery baseline. No duplicate confirmation or new action was written.

### Stop and restore

To stop recurrence without deleting history:

```sh
systemctl --user disable --now thermal-primal.timer
systemctl --user stop thermal-primal.service
```

Require the service to be terminal, then hold the collector state lock before
any database restore. Verify every outer `files_sha256` entry and the v6 data
manifest; do not copy a running SQLite file or overwrite a later signed reply.
The bundle's `restore_paths` maps the private profile/configuration, state,
runtime, recovery and user-unit destinations. Rebuild the dedicated interpreter
environment offline using its retained requirements and wheels; verify the
profile's interpreter/runtime/signer byte pins before check mode. A Python
binary upgrade requires renewed qualification, not editing the pin to bypass it.
Journal restoration is a separately attended operation using the proven v2
archive workflow; do not replace live PostgreSQL rows as part of a routine
collector restart. After restoration, require exact original ciphertext/journal
proofs, then the installed launcher `--check-release` and unit readback before
enabling the timer. No operator signing key or household control is included.

## Fixed recurring runtime mismatch

The service template previously selected the pre-trial v1 code. It now selects
`/home/sat/.local/libexec/earthship-thermal/primal-v2/code`, the exact nine-file
trial closure including the repaired default journal sink. It reuses only the
unchanged hash-pinned dependencies from the dedicated `primal-v1/venv`.

The staged inactive v2 manifest is
`129b950c4332bd47bc49fd6c829e0fd2119ee0f7e94c038dcd94036c1d1f5cd1`.
Independent verification passes; all six original source release gates remain
false. No shared model code, stock signer, operator bunker or OpenHAB service was
changed. This template still performs **reply polling only**: the automatic
follow-up candidate below is not in that frozen runtime or command.

The exact command passed configuration and local signer checks under the unit's
resource/security settings. Its closed-gate poll exited 2 before mutation. The
SQLite pair was byte-identical before/after. Unit syntax verification passes.
The unchanged timer uses `OnUnitInactiveSec=5min`, not overlapping wall-clock
polls, and `Persistent=false`, without catch-up on restart.

## Automatic follow-up candidate

`openhab/scripts/thermal_followup.py` is a default-off library, not a service or
sender. The explicitly selected, default-off `thermal_primal.py
--follow-recommendations` command now connects it to the existing transport and
journal coordinator. The library has no signer, relay, household control or journal dependencies. It
accepts only canonical recorded decisions paired with a successful publication
to `Thermal_Advisory`, the actual bank epoch, the reviewed
`forecast-intel-thermal-v1` policy and Mountain timezone. Publication identity
and timestamps must match their relational database origin. Failed/unknown
publication, future evidence, pre-activation decisions, malformed records and
over-budget reads cannot authorize a question. It selects the newest accepted
publication, even when that says `none`; it never resurrects older advice.

Notification opportunities are bounded and explicitly separate from controls:

| Recorded advice | Earliest question opportunity | Question state | Opportunity ends |
| --- | --- | --- | --- |
| `vent_tonight` | Recorded night-window start, currently 20:00 Mountain | Windows open | Recorded night-window end, currently next day 11:00 |
| `close_up_tomorrow` | Next day 08:00 Mountain | Windows closed | End of that next local day |
| `none` | Never | None | None |

These questions do not recommend or assume skylight use, shade positions, shade
percentages, or Kiva operation. The legacy aggregate advisory has no explicit
recommendation for those separate states. A verified observation outside the
recommended action interval remains an observation, not proof of compliance or
causal benefit. No automatic outcome reward is computed here.

The existing `advisory_assessor` connection performs a read-only repeatable-read
query of at most 256 publications from the preceding 48 hours, with 2-second
statement and 1-second lock limits. Admin and capture-writer identities are
refused. No grants, role provisioning or new database write permission are
needed for that read. A production dry-run at `2026-10-03T14:53:48.592613Z`
verified the actual restricted reader and one recorded publication, category
`none`. No eligible follow-up, reservation, message or journal write resulted.
The dry-run used the existing assessment cutover for inspection, not a newly
activated collector or permission to backfill old recommendations.

The recurring command additionally requires a private, closed-schema follow-up
configuration: version 1, explicit offset-qualified activation timestamp, the
actual bank epoch, Mountain timezone, and daily limit exactly 1 (not a boolean).
Its configuration is pinned to the collector/operator identities in the ledger;
changing activation or bank/identity does not silently reset consent. A separate
private `ADVISORY_ASSESS_DSN` must identify `advisory_assessor` on exactly
127.0.0.1:5432/openhab. Capture writer, admin, another database/host, ambient
service configuration and missing/extra DSN fields are refused before state
creation. No operator signing key is used.

Reservations are inside the existing `primal.sqlite3`, not another database:
`automatic_questions` uniquely binds both Mountain calendar day and decision ID.
The origin decision/result, their digest, approved identities and exact canonical
question snapshot are retained before any signing or send. Retries reuse the
original question; changed advice cannot replace the day's reservation. The
same decision cannot generate another question after midnight. Separately
reviewed questions count against that day's budget, including original questions
retained in the ledger but removed from the current policy. DST does not reset
the local-day limit. Expired reservations are not replaced with new questions.

Caller must hold the same state lock as the collector and its backups. The
table addition preserves ledger version 1 and existing tables; the whole ledger
is already included in Primal snapshots. An actual disposable SQLite snapshot
and cold reopening preserved the exact reservation and question ID. This is
**not** yet a production migration or a complete recurring-runtime restore.

## October 3 command integration and inactive host staging

The new recurring command holds the existing state lock across configuration
pinning, origin reading/selection, reservation, original-cipher queueing, reply
polling and acknowledgement recovery. Only automatic reservations are queued;
an unqueued manual question in the base policy is not automatically sent.
Retained manual and automatic snapshots are independently validated and merged
for idempotent reply/ACK recovery. The external base-policy cap remains 100;
derived retained history is separately bounded at 4096+100, so the 101st retained
question does not break long-term polling. No historical row is deleted.

An evidence-reader outage or malformed new recommendation withholds new
reservations while continuing authenticated ingress for already retained
questions. Corrupt retained origins or changed pinned settings refuse the
command; they cannot cause a replacement question. The command is bounded by
the existing relay budgets and requires both the original Primal release and
the additional automatic-follow-up release before private reads or signing.

The independently frozen **12-file** v3 inactive closure is staged at
`/home/sat/.local/libexec/earthship-thermal/primal-v3`; its manifest SHA-256 is
`490ef7f0d6bb628d12b1377225cd9ca316e42c849a5dde7b2bc3866667dbf1e2`.
The v2 manifest layout in the verifier includes the follow-up library and its
two pure advisory dependencies. The original nine-file v1 manifest layout
remains verifiable, including the actual unchanged successful-trial runtime.
All **seven** source release gates remain false.

The private, mode-0600 eight-field recurring environment is staged separately at
`/home/sat/.config/hex/thermal-primal-followup.env`; its byte pin is
`8b28140c708216b09859589f10ef128c2a53d75bce4a9bdf8afe9f1500e9efc4`.
Only the existing Hex, restricted journal and restricted assessor credentials
were selected; no capture-writer/operator/admin credential was copied there.
No secret value was printed or committed. The original environment, trial
runtime, signer and bunker remain unchanged. A production activation timestamp
and active release profile have **not** been created yet.

The exact staged v3 command under unit-equivalent resource/security restrictions
passed signed-route configuration and actual stdin-capable Hex NIP-04/NIP-17
local self-roundtrips. Its recurring mode refused the closed gate with exit 2.
The original production SQLite pair remains byte-identical:
`df1d6230b428b30911a0ee24a57161500326fee733a67acb88014de591915408`
and `d9b108450bf38025b5a0ac051349200817cf2ff7fc229736dc8e766b1292ee58`.
Permanent collector/timer units are still not-found/inactive; the existing v2
poll-only template was not replaced or installed during this staging.

## Verification and remaining release work

The staged runtime/CLI/signer/backup group passed 57 tests with no skips, using
the actual pinned stdin-capable signer. The combined suite with the initial
32 follow-up cases passed 89 tests. The final combined run with the expanded
41-case follow-up suite passed **98 tests, no skips, in 41.59 seconds**, including
the restricted reader and relational provenance checks. System
WebSocket 10.4 lacks the loopback server API: qualifying tests must use the
collector's pinned WebSocket 15.0.1, not skip those tests or change system packages.

The expanded command/reader/stager/signer/backup/actual-loopback-relay/ledger
regression run passed **164 tests, no skips, in 160.60 seconds**. It exercises
restart after reservation, ledger commit and outbox commit; changed advice;
fixed activation; a successful authenticated reply during reader failure; no
automatic manual-question send; actual original-cipher retention; DSN/identity
refusals; and history beyond 100 retained questions. These are disposable
identities and external reader/journal doubles where explicitly marked, not new
household observations or proof of active collection.
The final 18-case stager run also passed, including a new explicit refusal of an
enabled automatic-follow-up source gate. Owned disposable test directories were
removed after all processes completed; the qualified host runtimes and intentional
private recovery points remain.

Original prerelease checklist (completed by the exact recovery/deployment above):

1. The command integration, frozen closure and separate credential staging above
   are done. Build/qualify the exact pinned active entry point and user-unit
   profile. Keep repository/generic-runtime gates default-off; only that approved
   process may open Primal, v2 journal write and automatic-follow-up gates.
2. Capture the exact activation time in a new private policy and pin it before
   first use, so old advice is not backfilled. The example policy is intentionally
   invalid until that timestamp is set. No new privileges/credentials are needed.
3. Retained-question reconstruction, daily reservation, crash recovery and
   reader-outage behavior are implemented/tested. Qualify these same paths from
   the exact active entry point under its user-unit restrictions. Preserve the
   five-minute completion-based cadence, expiry and signed-route revocation.
4. Require the real restricted journal's exact schema/readback and original
   authenticated trial proof in the refreshed profile. No NIP-17 fallback,
   manufactured household question, inferred state or actuator is authorized.
5. Refresh and cold-rehearse the complete recovery bundle with exact new code,
   service/timer, credential files, reservation table, original ciphertext,
   policy/routes and current stopped-writer PostgreSQL journal archive. Preserve
   the already-qualified October 3 authentic-observation recovery point.
6. Install the qualified **user** units, enable the timer, independently verify
   effective paths/gates/identities and its first natural cycles. No advisory
   means idle polling, not a fabricated test recommendation. Record the first
   actual automatic question and authenticated reply when naturally available.

The broad Earthship/OpenHAB goal remains active. This change does not graduate
the thermal model or enable any household actuator.

Current remaining collection work: resolve the explicitly requested relay-auth
decision and observe a genuinely eligible future recorded recommendation,
automatic question, operator receipt and authenticated reply. Do not manufacture
an advisory to close these natural-behavior gates. Signed action consumption
and model skill/graduation remain separate work.
