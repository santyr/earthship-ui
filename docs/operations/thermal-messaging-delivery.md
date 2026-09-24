# Attended thermal messaging and keyer qualification

## September 22, 2026 checkpoint

The operator's `/home/sat/.local/bin/nak` v0.20.7 passed the installed-binary
qualification with SHA-256
`ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e`.
Do not ask for the same binary inventory again or treat v0.18.2 as the installed
version. The old fingerprint remains refused as a rollback guard.

CI run `35742165746` for `e6ba9ed` completed successfully in both the main test
job and nak-authentication. That result precedes the new delivery code and does
not establish its acceptance. The new dedicated workflow tests delivery below.

## Implemented scope

`openhab/scripts/thermal_messaging.py` adds the configured-keyer self-check,
encrypted prompt transmission, single-file authenticated reply processing,
encrypted storage acknowledgements, and a persistent outbox. This is attended
source functionality, not an activated service or an automatic inbox subscriber.

Messages are canonical unsigned kind-14 rumors sealed and gift-wrapped through
the qualified nak. Plaintext goes over stdin, not command arguments. Both the
operator and collector get separately encrypted copies. Identity encryption is
explicit; decoupled-key addressing is not enabled. Recipient routes come only
from reviewed, signed kind-10050 announcements. Publication sends kind-1059
wrappers, never a public plaintext note or the raw signed keyer probe.

The relay adapter requires a boolean-true NIP-01 OK naming the exact envelope
ID. Socket writes, process success, NOTICE, EOSE, wrong IDs and negative OK do
not count as acceptance. An OK means relay acceptance, not operator receipt or
reading. Optional NIP-42 auth is bounded to one challenge per connection and
requires `--relay-auth`: it reveals the collector identity to the approved
relay. No arbitrary event-signing endpoint is exposed by the CLI.

SQLite stores each randomized envelope before publication. Retries and process
restarts reuse the original envelope ID. A lost OK can cause retransmission of
that same event, never a claim of exactly-once network delivery. Positive OKs
are saved per route. Retrying is attended with `--flush`, using exponential
backoff from 10 seconds to one hour; nothing starts a timer automatically.

Every acknowledgement is generated from the existing ingress receipt, not
caller-provided success JSON. Before publication the original reply is
reauthenticated and the existing JournalSink repeats exact record readback.
Journal failure cannot generate a success receipt. Reconciliation repairs the
crash window between journal commit, local acknowledgement and outbox queue.
Revoked operators, modified questions and expired prompts are withheld.

A batch admits at most 16 pending copies. New work stops after a 90-second
batch budget; an in-flight bounded keyer/relay operation may finish beyond it.
The relay has a 45-second response budget, 32-frame limit, 64-KiB message limit,
10-second connect timeout and two-second close timeout. There is no unlimited
relay replay or automatic message polling in this change.

The outbox caps itself at 4,096 copies and refuses further insertion rather
than silently pruning evidence. Retention and encrypted, SQLite-consistent
backup procedures must be reviewed before long-running deployment. Its private
plaintext state is not a tamper-proof ledger against an administrator.

## September 23 host delivery checkpoint

The installed pinned nak passed `scripts/qualify-thermal-delivery.py` with
`websockets==16.0` in a disposable virtual environment. All eight real-keyer
and loopback-relay checks passed, including signed recipient routes, bounded
NIP-42 authentication, exact relay OKs for both encrypted copies, authenticated
reply/receipt content, and no republishing after restart. This test used only
disposable identities and an in-memory journal double. It made zero production
journal writes and verified neither household keys nor external relay delivery.
The disposable environment was removed after the run.

The operator approved the existing recipient of Hex's Nostr DMs as the sole
authorized thermal-confirmation operator. Host readback matched the public key
in the current OpenHAB DM notifier with that approved identity; the configured
Hex public identity is available for a collector policy. Read-only kind-10050
queries against all three relays already configured for the OpenHAB notifier
initially returned no signed recipient relay-list event for either identity. Connectivity
to at least one relay was confirmed separately. The notifier's existing relay
arguments are not signed recipient inbox routes and must not be silently
substituted for them. No private policy, reviewed route inventory, production
outbox, listener, question, or journal write was created or enabled.

Before an attended household trial, arrange and verify signed kind-10050
announcements for both identities, review their endpoints, install the private
policy and route inventory, and qualify the real journal and encrypted-state
backup. The operator-identity approval does not authorize guessing those routes.

