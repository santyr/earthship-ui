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

## Production entry-point and pinned dependency checkpoint

`pre_dusk_notification_cli.py` now provides `--check-source` and separately
release-gated `--deliver`. Identities are fixed to the operator-approved Hex
sender and DM recipient npubs; the Sat NIP-46 client identity is not substituted
for either. Source checks use the real clock and fixed private local reader
configuration (`energy_power_reader`, OpenHAB on loopback). There is no
historical-clock flag. Delivery cannot override its active prediction date.
The active target rolls at 11:00 Mountain, including the DST transition.

Delivery still rejects before credentials, history, signer or state access
while `RELEASE_READY=False`. If later qualified, it uses the fixed private
route snapshot and dedicated state paths, approved signed routes and pinned
keyer; it exposes no listener, prompt, journal or control capability. Source
checks never open the outbox or load the signer and print closed status fields,
not original source JSON, transport errors, tokens, keys or signing connections.

The September 30 real-clock check was correctly withheld: the host token and
restricted reader configuration validated, the current-day archive had exactly
one morning issue and zero pre-dusk issues. No forecast was rerun. This is an
expected pre-issue state, not a delivery or source-provenance failure.

Installed-script inspection found the required `thermal_messaging.py`,
`thermal_confirmation.py`, `thermal_state_backup.py`, and original-issue helper
modules absent from `/home/sat/openhab/scripts`. Do not install only the CLI or
claim a production deployment from the working-tree tests. A reviewed bundle,
dependency/runtime validation and rollback plan are still needed.

The exact pinned `websockets==16.0` package was installed in an owned temporary
target only. Under system CPython 3.12.3 it passed all 174 focused tests and the
full 475-test completion suite, including actual loopback relay exchanges.
Distribution RECORD SHA-256:
`d8f7088dc54e89da7edd97671bd1d5a43910f91e0520865ac36207d382450b4b`.
The package metadata requires Python >=3.10. This supersedes the earlier cached
15.0.1 loopback check, but is not household identity or public-relay delivery
qualification. No global/production package installation occurred.
Owned dependency and test temporary directories were removed; normal package
manager cache is retained for efficient reuse. No startup unit/timer was
created, no release gate opened, and no message was sent.

## Inactive deployment-bundle checkpoint

`scripts/build-pre-dusk-notification-bundle.py` builds all twelve required
tracked Python modules into an existing empty, owned private directory. It
performs bounded source reads, compilation without execution and default-off
notification/collector gate checks before output writes; files are exclusive
0600 creates, fsynced along with the directory. It packages no host credentials,
routes, outbox, Solar_PV code or service definitions. External dependencies
remain the restricted Solar_PV reader package, psycopg2 and pinned websockets.

Verification requires the externally retained expected manifest digest, exact
membership, private ownership/modes, matching per-file digests, compilable
sources and inactive gates. Ten disconnected tests passed, including changed,
missing, unexpected, public and symlinked files, no overwrite of existing
outputs, each gate activated before build, and independent copy recovery with
exact checksums. This is code-bundle recovery, not production rollback.

A fresh twelve-file temporary bundle independently verified with manifest
SHA-256 `140619756fedbe053532818bf55a4fc0ed44f142782d345cae886e369fc5c52e`.
Its CLI imported outside the repository and its real `--deliver` invocation
returned the closed `withheld` status (exit 2), without releasing messaging.
No active pointer, production files, credentials, units, timers or control
state were changed. The owned bundle and test directories were removed.
Reviewed inactive installation/rollback and household route/keyer/delivery
qualification remain next; building a bundle is not deployment.

## Inactive local installation and rollback checkpoint

`scripts/install-pre-dusk-notification-bundle.py` now provides a read-only
preflight and explicit `--apply` for this code-only namespace:
`/home/sat/.local/lib/earthship-pre-dusk-notification`. It creates private,
digest-named releases and switches only its owned `current` symlink. It never
overwrites the shared OpenHAB forecast script tree. A nonblocking installation
lock and exact expected pointer preimage reject overlaps/concurrent changes.
Copied stage files and directories are fsynced and verified before publication;
failed post-switch checks restore the verified previous pointer only if the
current pointer still belongs to this operation. Concurrent pointer changes
are not overwritten. Broken candidate contents do not prevent guarded
restoration of the original verified release or empty state.

