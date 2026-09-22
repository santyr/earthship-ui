# Thermal delivery validation receipt — September 22, 2026

Implementation: `f28a718de5d5bd4f1550caa86f9889528e9872b3`.
This receipt documents source/test evidence, not household deployment.

## Verified encrypted delivery qualification

Workflow `35746594942`, job `106809716521` (`encrypted-delivery`), was read
back as completed/success. Its real test receipt was emitted at
`2026-09-22T15:20:30.4899516Z`.

[Completed qualification job](https://github.com/santyr/earthship-ui/actions/runs/35746594942/job/106809716521)

The job downloaded the fixed upstream nak v0.20.7 Linux AMD64 release and
verified SHA-256
`ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e`
before executing it. It installed websockets 16.0 and ran in a disconnected
network namespace with only loopback enabled. Only disposable public test keys
were provided in a replacement environment. No household identity, bunker,
production PostgreSQL connection or external delivery route was used.

All eight real-binary/loopback checks passed:

- Configured signer signing/encryption/decryption self-check.
- Rejection when the expected collector identity does not match the signer.
- Verification of signed recipient relay announcements.
- NIP-42 challenge signatures verified by the local relay.
- Exact relay OK acceptance for the operator and sender copies.
- Both encrypted copies decrypt to the exact canonical question.
- An authenticated reply produces the expected encrypted storage receipt.
- Restarting the outbox does not republish already accepted events.

The journal in this particular test is explicitly in-memory. The result does
not claim PostgreSQL integration. It is separate from the existing real
PostgreSQL ingress tests. The relay is a real local WebSocket server, not an
external production relay. No cryptographic or WebSocket-client double was
used in this qualification.

Receipt scope: `real-local-key-and-loopback-relay`.
`status=passed`; `household_keys_used=false`;
`household_bunker_verified=false`; `journal_test_double=true`;
`production_journal_writes=0`; `external_relay_delivery_verified=false`;
`production_ready=false`.

## Local regression evidence

The 56 new delivery tests passed, including SQLite restart/retry, lost-OK
retransmission, atomic two-copy enqueue, withheld receipts on journal failure,
recovery of unacknowledged accepted input, policy revocation, prompt expiry,
route checks and actual loopback relay connections. Their cryptography and
journal boundaries are explicit test doubles. Together with the original 137
package cases, 193 tests passed in the local fixture.

The existing `thermal_confirmation.py` used by that fixture matched its current
upstream Git blob `a042fc90e9602e8bffbb530dd391f7e43d191eb5`. The new module,
tests and integration script uploaded to GitHub matched local blob hashes
`9a42d933dc1a1fb8aecb8497d1d02b0333000172`,
`3ccfc3e80b87560b9b07ea4e06da6d9c56288069`, and
`c9369125e2a44b8a7387ed3502c65c32231db388`, respectively.
The local fixture is not a full application checkout. Full application evidence
must come from the separate CI workflow, not those local case counts.

At this receipt's checkpoint, CI run `35746595291` for the implementation had
passed UI tests, the production build, completion regressions and the separate
nak-authentication job. Its longer OpenHAB Python suite was still running and
operational tooling was pending. Do not attribute a complete green CI result to
that checkpoint before reading the finished job. This follow-up is documentation
only and does not change the tested implementation or workflows.

## Remaining operational gates

The installed-binary authentication check is already complete; do not repeat
that prerequisite. Next use the configured-keyer self-check described in
[the delivery runbook](thermal-messaging-delivery.md). It deliberately tests
the actual selected keyer against the expected collector public key without
publishing the self-check or writing to the household journal.

Then qualify reviewed recipient routes and an attended genuine
question/reply/journal/acknowledgement flow. Bounded durable inbox polling,
retention/backups and scheduled service deployment remain to be implemented or
qualified. This commit does not enable any collector, alter household controls,
or promote the thermal model from shadow.
