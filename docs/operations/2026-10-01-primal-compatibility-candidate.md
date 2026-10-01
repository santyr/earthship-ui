# Primal-compatible thermal confirmations — October 1 source candidate

## Scope and release boundary

`openhab/scripts/thermal_nip04.py` implements authenticated NIP-04 message and
question/reply primitives, a separate private original-cipher ledger and gated
journal ingress. It is **not yet a deployed sender or collector**.
`PRIMAL_RELEASE_READY` remains false and ingress refuses before dependencies
or writes. Low-level ledger preparation can write its explicitly supplied
private SQLite database; it is not a service or release. There is no CLI,
network connection, scheduler or actuator call in this module. The
existing NIP-17 delivery intents, runtime scripts, release flags, installed
signers and operator bunker are unchanged. No live question or DM was sent.

The operator explicitly approved preparing Primal compatibility after reporting
that the September 30 NIP-17 test did not arrive. This is an explicit separate
transport candidate, never an automatic downgrade of an existing NIP-17 intent.
NIP-04 is deprecated and exposes sender/recipient metadata without NIP-17's
gift-wrap privacy or forward secrecy. See the [official NIP-04
specification](https://github.com/nostr-protocol/nips/blob/master/04.md).

## Authenticated message and question binding

- Outbound plaintext is bounded UTF-8, passed only on stdin to an explicitly
  SHA-pinned signer. An unsupported signer refuses; there is no positional
  plaintext or implicit identity fallback. Signed kind-4 readback must match
  the requested author, recipient, creation time and ciphertext exactly.
- Inbound messages require the configured recipient and explicit authorized
  authors. Original kind-4 hashes and signatures are checked before decryption.
  The original signed ciphertext bytes and event ID remain the reply identity;
  the candidate never manufactures a kind-14 event or signature for cleartext.
- Question text retains the canonical policy's exact window/skylight/action
  states and includes its full 64-character question reference. Accepted text
  is `yes <reference>`, optionally with a verified local/offset time,
  `not yet <reference>`, or `skip <reference>`. Bare or ambiguous replies,
  another operator/question, future messages, expired questions, and claims
  received after expiry are refused. Existing Mountain/DST-aware time parsing
  is reused. A chat recollection is not a training label.
- The reference is the canonical thermal question ID, **not** the encrypted
  kind-4 wire event ID. Native `e` context is accepted only when it names the
  exact retained and reverified outgoing wire event for that question. Unknown,
  contradictory or duplicate native context is refused. Bare replies still
  do not select a question; the explicit full question reference is required.
- Authenticated cleartext is an in-process result, not an independent signed
  artifact. Recovery must reverify/decrypt the preserved original event; it
  must not trust mutable archived cleartext as operator evidence.

## Stdin-capable signer candidate

The installed `nak` v0.20.7 NIP-04 encrypt command accepts plaintext as a
positional argument and does not consume stdin. The real stock-binary test
refused the candidate's `--stdin` invocation. The upstream source is
[`encrypt_decrypt.go` at tag v0.20.7](https://github.com/fiatjaf/nak/blob/8b1c3c9403d5fdce9f8e7c77b6d6fc6f1b86302c/encrypt_decrypt.go),
commit `8b1c3c9403d5fdce9f8e7c77b6d6fc6f1b86302c`.

`deploy/nostr-bunker/nak-nip04-stdin.patch` adds an opt-in `--stdin` flag to
encrypt/decrypt. It requires NIP-04 and no positional input, accepts only
1–65,536 bytes, and preserves input exactly. Existing positional, NIP-44 and
bunker code paths are not changed. Errors do not echo the supplied input.

The candidate was built in a task-owned private temporary directory using the
already-present Go 1.25.8 toolchain, `GOTOOLCHAIN=local`, `GOMAXPROCS=2`,
`go build -p 2 -trimpath`, and isolated module/build caches. No system toolchain
or package was installed. Its version is `nak version debug`, **not** a newly
qualified production release. Module checksums verified; `gofmt` had no diff
and reverse patch dry-run confirmed the patch applies to that exact source.

| Artifact | SHA-256 |
| --- | --- |
| Upstream `encrypt_decrypt.go` | `9359f1eb4b17f034d34a7f568314acf161cac4ffa4ca139d48f05bd3044ad2ad` |
| Patched `encrypt_decrypt.go` | `a5a950ff99f7ced7bf4602b909cb02f32ba61fdcdd4904c73654cbec459e1753` |
| Patch | `57002bb0e7d11707e496594ba2f49b970caf532b1e509dd3f758222d729ab297` |
| Unchanged `go.mod` | `dfb500342a7ad68629ab74ce361f2731980fb6146ffc1996298f5a99ab8f655f` |
| Unchanged `go.sum` | `af1ab416ef708ac310cae4d66980c1e05632d5ab9f1b5b73c4e006e65551727c` |
| Isolated `nak-stdin` build | `f1207759c8c7a238ee695451dc29155a128eba5fb8ccfef08396e5bbc46ce802` |
| Initial Python primitives at `6e20d01` | `9ad86ad3a031cf64d3e5d5d519b9aa1fcb72acda92fcd671cf9ca9a602fa2f1f` |
| Both unchanged installed `nak` binaries | `ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e` |

The installed binaries are `/home/sat/.local/bin/nak` and
`/usr/local/libexec/nostr-bunker/nak`. Neither was replaced, repinned or restarted.
Temporary source, binary and caches must be removed after terminal tests; this
digest describes a qualification build, not an installed runtime artifact.

## Qualification

`tests/completion/test_thermal_nip04.py` uses real crypto only when explicitly
given `EARTHSHIP_TEST_NAK` and `EARTHSHIP_TEST_NAK_SHA256`. It clears inherited
credentials, relay/proxy and database variables and uses known disposable
private scalars 1 and 2. There are no household identities, relay connections,
operator bunker calls, journal writes, or live release flags in these tests.

Coverage includes exact signed/ciphertext identity, multiline plaintext,
signature/hash/ciphertext/author/recipient/kind tampering, an actually signed
malformed cipher, wrong signer, invalid or excessive cleartext, question
binding, all three dispositions, verified earlier time, future/expired and
ambiguous replies, native-context refusal, argv/environment boundaries, and
closed-gate behavior. The stock installed signer test refuses safely.

The existing eight disposable NIP-17 qualification checks also passed against
the isolated build: authenticated round trip, outer ID/signature, forged seal,
seal-content binding, raw-author mismatch, corrupt cipher and wrong recipient.
Only that in-process test's expected version was set to `nak version debug`;
production pins and the qualifier source were not changed. This is regression
evidence, not qualification of remote NIP-46 encryption/decryption.

The broader suite also exposed private-umask-sensitive **negative permission
fixtures**. They now explicitly chmod their test-only directories to 0755,
so world-readable refusal is exercised even under umask 077. Another stale
persistence fixture now includes the already-deployed runtime evidence Item's
explicit persistence group. Production persistence and permission policies
were not changed. The existing cached `websockets` package is supplied on the
test PYTHONPATH rather than installing a new runtime dependency.

The focused final permission/real-crypto run passed **50 tests**. The final
broad run over `openhab/scripts`, `scripts`, and `tests/completion` passed
**2,935 tests and 74 subtests**, with six explicitly skipped optional
integration cases, in 142.01 seconds under umask 077. The exact isolated
signer pin above was supplied, so the new crypto cases were executed rather
than skipped. Bytecode and pytest cache were disabled. These results do not
prove a live Primal journal/relay path or full PostgreSQL recovery.

## Durable original-cipher and journal candidate

The subsequent source extension uses **`primal.sqlite3`**, schema version 1,
in an explicitly supplied owned, mode-0700, non-symlink directory. Its database
is owned mode 0600, SQLite synchronous FULL, with foreign keys enabled.
Existing NIP-17 databases are not opened, migrated or relabeled. Question and
reply retention is bounded to 4,096 rows each; retention exhaustion refuses
rather than deleting original evidence automatically.

The queue stores the exact canonical signed outgoing cipher, digest, wire ID,
operator/collector and canonical question snapshot before any future publisher
can use it. Signing authority, destination, original creation time and decrypted
content must match that exact question. Outgoing validation uses only the
collector's key and the operator's **public** key. Retrying a queue operation
does not generate or substitute a new random cipher. Readback rechecks the
original signature, digest, policy and cleartext; no relay publication exists yet.

Incoming signature/decryption and wire context are reverified on every receive.
First receipt time, original canonical signed cipher, policy snapshot, transport
and derived records commit locally before a journal side effect. A previously
accepted message can recover after question expiry using its original valid
receipt time; a newly arriving expired message cannot. Altered saved records,
question/cipher identity or withdrawn current policy are refused. Confirmed or
skipped questions are terminal; `not yet` does not fabricate an action.

`ingest_primal()` is gated before any dependency. Position vocabulary also
requires the existing exact v2 restricted-writer preflight **before spooling**,
including for negative replies. Confirmations use the actual signed kind-4
cipher as the PostgreSQL payload and `nostr:<original event id>` as the
idempotency key. The existing journal append/exact-readback path is reused.
Only successful readback permits committing the deterministic local receipt.
This local acknowledgement is **not yet encrypted/published to the operator**.

Corrections require an acknowledged original by the same operator, the same
action scope, and an unsuperseded target. Original parent ciphers, question
snapshots, first receipt times, records and acknowledgement contents are
reauthenticated rather than trusting mutable saved record IDs. Parent chains
are bounded to 32 and cyclic/missing chains refuse. No cleartext pseudo-event
or kind-14 hash is manufactured. Cross-transport correction migration is not
implemented; no existing NIP-17 question/intent may be silently reissued.

Current extended source SHA-256:
`d6396b756474b5444ec3248a26c2f5e0882eef1f3ce69d9a93e8e4c769adcfa6`.
The dedicated ledger suite passes **19 tests**, including real signed/decrypted
NIP-04 fixtures and an actual isolated PostgreSQL v1-to-v2 migration, restricted
writer audit, commit-before-readback interruption, expiry recovery, exact
original-cipher payload digest, duplicate refusal and real correction records.
All release changes and database writes in that test target only its disposable
database. Temporary storage/containers are cleaned after terminal runs.

For these tests, the unchanged pinned stock signer encrypts only public
synthetic fixture text on argv; this avoids rebuilding the unchanged backport.
**Production encoding still requires stdin and refuses stock `nak`.** No
household key, relay, operator bunker or live journal is used. The earlier
stdin-build tests above are historical evidence for the unchanged encoder, not
a claim that this ledger's entire live deployment is qualified.

The subsequent combined run over `openhab/scripts`, `scripts`, and
`tests/completion` passed **2,921 tests and 74 subtests**, with **39 skips**, in
153.02 seconds under umask 077. All 19 new ledger tests ran, including the
actual disposable PostgreSQL case. The skips are the previous six optional
integration cases plus 33 optional stdin-build cases: that initial temporary
binary was already removed after its earlier qualification. Those 33 cases
must not be reported as executed in this later run. Cached websocket support
was supplied on PYTHONPATH; no package or toolchain was installed.

## Remaining work before a live Primal collector

1. Connect the qualified original-cipher ledger/journal adapter to bounded kind-4
   publication, reply fetching, refusal backoff and encrypted receipt delivery.
   Preserve original intents/envelopes and require signed-route validation.
   Qualify publisher/poller deadlines, delivery retry, crash ordering and
   acknowledgement recovery; no silent NIP-17 reissue or cross-transport rewrite.
2. Select a distinctly versioned stdin-capable signer and qualify its exact
   runtime, including backward NIP-17/NIP-42 and any actual required NIP-46
   encrypt/decrypt path. Obtain exact narrow deployment approval; preparing a
   Hex sender must not silently replace or restart the operator's signer.
   Regenerate the consumer/runtime/recovery pins for the actual configuration.
3. Recheck signed routes and exact restricted journal access. Qualify stopped-
   writer full-bundle recovery against the real v2 configuration, including the
   original envelopes and new `primal.sqlite3` first-receipt ledger;
   journal-only restore or the older two-database bundle is not enough.
4. Review one truthful attended question and verify an authenticated Primal reply,
   resulting journal data and receipt. Confirm actual operator delivery, not
   merely relay ACK. Existing test non-receipt remains on record.
5. Only then release bounded collection through a user unit and verify natural
   receipts. Collection is not predictive-skill graduation or actuator authority.

The goal remains open. These primitives are a prerequisite, not a substitute
for end-to-end collection, thermal accuracy or the wider Earthship/OpenHAB work.
