# Primal-compatible thermal confirmations — October 1 source candidate

## Scope and release boundary

`openhab/scripts/thermal_nip04.py` implements authenticated NIP-04 message and
question/reply primitives, a separate private original-cipher ledger, gated
journal ingress and bounded relay delivery/polling. It is **not yet a deployed
sender or collector**.
`PRIMAL_RELEASE_READY` remains false and ingress refuses before dependencies
or writes. Low-level ledger preparation can write its explicitly supplied
private SQLite database; it is not a service or release. Network methods
require the closed release gate. The separate `thermal_primal.py` command and
user-service templates are now source candidates, not installed services.
There is no actuator call. The
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
That initial temporary source, binary and isolated caches were removed after
terminal tests; this digest describes the earlier qualification build, not an
installed runtime artifact. The separately versioned candidate below supersedes
it for the next deployment qualification.

### Distinctly versioned sender qualification — October 1

The exact same upstream revision and reviewed stdin patch have now been built
as **`nak version v0.20.7-earthship-nip04-stdin.1`**, with SHA-256
`2620c86f7a2b466a41977ae7e318d1810c727503deaf53ea1c76a5ac24e6f927`.
The original/patched Go and unchanged module-file digests above still match.
`gofmt` has no diff, reverse patch dry-run passes, and `go mod verify` reports
`all modules verified`. Only checksum-verified, pinned upstream dependencies
were fetched. The existing Go 1.25.8 toolchain and ordinary module/build caches
were reused instead of installing a toolchain or recreating isolated caches.

The build used `GOTOOLCHAIN=local`, `GOMAXPROCS=2` and:

```sh
go build -p 2 -mod=readonly -trimpath \
  -ldflags '-X main.version=v0.20.7-earthship-nip04-stdin.1' \
  -o /absolute/task-owned/path/nak-stdin
```

`scripts/qualify-thermal-nak.py` now accepts an explicit `--expected-version`
**only with an explicit `--sha256`**. Its default stock version and architecture
release pins are unchanged. The candidate cannot pass as stock v0.20.7 and a
version override cannot bypass independent byte/permission checks. Two new
unit regressions first failed without the option and pass after its addition.

The focused run passed **59 tests in 23.49 seconds**, with the exact candidate
pin supplied. This includes the earlier stdin crypto cases, all eight existing
NIP-17 authenticated-envelope checks, the actual Primal command's NIP-04 and
NIP-17 local self-roundtrips, and real loopback NIP-42 challenge/signature/OK/
resend checks with both explicit authorization and refusal. Disposable fixture
keys only are used in these tests. They are not public relay delivery evidence.

A separate sanitized inspection of the **actual existing Hex sender** confirms
it uses a local hex private key, not a NIP-46 connection. The new candidate
passed actual local NIP-04 stdin and NIP-17 self-roundtrips under the configured,
approved Hex collector public identity. There were **zero journal writes and
no publication**; the operator bunker was not accessed. Consequently remote
NIP-46 encrypt/decrypt is not required for this selected Hex sender path, and
is **not claimed as qualified** for the candidate. The operator's independent
NIP-46 service remains active, enabled and at zero restarts, using its original
unchanged stock binary/pin; its earlier challenge remains separate evidence.

Actual installed-path/dependency/configuration and full household-bundle
recovery still precede any truthful Primal question or collection release.

### Approved additive signer installation

The operator approved installation of this separate Hex signer only. The exact
artifact is now installed at:

`/home/sat/.local/libexec/earthship-thermal/nak-v0.20.7-earthship-nip04-stdin.1`

It is owned `sat:sat`, mode 0755, under newly created owned mode-0700 `libexec`
and `earthship-thermal` directories. The target was new; installation guarded
against overwriting an existing target. Installed SHA/version match the selected pin above;
the installed-path CLI qualifier passes all eight disposable NIP-17 checks.
The same focused stdin/command/NIP-42 suite passes **59 tests in 23.72 seconds**
using this installed path. No unversioned alias or default signer pin changed.
The configured Hex identity also passes both-protocol local self-roundtrips
under this **installed path**, with zero journal writes/publication and no
operator-bunker access, not only under the earlier build fixture.

The complete discovered Python suite, with the exact candidate pin explicitly
supplied, passed **3,014 tests and 74 subtests**, with **six optional integration
skips**, in 239.58 seconds. The 33 stdin cases skipped in the preceding suite
now execute, as do the five new exact-candidate integration cases. The real
disposable PostgreSQL ledger/full data restore cases also ran; no test container
remains. Private umask and disabled bytecode/pytest caches were retained.
After all build/test/self-check handles were terminal, five remaining explicitly
validated task-owned source/build/test directories were removed. The single approved
installed signer, ordinary dependency caches and operational backups remain;
there is no leftover second qualification binary.

Both original stock signer hashes are still `ba918faf...ae56e`. The operator
bunker remains active/enabled with zero restarts. `thermal-primal.service` and
`.timer` are still **not found/inactive**, not merely disabled. Installation did
not deploy a collector command, provision its credentials, enable any release
flag, publish a DM or create a live Primal ledger. It closes the separate signer
installation/qualification gate, not collector deployment or household recovery.

The byte/version qualification can be rerun without household credentials:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-thermal-nak.py \
  --nak /home/sat/.local/libexec/earthship-thermal/nak-v0.20.7-earthship-nip04-stdin.1 \
  --sha256 2620c86f7a2b466a41977ae7e318d1810c727503deaf53ea1c76a5ac24e6f927 \
  --expected-version 'nak version v0.20.7-earthship-nip04-stdin.1'
