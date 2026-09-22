# Scoped thermal confirmation ingress

**Status: source-only; not deployed or cryptographically/database-qualified on the household host.**
The new module is `openhab/scripts/thermal_confirmation.py`. Its tests live in
`tests/completion/test_thermal_confirmation.py`. Nothing enables a service,
subscribes to a relay, sends a message, changes an Item, runs a control, promotes
a model, or changes existing journal rows automatically.

This closes an implementation portion of the confirmation-collection gap in
[thermal-model-graduation.md](thermal-model-graduation.md). It does **not** close
that goal or establish that genuine operator action/outcome evidence exists.

## Contract and trust boundary

The input is one encrypted NIP-59 gift wrap (`kind:1059`) containing a NIP-17
message (`kind:14`). The operator must be allowlisted; both envelope and inner
message must address the configured collector identity. The authenticated inner
sender, not the ephemeral outer wrapper author, is checked. Identity-addressed
NIP-17 is supported; NIP-04 and decoupled-key-addressed routing are not enabled.

Cryptographic work is delegated to an explicitly selected, SHA-256-pinned `nak`
binary. The adapter first runs `nak verify` on the original wrapper, then
`nak gift unwrap`. The required upstream contract is that unwrap verifies the
seal and derives the output rumor author from the authenticated seal author.
The adapter additionally checks canonical event hashes, types, recipient, sender,
and exactly one prompt reference. The approved binary must be qualified against
this contract before deployment. Unit-test doubles are **not** proof of actual
Schnorr verification, NIP-44 decryption, bunker behavior, or relay compatibility.

The `NOSTR_SECRET_KEY` environment setting is mandatory: there is no fallback to
nak's machine-default identity. It may identify an already configured supported
keyer. Credentials are never put in command arguments, acknowledgements, or
forwarded diagnostics. The crypto child does not receive the PostgreSQL DSN.
The two nak subprocesses have bounded time/output and fail closed. Nak itself may
consult its configured network/keyer; no real keyer was invoked in local tests.

## Bind the question before collecting replies

Policy preparation generates a canonical **unsigned** kind-14 question. Its ID
binds the collector identity, operator, issue time, exact action states, expiry,
and optional correction target. A policy loaded for ingestion must match that
ID exactly. An arbitrary event ID cannot be attached to a different question and
used to reinterpret a `yes`.

Example draft policy; replace the public-key placeholders and choose actual
aware timestamps. The action states below are examples of a question, **not
instructions or advice to change the house**.

```json
{
  "version": 1,
  "recipient": "<collector-identity-64-character-lowercase-hex-public-key>",
  "operators": ["<operator-64-character-lowercase-hex-public-key>"],
  "prompts": [{
    "operator": "<operator-64-character-lowercase-hex-public-key>",
    "issued_at": "2026-09-21T08:00:00-06:00",
    "expires_at": "2026-09-21T10:00:00-06:00",
    "actions": {"vent": "closed", "indoor_shade": "closed"}
  }]
}
```

Keep the draft, normalized policy, encrypted messages and spool in a dedicated
private directory. These operations are offline and do not require a key or DSN:

```bash
umask 077
# Set these paths to private files; do not overwrite the draft with its output.
python3 openhab/scripts/thermal_confirmation.py \
  --policy "$DRAFT_POLICY" --prepare-policy > "$NORMALIZED_POLICY"
python3 openhab/scripts/thermal_confirmation.py \
  --policy "$NORMALIZED_POLICY" --render-prompts > "$UNSIGNED_PROMPTS"
```

The separately reviewed outbound sender must encrypt these **exact** rumors to
the operator under the configured collector identity, retain the returned
message identity, and verify that it equals the policy ID. Do not publish the
unsigned JSON as a public note or silently regenerate its content, timestamp,
tags, or author. Sending and listening are deliberately not wired to the obsolete
`nostr-inbox.service` or an unrelated Lightning Goats service.

A prompt belongs to one operator and is active for at most 48 hours. Replies
require one matching `e` reference. Multiple recipients or prompt references are
rejected. Policies are a trusted local approval surface; protect them from
unreviewed edits. Retain original prompt entries for retries; changing their
contents changes their IDs. Removing an operator revokes even cached retries.

## Accepted replies and time semantics

`yes` confirms all listed actions as of the authenticated inner message time.
`yes HH:MM` uses that message's America/Denver calendar date. A future same-day
clock time is rejected rather than guessed to mean yesterday. Ambiguous or
nonexistent daylight-saving times require an explicit timestamp and offset, for
example `yes 2026-11-01T01:30:00-07:00`. Reports can refer to completed actions no
more than 48 hours before the message. Future actions are never recorded.

