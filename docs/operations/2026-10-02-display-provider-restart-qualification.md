# October 2 production display-provider restart qualification

The existing production JVM started at **07:25:20 MDT / 13:25:20Z**,
PID **1696**. This audit did not restart, pause, run or edit a production
service/rule, post any state, issue a command or change privileges. It used
GET/SELECT-only checks, including one narrowly scoped privileged read that
reported only whether three exact rule IDs remain in the managed store.

## Four completed display gates

At `2026-10-02T21:48:32.091057Z`, the independently checked source files
still existed before this JVM start, match their canonical bytes/pins, and
are not symlinks. Each rule is uniquely file-owned, IDLE/NONE, has its exact
original trigger, no conditions and one JS action. No managed-store entry
exists for any of these three rule IDs. Item types and current values match
their unique JDBC mappings. These are display-resource checks, not a claim
about protected-control or whole-install restoration.

| Resource | Exact source SHA-256 | Post-restart evidence |
| --- | --- | --- |
| `DaysUntilNextSeason` Item | `56b31562a03c03f8a95e0190ef3caf80fc6c12b61c3ab45d96bbd189461906e9` | Sole unlinked file Item; original definition/metadata preserved; Item 176 prefix identical |
| `update_days_until_season` rule | `d101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36` | Exact `Sun_TimeLeft` change trigger; natural file-attributed countdown |
| `temp-highlow-24h` rule | `4c6c32a4847c93792f9748028ad8d53ac7116bc837a385544b7523fcd5c62297` | Exact 15-minute trigger; naturally posts all four extrema |
| `hex_btc_24h_change` rule | `41893bdbd9eeefb60fab2ffa5bbe12c49ebc1c0f09e91176d285c02d9d719391` | Exact price-update trigger; natural file-attributed output and JDBC Item 139 |

The retained countdown cutover is
`/home/sat/.local/state/openhab-config-migration/season-countdown-item-20260930T012118Z`.
Its first **217** rows still match the original ordered CSV byte-for-byte,
SHA `e0bb2630eee9df6689ddf81f25a62b7ba19225b2a7011050ad86efe1c65a387a`.
Current history has **220** rows. At 14:51:27.280 MDT Astro naturally
changed `Sun_TimeLeft` from 6,912,000 to 6,825,600 seconds; at
14:51:27.289 the file rule changed the display from 80 to
**79 days until Winter**. Original JDBC persistence is
`2026-10-02T20:51:27.289278Z`, matching the current state. Restoration-only
and unchanged startup events are not counted as that natural receipt.

The 15:45 natural extrema timer logs both source calculations and all four
Item updates: indoor low/high **64.76/78.62°F**, outdoor **32.54/75.02°F**.
Mappings remain 178/179/180/181. Their unchanged lows retain earlier JDBC
change times; everyChange persistence does not make these values stale.
At 15:48:26 the Bitcoin file rule naturally posts
`-0.03548490117455023%`; Item 139 persists it at
`21:48:26.261137Z`, matching independent current readback.

Exactly these **four** manifest entries move from `provisional` to `verified`.
Private rollback copies are retained. No ownership/provider or executable
production change is performed by that status promotion.

## Verifier defect fixed, regression-first

The existing countdown Item adapter's `rule_idle()` incorrectly required
`privId=i0`. After the actual JVM restart, unchanged pinned source registers
as `i4`; extrema and Bitcoin use `i3` and `i2`. These runtime registration
IDs changed independently of the pinned source. New no-network tests first reproduced
the refusal; the helper now accepts only bounded `i`/digit IDs with the exact
singleton configuration key, while preserving UID, provider, IDLE/NONE,
trigger, one-action/no-condition, non-symlink and installed-source SHA checks.
The attended Item apply gate remains false. The completed season/extrema
rule handoff gates are also reclosed; all four rule-kind gates are now false.

All **91** affected migration, ownership and Moon-definition tests pass,
including **24** new countdown tests. Extra actions/configuration, wrong
triggers, unknown IDs, source drift, symlinks and a closed apply gate are
covered. Owned temporary fixtures are removed. Only the repository operational
helper changes; no scheduled production worker/rule is redeployed.

The first broad check stopped on the Moon protected digest mismatch before
mutation. A later display check stopped on the hardcoded registration ID,
and another on OS permissions reading the managed store. The latter was
resolved by the scoped read-only privileged check; no raw store was printed
and no validation gate was silently bypassed.

## Moon remains provisional: protected digest drift

Both Moon Item/link definitions, metadata, fractional unit, profiles and
current states match the cutover. The exact original JDBC prefixes remain:

| Item | Original rows | Preserved prefix SHA-256 |
| --- | ---: | --- |
| Phase 59 | 998 | `bf988fdf6e57c428eb5a1b2fbe77e33a994610df4bba7f1ca251d3981c39a965` |
| Illumination 41 | 136,511 | `96c53ecaa075bda1c8e4f61caec489d076bce3cc542ab60121996bc850aa51cf` |

There are no changed Item-definition fields, prefix keys or link profiles.
However, the broad Moon Group/Thing/protected-rule definition digest is now
`e1741940c5e9b2fb7418852cc86a7097badd9c9301f2ea704a15dd5cfc2483c7`,
not the cutover's
`91bf14c17c7f3b98b512bc5a55e709fb9d3e6b4718b99b9a6064f222b4be16b1`.
The proof helper verifies current protected rules are healthy, but that
does not explain the definition mismatch or authorize normalizing it away.
All four Moon ownership declarations stay **provisional**. Diagnose against
retained original definitions before promotion; do not infer control freshness
from a successful collector, fabricate a phase change, rewrite history or
request another whole-OpenHAB restart merely to retry this gate.
