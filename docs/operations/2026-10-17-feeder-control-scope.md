# Feeder control scope — October 17, 2026

The operator requires feeder triggerings to remain manual or automated from Lightning payments. They are excluded from Earthship-UI automated actuation suggestions and from the household planner's prospective actuation/qualification scope.

The live planner currently generates greywater and night-load candidates, not feeder candidates. This change removes the goat-card recommendation preview, excludes feeder intents from displayed selected/proposed actions, and removes feeder rows from automated chronology/qualification views. Even a retained report marking a feeder intent selected cannot produce a feeding suggestion in these views. Feeding count, motor status, animation and sound feedback remain observational.

Original observation/qualification schemas still parse their complete sealed reports, including historical feeder families. Historical records and manual/Lightning owner contracts are preserved. This change installs only four UI sources; it requires no backend, model, service, timer, permission or physical-control change.

Verification: 100 focused UI/parser tests passed, including selected-feeder exclusion, unchanged other recommendations, three displayed automated qualification families, existing feeding-status feedback and retained four-family report parsing. The four UI sources are deployed. Actual Home and Earthship rendering on laptop (1280×800) and tablet (1340×800) confirms the feeding counter remains visible, feeding recommendations are absent, and only three automated qualification families appear. All four browser cases had zero errors, write attempts or outer overflow. All 158 unrelated local overlays were preserved; no service was restarted.
