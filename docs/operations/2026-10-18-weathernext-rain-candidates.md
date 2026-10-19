# WeatherNext precipitation candidate capture

Observed 2026-10-18. This completes the acquisition prerequisite for the approved precipitation-head comparison; it does not choose or qualify a production product.

The current official model guide and 0.1-degree catalogue list three distinct hourly products: `total_precipitation_1hr`, `imerg_tp_1hr`, and `experimental_tp_1hr`. All report one-hour accumulated depth in metres. The private collector now requests each mean band separately in its existing bounded gridded request. Normalization preserves product identity, original metre values, millimetre conversion, source digest, native cell and interval end. Missing values remain missing; negative/nonfinite depths and wrong units are refused. No precipitation probability is inferred from these means.

`daily_rain_depth` aggregates one explicitly named mean product over complete local trailing-hour intervals. DST days require their actual 23/25 hourly intervals. Missing hours cannot borrow values from another product, and marginal quantiles cannot be summed as daily totals. It shares the existing complete-interval accumulation logic with solar energy without changing solar conversion or accumulation order. Production-provider selection and existing forecast payloads remain unchanged.

## Actual data and verification

A real 06Z run capture completed at **2026-10-18T18:40:00.590530Z**, retaining **360 hours / 12 bands / 4,320 points** with digest `9eb1921f06783d7e677f49329c0f76e59fdaa7a3256710f46388e4185e965e94`. It took **9.729 seconds**, transferred **1,272,037 bytes across 7 requests**, and peaked at **74,552 KiB RSS** under unchanged 256MiB / 24-task / 90-second admission. This is 16,457 additional response bytes relative to the preceding ten-band run; it is a measured case, not a guaranteed constant.

All three products supplied 360 native hourly values. Original-source rederivation passed, and each produced a separate complete October 19 forecast-only daily total. Those totals are not local observations or skill evidence. Private originals and the audit are retained outside Git/browser assets.

New tests first failed for the omitted product mappings/capture and absent daily aggregation. All **128 pinned WeatherNext tests** then passed in **3.177 seconds**, covering separate units/identities, missing/invalid data, actual collector request selection, DST totals, no cross-product filling and no quantile summation.

## Installed capture upgrade

At 18:47Z the private backend source/revision settings advanced atomically to tested commit `f5775f8132a35b177ba503d6fc605e1b9d94df47`. All 1,102 packaged files were independently checked against their Git blob identities before activation. Existing archive/issue clocks and identities, credentials, unit definitions, timer states, no-publication override and resource limits were preserved.

The installed collector retained **4,320 points** at **18:47:33.952364Z**, digest `5511f70b50c76f296faad2f319277350b9988e543d97000e28c8e342c690c0e8`, in **8.698 seconds / 1,272,037 bytes / 7 requests / 75,048 KiB peak RSS**. Each precipitation product has 360 rows. The installed shadow worker then retained a `READY` issue from that exact snapshot and source commit, generation `d9ec2cace2f51f960b353aa9714dc7c8f5dc279afcc952ab4e84902a22bb69a6`, with publication/actuation disabled and the candidate still untrained. No production provider or model-selection behavior changed.

## Comparison rule before outcomes

Compare all three products on identical complete local days, using a retained original Google issue available before the day starts and the existing source-qualified local rain-counter reader. Freeze the issue-selection rule before evaluating outcomes; later/reissued forecasts cannot replace an earlier original decision. Retain sensor epochs, native grid, original source/outcome identities, source availability and gauge boundary uncertainty. Partition sensor epochs rather than pooling them.

The [implemented comparison](2026-10-18-weathernext-rain-comparison.md) freezes the operational issue rule as the latest retained issue strictly before local day start, selected before checking product completeness or outcomes; all three products must be complete on a common day. The primary product-selection metric is paired complete-day MAE in millimetres. Also report RMSE, signed bias, error tails, observed wet/dry and uncertain-boundary cases and horizon support, so dry days cannot conceal poor wet-event performance. Choose on chronological selection data and assess the frozen choice on untouched later data; do not select on the final holdout. The existing requirement for adequate actual precipitation events and unchanged release gates remains; this report adds no new numeric event-count gate and grants no automatic qualification. No product is selected or promoted now.

## Official references

- [WeatherNext model variables and hourly precipitation units](https://developers.google.com/weathernext/guides/models).
- [0.1-degree catalogue: distinct precipitation bands](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p1deg).
- [Approved migration design: precipitation qualification](../superpowers/specs/2026-10-05-weathernext-exclusive-forecast-design.md).