Later September 23, the operator approved those three existing relay endpoints
as Hex's collector inbox routes. Hex signed and published one kind-10050 route
announcement, event ID
`f75b3a5fd8fc5a6734af6cee3a4c5a64009e86bc0efd57e6926b9ec434a16c84`.
The pinned nak verified its signature, expected collector author, empty content
and exact three relay tags before publication; independent read-only requests
returned that same event from each relay afterward. The disposable nak config
directory was removed. No operator-signed kind-10050 announcement was found at
the final readback, so the complete reviewed route inventory still cannot be
installed. No prompt, listener, outbox or journal action was enabled.

At a new September23 approximately 15:10 MDT read-only query, the approved
operator identity still had zero kind-10050 route events returned on each of
the same three configured relays. All three queries completed successfully.
The existing DM notifier's local key signs as Hex, not as the recipient; it
cannot create the missing operator-signed announcement. Collector activation
remains withheld, while independent storage and accounting work continues.

At September23 22:37 MDT, another **read-only** public-event check returned
zero operator-authored kind-10050 announcements from each of the three
notifier relays. The previously signed Hex collector announcement remained
available with the same event ID on `nos.lol` and `relay.primal.net`.
The installed OpenHAB notifier uses Hex's key to send legacy encrypted
kind-4 DMs to the approved recipient; it does not possess the recipient's
signing key. A bounded metadata-only query found 100 recent Hex-to-recipient
events at `nos.lol` (the query cap, **not** an all-time count) and five at
`relay.primal.net`; a separate DM query to `relay.damus.io` returned HTTP 503,
so no absence claim is made for that relay. No ciphertext, plaintext, signing
material, prompt or reply was printed, sent or stored by this check. Existing
DM traffic shows that some encrypted events are retrievable; it does not
replace an operator-signed inbox route, prove operator reading, or verify
advisory compliance. Thermal collector activation remains withheld.

At September 24 03:40 MDT, a new bounded read-only `nak req` for kind-10050
used the notifier's approved recipient public key. Signature verification
remained enabled and no signing key was supplied to the query. `nos.lol` and
`relay.primal.net` completed successfully and returned zero operator-authored
inbox announcements. `relay.damus.io` returned a query error (exit 3), so its
current state is unknown. A local metadata-only comparison also confirmed the
configured Hex signer and approved DM recipient are distinct 64-character
public identities; the notifier cannot sign for the recipient. No message,
policy, outbox, listener or journal write was created. The approved operator
must publish their own signed inbox announcement before this collector can use
that identity; the two successful negative queries do not prove absence on
every relay.

## Earlier configured-keyer check

September 23 host readback: the configured-keyer self-check completed with
`status=passed`, `scope=configured-keyer-self-roundtrip`, and true signing,
encryption and decryption flags using the pinned v0.20.7 binary. It reported
`message_published=false`, `journal_writes=0`, `relay_delivery_verified=false`,
`bunker_verified=false`, and `production_ready=false`. The expected public
identity came from the existing private Nostr environment; no key, address,
rumor, ciphertext or policy was printed or saved. This closes the local-key
self-check only. No private thermal collector policy or reviewed route inventory
was found in the checked host locations. This check alone did not establish an
operator identity or authorize selecting relays, sending a question, or enabling
a listener; the later identity approval and route query are recorded above.

Use the existing private signer environment on the host. `NOSTR_SECRET_KEY`
selects the intended keyer; for a remote signer this is the existing bunker URL.
An explicitly configured `NOSTR_CLIENT_KEY` is preserved. Do not paste either
setting, an environment file or a database DSN into chat or commit it.

From the updated repository, substitute the collector's expected public hex key:

```bash
python3 openhab/scripts/thermal_messaging.py --check-keyer \
  --collector COLLECTOR_HEX_PUBLIC_KEY
```

Or use the collector already bound in a private normalized policy:

```bash
python3 openhab/scripts/thermal_messaging.py --check-keyer \
  --policy "$NORMALIZED_POLICY"
```

No new Python package is required for this check. It verifies the pinned binary,
asks the configured signer to sign a random self-check, verifies that signature
and its expected author, then encrypts and decrypts the self-check. The probe
is not published and creates no production journal, outbox or service.

