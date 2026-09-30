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

1. Implement a bounded read-only adapter that uniquely identifies the original
   pre-dusk JDBC issue and exact atomic input, and a locked dedicated outbox
   invocation. Do not re-run the forecast just to create an alert.
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
