# Primal-compatible thermal confirmations — October 1 source candidate

## Scope and release boundary

`openhab/scripts/thermal_nip04.py` implements authenticated NIP-04 message and
question/reply primitives. It is **not yet a deployed sender or collector**.
`PRIMAL_RELEASE_READY` remains false. There is no CLI, network connection,
scheduler, journal write, spool write or actuator call in this module. The
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
- The reference is the canonical thermal question ID, **not** the eventual
  encrypted kind-4 wire event ID. Native `e` reply context is currently refused:
  the durable outgoing wire-ID mapping needed to authenticate it is not yet
  implemented. Ignoring contradictory native context is not acceptable.
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
| Python primitive candidate | `9ad86ad3a031cf64d3e5d5d519b9aa1fcb72acda92fcd671cf9ca9a602fa2f1f` |
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

## Remaining work before a live Primal collector

1. Implement the durable kind-4 outbox/first-receipt adapter with original signed
   ciphertext IDs, transport provenance and exact canonical-question/wire-ID
   binding. Preserve existing NIP-17 rows. Qualify restart/crash/replay,
   deduplication, receipt-time expiry, corrections, journal writes and acknowledgements.
2. Select a distinctly versioned stdin-capable signer and qualify its exact
   runtime, including backward NIP-17/NIP-42 and any actual required NIP-46
   encrypt/decrypt path. Obtain exact narrow deployment approval; preparing a
   Hex sender must not silently replace or restart the operator's signer.
   Regenerate the consumer/runtime/recovery pins for the actual configuration.
3. Recheck signed routes and exact restricted journal access. Qualify stopped-
   writer full-bundle recovery against the real v2 configuration, including the
   original envelopes and first receipt ledger; journal-only restore is not enough.
4. Review one truthful attended question and verify an authenticated Primal reply,
   resulting journal data and receipt. Confirm actual operator delivery, not
   merely relay ACK. Existing test non-receipt remains on record.
5. Only then release bounded collection through a user unit and verify natural
   receipts. Collection is not predictive-skill graduation or actuator authority.

The goal remains open. These primitives are a prerequisite, not a substitute
for end-to-end collection, thermal accuracy or the wider Earthship/OpenHAB work.
