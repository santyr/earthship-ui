# WeatherNext energy and action evidence inventory

Observed 2026-10-18 from 16:24:10Z to 16:24:23Z. This read-only audit used the existing source-bound readers, private runtime credentials and shared 512 MiB job admission. It fitted no model, issued no forecast and changed no database grant, source policy, resource limit or actuator setting. Original per-window summaries and digests remain private in this plan's `energy-action-audit.json`.

## Battery outcome windows

The audit independently bound the current `BMS_SOC_Evidence_JSON` owner receipt, receiver epoch and physical bank configuration before reading historical nights. The physical bank is `discover_4_module_2026`; its configuration digest was `89ee920a9599d506348502372cd42b68a1b02264a1bab887e3fc189b8ca86e8b`. The current receiver epoch was `092f03b8-a4af-4292-afcb-2acaee21a4aa`. Historical receipts from other receiver epochs were not silently reassigned to that cohort.

Across 28 prediction dates, September 20–October 17, the unchanged whole-night reader returned:

| Result | Count | Meaning |
|---|---:|---|
| Measured | 7 | Prediction dates October 10–16; at least 99.9876% measured coverage for each 15-hour night |
| Refused | 20 | Existing original-source validation refused the packet; no measured outcome or specific internal cause is inferred from its sanitized `ValueError` |
| Pending | 1 | Prediction date October 17, whose window ends October 18 at 17:00Z / 11:00 AM MDT |

The original measurement rule requires at least 90% validated coverage; this audit did not raise or lower it. The seven measured windows exceed that threshold. A prediction date identifies the night beginning at 8:00 PM local time and ending at 11:00 AM the following day. Therefore this inventory is not seven full 24-hour battery days. Measured nights alone do not establish original forecast origins, available-PV labels, charge/no-full outcomes or weather skill.

## Inverter AC-output hours

For the existing load profile's 14-day lookback, October 4–17, the audit captured and replayed all 336 original hourly windows. **327 hours** were accounted with at least the existing **99% coverage** and exactly one validated receiver epoch. Nine hours were below 99%; four of those also crossed receiver epochs. The overlapping exclusions are not added together. Missing intervals were not filled with zero load.

| Receiver epoch | Eligible hours |
|---|---:|
| `06b74281-cfbc-4f7c-b293-49c5a41eb271` | 58 |
| `e30bcd62-6b2d-473b-a224-92bb5cb88070` | 21 |
| `d943d2a9-50d2-47e1-87bb-b4c237b163aa` | 43 |
| `de5e8a44-04cd-4225-bcf7-d7eefdedcdcc` | 22 |
| `b901c05f-4bf4-4582-8118-60375765a7c4` | 183 |

These are qualified inverter-output accounting hours partitioned by receiver epoch. They are not a single pooled weather-training cohort, complete household-demand ground truth, proof of topology or calibrated physical energy. The existing topology/source qualification and independent-day support rules continue to apply. No load profile was fitted or replaced by this inventory.

## Action and shade context

The configured runtime `THERMAL_DATABASE_URL` is in `/home/sat/.config/hex/openhab.env`, a service EnvironmentFile. The earlier audit inspected only systemd's inline Environment property and therefore missed the reference. The existing runtime credential sufficed for read-only transactions; the admin credential was not used.

The journal contains 19 action events (effective dates October 16, 2025 through October 16, 2026), 4 mode events (effective dates October 16, 2025 through May 22, 2026), and 13 message receipts (created August 20 through October 16, 2026). Effective time is not original availability: retrospective events cannot be made known before their receipt/creation clocks.

The existing v1 origin selector successfully produced fourteen daily 06:40-local snapshots, October 5–18, respecting effective, received, created and supersession clocks. The selected vocabulary includes indoor/outdoor shade context and later ventilation context. A selected state is not proof of continuous observation, per-zone motor telemetry, action effect, complete shade coverage or causal benefit. The v2 fetch release gate remains unchanged and was not bypassed. This audit does not turn the operator's shade installation plans into observed device history.

## Qualification implications

Battery, AC and action histories now have explicit sampled ranges and refusal/support counts for the migration inventory. These local histories may be reused through their existing qualified adapters while weather-dependent learning starts afresh with Google forecasts. Nothing here permits old Open-Meteo-trained weather weights or pending targets to enter the new model.

Task 7 still needs actual original WeatherNext issues paired with these outcomes, qualified irradiance and rain evidence, fixed-artifact downstream attribution, fresh weather-dependent components, and the existing release gates. The seven battery nights and 327 AC hours do not replace those requirements. See [readiness](weathernext-readiness.md), [the migration plan](../superpowers/plans/2026-10-05-weathernext-exclusive-forecast.md) and [the reset contract](openmeteo-retirement.md).
