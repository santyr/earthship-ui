# Forecast-energy Number Items: file-provider staging

`Predicted_PV_Today_kWh` and `Predicted_SoC_Trough_Tomorrow` are two
unlinked, REST-managed Number Items from the existing `forecast-intel.service`.
Their current live labels and `forecast-intel` tags are reproduced exactly in
`openhab/file-config/items/forecast-energy.items`. The latter Item also feeds
UI alerts, so no handoff may lose its state or scheduled publication.

The September 24 live **read-only** preflight passed: PV Item 573 has 71 JDBC
rows; trough Item 575 has 68. Both current states agree numerically with the
latest persisted values. A disconnected OpenHAB 5.2.1 file-provider test
verified both full Item DTOs and removed its owned networkless container.
An isolated OpenHAB/PostgreSQL rehearsal used synthetic values only inside
disposable containers; it passed JDBC writes, managed rollback, forward file
transfer, hot reload, and full restart with exact state/history preservation.
Both containers and the temporary database were removed. Production writes: 0.

The live transfer wrapper is read-only by default and has
`RELEASE_READY=False`; its source SHA-256 at staging is
`6aaae6398829f25fc5b046b24e35b67c3a94308563b5275252270b7d3f313018`.
The file is **not installed**. Keep the managed provider and timer unchanged
until the natural 06:40 MDT qualified-SoC forecast publication is verified.
If an attended transfer is later authorized, repeat the live preflight, make
the private rollback backup, verify unchanged JDBC identities/history and
current states, exercise live rollback, then require a later natural writer.
The adjacent `Predicted_Curtailment_Hours` transfer is separately staged; this
receipt does not activate either transfer or qualify forecast learning.
