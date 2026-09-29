# TP-Link switch evidence v2 observational cutover

At 04:50 MDT on September 29, 2026, the guarded adapter changed only the
managed `hex_tplink_switch_evidence` rule script from SHA-256
`e725970e0e47ee1c9108c8b1ab4203ea6568987379e5b27bd748defe772b3c1d`
to the reviewed v2 source SHA-256
`40b34d9b2afa3ce9451aecdf5b26aef3f46a85adda402cb6a0f7f6106f4466d9`.
Its read-only preflight confirmed the exact old rule, `IDLE/NONE`, six unchanged
triggers, and both source Things ONLINE. The adapter backed up the complete
old managed rule at
`/home/sat/.local/state/tplink-switch-evidence-release/v2-u61c2_2h/original-rule.json`
before disabling, replacing and re-enabling it. The backup directory and file
read back mode 0700 and 0600. Exact post-apply DTO and script-hash readback
passed; no OpenHAB restart or switch command was used.

The first natural v2 publication was sequence 1 with both fields unavailable,
establishing a new stream epoch. Binding-origin reports then restored both
fields: live sequence 3 was `valid/ok` with exactly 95,000 milliseconds from
original observation to `validUntil`. Strict parsing of the seven most recent
JDBC rows found old-v1 sequences 563–566, followed by new-v2 sequences 1–3
in a different epoch, without a sequence gap or unbarriered version change.
Both TP-Link Things remained ONLINE.

The v2 TTL addresses a measured normal source cadence of up to 90.054 seconds
while still expiring a source with no new report after 95 seconds. The reader
continues enforcing the original 90-second TTL for v1 receipts. A synthetic
complete day at 90.04-second cadence qualifies only under v2. Verification
before deployment: 29 focused reader/history tests, 1,840 UI/OpenHAB tests,
880 Solar_PV analytics tests using the candidate reader, and four cutover
adapter tests passed. These tests and first natural receipts establish the
versioned handoff, not a completed day or a physical network-fault trial.

September 29 is a mixed, partial day and is **not qualified**. Solar_PV's
opt-in switch-quality flags and daily publisher remain unchanged. The first
possible complete v2 Denver day is September 30, assessable after its midnight
on October 1; strict coverage, sequence, fault/restart and withdrawal/recovery
checks are still required before production quality publication. Earlier
v1 gaps must not be backfilled or relabeled.
