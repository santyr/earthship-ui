# Recurring thermal confirmations: approved policy and qualified candidate

## Authority and current state

On October 3 the operator selected **automatic questions after recorded thermal
recommendations, at most once daily**, with five-minute inbox polling. This is
approval for observational collection, not actuator access, model promotion,
inferred compliance, or new thermal advice. No further policy approval is needed
for this scope; the remaining work is implementation and release qualification.

**Not live yet.** `thermal-primal.service` and `.timer` remain not-found/inactive.
No question was sent or journal row written in these checks. The successful
October 2/3 attended Primal trial and its recovered authentic shade observation
remain intact. See [the trial evidence](2026-10-01-primal-compatibility-candidate.md).

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
sender. It has no signer, relay, household control or journal dependencies. It
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

## Verification and remaining release work

The staged runtime/CLI/signer/backup group passed 57 tests with no skips, using
the actual pinned stdin-capable signer. The combined suite with the initial
32 follow-up cases passed 89 tests. The final combined run with the expanded
41-case follow-up suite passed **98 tests, no skips, in 41.59 seconds**, including
the restricted reader and relational provenance checks. System
WebSocket 10.4 lacks the loopback server API: qualifying tests must use the
collector's pinned WebSocket 15.0.1, not skip those tests or change system packages.

Before enabling recurrence:

1. Connect this candidate to a separately frozen collector closure and explicit
   active release entry point. Keep repository gates and generic staged runtimes
   default-off. Capture the exact activation time so old advice is not backfilled.
2. Supply the existing assessor credential privately to that dedicated runtime;
   never broaden the journal writer's privileges or print/commit credentials.
3. Under the shared state lock, reconstruct retained automatic questions, merge
   them with the approved base policy, enforce its bounded inventory, reserve
   before signing and reuse the existing original-cipher delivery machinery.
   Poll replies on the same five-minute completion-based cadence. A changed
   policy/operator or missing origin must withhold, not create a fresh question.
4. Qualify crash boundaries before/after reservation, signing, ledger/outbox
   commits and policy reconstruction, plus route revocation and expiry. Preserve
   authenticated authorship, exact reply-reference binding, first receipt time,
   journal readback and bounded relay retries. No NIP-17 fallback or artificial
   household questions are authorized.
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