```

The exact private runtime/dependency/configuration bundle and stopped-writer
household journal recovery remain next. Only after those gates and truthful
question review may a separate attended Primal delivery/reply trial proceed.

### Approved inactive collector runtime and configuration

The operator subsequently approved **inactive** collector staging, including
only the existing Hex sender and restricted journal credentials. A frozen nine-
file collector import closure is staged under
`/home/sat/.local/libexec/earthship-thermal/primal-v1/code`. It does not modify
`/home/sat/openhab/scripts`, Solar_PV, the operator bunker or any model unit.
`scripts/thermal-primal-runtime.py` stages only new private destinations and
verifies an independently selected code-manifest SHA, exact file inventory,
Python syntax, private deployed files and six explicitly false collector/write/
migration gates. It does not qualify dependencies, credentials or release by
itself. Its private environment writer permits only seven reviewed fields,
refuses control-character/extra-field injection and never overwrites a file.

The initial staging exposed a real policy contract issue: `Policy.load()`
required at least one question. Two regressions reproduced it. An explicit
`allow_empty=True` option now permits an empty **v2 only** inventory; ordinary
and legacy loaders still require questions. Only the Primal command opts in.
No old proposal, chat observation or invented state is inserted to satisfy
startup. The corrected inactive code was pin-checked before/after replacing
the first unactivated staging; its dedicated dependencies were preserved.

| Qualified component | Exact identity |
| --- | --- |
| Frozen code manifest | `bf452e146f9f7a6bd966caec92ec5f7dd9a68478b96970a3d4305e0aa3a48bcb` |
| `thermal_confirmation.py` | `5606352760ee7764d7e9f31cddae2719fe2921a2c9abc8555638e0893a5c5863` |
| `thermal_primal.py` | `b8ee94e6fa52bc3a33173a40a8de41922468d1cddc890e2d12a225e484c11d2e` |
| CPython 3.12.3 `/usr/bin/python3.12` | `e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f` |
| CPython 3.12/Linux x86_64 websockets 15.0.1 wheel | `64dee438fed052b52e4f98f76c5790513235efaa1ef7f3f2192c392cd7c91b65` |
| CPython 3.12/Linux x86_64 psycopg2-binary 2.9.10 wheel | `8cd9b4f2cfab88ed4a9106192de509464b75a906462fb846b936eabe45c2063e` |
| Dependency requirements | `47e6e9d583d0e9431eb7bbbd4d3dc7350c496df6d6dae862e44d6e628181bcba` |
| Empty policy | `ec1709334d30244162d46fd5f15758f5f66f2c9857095e5bb42f8c7f41c9b76a` |
| Signed routes | `5860ad656eef83f603f470cfc1d673d7666daef32e1579ef2bc5456f6a897604` |
| Updated uninstalled user service | `5e167f5a6947c3997b70c176b9ff8c7e226f5c0b19503cb10d6f0a6b51631edc` |

The private dedicated `venv` contains only the two pinned dependencies; system
websockets remains 10.4. Wheel hashes came from primary PyPI release metadata;
download and installation used `--require-hashes`, binary-only/no-dependency
selection and offline installation from the retained two-wheel directory.
These wheels are recovery inputs, not abandoned test artifacts. The user-service
template now targets this virtual environment/code closure rather than system
Python and shared OpenHAB/Solar_PV imports; it remains uninstalled.

The new `/home/sat/.config/hex/thermal-primal/` is mode 0700 with mode-0600
`policy.json` and `routes.json`. `/home/sat/.config/hex/thermal-primal.env` is
mode 0600 and contains only the reviewed seven fields. No operator private key,
Sat client key, unrelated token or administrator credential is copied. The
restricted journal role/owner are bound from a read-only connection and exact
v2 fingerprint audit. Credential values were neither printed nor committed.
Fresh public-only route verification returned both approved announcements from
nos.lol, preserving the exact three destinations; nothing was republished.

Four actual transient user processes passed under the template's principal
resource/security restrictions and were automatically collected:

| Check | Invocation | Result |
| --- | --- | --- |
| Exact private configuration/signed routes | `06bbea99133f4d688bb4bd897b95d953` | Exit 0, 424 ms, release false |
| Configured Hex NIP-04 stdin/NIP-17 self-roundtrips | `d3ce64d4280748c89e51fb22e8186067` | Exit 0, 1.819 s, no publication |
| New systemd environment and restricted v2 journal | `b24d560c923440969a803f8421428239` | Exit 0, 68 ms, exact fingerprint, read-only |
| Actual staged polling command with release closed | `ff101033e13843309fa71ab290ed10ae` | Expected exit 2, 53 ms, no state creation |

Thirteen frozen-code/environment guards and all 21 adjacent command tests pass
in 13.43 seconds. Actual deployed checks above use household identity/config
but no journal writes, relay publication, listener or question. No live
`thermal-primal` state directory exists; permanent service/timer remain absent.
The full stopped-writer recovery of **this exact configuration/runtime/signer**,
both future Primal databases and original household journal remains next. The
older v1 baseline or disposable v6 data test is not substituted for that gate.

The complete discovered Python suite passed **3,029 tests and 74 subtests**,
with **six optional integration skips**, in 240.45 seconds, with the actual
installed stdin signer pin supplied. All optional crypto cases execute. This
includes the 13 new runtime/environment guards and two explicit empty-policy
regressions; it is not proof of the outstanding exact household recovery trial.
After terminal results, remaining task-owned test/code-refresh fixtures were
removed, all four transient units read back `not-found`, and no disposable
PostgreSQL test container remained. The approved inactive runtime/private
configuration, two recovery wheels and existing operational backups are retained.

### Exact inactive household recovery — October 1, 11:58 MDT

The subsequent **inactive, empty-policy** same-host recovery rehearsal passed
against the actual staged runtime, configured Hex identity and restricted v2
household journal. A new empty baseline was initialized through the frozen
`PrimalLedger` and `PrimalOutbox` classes at
`/home/sat/.local/state/thermal-primal`; all seven application tables contain
zero rows. This is inactive preparation, not a listener or sending policy.
The earlier statement that no state directory exists describes the staging
checkpoint above, not this later baseline.

The retained private recovery directory is
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-10-01-primal-inactive`.
Its independently recorded `bundle-manifest.json` SHA-256 is
`4e99025c6652371cc51020be387bfd404481db33c4402f818f50d8985561dcc4`.
The outer manifest pins 25 files, with private directories/files and no
operator key, Sat client key or administrator credential:

