# Pre-dusk forecast notification candidate

Source-only, default-off implementation:
`openhab/scripts/pre_dusk_notification.py`. It is not installed, scheduled,
or enabled. The pre-dusk publisher remains unchanged and sends no DM.
The retired morning-trough DM remains disabled. No thermal question, listener,
journal migration, learned threshold, or equipment command is included.

## Delivery contract

- Use the existing full-bank DM threshold: alert strictly below 30%.
  This does not change the separate UI alert policy.
- Require the exact pre-dusk receipt schema, issue-date/sunset window,
  earlier same-day morning origin, internally consistent trough calculation,
  and exact original atomic SoC input/provenance.
- A caller must obtain the original immutable issue and original JDBC SoC
  receipt. Passing a held current Item is not proof of that lookup. Revalidate
  both on every attempt; the module does no database reads itself.
- Expire at the following-day 11:00 Mountain target, matching the UI.
  Recheck expiry after slow signing and before each relay publication.
- Use a deterministic NIP-17 rumor timestamped at issue time, with the exact
  issue digest attached. One durable intent per prediction day. A conflicting
  same-day issue is refused, never substituted over the original.
- Reuse the existing private SQLite `Outbox`, including sender's household
  copy. Persist each signed encrypted event before publication, then retry the
  exact ciphertext/ID after an ambiguous failure or restart. Persist ACKs per
  relay, retry only the remaining approved routes, and honor existing backoff.
- Use a **dedicated private directory**, not the thermal collector's outbox.
  The future production caller must hold its state lock throughout queue/flush.
  Use reviewed signed routes and the verified Hex identity; do not use the
  operator signing key as the sender or create another Sat challenge.
- A relay ACK means relay acceptance only. It proves neither operator receipt
  nor completed action, and must never become a training reward.

`RELEASE_READY=False` rejects both queue and flush before sending or inserting
an intent. Preparing a pure validated notice performs no network or state
writes. No command-line/live adapter is included at this checkpoint.

## September 30 verification

136 focused tests passed across the new notification candidate, existing
messaging, pre-dusk publisher, paired scoring and exact issue-source reader.
Tests cover default-off behavior, deterministic identity, threshold equality,
invalid/future/expired receipts, source digest mismatch, original calculation,
restart after ambiguous publication, partial ACKs/backoff, conflicting issue
provenance, mutated durable bodies and expiry crossed during signing.

The new tests use real SQLite but **fake cryptography and fake relays**; they
are not household identity or public delivery evidence. Existing messaging
tests include actual loopback WebSocket exchanges. System Python initially
lacked the existing Solar_PV import path and `websockets.sync`; the complete
run used the existing Solar_PV source and cached websockets 15.0.1 through
temporary `PYTHONPATH`. No dependencies were installed or production files
changed. This cached test version is not a qualification of the pinned
production `websockets==16.0` dependency.

## Remaining live gates

1. Finish the deployment adapter using the qualified source reader and locked
   worker below. Do not re-run the forecast just to create an alert.
   Credentials/endpoints and clock handling require explicit production
   validation; dependency-injected tests cannot establish them.
2. Qualify the installed keyer/runtime and the approved Hex/operator signed
   inbox routes with the actual dependency versions. Verify both encrypted
   copies and restart recovery without a forecast or control write.
3. Exercise attended labelled delivery using the correct Hex sender and
   operator recipient, and obtain actual operator receipt confirmation.
4. Only then install/activate the separate notification worker, verify natural
   issue delivery and retries, and update the release flag. A high valid
   forecast intentionally sends nothing; never fabricate a low live forecast
   for testing.

The source candidate alone closes neither these gates nor the broader goal.

## Original-JDBC preparation checkpoint

`pre_dusk_notification_source.read_notice` now uses the existing bounded local
JDBC history transport for both immutable morning and pre-dusk issues. It
requires exactly one pre-dusk origin, its uniquely linked morning issue,
morning persistence before pre-dusk issuance, and pre-dusk persistence before
the reference clock. Future/expired target dates are rejected before I/O.
The existing restricted repeatable-read SQL source lookup then validates the
exact latest original atomic SoC receipt at/before the issue. Its new internal
`read_issue_input` API returns that validated original payload for notice
validation; the existing public metadata-only `read_issue_source` contract is
unchanged. Neither source API writes or logs its payload.

160 adjacent tests pass, including archive ambiguity/chronology, missing
original source, no current-Item fallback and the unchanged scoring reader.
A read-only real-archive check for September 29, with the explicit historical
reference clock `2026-09-29T23:31:00Z`, successfully prepared **no alert** for
the original 81% issue. This used the actual local JDBC REST transport and
`energy_power_reader` connection. Synthetic public identities were passed to
the pure validator only; no identity qualification, wrapping, outbox insertion,
DM publication, forecast rewrite, or receipt/action collection occurred.
It is historical provenance evidence, **not** current alert eligibility.

No production deployment or startup unit exists yet. The locked worker,
actual identities/keyer/routes, attended receipt and activation gates above
remain open. Temporary test storage was removed; no package was installed.

## Locked worker integration checkpoint

`pre_dusk_notification_worker.run` now holds the private state lock throughout
original history/source reads, queueing and flush. Its default-off release
check precedes all state creation, credentials, history and signer operations.
It checks both route scopes and signer identity before opening the dedicated
outbox. A non-low forecast requires neither signing nor an outbox database.
Every retry rereads the original source bundle; existing envelopes remain
unchanged. The worker releases its lock and closes the database on return or
exception. It never creates a prompt, listener or journal record.

165 focused tests pass. The added integration tests cover closed-gate zero I/O,
lock contention before source reads, high-forecast signing suppression, signer
failure before intent creation and exact ciphertext reuse across worker runs.
These use a fake signer and relays and are not household identity/delivery
evidence. The optional injected clock is for disconnected tests only; a live
deployment adapter must use the real clock and expose no historical override.

This closes source-level locked worker composition, not installed production
credentials, signer/dependency/route qualification, attended delivery or
activation. No CLI, startup unit, timer or production change is included.
Owned temporary test storage was removed.
