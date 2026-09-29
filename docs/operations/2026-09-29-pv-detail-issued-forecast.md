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

The focused forecast and qualified-SoC suites passed 101 tests, including a
high-resource case where the issued day-zero value exceeds 6.9 kWh and a
withheld-SoC case that keeps the detailed value null. Source and installed
worker matched SHA-256 `f1bce4a219319ac725239a19842fa643ef6d2b38fe900fbf0efecb1385a3c564`
before this change. The next natural 06:40 run must verify that the issued
Item, prediction receipt and detailed day-zero JSON agree; this change does
not resolve the larger PV or overnight-trough calibration bias.