- `data/`: explicit Primal v6 snapshot, both application databases, exact
  empty v2 policy and signed routes, original custom journal archive and its
  five-component manifest. The strict v6 inventory remains unchanged.
- `runtime/`: nine frozen source files and their independently pinned code
  manifest, both exact recovery wheels, hash-locked requirements and the
  separately qualified stdin signer executable.
- `credentials/`: only the already approved seven-field collector environment.
- `units/`: the two uninstalled user-unit templates.
- `platform.json` and `qualification.json`: same-host interpreter/signing
  anchors and sanitized observed recovery evidence. This is not an OS image,
  portable off-host recovery, reviewed sending policy or live-service release.

Production PostgreSQL remained read-only. Export used one repeatable-read
snapshot and ACCESS SHARE locks; no collector or journal-owner role sessions
were observed before/after. A second independent production read matched the
retained/restored rows. These checks do **not** claim that the whole PostgreSQL
cluster or all possible administrator writers were frozen.

| Original/restored table | Rows | Ordered CSV SHA-256 |
| --- | --- | --- |
| `action_events` | 10 | `7006a6beab68bca825a0cc787119b709a137198d4e9fd1be0f5c6f0bf46a0ad3` |
| `message_receipts` | 4 | `056d846d36b18745fe9da23d3552322af2301ffe3097c078690d39ebfc4a3309` |
| `mode_events` | 4 | `73f4a3a3445d91047886524f3a1a8cf040d526bac94af025c86a340c0642d966` |

Recovery rebuilt a fresh CPython 3.12 environment **offline**, from the retained
hash-checked wheels rather than copying the installed virtual environment.
Separate working copies of code, configuration, signer and both SQLite files
were reopened through the actual application classes. The recovered seven
environment values were parsed and compared without printing; probe credentials
were rebound to only the loopback disposable PostgreSQL database, restricted
role and default-read-only transactions. The backed-up production DSN was never
used for a restored writer.

The exact v2 fingerprint `f3e09cdd...` and all original ordered row digests
matched before any synthetic fixture insert. Restored configuration/signed-route
validation and configured Hex NIP-04 stdin/NIP-17 self-roundtrips passed without
publication. A closed-gate polling attempt exited 2 without creating its target
state directory. The current installed model consumer `7f57eb3f...` then passed
its separate six-observation fixture coexistence check **only in disposable
storage**, preserving legacy samples and one supported bucket. Those fixtures
were removed with the disposable database and are not household evidence.

The first rehearsal invocation `971c34ba1ce04decb81297de61b2211c` stopped because
Snap's Docker launcher cannot run under `NoNewPrivileges`. Two read-only Docker
metadata probes isolated this: the restricted launcher failed with the missing
capability diagnostic; the normal launcher succeeded. No container remained.
The retained snapshot was resumed, not overwritten or re-exported. Container
management used normal user-launch privileges; all restored collector probes
explicitly retained `PR_SET_NO_NEW_PRIVS`. The permanent collector template's
`NoNewPrivileges=yes` is unchanged.

The successful resume invocation `4b25a9b0a44546088ca0573b85b462ee` exited 0 in
4.829 seconds; qualification time is `2026-10-01T17:58:54.379622Z`. Both
disposable working storage and its exact owned Docker container were removed.
All four rehearsal/diagnostic user units subsequently read back `not-found`.
The approved inactive SQLite baseline and qualified recovery bundle are retained;
all six release gates remain false and permanent collector/timer remain absent.
Existing NIP-17 files and intents were neither opened, migrated nor reissued.

This closes recovery of the **actual inactive empty-question baseline**, not
recovery of a future reviewed question/received reply. Before that trial, retain
and rehearse the exact newly reviewed policy and preserve any new original
ciphertext/first-receipt state; do not substitute this empty baseline for it.
Truthful question review, authenticated attended Primal reply, and bounded
user-service release remain open. Off-host backups remain operator-deferred.

After the rehearsal, an independent verifier checked the externally selected
outer manifest pin, exact 25-file inventory, every retained byte digest/private
file mode and strict five-component Primal v6 manifest. The existing Primal/
legacy backup, explicit command and frozen-runtime regression set passed
**64 tests in 25.86 seconds**, with the exact installed stdin signer and dedicated
dependency path. This is a focused recovery rerun, not a new full-project suite
claim. Task-owned pytest fixtures and the temporary operational rehearsal script
are removed after terminal verification; qualified backups and inactive runtime
are retained.

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

Ledger-stage source SHA-256 at `30d51b0`:
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

## Bounded relay delivery and encrypted receipt candidate

The subsequent source extension adds `PrimalRelay`, `PrimalOutbox` and
`PrimalDelivery`. These are explicitly selected, gated classes, not a deployed
daemon. The existing NIP-17 transport remains kind 1059 by default; shared
relay hooks permit only the explicitly constructed Primal transport to use
kind 4. The Primal filter binds kind, approved authors, collector recipient
and an inclusive bounded time window. Actual signatures, recipient, author,
cipher dimensions, subscription identity and matching EOSE are verified.
Only a positive, matching relay `OK` records publication acceptance. This
does not establish human receipt. Existing explicit NIP-42 authorization is
reused; no authentication policy is expanded.

