# Upgraded household nak: reproducible authentication qualification

## Installation checkpoint: host local-key authentication passed

On September 22, 2026, Sat submitted the successful qualification receipt below
from `/home/sat/.local/bin/nak`. This supersedes the older installed v0.18.2
inventory and permission blocker in the ingress runbook. The reported v0.20.7
binary matches the official Linux AMD64 asset already tested in CI. Retain this
exact path and fixed digest; no separate filename or repeat inventory is needed
for this unchanged binary.

This is an operator-submitted host test result, not a remotely executed test or
signed machine attestation. The receipt does not supply its exact execution
time or checkout SHA; neither is inferred here. Its authentication scope is
complete, but its explicit production, bunker and delivery flags remain false.

### Operator-submitted receipt

```json
{
  "bunker_verified": false,
  "checks": [
    "valid_authenticated_roundtrip",
    "outer_id_tamper_rejected",
    "outer_signature_tamper_rejected",
    "forged_seal_signature_rejected",
    "seal_content_signature_binding",
    "rumor_author_and_id_bound_to_seal",
    "corrupt_ciphertext_rejected",
    "wrong_outer_recipient_rejected"
  ],
  "household_keys_used": false,
  "journal_writes": 0,
  "nak_path": "/home/sat/.local/bin/nak",
  "nak_sha256": "ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e",
  "nak_version": "nak version v0.20.7",
  "production_ready": false,
  "relay_delivery_verified": false,
  "scope": "disposable-local-key-authentication",
  "status": "passed",
  "version": 1
}
```

Accepted inventory for the tested authentication scope:

- Path: `/home/sat/.local/bin/nak`
- Version: `v0.20.7`
- Fixed SHA-256: `ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e`

Do not reuse the earlier v0.18.2 fingerprint, which remains refused. Changing
the binary requires renewed review rather than automatically trusting a freshly
calculated hash. This document does not change installed service configuration.

## Reproducing the host qualification

The operator has already run this successfully. Preserve the command for
reproduction after a relevant change, rather than treating it as an open task:

```bash
python3 scripts/qualify-thermal-nak.py --nak /home/sat/.local/bin/nak
```

This command needs only Python's standard library plus the installed binary.
It compares the executable to the fixed official v0.20.7 Linux AMD64 or ARM64
asset digest (according to the local architecture), checks safe permissions and
exact version, then generates genuine encrypted/signed messages with public
**disposable test keys**. It tests the eight cases in the receipt. A timeout is
an incomplete qualification, not successful rejection of a forged message.

No household key, bunker URL, OpenHAB token or PostgreSQL DSN is used. It creates
and removes temporary configuration, does not publish messages, and does not
install, chmod, activate services, create a production spool or write a journal.
The nak unwrap command may make read-only relay-discovery requests for the
public test identities; the CI invocation additionally disables all network
access using a separate network namespace. This is not a relay-delivery test.

Exit 0 prints a JSON receipt with the observed hash, version, path and passed
checks. Exit 1 means rejection or a failed assertion; exit 2 means an incomplete
run. A passing receipt still explicitly says `production_ready:false`,
`bunker_verified:false`, `relay_delivery_verified:false`, and `journal_writes:0`.
Those scope flags are not additional failed binary tests. Never share real
credentials as part of a qualification report.

A locally compiled or different release will not silently pass the official
asset pin. The `--sha256` override is for a separately reviewed v0.20.7 build;
it must be supplied deliberately, not automatically read from any installed
binary. Other versions require separate review and a test-harness update.

## Automation and CI evidence

The `nak-authentication` job downloads the fixed release asset, checks its
published digest before execution, and runs the same test in a disconnected
network namespace with disposable configuration. Missing tools, hash mismatch,
failed valid cases and timeouts fail the job; there are no skip paths.

The 17 harness unit cases exercise file checks, secret isolation, CLI failure
semantics and the distinction between refusal and timeout; they do not execute
nak or establish actual cryptography. The real-binary job supplies that evidence.

