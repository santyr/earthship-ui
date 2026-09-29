# Attended thermal messaging and keyer qualification

## September 28 inbound backlog review

September 29 attended household signer update: the approved Sat NIP-46 client
completed a remote signing challenge against the root Earthship operator
bunker. The labelled kind-1 test event
`fac909b6c4bf8dbbdc30e551f410c717a0bcd1d94c25f5eb96bfb3b976c94cf6`
was independently signature-, author-, and content-verified on two of the
three approved relays. A separate fresh kind-10050 read returned both exact
signed operator and Hex inbox announcements from all three relays. This
qualifies the tested client-to-bunker signature path. Fresh copies of the
announcements passed the collector's actual `Routes` validator with the pinned
verifier, but no private route snapshot has yet been approved or installed.
It does not exercise a signed NIP-17 confirmation, the private
collector policy, PostgreSQL journal, consistent recovery or hostile backlog;
`POLL_RELEASE_READY` remains false and no collector service was started.
Focused bunker/messaging regressions passed 85 tests using the previously
documented cached `websockets` 15.0.1 package via temporary `PYTHONPATH`;
the system Python alone lacks `websockets.sync`. No package was installed.

The source-only collector remains release-gated. Its current relay query asks
for at most 64 kind-1059 events over up to four days, waits for EOSE, and
refuses a page of exactly 64 events. This prevents an obviously truncated
page from being called complete. It is not a pagination solution: the
[NIP-01 filter contract](https://github.com/nostr-protocol/nips/blob/master/01.md)
says `limit` is a SHOULD for relays and permits fewer returned events, while
EOSE marks the end of what the relay chose to send initially. NIP-01 defines
inclusive second-resolution `since`/`until` and a recommended newest-first
order with event-ID tie breaking; an overlapping time cursor therefore needs
an explicit same-second boundary check and a fail-closed response when a
boundary bucket itself cannot be enumerated. A short page alone cannot prove
archive completeness across arbitrary relays.

Separately, the original `poll_replies` counted every not-yet-ingested
envelope against its 16-attempt batch before authenticated decoding. Rejected
envelopes were not marked ingested, correctly preserving retryability, but
the same 16 rejected events could consume each later batch and starve an older
valid confirmation. Do not treat rejection as a successful journal receipt or
silently advance an unverified cursor. A release design must bound rejected-
envelope retries and prove progress under hostile streams, retain an operator-
visible no-ack/retry path, and review encrypted-state backup and relay
retention. `POLL_RELEASE_READY` stayed false throughout this review.

### Source-only repeated-refusal backoff

The disabled collector now has a version-3 SQLite refusal ledger, migrated in
place from versions 1 and 2 without dropping delivery or completed-ingress
rows. Each signed envelope ID is bound to the canonical envelope digest;
after a refused decode, it is deferred for five minutes, then exponentially
up to one hour. Refusals remain retryable and are never counted as successful
journal ingestion or acknowledged. A later successful, verified ingestion
atomically clears that envelope's refusal entry. The ledger refuses new rows
at 4,096 rather than silently pruning, and the poll result separately reports
`refusal_backoff` alongside the aggregate deferred count.

An isolated restart regression confirms that two repeatedly refused envelopes
consume a two-attempt first poll, then are skipped on the next poll so an older
valid confirmation reaches the journal/ack path exactly once. Quota, retry
timing, migration and clearing tests also pass; the full source-only completion
suite passed 368 tests at that checkpoint with a pre-existing cached WebSocket package, without
installing a new environment. This closes only repeated-*same-ID* starvation.
An attacker rotating event IDs can still exhaust each batch or the ledger,
and relay pagination/completeness, operator route, household trial and
consistent private backup remain open. `POLL_RELEASE_READY` remains false;
no household relay, prompt, collector state or production journal was used.

### Source-only saturated-window splitting

The read-only relay fetch now fixes an inclusive `until` at poll start. An
exactly saturated 64-event page is split into disjoint, inclusive second
windows and each subquery must reach its own matching EOSE. The retrieval is
bounded to eight pages, 256 distinct envelopes, the existing per-page frame
cap, and one shared 45-second deadline. A saturated single-second bucket or
any exhausted budget refuses the whole relay result; no partial page reaches
ingestion. Tests exercise a multi-page complete result, a saturated second,
the page budget, NIP-42 retry and ordinary one-page reads. The full source-
only completion suite passed 369 tests with the existing cached WebSocket
package and no new installation.

This handles *visible saturation* only. NIP-01 says relays SHOULD apply the
requested `limit` and may return fewer events, so even a short EOSE-complete
page is not proof of every stored event. Rotating-ID spam, signed operator
route, acknowledged delivery/retry, private backup and attended household
qualification remain open. `POLL_RELEASE_READY` is still false; no production
relay or collector state was used.

### Source-only refusal retry visibility

An attended poll result now includes an aggregate `inbox_refusals` summary:
the number of locally refused envelopes still pending, how many are due now,
and the earliest future retry time. It prints no envelope IDs or contents.
Successful ingress removes that envelope from the summary. The local refusal
status and its time transitions have focused tests; the full completion suite
passed 370 tests with the cached WebSocket package. This is operator-visible
local retry state, not evidence that a relay retained or delivered every
message. The poll CLI release gate remains false and no live inbox was polled.

### Source-only bounded inbox batch fairness

Within each already-bounded newest-first relay result, the attended poll now
alternates attempts from the newest and oldest ends before the middle. A test
with 20 distinct newer invalid envelopes and one older valid reply confirms
that the older reply reaches the journal in the first 16-attempt batch, while
unattempted envelopes remain deferred. The full completion suite passed 371
tests. This mitigates a single-sided burst; a hostile stream at both ends,
under-limit relay omissions, or a saturated relay result can still prevent
progress. It does not relax the page, total-event, time, signature or release
gates, and no household inbox was polled.

September 29 follow-up: the disabled collector now fetches each of at most
three reviewed recipient routes before spending the common 16-attempt ingress
budget, then alternates one already-bounded envelope from each route. The
existing newest/oldest alternation remains within each route. A regression
with 20 distinct invalid envelopes on the first relay and one valid reply on
the second confirms the latter reaches the journal on the first attended
poll. All 78 messaging tests and 379 source-only completion tests pass using
the existing cached WebSocket package; no package was installed. This closes
one cross-route starvation case, not adversarial two-sided spam, under-limit
relay omissions, signed operator route, private journal recovery, or household
qualification. `POLL_RELEASE_READY` remains false; no live inbox was polled.

### Source-only private SQLite pair recovery

The attended messaging CLI now holds a nonblocking, private `state.lock`
through both SQLite connection closes; a second CLI or snapshot refuses while
it is held. `thermal_state_backup.py --snapshot` uses that same lock and the
SQLite backup API to capture `confirmations.sqlite3` and `delivery.sqlite3`
into a new private directory. It writes a hash manifest only after both
copies pass integrity checks. `--verify` rechecks both hashes and SQLite
integrity. A missing, symlinked or public source/lock is refused; an existing
destination is never overwritten or automatically removed after failure.
Disposable tests reopened both restored application databases, exercised lock
contention, tamper refusal and missing-source no-cruft behavior; all 377
completion tests pass.

This is a source-only, same-host SQLite-pair tool. It has not touched the
household collector or its state and does **not** capture the PostgreSQL
action journal, policy/routes, signing authority, or an off-host recovery
point. A coordinated stopped-collector journal/SQLite restore rehearsal and
reviewed destination/retention still block release. `POLL_RELEASE_READY`
remains false.
The follow-up writer census found a second attended source entrypoint,
`thermal_confirmation.py --apply`, which could otherwise mutate the spool
outside that lock. It now takes the same lock through spool close and refuses
contention before opening the database. A CLI regression and all 378
completion tests pass. The disposable delivery-qualification harness uses
its own isolated state; no live collector or installed CLI was changed.

## September 27 source-only backlog checkpoint

The disabled inbound collector now keeps a private, durable ledger of envelope
IDs only after the existing journal-and-acknowledgement path succeeds. A later
attended poll skips those completed envelopes before applying its 16-attempt
batch cap, so a backlog can advance across process restarts. An incomplete or
retryable ingress is not marked complete and is retried. The existing outbox
schema migrates from version 1 to 2 without dropping queued delivery intents.
The ledger has the same 4,096-row refuse-on-full policy as the outbox; it is
not an automatic retention or pruning mechanism.

Focused thermal messaging/confirmation tests passed (182), including restart,
retry and version-1 migration cases; the full source-only completion suite
passed (361). Tests used the existing cached WebSocket package without an
installation. No household key, relay, private journal or production collector
was used. `POLL_RELEASE_READY` remains **false**. Saturated-page pagination,
spam/refused-envelope starvation, consistent private spool/outbox backup,
signed operator inbox routes and an attended end-to-end trial remain release
blockers. This change does not make unattended collection safe.

## September 27 route recheck

A bounded, signature-verifying, read-only `nak req` queried kind-10050 events
authored by the existing approved DM recipient on `nos.lol`,
`relay.primal.net` and `relay.damus.io`. All three relay connections completed
and each returned zero announcements. The query used only the recipient's
public key; no operator or Hex signing key was loaded, no message was sent,
and no collector state or journal changed. This is absence on those three
approved routes at this time, not a global Nostr absence claim. The collector
release gate remains closed until the operator publishes a signed inbox
announcement and its event/endpoints are verified, followed by the already
documented household, backup and spam-liveness gates.

## September 24 source-only inbound poll checkpoint

At 17:20 MDT, a fresh public, read-only kind-10050 query used only the
existing notifier's approved recipient **public** key. `nos.lol`,
`relay.primal.net` and `relay.damus.io` each completed successfully and
returned zero operator-authored inbox announcements. The public key, route
events, message bodies and private notifier configuration were not printed;
no signing key was loaded. This confirms the operator route is still absent
on those three proposed relays at this checkpoint, not on every possible
relay. The collector remains disabled.

The disabled inbound poller's NIP-42 handling now accepts either ordering of
an `auth-required` CLOSED frame and the matching AUTH challenge. It still
signs only when `--relay-auth` is explicit, accepts one challenge, requires
the exact positive auth OK, and retries the same bounded REQ. A real loopback
regression covers CLOSED-before-AUTH. The focused messaging suite now passes
68 tests and the full source-only completion suite passes 358 tests. This
does not qualify a household key or public relay for collection.

The missing relay-to-ingress seam now has an attended `--poll-replies` source
path, but `POLL_RELEASE_READY` remains **false**. The CLI refuses this mode
before opening a private policy, spool, keyer or journal. No household relay,
question, acknowledgement, collector state or production journal was touched.

The poller reads only the collector's reviewed, signed kind-10050 inbox
routes, selects kind-1059 envelopes addressed to that collector, validates
their signatures through the pinned keyer and waits for the matching NIP-01
EOSE before treating a stored-event page as complete. Each successful
envelope then goes through the existing authenticated NIP-59/NIP-17 decoder,
durable first-receipt spool, exact journal readback and acknowledgement
outbox. Optional NIP-42 challenge signing remains an explicit identity-
disclosure choice. Reads have a four-day maximum lookback, 64-event and
128-frame caps, a 45-second response budget, and a 16-envelope ingestion
batch cap. A saturated page is reported incomplete rather than silently
claiming coverage; pagination/retention and spam-starvation handling remain
release blockers for any unattended listener.

The focused messaging suite passed 67 tests, including actual loopback
WebSocket EOSE and NIP-42 read flows, duplicate envelopes on two reviewed
routes, bounded-page refusal and the closed CLI gate. The full source-only
completion suite passed 357 tests, and 37 adjacent confirmation/journal
tests passed. A stale persistence test double was updated to accept the
current renderer's `allow_file` keyword. The host's system Python lacks
`websockets.sync`; tests used an existing cached websockets 15.0.1 package
through a temporary `PYTHONPATH` only, without installing or leaving a test
environment.

These are source and loopback results, not household-key, public-relay,
signed-operator-route, restricted-database, backup or real-operator evidence.
Keep polling off until those gates and an attended end-to-end trial pass.

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

At September 24 05:07 MDT, a fresh bounded, read-only query used the approved
operator public key from the existing notifier configuration without printing
it or loading an operator signer. Signature verification remained enabled.
`nos.lol`, `relay.primal.net` and `relay.damus.io` all completed successfully;
each returned zero matching kind-10050 operator-authored events. This now
establishes absence on all three proposed routes at that checkpoint, not
absence on every Nostr relay. The configured DM signer remains Hex's distinct
identity and cannot make the operator's announcement. No prompt, listener,
outbox, private policy or journal write was activated.

September 29 local signer-discovery update: the operator recalled a `nak`
NIP-46 bunker from the now-decommissioned Lightning Goats VPS. The local
Lightning Goats checkout contains a bunker unit template and launcher using
`LoadCredentialEncrypted`, but `lightning-goats-nostr-bunker.service`, its
`/etc/lightning-goats/bunker.env`, launcher installation and encrypted signer
credential are all absent on this host. The only local Nostr user unit found
is the disabled, inactive legacy `nostr-inbox.service`, whose target script is
absent. The Lightning Goats template is documented as a **project** signer;
its existence does not prove possession of or authority over the distinct
Earthship operator key. Its default `/usr/local/bin/nak` path is currently
group-writable (`0775`) and not the Earthship-qualified pinned binary; do not
deploy that template here unchanged. A reusable local launcher could share
code across projects, but each signing identity needs separate credentials,
client allowlists and runtime state. The operator-key provisioning path and
signed kind-10050 route remain open; no service, secret or message changed.

Later September 29, the operator installed the original operator key as a
mode-0600 root-owned systemd-encrypted credential. Their root-run offline
identity verifier reported `operator credential matches existing DM recipient`.
Host readback showed the root-owned verifier identical to the reviewed source
and the root-owned `nak` identical to the qualified v0.20.7 digest. The
operator's supplied recipient npub and Hex sender npub both matched the
respective current OpenHAB public identities. This proves local key custody
for the intended recipient, not a signed operator inbox route or a configured
NIP-46 client. The systemd host credential key is on an unencrypted root
filesystem, so whole-drive theft remains a key-custody risk.

The legacy OpenHAB Hex DM notifier was then narrowly changed to use nak's
`NOSTR_SECRET_KEY` environment support instead of passing the sender key in
command arguments. A disposable-key offline test passed, live source readback
matched, and one operator-authorized labelled test DM received ACKs from all
three configured relays. The operator separately confirmed receipt of that
labelled DM in their inbox. This verifies the existing Hex-to-operator NIP-04
path, not the NIP-17 thermal-confirmation path. Sender-key rotation needs
coordinated recipient-side handling because it changes Hex's public identity.
No thermal confirmation prompt, listener, route announcement or journal write
was activated by these checks.

Later September 29, the operator ran the root-owned one-shot route publisher.
It reported event ID
`defe6a8571ae87261278bcae968f88d821e304930e7fad5e7e486f46e1fb20d2`
on all three approved relays. Independent read-only queries returned that same
event from `nos.lol`, `relay.primal.net` and `relay.damus.io`; its Schnorr
signature, approved operator author, empty content and exact three relay tags
all verified. The installed publisher matched the reviewed source digest.
This closes the operator-signed inbox-route gate only. A fresh read-only query
for the previously recorded Hex collector route event returned it on
`relay.damus.io` with a valid signature and exact three-relay set, but returned
no Hex kind-10050 event from `nos.lol` or `relay.primal.net` at this checkpoint.
The complete two-identity route inventory and thermal collector remain off;
the missing Hex copies and sender-key rotation decision need resolution before
a household NIP-17 confirmation trial.

The operator chose to retain Hex's existing npub after reviewing its
key-custody implications. The already-signed public Hex event
`f75b3a5fd8fc5a6734af6cee3a4c5a64009e86bc0efd57e6926b9ec434a16c84`
was fetched from `relay.damus.io`, signature/author/tag verified and republished
**without loading a private key** to `nos.lol` and `relay.primal.net`. Both
relays acknowledged it, and independent readback verified the exact event on
all three approved endpoints. This repairs current route availability, not
signer custody, long-term relay retention or the remaining collector
release gates. The public route should be rechecked immediately before any
attended household trial.

The operator selected separate identities per project. Source-only
`deploy/nostr-bunker/` now contains a reusable local systemd instance template,
launcher and installation boundary. It is not installed, enabled, or proof of
operator-key custody. Each instance needs its own encrypted key and explicit
client allowlist; the Hex collector must not be granted the operator signer
merely to publish the operator's kind-10050 inbox announcement.

Later September 29, the operator selected Sat's public key
`5302cd2bfe2dcc76c5a9abcba74e6c5f1a07444b35c25e0cd74bac5b453fb5f6`
as the only proposed Earthship NIP-46 client. The deployable public instance
example records that choice; it has not been installed or started. A separate
password-store entry described as the bunker pubkey,
`4bf9fcbda64b18e885ce04d593c37264d3561a1baf3adb8c3fe01b1a8bc7edde`,
does not equal the verified operator signing pubkey
`669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6`.
The current `nak bunker` template has no separately configured transport key.
Resolve which bunker identity Sat's client expects before installing or
activating the service. This does not alter the verified operator inbox route.

The operator subsequently confirmed Sat's client expects the verified
operator identity as remote signer. The exact public allowlist, launcher and
log-safe unit were installed and independently compared to source; systemd
reported the unit loaded, inactive and disabled. The service now discards both
output streams because `nak bunker` can print a connection secret and
request/response details. An attended start and actual Sat-client challenge
remain; no operator bunker or thermal collector is running at this checkpoint.

At 10:42:32 MDT on September 29, the operator completed the verifier and an
attended start. Repeated systemd readback found the Earthship operator bunker
active/running with the same PID and zero restarts; boot enablement remains
disabled. The approved Sat client has not yet performed an authenticated
challenge, so service liveness does not release any thermal question, listener
or journal write. The host user's default `nak` key is not the allowlisted
Sat-client key.

A fresh signer-free read-only kind-10050 check later September 29 found the
operator's exact signed route on all three approved relays and Hex's exact
signed route on Primal and Damus, but not nos.lol. Hex's event was nearly six
days old. The exact already-signed public Hex event was fetched, signature,
author and relay-set verified, then republished to nos.lol without loading a
private key; a fresh query returned the identical signed event. The relay's
reason for dropping the event is unknown. Recheck both identities on every
approved endpoint immediately before any attended household trial, and do not
infer long-term retention from this one readback.

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
