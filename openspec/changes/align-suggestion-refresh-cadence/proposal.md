# Five-minute suggestion updates

## Why
The seasonal OpenHAB temperature study supports the accepted five-minute generation cadence. The UI still polls every 30 seconds, can miss short-lived publications, and drops the previous report on a failed read without a useful age indicator.

## What Changes
Retain the existing five-minute generation cycle and original evidence/expiry clocks. Deliver fixed same-origin publication notifications to the shared UI advice store, with one five-minute fallback poll, immediate opening/resume/reconnect refresh, and early refresh after human records change. Retain the last validated report on transport failure and label its issue age, stale evaluation or failed refresh clearly. Preserve immediate suppression of expired or invalidated actionable recommendations.

## Impact
UI transport and presentation only. No numerical-model, temperature-policy, forecast lifecycle, hardware or actuation change. Explicit input expiry remains authoritative even when shorter than the generation interval. Deploy the qualified UI candidate using existing user approval, with rollback and live readback.
