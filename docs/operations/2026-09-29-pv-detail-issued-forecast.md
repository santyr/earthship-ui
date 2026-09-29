# Align today's detailed PV forecast with its issued prediction

The 06:40 forecast producer publishes `Predicted_PV_Today_kWh` from its
learned `k_res` and `d_direct` resource/demand model. The same run previously
filled the detailed seven/ten-day PV series from a separate resource estimate
with a fixed 6.9 kWh cap, so the Energy/Weather detail for **today** could
disagree with the as-issued prediction and its immutable receipt. When atomic
SoC was unavailable, the issued PV value was correctly withheld but the
detailed series could still show a numeric estimate.

`pv_display_days()` now sets only day zero to the exact issued `pv_pred`,
including `None` when the qualified SoC input withholds it. Later days retain
their existing indicative, capped resource estimates because no qualified
future SoC/demand trajectory is available. The two-hourly JSON refresher
continues to reuse and date-align the morning series; no forecast coefficient,
trough formula, score, advisory, alert or DM threshold changes.
The day-zero value is also withheld if the prediction receipt itself is not
published. A computed value alone is not an issued, provenance-backed value.

The focused forecast and qualified-SoC suites passed 102 tests, including a
high-resource case where the issued day-zero value exceeds 6.9 kWh and a
withheld-SoC case and a failed-receipt case that keep the detailed value null.
Source and installed
worker matched SHA-256 `f1bce4a219319ac725239a19842fa643ef6d2b38fe900fbf0efecb1385a3c564`
before this change. The next natural 06:40 run must verify that the issued
Item, prediction receipt and detailed day-zero JSON agree; this change does
not resolve the larger PV or overnight-trough calibration bias.

## Exact-file production installation — September 29, 03:18 MDT

Commit `3a87076` is on `origin/main`. The idle production worker and active
06:40 timer were rechecked immediately before installation. The installed
preimage SHA-256 was
`f1bce4a219319ac725239a19842fa643ef6d2b38fe900fbf0efecb1385a3c564`;
an exact mode-0600 rollback copy is retained in private mode-0700 directory
`/home/sat/.local/state/forecast-intel/pv-detail-20260929-Zoc1TP`.
Only `/home/sat/openhab/scripts/forecast_intel.py` was atomically replaced.
Its installed/source SHA-256 is
`b4a2301e3ad0e6c5781024a6a2873611bacae34ae3f13e1f29139c6c8f9062c8`,
mode 0644, owner `sat:sat`. An installed-path import reproduced the new helper
case. The learned state still reads `k_res=1.3`, `d_direct=5.40326272`, and
`PV_QUALIFIED_CALIBRATION_RELEASE=False`; the service remains inactive/success
and the timer is active for 06:40 MDT. No job, Item write, OpenHAB restart,
coefficient change or alert-policy change was part of this installation.

Before the first natural 06:40 run, a review exposed one remaining publication
edge: a failed prediction receipt could leave an unconfirmed computed PV value
in the detailed JSON. The source was tightened to require receipt success for
day zero; 102 adjacent tests pass. This follow-up needs exact-file installation
before the natural run. The prior installed source remains safe and idle until
that replacement, but it lacks this extra failure gate.
