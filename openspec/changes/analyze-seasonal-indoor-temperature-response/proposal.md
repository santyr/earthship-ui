# Seasonal indoor temperature response analysis

## Why
Measure actual OpenHAB indoor temperature changes before changing suggestion freshness policy. The user accepts the five-minute cadence and requests comparison of winter and summer history.

## What Changes
Read-only analysis and reproducible local report. Identify actual indoor-air and wall sensors; extract available complete winter/summer months through OpenHAB persistence; quantify directional changes, daily ranges and short-window movement with explicit gap/quantization treatment.

## Impact
No production, sensor mapping, suggestion cadence, freshness policy, model or database changes. Preserve current live repair releases and unrelated checkout changes.
