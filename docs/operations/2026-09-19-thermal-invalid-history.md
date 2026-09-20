# Thermal invalid-history barrier correction

The deployed thermal reader discarded timestamped UNDEF/NULL/unparseable states.
The dataset builder also silently discarded direct nonnumeric input. A sequence
valid at00:00, invalid at00:05, recovered at00:15 could therefore yield interpolated
thermal samples at00:05/00:10. A final invalid reading could also disappear and
allow up to60minutes of held data beyond it. This is distinct from healthy
unchanged sensor values under everyChange persistence.

Correction5fc437a retains valid timestamps with NaN barriers in the JDBC adapter.
The pure dataset builder treats nonnumeric/boolean inputs as invalid buckets.
Existing invalid-bucket interpolation/hold rejection then prevents filling until
real recovery. Existing mixed finite/nonfinite bucket behavior, interpolation
limits, radiation-night reconstruction, model gates, thresholds and authority
are unchanged. Invalid timestamps still follow the previous reader behavior;
this narrow patch is not a complete source-integrity contract.

Verification:10new tests failed before implementation;118focused dataset/pipeline
tests passed afterward. Full branch suite1031passed,42subtests,1expected separately
exercised PostgreSQL skip in140.50seconds. Cases cover UNDEF,NULL,bad,empty,None,
boolean, invalid tail, recovery and adapter-to-dataset flow.

Deployment checked exact old hashes and both thermal jobs inactive, backed up
the two originals into `/tmp/thermal-invalid-history-i7u56scd` (0700), then
installed only those two files with original modes/owners. New installed hashes:

- thermal_intel.py:
  `bfd782a07869294e8d25e6c29701990d7946b245eb57b79353bb5911418c6d8a`.
- thermal_model/dataset.py:
  `111beb36aadf52943b40e50ba5df5cc4b0792b01e8ce5302f6c5bdcb6c2cbc5d`.

Installed reader-to-dataset regression passed using a mocked transport, no
OpenHAB requests or production observations. No training/shadow service was
forced, model artifact reset, scheduler changed, or authority advanced. Prior
natural September17–19 training runs exited0 and promoted candidates; that proves
existing scheduling, not qualification of this new version's future training.

The larger thermal receipt migration remains outstanding: historical training
still uses numeric temperature series and its existing gap reconstruction.
Freshness/identity-qualified new receipts are now available for indoor235,
north-wall193 and outdoor206, but this patch does not label legacy thermal
history as receipt-qualified or silently substitute new records into old models.