Nineteen builder/installer tests passed, covering initial rollback, failed
upgrade to the exact previous release, corrupt candidate rollback, preimage
drift, existing corruption, overlaps, unknown files and concurrent withdrawal.
The earlier first-install test incorrectly passed the `current` symlink to
the raw bundle verifier, which intentionally refuses symlink directories;
the test now verifies the exact digest directory, preserving the guard.

Actual host sequence passed: empty-namespace preflight; inactive install;
installed CLI import and closed `--deliver` (exit 2); guarded rollback to the
original empty pointer; reinstall; and independent verification of all twelve
installed sources. Current pointer:
`releases/140619756fedbe053532818bf55a4fc0ed44f142782d345cae886e369fc5c52e`.
The rollback briefly removed only the newly owned pointer, then reinstall
restored it. The operational release and installation lock are retained, not
test clutter. Owned staging/test directories were removed.

This is **installed inactive code**, not an enabled worker: all notification
and collector gates remain false, no unit/timer was installed, and the
dedicated notification state directory is absent. No outbox, host credentials,
route snapshot, journal/model/forecast Item, OpenHAB restart or equipment
control was changed. Installed pinned dependency configuration, household
keyer/routes, attended operator receipt and notification activation remain
open. The code-builder's verification receipt is context-independent and
does not itself assert whether a bundle directory was installed.

## Household signer and labelled NIP-17 path trial

The installed code bundle passed `Keyer.check_identity` with the existing Hex
sender credential and SHA-pinned nak (`ba918faf...ae56e`). Actual signing,
NIP-44 encryption/decryption and authenticated self-roundtrip verified. This
used Hex's local sender key, **not** the operator bunker or Sat client key;
`bunker_verified=false` is expected and does not revoke the earlier operator
NIP-46 challenge. No credential was printed, rotated or copied.

The existing approved private signed-route snapshot passed the actual `Routes`
validator for both identities and three endpoints each. Fresh latest-kind-10050
queries independently returned both exact approved event IDs on nos.lol.
Primal and Damus produced no qualifying latest responses in that bounded check;
do not claim fresh 3/3 discovery or infer their precise failure cause.

Under the operator's prior approval to send a labelled test as Hex, one NIP-17
rumor was sent through nos.lol, with distinct operator and sender encrypted
copies. It explicitly says messaging test only: no forecast, thermal question,
action request, control change or training label. A dedicated private durable
outbox persisted the original envelopes before publication; the sender copy
was actually decrypted/verified and exactly matched the original rumor.
Both matching event ACKs were boolean true. Public IDs:

- Rumor: `521e61228d33862b00e10cd2a7eda9a96ac3528ef488f7559362aba0daa095a8`
- Operator envelope: `e03cf74a156c6a4f52c3b6d05ab1c2d7c64e4743c5bcbc166ed0853deeefe713`
- Sender envelope: `6ce51e82f435057d60ef9b4a5850e8914bfa3f35c39a950af83d5a037c070425`

An independent credential-free relay read returned the operator's **exact**
persisted encrypted envelope, with a valid kind-1059 signature. Ciphertext
canonical SHA-256:
`c1af1bb478e1b6eb90f34e2c3db5bf351d47c1cf43ff5b1d33e4ca9e74195fb3`.
This proves tested relay storage/readback, not recipient decryption or receipt.
Operator receipt confirmation was requested and is still pending at this
checkpoint. No signed action/state label or learned reward follows from it.

The trial used the pinned websockets 16.0 in temporary storage, since removed.
Its operational retry/audit state is retained pending receipt at
`/home/sat/.local/state/hex/pre-dusk-delivery-trial-20260930` (two envelope rows,
no sender key). It is separate from the still-absent live notification outbox.
Do not create another rumor to retry: use those original envelopes. Review
cleanup after the receipt/retry audit finishes. No production dependency or
unit/timer was installed; notification and collector release gates stay off.
