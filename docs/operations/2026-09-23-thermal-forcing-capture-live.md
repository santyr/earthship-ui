# Thermal shadow forcing capture: live activation

On September 23, 2026, the existing two-hour `thermal-model-shadow.service`
was given a default-off observational capture directory. The installed v4
publisher received only the capture hook and decision-timestamp backport;
the separate source v5/journal changes were not deployed. No model was promoted
out of shadow, and no actuation authority changed.

- Private archive root: `/home/sat/.local/state/thermal-intel/forcing-captures`
  (owner `sat`, mode `0700`); month directories are `0700`, immutable archive
  files `0600`. The user-service drop-in
  `thermal-model-shadow.service.d/forcing-capture.conf` sets
  `THERMAL_SHADOW_CAPTURE_DIR` to that root. The pre-capture installed v4
  publisher backup is
  `/home/sat/.local/state/thermal-intel/runtime-backups/thermal_intel-v4-pre-capture-20260923.py`
  (mode `0600`). Neither private capture data nor this backup is in Git.
- The natural 09:48 MDT run published successfully but recorded a capture gap:
  `generatedAt` had been truncated to seconds, preceding the actual
  post-input decision time by less than one second. The publisher now retains
  full decision-clock precision in `generatedAt`. A fractional-second
  regression test covers that contract.
- After the fix, 77 focused publisher/capture tests passed. An attended
  09:50 MDT shadow run exited `0` and wrote one 8,770-byte archive. Its
  verifier accepted the private file and all four content digests. The archive
  contains 240 raw Open-Meteo forecast hours and 240 normalized rows.
  `inputs_available_at` and `decision_at` were both
  `2026-09-23T15:50:54.866271+00:00`; publication followed at
  `15:50:57.111209+00:00`. The captured output digest matched the live
  `Thermal_Model_JSON` state exactly. The output remains `shadow` and
  low-confidence. No archive was fabricated for the 09:48 gap.
- Installed publisher SHA-256 after the fix:
  `e0b79aae4887af8502697bfeb813b6c8d9868374e8deaf337957c00897388b45`.
  Installed capture helper SHA-256:
  `73e8afb340bf8b3100528f5ba1c48aaf3e63b1731982bd234d3f02af1ba1d24c`.

Future thermal qualification must use the exact per-publication forcing archive,
qualified action/outcome receipts, and scored shadow forecasts. This archive
alone does not demonstrate a useful model or justify leaving shadow mode.
