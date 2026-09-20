# Thermal qualified-history activation — September 19

## Live state verified

Thermal training now opts into the receipt-qualified source integration from
`c92454c`. The explicit cutover is `2026-09-20T00:30:00+00:00`, an elapsed
five-minute boundary already verified in natural persisted receipts. Earlier
numeric history is retained and labeled legacy; it is not retroactively claimed
as receipt-qualified.

The scoped training-service drop-in is
`/home/sat/.config/systemd/user/thermal-model-train.service.d/qualified-temperature.conf`
(0644), with effective settings checked through systemd:

```
THERMAL_TEMP_QUALIFIED_ENABLE=1
THERMAL_TEMP_EVIDENCE_CUTOVER=2026-09-20T00:30:00+00:00
THERMAL_TEMP_DB_CONFIG=/home/sat/.config/hex/weather-temperature-db.json
THERMAL_TEMP_POLICY=/home/sat/.config/hex/weather-temperature-policy.json
```

Only paths, not credentials, are in the drop-in. Existing restricted-role and
policy files were reused without permission or content changes.

## Guarded release evidence

- Rechecked clean source at `c92454c`, exact preexisting runtime bytes and absence
  of the two new modules. All affected jobs were inactive before the change.
- Backed up the exact runtime, four thermal unit files and all model JSON files
  under the private receipt directory below. The receipt-bound installer checked
  the complete dependency graph before and after installation.
- Briefly stopped only thermal training, thermal shadow and forecast timers.
  No service, pump, manual forecast, training job or OpenHAB restart was forced.
- Installed-reader verification imported from `/home/sat/openhab/scripts`, not
  the checkout. It qualified all36targets across air/mass/outdoor for the
  half-open interval `2026-09-20T00:55:00Z`–`2026-09-20T01:55:00Z`, with a
  forbidden numeric fallback reader. The existing hourly evidence reader also
  qualified a real elapsed target after shared dependencies were updated.
- All model JSON filenames and bytes remained identical to backup. The actual
  accepted and previous models still decoded and validated successfully.
- Enabled the drop-in only after installed verification, reloaded systemd, then
  restored all three timers to active. The four original thermal unit files and
  modes are byte-for-byte unchanged; shadow retains `OnUnitActiveSec=2h`.
- At20:01:54MDT, all three services were inactive with previous successful
  results and no new service journal entries in the release interval. Their old
  successful results are not evidence of training under this new configuration.

Private receipt root:
`/home/sat/.local/state/thermal-intel/deploy-receipts/thermal-qualified-20260919T1955`

- Complete installed runtime revision:
  `f17781c7481fc52154330e5aa8680da87dab171d2a0a045badde97b125dda841`
- File receipt SHA256:
  `03ea40678173160ac9f223fb769cbb6d91f12b44df5274b013061a36b3384c8a`
- Activation drop-in SHA256:
  `88b7708a08bc425876a72b0c28f32ae1ae85e8751c98f0b8f5d92be2b6b0a0a9`
- Accepted model SHA256, unchanged:
  `fee779a0bc862e08c52ceaa0dc11b178f3eeccfb7c7bbd7162ae3c4ce3164c18`
- Previous model SHA256, unchanged:
  `f052d7be14012e8ceff6cede1a79c40ecfbcd31adebc6199004a6a241b44e777`

## Remaining verification and rollback

Next normal training is September20 at06:50MDT (forecast remains06:40MDT).
Verify its real candidate/accepted artifact, source counts/digests, promotion
gates and natural service outcome. Do not force training to manufacture proof.
Current-shadow receipt migration and other source-health work remain outstanding.

Use the [integration rollback contract](2026-09-19-thermal-qualified-integration.md):
removing the activation override can return training to its previous input mode,
but retain the compatible validator once newer artifacts carry receipt evidence.
Do not blindly overwrite new learned state or restore an old strict loader.
