# Thermal receipt-history integration

## Implemented source contract

Training and backtest CLI ingestion can now opt into `QualifiedTemperatureHistory`:

- Before an explicit five-minute-aligned cutover, use the existing numeric JDBC
  reader, clipped strictly before that boundary and identified as legacy.
- At and after cutover, air uses indoor235, north-wall observation uses193, and
  outdoor uses206. Every five-minute target is represented by its as-of qualified
  receipt value or an invalid marker. Numeric fallback is forbidden.
- Missing targets, including the first cutover target, remain invalid through
  dataset construction. Existing interpolation cannot fill them. Latent-mass
  estimation, physics/promotion gates and radiation handling remain unchanged.
- Each child reads at most one day using the restricted temperature reader role.
  Existing connection/query bounds remain; subprocess timeout is30seconds and
  the whole ingestion reader has a900second budget. Training range is capped at
  401days, covering the normal400day archive.
- New artifacts carry a closed `temperature_evidence` manifest: cutover,
  semantics, fixed identities/policies, legacy point counts, qualified/missing
  target counts and a canonical receipt-provenance grid digest per role. Target
  counts must match the actual post-cutover training range.
- Existing artifacts without this additive evidence field remain valid and are
  not reclassified as receipt-qualified. Runtime hashing and the receipt-bound
  deployment manifest include all new dependencies.

Other fields remain explicitly separate: this change does not establish receipt
health for glazing, optional living-office temperature or radiation. Current
shadow inputs still use their existing source path; their migration is outstanding.

## Activation contract

No runtime activation is included in this source change. The training service
needs a scoped drop-in supplying:

```
THERMAL_TEMP_QUALIFIED_ENABLE=1
THERMAL_TEMP_EVIDENCE_CUTOVER=<explicit elapsed UTC five-minute boundary>
THERMAL_TEMP_DB_CONFIG=/home/sat/.config/hex/weather-temperature-db.json
THERMAL_TEMP_POLICY=/home/sat/.config/hex/weather-temperature-policy.json
```

Absent opt-in preserves the current reader. Any explicit value other than1 or
invalid configuration refuses the qualified training path; it does not silently
fall back. No credential contents belong in the drop-in or repository.

Before release, recheck actual job inactivity, current source hashes, policy
identity and accepted-model hashes. Back up exact originals and install the
complete dependency graph without changing schedules or forcing a training run.
Verify installed restricted-worker reads and unchanged models before enabling
the training drop-in. The first naturally trained artifact must be checked for
real provenance and promotion evidence; installation alone is not learning proof.

For rollback, remove the activation override while retaining the compatible new
artifact validator. An old strict validator cannot read a newly produced artifact
containing `temperature_evidence`. Do not blindly restore old code or overwrite
new learned state from a release backup. Full code rollback requires an explicitly
selected compatible model and preservation of newer evidence.

## Verification

Twenty-two focused integration tests cover cutover, unchanged values, expiry/
missing barriers, no fallback, bounded requests, CLI wiring, source provenance
in candidates, artifact compatibility, malformed provenance, worker timeout and
total budget. Deployment/reader focused run passed105tests.
The final full Python suite passed1,069tests and42subtests with one expected
optional PostgreSQL skip in140.14seconds. The focused artifact/integration suite
passed168tests, including actual JSON encode/decode with the new provenance.

A real restricted child-worker read covered the half-open interval
`2026-09-20T00:35:00Z`–`2026-09-20T01:35:00Z`:12targets per source, all36qualified,
zero missing and zero numeric legacy reads, in0.209seconds. This used an injected
forbidden legacy reader and did not invoke training or any model write.

Actual production accepted and previous artifacts validate read-only with the
new validator. Their hashes at verification were:

- accepted: `fee779a0bc862e08c52ceaa0dc11b178f3eeccfb7c7bbd7162ae3c4ce3164c18`
- previous: `f052d7be14012e8ceff6cede1a79c40ecfbcd31adebc6199004a6a241b44e777`

The first full run exposed two exact-manifest expectations; the installer
dependency list and revision-contract test were corrected before the final run.
An additional real JSON encode/decode check exposed the loader's separate closed
manifest-key check. The new artifact roundtrip test reproduced that failure, and
the loader now accepts exactly the same optional provenance field as validation.
