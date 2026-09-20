# First natural qualified-input shadow publication — September 20

## Follow-up: today's accepted model used naturally

The next scheduled job ran09:25:48–09:25:52MDT and completed successfully.
Saved `shadow.json` and live `Thermal_Model_JSON` matched exactly and passed
the installed production schema validator. generatedAt is15:25:48Z, with25
observed rows. It now identifies today's model, created/trained-through
`2026-09-20T12:50:29Z`, codeRevision
`261d0da8b615ea99ef2f3a2fad25a454ffd34d2f20479b98aa85e9d38ffd0e1a`.
The accepted artifact hash remains
`40a48cf6e491054a83b2577c2974a5a65ec37e8c8298f0e36613238ce4201e18`.
This closes natural shadow use of the newly promoted qualified-training model.
Status remains shadow and confidence low; no candidate was emitted because
minimum modeled improvement was not met. This is not proof of predictive
accuracy or authorization for additional controls. No run was forced.

## Earlier publication using yesterday's model

The scheduled thermal-model-shadow job ran07:25:29–07:25:32MDT and completed
successfully, with no forced run. This is the first verified natural output after
the [qualified shadow-input activation](2026-09-20-shadow-receipt-activation.md).

The saved shadow.json and live Thermal_Model_JSON parsed to identical objects
and both passed the production schema validator. Effective service configuration
still has THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE=1. The installed runtime contents
were separately checked against reviewed63529ea during read-only release preflight.

- generatedAt2026-09-20T13:25:29Z; statusshadow; confidence grade low.
-25observed rows,72-hour forecast availability.
- Current receipt ages: air1.338minutes, mass1.146minutes, outdoor0.604minutes.
  Glazing4.463minutes and radiation0.401minutes retain their separate legacy
  contracts; they are not newly receipt-qualified by this release.
- Model created/trained-through2026-09-19T12:50:29Z, artifact codeRevision
  fa218bd409057fc2b1d1a7fe3e2aab9d1fffda8a0d51c417ba1c586c82accda2.

That artifact revision describes yesterday's accepted model, not a new qualified
training result or the current runtime revision. Today's06:50training job remains
active; it was not restarted or overwritten. This closes natural shadow input/
publication verification only, not training provenance, candidate promotion,
causal/advisory outcomes or low-confidence model limitations.
