# First natural qualified-input shadow publication — September 20

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
