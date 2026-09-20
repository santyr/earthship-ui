# Thermal shadow receipt activation — September 20

Committed and pushed source `63529ea`; deployed and enabled the shadow-specific
receipt reader. Air/indoor235, north-wall193 and outdoor206 now use qualified
sensor receipts for their current values and trailing five-minute history.
Missing history remains invalid; an unavailable current receipt refuses the
shadow path without numeric-history or REST-update-time fallback.

The pure prediction pipeline enforces receipt expiry. A second expiry check
after computation prevents a receipt that expires during prediction from
supporting publication. Glazing and radiation retain their existing contracts;
this release does not claim receipt qualification for those sources.

## Verification

- Full Python suite:1,078passed,42subtests passed, one expected optional
  PostgreSQL skip. Fresh targeted run:31passed.
- Live source verification at12:38:34Z found288history targets per stream:
  air/outdoor148qualified and140missing; north-wall147qualified and141missing.
  Missing pre-collection history was not filled or reclassified as healthy.
- Installed complete `_current_states` and pipeline-input validation passed
  at12:40:27Z. Receipt ages were78.18s air,50.91s north-wall and38.33s outdoor;
  the existing observed-history output contained25rows.
- All thermal model JSON files remained byte-identical to private backups.
  All four original thermal service/timer files and modes are unchanged.
- Existing training qualification remains enabled and is not given the new
  shadow activation flag. Both thermal timers were briefly paused and restored;
  the forecast timer was untouched. No service run, training, forecast
  publication, pump command or OpenHAB restart was forced.

## Live configuration and recovery

Scoped override (0644):
`/home/sat/.config/systemd/user/thermal-model-shadow.service.d/qualified-temperature.conf`

```
THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE=1
THERMAL_TEMP_DB_CONFIG=/home/sat/.config/hex/weather-temperature-db.json
THERMAL_TEMP_POLICY=/home/sat/.config/hex/weather-temperature-policy.json
```

Effective systemd settings were read back and verified. No credential contents
were copied into the override or repository.

- Complete installed runtime revision:
  `261d0da8b615ea99ef2f3a2fad25a454ffd34d2f20479b98aa85e9d38ffd0e1a`
- Override SHA256:
  `79fc13fdded3a419d714f6c818fc671912654aeb552ccf14471b28e8b5c298f0`
- Private release root:
  `/home/sat/.local/state/thermal-intel/deploy-receipts/thermal-shadow-20260920T0639`

Only three runtime files changed: thermal_intel.py, thermal_model/pipeline.py,
and thermal_temperature_runtime.py. The receipt-bound installer used their
narrow manifest, plus unchanged unit backups and the forecast dependency check.
The complete installed runtime graph was also compared with the published source.

Removing this shadow override returns only shadow inputs to the prior path;
retain the compatible artifact validator and the existing training override.
Do not overwrite newer models with release backups.

## Natural outcome gate

Post-release thermal service states are inactive with no new journal errors.
Their previous successful runs are not verification of this deployment. Training
remains scheduled for06:50MDT and shadow retains its two-hour cadence (last
natural start05:25:29MDT). Verify subsequent natural runs and outputs separately.
