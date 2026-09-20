# Natural full-day atomic BMS verification

Read-only verification September19,2026 closes the full-day materialization gap
left after the partial September10 cutover. It does not close independent power
source-health, live fault/restart experiments, or all historical-algorithm work.

The normal midnight aggregation journals confirm scheduled materialization.
Latest observed run September19 00:22:29MDT successfully materialized September18,
five tables and21source-quality rows. No manual aggregate, backfill, source
injection, rule execution or learned-state mutation was performed.

For each September10–18 local day, the installed reader fetched original
`public.item0613` atomic envelopes with original carry/120-second lookback,
validated them, and rebuilt expiry/fault/bank-clipped intervals. Recomputed
coverage, min/max, DoD and original row counts matched daily_battery and
daily_source_quality. Quality provenance is atomic_bms_evidence with freshness
basis BMS_SOC_Evidence_JSON, not the numeric SoC change timestamp.

| Local date | Qualified coverage | Minimum SoC | Daily DoD | Original rows |
| --- | ---: | ---: | ---: | ---: |
| September10 | 33.835354% | 92% | 8 points | 679 |
| September11 | 99.982791% | 84% | 16 points | 1829 |
| September12 | 99.982921% | 85% | 15 points | 1810 |
| September13 | 99.936535% | 84% | 16 points | 1701 |
| September14 | 99.986893% | 85% | 15 points | 1514 |
| September15 | 99.984704% | 81% | 19 points | 1646 |
| September16 | 99.985087% | 85% | 15 points | 1689 |
| September17 | 99.988446% | 82% | 18 points | 1408 |
| September18 | 99.968633% | 84% | 16 points | 1686 |

Every day reached a qualified maximum100%. September10 remains insufficient_data;
its extrema are partial observations, not full-day truth. September11–18 have
quality ok. Small uncovered publication intervals remain gaps rather than being
rounded away or filled. A complete local-day window does not mean100%coverage.

The current Energy_Analytics_JSON battery block reports status ok, latest minimum
84%, DoD16, daily EFC0.16651739643664593 and cumulative EFC9.646097200107. The sum
of stored daily EFC within discover_4_module_2026 matches that cumulative value
to1e-9. This validates accounting consistency and publication, not independent
power-meter accuracy or manufacturer lifetime cycles. No BMS counter changed.