`primal-delivery.sqlite3` is a **second new private file**, using delivery
bookkeeping schema 3. It is separate from both `primal.sqlite3` and the older
NIP-17 `delivery.sqlite3`. Exact original signed ciphertext is committed before
publication, retained across retries/restarts and never replaced by fresh
random encryption on retry. Outgoing plaintext is not retained in this file.
Unsigned legacy delivery intents are refused. Each send rechecks the current
authority and original question or original receipt/journal readback.

Publication/fetching uses a shared 90-second coordination deadline with each
relay call capped at 45 seconds, bounded pages/frames/events and at most 16
delivery or ingress attempts per pass. Finite deadlines are validated before
connecting. Cryptographic and local storage operations retain their own
timeouts; this is not a claim of an exact 90-second whole-process wall limit.
Expired/withdrawn questions are withheld without consuming the send budget,
so a retained stale prefix cannot starve newer authorized messages. Evidence
is retained, not deleted to obtain progress.

Polling balances oldest/newest candidates across signed routes, deduplicates
original event IDs and uses durable refusal backoff. An accepted-ingress marker
is written only after original reply authentication, journal verification and
encrypted receipt queueing. A journal outage leaves the fixed original first
receipt time and retryable work; recovery after question expiry reuses that
first receipt without accepting a newly arriving expired claim. ACK recovery
queues an actual signed kind-4 encrypted deterministic receipt only after
journal readback. Its exact original ciphertext survives restart and is
reverified before publication. No NIP-17 intent is silently reissued.

The focused relay/ledger/existing-messaging run passed **115 tests in 42.83
seconds**. Two additional real-crypto loopback regressions reproduced stale
prefix starvation and then passed after its fix (**2 tests in 26.55 seconds**).
The coordinator tests use an explicit journal double; they do not replace the
19 ledger tests' actual disposable PostgreSQL evidence above. Real stock `nak`
signatures/decryption and synthetic fixture-only argv encryption are used;
this run is not fresh qualification of the removed stdin-build fixture.
No household key, public relay, live journal write or operator bunker is used.

The final **complete discovered Python suite** (`python3 -m pytest`, without
path restrictions) passed **2,939 tests and 74 subtests**, with **39 skips**, in
193.02 seconds under umask 077. All 18 new delivery tests and all 19 ledger
tests ran. The skips retain the same six optional integration and 33 optional
stdin-build cases described above; they are not claimed as executed. Bytecode
and pytest caches were disabled, cached websocket support was supplied on
PYTHONPATH, and no package/toolchain was installed. All owned temporary test
directories were removed after terminal results; the disposable PostgreSQL
fixture left no test container. Operational rollback/recovery backups remain.

Current candidate source identities:

| File | SHA-256 |
| --- | --- |
| `thermal_nip04.py` | `21439920b75d6d0de953a1cc34ba0ff6c9fb3f95452ce8259104d780b53555fd` |
| `thermal_messaging.py` | `ca066232487d2357611a535c03a4a305c1cffb1ce7ee739f8296942c22c0cffb` |

## Remaining work before a live Primal collector

The operator approved automatic follow-ups to recorded recommendations, at most
once per Mountain day, on October 3. The repaired recurring runtime, default-off
selector/reservation candidate and remaining integration/recovery work are
tracked in [recurring confirmations](2026-10-03-thermal-recurring-confirmations.md).
The permanent collector remains off; this approval does not reopen the completed
one-question trial or authorize another trial DM.

### October 2 approved one-question trial — authenticated and recovered October 3

After the operator reported sending the explicitly dated reply, the approved
bounded poll accepted one authenticated NIP-04 reply. Its first receipt is
`2026-10-03T14:02:23.796322Z`, public event ID
`66fd98c7bf7bfad7ae5041ee8f7d1c5732be43c3275b8c031a917f3249e980fe`.
The original encrypted event digest is
`5f42bc50bf00d23b56ecc02eaae3363b692192569e93115f0cecfff85a5ca207`.
Reopening the ledger revalidates signature, operator/collector identities,
original outgoing question and ciphertext, exact reply binding and first receipt
time. Independent read-only PostgreSQL readback matches the entire immutable
action and original-cipher receipt digest: `indoor_shade=closed`, effective
October 2 at 18:30Z (12:30 MDT), source `nostr_confirmed`, confidence 1. No
window/skylight state, motor report or percentage is inferred. Poll exit 3
reflects an unrelated deferred refusal and one relay failure, not rejection of
this accepted reply. Its acknowledgement was accepted on all three routes;
operator receipt of that acknowledgement is not claimed.

The stopped/absent collector units remain inactive. A complete private v6
snapshot captures both Primal SQLite databases, exact policy/routes and the
original PostgreSQL journal archive. At 14:12:09Z an actual cold copy reopened
the authenticated original ledger and signed route configuration, then restored
the archive to disposable PostgreSQL. All original row digests and schema match:
11 action events, five message receipts and four mode events. Exact action and
receipt readback passes in the cold restore and again in unchanged production.
No production SQL write, new DM, collector enable or household control occurs
in this verification. The owned container and cold temporary directory are
removed. Snap Docker cannot launch under `NoNewPrivileges=true`; that optional
setting was omitted only from this disposable verification unit, not from any
production service. Failed duplicate backup attempts are cleaned after retaining
the independently qualified point.