The preceding run `35736760129` passed 1,627 UI tests, the production bundle,
141 completion cases and the OpenHAB Python suite (1,206 passed, 15 skipped,
61 subtests passed). It then failed collecting operational tests due to missing
`openhab_sanity_check` and companion `earthship_energy` imports. The workflow
repair checks out Solar_PV at fixed revision
`d24771b77de540f32e592a7c44a0bff6385e8cd4` and supplies the two source paths only
for that test step. No tests were removed; this is not a household library upgrade.

### Verified real-binary result

At `2026-09-22T14:18:44Z`, run `35739410979`, job `106784921790`, at source
commit `486b867a74d260ae0f8e5347280c3b48537a5d67` completed successfully.
The actual Linux AMD64 v0.20.7 release binary matched the same SHA-256 as the
host receipt. All eight checks passed through the real `NakDecoder` and nak
subprocesses inside the disconnected network namespace. No cryptographic or
decoder double, household identity, or production journal was used in that job.

Evidence: [completed authentication job](https://github.com/santyr/earthship-ui/actions/runs/35739410979/job/106784921790).

### Broader run has now completed successfully

The previously pending `test` job `106784921523` in the same run was subsequently
read back as **completed/success**, as was `nak-authentication`. All recorded
steps passed, including UI tests, the production build, completion regressions,
OpenHAB Python tests using disposable PostgreSQL, and operational tooling tests.
This supersedes the earlier statement that the broader job was still running.
Existing host-specific skipped tests are not converted into passed checks.

Evidence: [completed test job](https://github.com/santyr/earthship-ui/actions/runs/35739410979/job/106784921523).

The documentation-only commit `f64ad1d` followed that tested implementation.
The client-key follow-up below is a new source change and requires its own CI
result; the earlier green run is not attributed to untested future code.

## Next integration fix: preserve the configured bunker client identity

The decoder previously forwarded `NOSTR_SECRET_KEY` to `nak gift unwrap` but
silently omitted `NOSTR_CLIENT_KEY`. In [nak v0.20.7](https://github.com/fiatjaf/nak/blob/v0.20.7/main.go),
the latter supplies the separate `connect-as` identity for NIP-46 communication.
Losing it could select nak's default client instead of the configured client.

The decoder now preserves a nonempty, explicitly configured `NOSTR_CLIENT_KEY`
only for the keyer-enabled unwrap child. Neither identity setting is passed to
`nak verify` or placed in command arguments. Database/OpenHAB credentials and
unrelated environment settings remain excluded. An absent client key preserves
the existing nak behavior; it does not become a new mandatory configuration gate.
The main signer/keyer setting remains mandatory and cannot be replaced by the
client key. No real bunker URL or key is embedded in the repository.

Ten new subprocess-boundary tests passed locally alongside the original 137
package regressions (147 cases in that local subset). The production module was
reconstructed against its exact current Git blob before editing. These tests use
an explicit subprocess double: they do not claim a live NIP-46 round trip. Full
repository and real-binary CI must validate this new commit independently.

## Remaining boundary

The installed binary's local-key authentication check is now complete on the
operator-submitted evidence. Do not leave the old build or permission repair as
an active blocker. Remaining work is actual bunker/keyer connectivity, encrypted
prompt/reply/acknowledgement delivery with reconnect/replay, restricted journal
integration on the host, and attended deployment. Genuine operator action and
temperature-outcome evidence is separate from test fixtures.

No production collector, control, service, model or database was changed here.
Journal replay, prompt binding, operator allowlist, old-build refusal, permission
checks and source/model release constraints remain unchanged.

Sources reviewed: upstream [v0.20.7 release](https://github.com/fiatjaf/nak/releases/tag/v0.20.7),
[tagged gift handling](https://github.com/fiatjaf/nak/blob/v0.20.7/gift.go),
[tagged encryption CLI](https://github.com/fiatjaf/nak/blob/v0.20.7/encrypt_decrypt.go),
[tagged signer settings](https://github.com/fiatjaf/nak/blob/v0.20.7/main.go)
and [NIP-59](https://github.com/nostr-protocol/nips/blob/master/59.md).
