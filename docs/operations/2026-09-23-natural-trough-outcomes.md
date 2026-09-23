# Natural completed-night advisory outcomes — September 23

Read-only PostgreSQL and OpenHAB checks at approximately 12:25 MDT verified
four naturally captured advisory decisions (September 20–23), twelve result
records, two frozen selections, and two completed-night outcome records. The
assessor ran naturally at 06:40 MDT on September 22 and 23. No rule, assessor,
threshold, persistence setting, or hardware control was changed for this check.

| Prediction day | Target-night coverage | Evidence rows | Measured minimum SoC | Predicted trough | Signed residual |
| --- | ---: | ---: | ---: | ---: | ---: |
| September 20 | 99.9875% | 891 | 85% | 84% | -1 point |
| September 21 | 99.9868% | 889 | 84% | 77% | -7 points |

Both outcome records have `measured` status, 64-character evidence digests,
and assessment times after their completed target windows. Both frozen
selections have `selected` status. The live
`Forecast_Trough_Error_7d` Item reads **4.0 percentage points**, the mean
absolute residual of these two qualified outcomes. This verifies the first
natural completed-night assessment and diagnostic publication, not seven nights
of evidence.

Both outcomes explicitly set `bandit_eligible=false`,
`publication_status=not_assessed`, and `action_attribution=not_assessed`.
Forecast residuals and measured SoC alone do not establish whether an advisory
was delivered, followed, or beneficial. Keep bandit/Thompson threshold tuning
deferred until action confirmations, attribution, and a bounded reward design
are independently qualified. Do not change the existing 95/92/90 F advisory
or 30% DM thresholds on this evidence.
