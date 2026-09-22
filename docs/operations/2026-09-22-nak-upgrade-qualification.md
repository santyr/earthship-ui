# Upgraded household nak: reproducible authentication qualification

## Installation checkpoint

Sat reports upgrading nak in place at `/home/sat/.local/bin/nak` and correcting
its permissions. Retain that exact path; a separate renamed executable is not
required. This supersedes the old installed-build inventory in the ingress
runbook. It is an operator report, not a remotely inspected version or new hash.
The earlier v0.18.2 fingerprint remains refused; it must not be reused as the
new binary's pin.

The candidate discussed with the operator is upstream v0.20.7. Its released
`gift.go` verifies the seal signature and binds the output rumor author and ID
to the authenticated seal author. Source inspection is distinct from executing
the binary with malformed messages and distinct from bunker qualification.

## One host qualification command

From an up-to-date earthship-ui checkout, run:

```bash
python3 scripts/qualify-thermal-nak.py --nak /home/sat/.local/bin/nak
```

This command needs only Python's standard library plus the installed binary.
It compares the executable to the fixed official v0.20.7 Linux AMD64 or ARM64
asset digest (according to the local architecture), checks safe permissions and
exact version, then generates genuine encrypted/signed messages with public
**disposable test keys**. It tests valid round-trip, tampered outer hash and
signature, forged seal signature, changed signed seal fields, spoofed rumor
author, corrupted ciphertext and wrong outer recipient. A timeout is an
incomplete qualification, not successful rejection of a forged message.

No household key, bunker URL, OpenHAB token or PostgreSQL DSN is used. It creates
and removes temporary configuration, does not publish messages, and does not
install, chmod, activate services, create a production spool or write a journal.
The nak unwrap command may make read-only relay-discovery requests for the
public test identities; the CI invocation additionally disables all network
access using a separate network namespace. This is not a relay-delivery test.

Exit 0 prints a JSON receipt with the actual observed hash, version, path and
passed checks. Exit 1 means rejection or a failed assertion; exit 2 means an
incomplete run. A passing receipt still explicitly says `production_ready:false`,
`bunker_verified:false`, `relay_delivery_verified:false`, and `journal_writes:0`.
Only the safe JSON receipt is needed for review; never share real credentials.

A locally compiled or different release will not silently pass the official
asset pin. The `--sha256` override is for a separately reviewed v0.20.7 build;
it must be supplied deliberately, not automatically read from any installed
binary. Other versions require separate review and a test-harness update.

## Automation and current evidence

The `nak-authentication` CI job downloads the fixed release asset, checks its
published digest before execution, and runs the same test in a disconnected
network namespace with disposable configuration. Missing tools, hash mismatch,
failed valid cases and timeouts fail the job; there are no skip paths.

Seventeen new local harness unit cases pass. These exercise file checks,
secret isolation, CLI failure semantics and the distinction between refusal
and timeout; they do **not** execute nak or prove actual cryptography. Read the
new CI job's result before claiming the release binary has passed. The actual
result is now recorded immediately below.

The preceding CI run 35736760129 passed 1,627 UI tests, the production bundle,
141 completion cases and the OpenHAB Python suite (1,206 passed, 15 skipped,
61 subtests passed). It then failed collecting operational tests due to missing
`openhab_sanity_check` and companion `earthship_energy` imports. The workflow now
checks out Solar_PV at the fixed revision
`d24771b77de540f32e592a7c44a0bff6385e8cd4` and supplies the two source paths only
for that test step. No tests were removed and production migration code was
not changed. This CI dependency checkout is not a household library upgrade.

### Verified real-binary result

At 2026-09-22T14:18:44Z, CI run `35739410979`, job `106784921790`, at source
commit `486b867a74d260ae0f8e5347280c3b48537a5d67` completed successfully.
The actual Linux AMD64 v0.20.7 release binary matched SHA-256
`ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e`.
All eight checks listed above passed through the real `NakDecoder` and real
nak subprocesses, inside the disconnected network namespace. No cryptographic
or decoder test double was used in that job. The temporary process environment
contained only disposable keys; the household identity and journal were unused.

This clears the tested release's local-key authentication compatibility gate,
not the household binary readback, bunker or delivery gates. The printed receipt
retained `production_ready:false`, `bunker_verified:false`,
`relay_delivery_verified:false`, and `journal_writes:0`. The broader test job
was still in progress when this result was recorded; this is not a claim that
the entire workflow passed. This documentation-only follow-up does not change
the tested scripts or workflow.

Evidence: [completed authentication job](https://github.com/santyr/earthship-ui/actions/runs/35739410979/job/106784921790).

## Remaining boundary

Even successful local-key authentication does not qualify the real bunker,
relay receiver, encrypted prompt sender or acknowledgement delivery. Production
activation and genuine operator action/outcome evidence remain separate tasks.
Existing journal replay, prompt binding, operator allowlist, old-build refusal,
permission checks and source/model release constraints remain unchanged.

Sources reviewed: upstream [v0.20.7 release](https://github.com/fiatjaf/nak/releases/tag/v0.20.7),
[tagged gift handling](https://github.com/fiatjaf/nak/blob/v0.20.7/gift.go),
[tagged encryption CLI](https://github.com/fiatjaf/nak/blob/v0.20.7/encrypt_decrypt.go)
and [NIP-59](https://github.com/nostr-protocol/nips/blob/master/59.md).
