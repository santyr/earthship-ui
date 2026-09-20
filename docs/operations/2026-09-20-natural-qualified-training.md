# First natural qualified-temperature training result

The September20 scheduled run started06:50:29MDT and finished08:44:23MDT.
systemd reports inactive/dead, MainPID0, Resultsuccess. The same original
PID2326440 completed; no restart, forced training or synthetic evidence was used.
The journal reports promoted, trainedThrough2026-09-20T12:50:29.206945Z, with
runtime revision261d0da8b615ea99ef2f3a2fad25a454ffd34d2f20479b98aa85e9d38ffd0e1a.

Both accepted.json and candidate.json independently passed the installed
production pure decoder and validate_artifact(require_eligible=True). They are
byte-identical, SHA256:
40a48cf6e491054a83b2577c2974a5a65ec37e8c8298f0e36613238ce4201e18.
The backtest report passed its production validator, SHA256:
4927326feed6c47c710d9fb488654b26c14e68879dd5bb361936b7c9033fdc5b.

previous.json retains the exact pre-run accepted artifact, SHA256:
fee779a0bc862e08c52ceaa0dc11b178f3eeccfb7c7bbd7162ae3c4ce3164c18.
Validation deliberately avoided ArtifactRegistry.load_accepted because that
method can quarantine or restore files. No model state was modified by checks.

The artifact now carries version1 temperature_evidence with cutover
2026-09-20T00:30:00+00:00 and explicit
legacy_before_cutover_receipt_asof_after semantics:

| Role | Sensor | Post-cutover targets | Qualified | Missing | Legacy points |
|---|---|---:|---:|---:|---:|
| air |Fineoffset-WH32B235|149|149|0|97009|
| mass |AmbientWeather-WH31E193|149|148|1|72610|
| outdoor |Fineoffset-WH65B206|149|149|0|359403|

Each role records its own grid SHA256 and the reviewed -40..140F/120-second
policy. The missing mass target remains explicit rather than being represented
as qualified. This closes the first natural training/provenance/promotion gate,
not a claim that legacy history became receipt-qualified or that model accuracy
improved. Subsequent natural shadow output using this new artifact still needs
its own receipt. The pending daily-temperature runtime release can now proceed
after checking forecast/shadow idleness and taking current post-training backups.
