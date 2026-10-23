# Missing future geometry defers one native forecast opportunity

At 18:48 UTC on October 23, the geometry preparer could not acquire its shared lock while the hourly publisher retried. The 18:50 geometry packet was absent. The native forecast driver then withdrew the previous forecast at 18:49, although that issued forecast's timestamps and validity had not changed. The next prepared cycles recovered normally. This caused a temporary empty thermal card.

The serving driver now distinguishes an absent packet for the next issue before starting publication. After the owned model is read, it verifies the original model/configuration bindings again and returns `deferred` with `native_geometry_not_prepared`. It transports no new forecast and changes no previous issue clock. Existing UI freshness/expiry checks continue to apply.

Other missing files, malformed or aliased geometry, expired/changed model bindings and configuration drift retain their withdrawal/refusal behavior. The repair changes no numerical kernel, model coefficient, training/admission clock, timer, resource allowance, provider or equipment authority. `household_cycle.py` is outside the active model's fitted 100-file closure; a source-only native handoff must preserve the exact candidate and runtime.

The normal driver regression reproduces the absent-file path and checks withdrawal boundaries and model/configuration revalidation. The affected 55-test native/household driver, forecast and family suites pass. Installation requires the normal reviewed-source CI gates, a verified compatible native stage, exact rollback and actual UI readback. This document initially records the repair before its source-only installation; the current release record carries installation status.