`not yet` records no action and permits a later confirmation. `skip` records no
action and closes that prompt. A second distinct terminal reply requires a new,
explicit question rather than creating another confirmation of the same prompt.
Free-form commands, plans, arbitrary THERMAL messages, and mode changes are not
accepted at this ingress.

The signed message time and the first collector receipt time remain distinct.
The original receipt time is durably saved before the first PostgreSQL side
effect. Retries, restarts, prompt expiry after acceptance, and rewrapping the same
rumor do not change it. A clock rollback or inconsistent local receipt is rejected.
The replay identity is the **inner rumor ID**, not the randomized outer gift-wrap
ID. The original encrypted wrapper is retained locally; a rewrap does not replace it.

## Apply only after host qualification

The existing journal runtime and restricted `THERMAL_DATABASE_URL` must be
available. The module imports the existing `ActionJournal` and `ActionEvent`
interfaces, writes `nostr_confirmed` records only after authenticated acceptance,
and compares complete stored records before returning success. It writes no mode
records. Use a connection with bounded connection/query/lock timeouts and verify
that the existing append-only schema, restricted role, and backup are qualified.
Do not deploy an incompatible thermal runtime/model pair to obtain this module.

An attended invocation, with credentials supplied through an existing private
environment rather than pasted in the shell command, is:

```bash
python3 openhab/scripts/thermal_confirmation.py --apply \
  --policy "$NORMALIZED_POLICY" \
  --spool-dir "$PRIVATE_SPOOL_DIRECTORY" \
  --nak "$ABSOLUTE_APPROVED_NAK_BINARY" \
  --nak-sha256 "$VERIFIED_BINARY_SHA256" \
  --event-file "$ENCRYPTED_REPLY_FILE"
```

The explicit binary path must be a non-symlink regular executable owned by the
current user or root, without group/world write permission. The spool directory
must be owned by the current user with mode 0700; the database is mode 0600.
Back up the entire spool using an SQLite-consistent method and encrypted storage.
It holds private household message/receipt data. It is not a tamper-proof ledger
against a compromised host administrator. Reconstructed records are checked
against authenticated content on replay to catch inconsistent pending data.

Exit 0 emits one local JSON storage receipt; exit 2 refuses input/policy; exit 3
means no acknowledgement and an operational dependency needs repair. A storage
receipt is **not** evidence that a Nostr acknowledgement was transmitted. Wire
an encrypted outbound acknowledgement only after this receipt is successfully
returned. Do not acknowledge on process launch, local queuing, or append alone.

If a PostgreSQL commit succeeds but readback or local receipt persistence fails,
replay the same encrypted message. The durable first receipt and journal
idempotency make this safe. Full readback is repeated even for an already
acknowledged duplicate. Missing, additional, changed, duplicate, or unavailable
records produce no success. The spool is committed before the database write.

## Corrections are append-only

Prepare a **new** prompt with `correction_of` equal to the original accepted inner
rumor ID. It must concern the same operator and exact action set. The resulting
records supersede the original action IDs; no original row is modified or deleted.
The original must already have a verified local storage receipt. A correction
cannot target a skip, an unknown receipt, or an already superseded ancestor;
further corrections must target the latest accepted correction. Correcting a
pending failed message is not a way to abandon or rewrite its receipt.

## Required production acceptance; still open

Run the full existing repository suites plus `python3 -m pytest tests/completion/ -q`.
Then qualify the exact approved nak/keyer and PostgreSQL implementation in isolation:

1. Use disposable identities to exercise genuine encrypted messages. Reject altered
   wrapper hashes/signatures, forged seals, corrupt ciphertext, unauthorized
   senders, wrong inner/outer recipients, duplicate references, and out-of-scope
   messages. Verify the actual binary's authenticated-author behavior.
2. Exercise real restricted PostgreSQL writes, duplicate/re-wrapped messages,
   append/readback failures, interrupted acknowledgements, process restarts,
   append-only correction links, and revocation. Verify exact row equality and
   no secret or plaintext diagnostic leakage. No production fixtures.
3. Review and connect a narrow relay receiver, encrypted question sender, and
   encrypted acknowledgement sender. Add bounded polling/reconnect/replay,
   durable delivery, retention/backups, and service restrictions through a separate
   attended release. Do not reactivate the missing legacy listener.
4. Capture genuine operator replies and later qualified temperature outcomes.
   Do not convert fixtures, expected household behavior, elapsed time, or an
   unanswered question into confirmed action or causal-benefit evidence.

This ingress does not authorize thermal advisory graduation, automatic actuation,
or a persistence migration. Those remain separate evidence and review gates.