Unlike the previous disposable-key test, this deliberately uses the configured
signer and may require a bunker approval. `bunker_verified` is true only when
the tested setting is a bunker URL. A local key's successful self-check is not
reported as a bunker test. No result establishes remote operator delivery.
Share only the resulting JSON receipt. An error is sanitized and never prints
keyer URLs, keys, decrypted messages or PostgreSQL diagnostics.

## Attended delivery setup (after keyer acceptance)

Install `openhab/scripts/requirements-messaging.txt` into the intended existing
virtual environment; do not modify unrelated application environments. It pins
websockets 16.0. The existing journal environment must also provide psycopg2.

Use the normalized prompt policy described in
[thermal-confirmation-ingress.md](thermal-confirmation-ingress.md). Keep policy,
routes and encrypted reply files owned by the service user with mode 0600;
state directories must be 0700. No production identities are supplied in Git.

The private routes file has this shape (the array holds complete signed events,
not strings or placeholder objects):

```json
{"version":1,"announcements":[]}
```

Replace the empty array with one verified kind-10050 event for the collector
and each allowlisted operator. Empty, missing or duplicate identities fail.
Review the current recipient announcements and their relay endpoints before
saving them. This implementation intentionally does not discover or silently
update routes from untrusted replies. It cannot establish that a supplied
snapshot is the newest network event: refreshing and approving snapshots is an
operator responsibility. Each list must have one to three unique wss endpoints,
without credentials, query strings or fragments. Pending sends obey the current
reviewed route file, not removed endpoints. No fallback public relay is used.

For an explicitly approved question, sending creates real encrypted messages:

```bash
python3 openhab/scripts/thermal_messaging.py --send-prompts \
  --policy "$NORMALIZED_POLICY" --routes "$PRIVATE_ROUTES" \
  --state-dir "$PRIVATE_THERMAL_STATE"
```

Processing a genuine reply writes to the existing restricted action journal
only through the qualified ingress, then queues its encrypted receipt:

```bash
python3 openhab/scripts/thermal_messaging.py --process-reply \
  --policy "$NORMALIZED_POLICY" --routes "$PRIVATE_ROUTES" \
  --state-dir "$PRIVATE_THERMAL_STATE" --event-file "$ENCRYPTED_REPLY_FILE"
```

After interrupted publication or a restored connection:

```bash
python3 openhab/scripts/thermal_messaging.py --flush \
  --policy "$NORMALIZED_POLICY" --routes "$PRIVATE_ROUTES" \
  --state-dir "$PRIVATE_THERMAL_STATE"
```

Add `--relay-auth` only after reviewing collector-identity disclosure to those
relays. Keep old accepted prompt entries for journal retries. For operational
commands exit 0 means no pending failure was reported, 2 means withheld/refused
work, and 3 means retryable/deferred/incomplete work. Read the counts; zero new
acceptances may simply mean all queued copies were accepted on an earlier run.
No command returns an operator-read receipt or promotes a model.

## Validation and remaining work

Local validation: 56 new tests exercise private SQLite state, atomic enqueue,
replay, journal-failure gating, recovery, expiry, revocation, route validation,
secret separation, exact OK semantics, and actual loopback WebSocket/NIP-42
connections. These unit tests explicitly double cryptography and the journal.
The existing 137 packaged regressions also pass in the local fixture; this is
not a local run of the complete repository.

The dedicated Thermal delivery qualification workflow executes the real pinned
nak with disposable keys and a real loopback WebSocket relay inside a network
namespace with only loopback enabled. It checks actual signing, wrapping,
operator/self decryption, NIP-42 signatures, exact prompt and receipt contents,
and restart deduplication. Its journal sink is explicitly in-memory; do not
claim that workflow alone proves a real PostgreSQL integration or live bunker.
Read the actual CI result before calling the new code qualified.

Remaining: genuine configured bunker check, reviewed recipient routes, a live
attended question/reply/journal/acknowledgement trial, durable bounded inbox
subscription/polling and reconnect tests, retention/backup qualification and
service deployment. No legacy listener, controller, timer, production journal
or thermal model has been activated by these repository changes.

Protocol references: [NIP-17](https://github.com/nostr-protocol/nips/blob/master/17.md),
[NIP-59](https://github.com/nostr-protocol/nips/blob/master/59.md),
[NIP-42](https://github.com/nostr-protocol/nips/blob/master/42.md),
and [WebSocket client API](https://websockets.readthedocs.io/en/16.0/reference/sync/client.html).