Retained recovery point:
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-10-03-primal-confirmed-94dea187`.
Trusted v6 snapshot manifest SHA-256:
`d42be04cf9a5c863fae8b91ea1b340311db2ccab385a5cfed525efa4c016c3b8`.
Frozen trial runtime remains
`129b950c4332bd47bc49fd6c829e0fd2119ee0f7e94c038dcd94036c1d1f5cd1`.
This closes the approved single-question Primal signed-ingress/journal/recovery
trial. Recurring collector policy, cadence and activation remain a separate
release; no chat recollection or unrelated refusal becomes a training label.
Earlier pending-reply checkpoints below are historical, not the current result.

October 3 operator-reported reply follow-through: the 12:54Z bounded poll
accepted zero replies; its next refusal retry is `2026-10-03T13:54:58Z`.
Separate metadata-only reads at 12:58–12:59Z found only the previously refused
October 2 21:01:57Z unrelated kind-4 message on nos.lol, zero kind-4 messages
on Primal, and no authenticated operator kind-1059 replies on either reachable
relay. Damus was unavailable. This does not prove the operator never sent a
message. No transport fallback, ingest, ACK or journal write occurred.
The ledger remains one question/zero authenticated receipts; recurring units
remain absent. The temporary diagnosis script was removed.

The earlier assistant instruction `yes <reference> 12:30` was incorrect for a
reply signed the following morning: shorthand means the signed message's local
date and is currently future-dated. For the reported October 2 action use
`yes <reference> 2026-10-02T12:30:00-06:00`. A local frozen-runtime parser check
maps that to October 2 18:30Z and refuses the shorthand at this checkpoint.
This format check is not an authenticated reply or training label; the original
question/policy and exact parser are unchanged.

October 3 10:37Z follow-through: the approved bounded poll completed (exit 3)
with `accepted=0`, `operator_read_verified=false`, one relay failure and one
withheld message. The existing refusal now reports `due=0`, `pending=1` and
`next_retry_at=2026-10-03T11:37:56+00:00`; respect that future deadline.
Independent read-only ledger counts remain one question and zero authenticated
receipts. Both permanent units remain not-found/inactive. Repeated trial
approval does not authorize a duplicate question or supply an action reply.

The operator personally reported closing all physical indoor shades at 12:30
MDT on October 2, reviewed the exact rendered question, and approved one
bounded Primal trial. The chat report is **not** a training label. Only an
authenticated operator reply bound to this question may supply the observation.
The question reference is
`9c1e75aed553ba10347cba03c63294d163a0e8b4bb2713e86d03952b6528a789`;
its sole state is `indoor_shade: closed`, issued at 19:12:46Z on October 2 and
expiring at 19:12:46Z on October 3. Windows, skylights, percentages, shade motor
reports and other states are not inferred.

Preflight discovered an actual default-sink initialization bug: the v2 schema
audit initialized the journal but left `action_factory` unset, so a subsequent
confirmed reply could not be stored. A new real-crypto/restricted-PostgreSQL
regression failed on that missing factory, then passed after initializing the
default `ActionEvent` alongside the default journal. Explicitly injected
factories remain unchanged. The relevant ledger/CLI/confirmation/recovery/runtime
slice passed **184 tests in 75.74 seconds**, with no skips. Corrected source
SHA-256 is `92d02c4b5e7e84faadb08b3f4208b3e16bbe48254f532eeef2c84830a4adf740`.
All repository release flags remain false.

A separate private nine-file trial runtime was staged at
`/home/sat/.local/libexec/earthship-thermal/primal-trial-20261002`, with manifest
SHA-256 `129b950c4332bd47bc49fd6c829e0fd2119ee0f7e94c038dcd94036c1d1f5cd1`.
Only `thermal_confirmation.py` differs from the frozen inactive baseline.
The original runtime, empty baseline policy, signer executable, credentials,
operator bunker and NIP-17 state were not replaced or migrated. Exact private
trial policy SHA-256 is
`ccf6466187cf4c5fbe29cda12218ae443af579bd08b1fc05af77e34abe14d010`.

Before sending, the changed-policy recovery rehearsal passed using the exact
trial policy, signed routes, both original empty SQLite databases and a fresh
read-only original-journal export. Both application database openers and exact
policy/route validation passed. Disposable PostgreSQL restore reproduces all
10 action, 4 receipt and 4 mode rows with the same ordered digests recorded in
the inactive baseline. A second independent household read also matches; no
synthetic fixture, journal label or production SQL write was added. The owned
container and temporary restore directory were removed. This retained delta
recovery point uses the separately qualified unchanged interpreter/dependencies
and the inactive baseline's pinned private credential file; it is not an
independent off-host or OS recovery image.

Recovery directory:
`/home/sat/.local/state/thermal-intel/collector-recovery/2026-10-02-primal-trial`.
Its `qualification.json` SHA-256 is
`69381086b50a13bb533a11bfbbfce1e2817f46963d1177c5c493bfff6b3ce122`.
The process-local attended helper opens only the Primal transport and v2-write
gates after exact runtime/policy/recovery/journal checks. It confines state to
this one question and never installs a unit/timer or enables migrations,
legacy polling, automatic question generation or household controls.

Current public signed-route readback matches both approved announcements on
nos.lol and Damus. Primal returned neither announcement; that is recorded as
missing readback, not signature failure or three-relay availability. Both
approved signed lists are verified and still name the same three endpoints.
The one-question send then exited zero: **3 relay acceptances**, no retries,
withheld intents or deferrals. Actual operator receipt and authenticated reply
remain pending; relay ACK is not delivery proof.

The original sent ciphertext, exact policy/routes and accepted-relay state are
retained in `post-send/` under that recovery directory. Its independently
recorded manifest SHA-256 is
`e39b2755a79eb174c231f9c53afc1ab33b258b11b87a18a5cc74f349e7d36e92`.
This is explicitly a v5 SQLite/config snapshot, **not** a new PostgreSQL
snapshot. Actual application reopening of live and retained state verifies
identical original question ciphertext and all three ACKs; both have zero
reply receipts. Preserve first-receipt/original-cipher and full journal state
after a genuine reply before considering recurring collection. Permanent
`thermal-primal.service` and `.timer` remain absent/inactive.
The first bounded inbox check accepted zero replies and reported one relay
failure (exit 3); no observation or ACK was written. This is a retryable relay
check, not operator delivery proof or successful end-to-end completion.

At the October 2 20:19Z follow-through, a single bounded poll against the same
frozen runtime and question again returned `accepted=0`,
`operator_read_verified=false` and `relay_failures=1` (exit 3). No replacement
question was sent. The transient unit completed; permanent Primal service and
timer both still report `LoadState=not-found`, `ActiveState=inactive`. This
does not identify which relay failed or prove operator non-receipt. Actual
receipt/authenticated reply remains the next trial gate.

The October 2 21:18Z forecast-work follow-through performed one further bounded
poll, preserving the frozen runtime and existing question. It returned
`accepted=0`, `operator_read_verified=false`, `relay_failures=1` and
`withheld=1` (exit 3), with one pending inbox refusal and next retry at
`2026-10-02T21:23:07Z`. No replacement question or recurring listener was
started. Post-check permanent service/timer states remain not-found/inactive.
This is an unresolved authenticated-reply gate, not proof of client receipt.

At the October 2 21:29Z checkpoint, a separate bounded **read-only** diagnosis
verified the same runtime/configuration pins, opened only readonly SQLite
connections, and fetched the approved operator's events since the original
question. nos.lol returned one previously refused event: its signature and
operator identity authenticate, but its decrypted content contains neither
the trial reference nor the required exact reply syntax. Only these booleans
and static validation categories were reported; no message text, ciphertext
or secret was emitted. Primal returned zero events; Damus fetch was unavailable.
The pending refusal therefore is **not a valid confirmation** of this question,
and a relay failure alone did not explain the withheld count. No syntax
relaxation, inference from an unrelated DM, journal/SQLite write, ACK, second
question or recurring listener occurred. The diagnostic unit completed
successfully; permanent collector/timer remain not-found/inactive. A genuine
authenticated reply binding this exact question remains required.

At the October 2 22:06Z approval follow-through, one bounded check reused the
original question and frozen runtime; it did not send a duplicate. It returned
`accepted=0`, `operator_read_verified=false`, `relay_failures=1` and
`withheld=1` (exit 3). The one pending inbox refusal has its next retry at
`2026-10-02T22:16:09Z`; this does not make it a valid confirmation. The transient
check ended, and post-check readback shows both permanent collector/timer and
the collected transient unit as not-found/inactive. No thermal observation or
household control was enabled. Actual authenticated reply remains required.

At the October 2 23:24Z bounded follow-through, the original frozen trial was
polled once without resending its question. It again returned `accepted=0`,
`operator_read_verified=false`, `relay_failures=1`, `withheld=1` (exit 3).
The single pending refusal's next retry is `2026-10-02T23:44:43Z`; it is not
an accepted action confirmation. The transient user unit completed and was
collected. Permanent collector/timer remain inactive, production OpenHAB
remains active at PID 1696, and no household control or thermal label was
enabled. Do not treat approval of the trial as an authenticated reply to it.

At the October 3 00:30Z checkpoint (October 2 evening MDT), one bounded poll
again returned `accepted=0`, `operator_read_verified=false`,
`relay_failures=1`, `withheld=1` (exit 3). The single pending inbox refusal's
next retry is `2026-10-03T01:09:29Z`. No duplicate question was sent, and the
transient check ended. Subsequent readback confirms the permanent collector
and timer remain not-found/inactive and OpenHAB remains active at PID 1696.
Neither trial approval nor the unrelated refused DM is a thermal observation.

At the October 3 02:16Z approval follow-through, a single bounded check waited
for the existing refusal retry deadline and reused the original frozen trial.
It returned `accepted=0`, `operator_read_verified=false`, `relay_failures=1`
and `withheld=1` (exit 3). The one pending inbox refusal next retries at
`2026-10-03T03:16:54Z`. No duplicate question was sent. Read-only SQLite counts
remain one question and zero reply receipts; permanent collector/timer remain
not-found/inactive, and OpenHAB remains active at PID 1696. This check is not
an authenticated thermal observation or evidence of actual operator receipt.

After that retry deadline, the October 3 03:17Z bounded check again reused the
same frozen one-question runtime without resending. It returned `accepted=0`,
`operator_read_verified=false`, `relay_failures=1`, `withheld=1` (exit 3).
The one pending refusal next retries at `2026-10-03T04:17:50Z`. Read-only ledger
verification still finds exactly one question and zero authenticated reply
receipts; permanent collector/timer remain not-found/inactive. No recurring
release, journal label or household command occurred. Do not poll before the
new deadline merely for an unchanged status or treat relay failure as proof
that the operator did or did not receive the original question.

The next due bounded poll ran at October 3 04:18Z. It again returned
`accepted=0`, `operator_read_verified=false`, `relay_failures=1`, `withheld=1`
(exit 3); the existing pending refusal now retries at
`2026-10-03T05:18:18Z`. Read-only SQLite verification still finds one question
and zero authenticated receipts. The transient poll has ended and no transient
unit remains; permanent collector/timer are not-found/inactive. Production
OpenHAB remains active at PID 1696. No duplicate question, recurring release,
synthetic label or household command was issued. Do not poll before that next
deadline merely to restate unchanged status.

The latest due October 3 09:24Z bounded poll again reused the original frozen trial
without sending a replacement. It ended with `accepted=0`,
`operator_read_verified=false`, `relay_failures=2` and `withheld=0` (exit 3).
The one pending refusal remains due (`due=1`, `next_retry_at=null`). The exact
status query's null means no future refusal deadline, **not** exhausted retries
or a confirmed reply. With no new eligible receipt, make no further poll before
`2026-10-03T10:27:00Z` unless the operator reports a new reply; this is an
operational one-hour network retry interval, not a journal/policy mutation. Independent
read-only ledger verification still finds one question and zero authenticated
receipts; permanent collector/timer are not-found/inactive with no process.
Repeated approval of the one-question trial is not its authenticated action
reply. OpenHAB remains active at PID 1696; no journal label, recurring release
or household command occurred. Do not
poll again before that interval merely to restate unchanged status.

### Remaining recurring-release gates

1. Qualify the complete installed command/service bundle, dependencies, private
   actual configuration, source pins and rollback. Source command boundaries
   are now tested as described below. Preserve original intents/envelopes and
   require signed-route validation; no silent NIP-17 reissue or cross-transport
   rewrite.
2. The distinctly versioned stdin-capable local Hex signer is now separately
   installed and qualified as described above, including backward NIP-17 and
   loopback NIP-42. This actual sender does not use NIP-46; remote candidate
   compatibility is not claimed. Do not replace/restart the operator's signer.
   Still regenerate the consumer/runtime/recovery pins for the actual installed
   command/dependency/private configuration bundle; a signer alone is insufficient.
3. Signed routes, restricted v2 access and exact inactive household baseline
   recovery now pass as recorded above, including runtime/dependencies/signer,
   selected private credentials and both new Primal databases. Retain/rehearse
   the exact newly reviewed truthful trial policy before sending; preserve all
   new original envelopes and first-receipt/ingress state after a real trial.
   Neither this empty baseline nor a journal-only/older two-database restore
   qualifies a later changed operational configuration.
4. Review one truthful attended question and verify an authenticated Primal reply,
   resulting journal data and receipt. Confirm actual operator delivery, not
   merely relay ACK. Existing test non-receipt remains on record.
5. Only then release bounded collection through a user unit and verify natural
   receipts. Collection is not predictive-skill graduation or actuator authority.

The goal remains open. These primitives are a prerequisite, not a substitute
for end-to-end collection, thermal accuracy or the wider Earthship/OpenHAB work.

## Explicit command and disabled user-service candidate

`openhab/scripts/thermal_primal.py` connects the bounded classes without any
automatic protocol fallback. Mutating modes (`--send-prompts`, `--process-reply`,
`--poll-replies`, `--flush`) check `PRIMAL_RELEASE_READY` before reading private
configuration, invoking a signer, creating a lock or opening state. No CLI flag
can enable that gate. Private policy/routes require owned private parents and
explicit absolute non-symlink paths. The policy must use position vocabulary
v2. Signer path, SHA-256 and exact version string are explicit requirements;
there is no default identity, signer or plaintext-on-argv fallback.

`--check-config` validates public signatures on the complete signed route
inventory and the private v2 policy without signing, connecting to the journal,
opening state or publishing. It explicitly reports that signer identity is
**not** verified. `--check-keyer` performs local NIP-04 stdin encryption,
signature/readback/decryption and independent existing NIP-17 self-roundtrips
for the configured collector. It publishes nothing and cannot count as an
operator's confirmation. Stock installed `nak` refuses this check because its
encrypt command lacks stdin support. A separately qualified signer is still
required before live use.

Mutating commands repeat that identity preflight, check exact restricted v2
journal storage **before creating state**, hold the shared state lock, then
open only `primal.sqlite3` and `primal-delivery.sqlite3`. Their complete operation
order is selected input/queue/poll, receipt recovery, then bounded flush. Only
reviewed active questions can be queued; polling never generates new questions.
Delivery authority and incoming receipt times are not frozen at command start.
The delayed-expiry regression reproduced an expired send and passed after
removing that frozen timestamp from polling/recovery/flush calls.

Exit 0 means the selected bounded pass had no withheld/retry/deferred work,
not human receipt or predictive skill. Exit 2 is refusal/withheld work; exit 3
is incomplete/retryable/deferred work. Diagnostics are fixed sanitized messages
or status counts, never encrypted event bodies, plaintext, credentials or relay
responses. Even rejected command arguments are not echoed.

`deploy/thermal-primal.service` and `.timer` are **uninstalled user-level
templates**. The oneshot polls the explicitly reviewed policy and recovers/
flushes existing work; it does not run `--send-prompts` or create a policy.
The timer waits five minutes after service inactivity, avoiding overlapping
passes. The service has private umask, no-new-privileges, address-family limits,
192 MiB memory limit, lower CPU priority and a 360-second process timeout;
timeout kills the full control group, including signer children. A private
`thermal-primal.env` provides exact sender pins and restricted credentials.
The companion `.env.example` contains placeholders only. Runtime Python,
Solar_PV reader, psycopg2 and websocket dependency qualification remains open.
Do not enable the timer merely because its syntax validates.

Nineteen focused command tests passed in 12.46 seconds, using real disposable
signature/route validation and explicit doubles only for external journal,
network and the unavailable stdin encoder. They cover release refusal before
dependencies, public-only checks without an identity, invalid signatures/
permissions/version/legacy vocabulary, stock-signer refusal, secret-safe
argument errors, durable retry, original-cipher journal/receipt ordering,
identity/journal/lock/missing-event startup failures, delayed expiry, and actual
default-off subprocess execution. These are not live transport qualification.

`systemd-analyze --user verify` accepts both templates. One real transient user
unit (`earthship-primal-refusal-20261001`, invocation
`47d6ffb9b1d34380b0797aa64398fef2`) executed the candidate with the gate closed
and the template's principal resource/security restrictions. It terminated
with the expected status 2 in 46 ms without creating its supplied state
directory. The transient unit was automatically collected; no permanent unit
or timer was installed/started/enabled. No credentials, journal access, network
request or household DM was needed for that check.

Source identities at this checkpoint:

| File | SHA-256 |
| --- | --- |
| `thermal_primal.py` | `f3311bee325a2743eed58bcea030db305e756acf44c0ce66284655211a453f38` |
| `thermal-primal.service` | `9555f98b5f4f04be5343da33dcb2472c457d5afe2549a050d0d764cc38c30dec` |
| `thermal-primal.timer` | `22cff438f779645a397c789a5641bb0b3cd728a14085c936c96a44228c0c1f23` |
| `thermal-primal.env.example` | `45b139cb9140c3b963fefe7171ccc1d3933cfc68dabb45d1a7cbcaf19c392de5` |

Stopped-writer recovery must include both new databases, the exact private
policy/routes, the original PostgreSQL journal and the selected code/signer/
dependency identities. The old two-database baseline does not prove this.
No operator-bunker binary, allowlist, service or credential was changed.

The complete discovered Python suite subsequently passed **2,958 tests and
74 subtests**, with the same **39 optional skips**, in 212.21 seconds. All 19
new command cases, 18 relay/delivery cases and 19 ledger cases executed. The
optional stdin-build fixture was not recreated and those 33 crypto cases are
not claimed as executed in this run. Private umask and disabled bytecode/cache
were retained. Task-owned fixtures were removed only after terminal results;
no disposable PostgreSQL test container remains. Operational backups are
unchanged. This closes source command regression, not installed/live release.

## Explicit Primal data snapshot and full disposable restore

`thermal_state_backup.py` now supports explicit `transport='nip04'` or CLI
`--transport nip04`. Creation still defaults to NIP-17; its original database
names and manifest versions 1–3 are unchanged. Primal never auto-detects,
migrates, deletes or relabels the older NIP-17 state. If both transports' files
exist in a source directory, the explicitly selected pair alone is captured;
the older pair is unchanged and needs its own retained recovery point.

New manifest scopes are deliberately distinct:

| Version | Primal data captured | Does not establish |
| --- | --- | --- |
| 4 | `primal.sqlite3`, `primal-delivery.sqlite3` | Config or PostgreSQL recovery |
| 5 | Both databases plus exact private `policy.json` and `routes.json` | PostgreSQL recovery |
| 6 | Both databases, both configs, custom `journal.dump` | Runtime/signer/dependency recovery or live release |

The snapshot holds the same state lock as the Primal command, uses SQLite's
backup API, verifies integrity, writes private exclusive files and fsyncs its
manifest/directory. Missing, public, unknown-version or busy source state
refuses before destination creation. Primal roots must be absolute, owned
mode-0700 and non-symlink. A failure after copying starts leaves a private
incomplete destination for inspection, not a valid reusable recovery point.
No automatic pruning or overwrite is introduced.

Verification binds exact scope, filename set, digests, SQLite integrity and
recognized application schema versions (ledger 1, delivery 3). Unexpected files
are refused, not ignored. `verify_snapshot(..., transport='nip04')` and CLI
`--verify --transport nip04` additionally refuse another transport's scope.
Config capture is byte preservation, not itself signature/policy validation;
the real restore test reopens them through `Policy` and `Routes`. Keep a
separately trusted manifest digest and selected runtime/source pins for actual
household recovery; self-contained file digests alone do not authenticate a
recovery point.

The full PostgreSQL scope requires a caller-supplied custom archive exporter
while **all external journal writers are stopped/quiescent**. The filesystem
lock only covers cooperating commands in the selected state directory; it
cannot stop another journal process. The existing PostgreSQL archive inventory
check remains in force. This CLI does not silently generate or label a live
PostgreSQL backup from a SQLite-only request.

Thirty-five focused Primal/legacy/baseline checks passed in 12.55 seconds.
Sixteen are new Primal backup cases, including a real five-data-file recovery
between two isolated PostgreSQL 16 databases. The test uses actual disposable
kind-4 signatures/decryption, a v2 journal with restricted runtime role, a
repeatable-read exported snapshot, real `pg_dump`/`pg_restore`, and exact
table/schema proofs. It restores private SQLite copies into a separate working
directory, revalidates original signed routes/questions/replies and authorizes
the retained pending ACK against the **restored** journal after question expiry.

The original cipher/ID, original first receipt, accepted-route and retry state,
ingress marker, pending encrypted ACK and PostgreSQL payload digest remain
unchanged. Replaying the original reply after expiry adds no duplicate action:
all journal table counts/digests still match. This is an actual application
recovery check, not only SQLite integrity or archive-list inspection. Synthetic
keys and isolated databases only were used; the production journal, private
household recovery anchors, operator bunker and relays were untouched.

Backup source SHA-256 at this checkpoint:
`6c5aece9f0c189fcb9dbfb3b64cf2cc56cf7f97e983b1d20995e0f06417c409c`.
This closes source support and **disposable** full data recovery. Qualification
of the actual inactive household Primal configuration, original journal copy,
selected signer/dependencies and code bundle remains open before any live trial.

The complete discovered Python suite passed **2,974 tests and 74 subtests**,
with the same **39 optional skips**, in 230.79 seconds. All 16 Primal backup
cases executed, including the real PostgreSQL export/restore/application
recovery. The optional removed stdin-build fixture remains skipped, not
implicitly requalified. Bytecode/cache stayed disabled and umask private.
Task-owned temporary directories were cleaned only after terminal test results;
both source/restore disposable containers were removed. Retained operational
backups were neither modified nor deleted. No live service, release flag,
signer, journal, forecast or control changed.
