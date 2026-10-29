- [x] Implement bounded forecast shade-schedule comparisons, including future risk and solar-access timing.
- [x] Verify proactive heating/cooling, thermal lag, shade/ventilation coordination, solar angles, missing/stale input and replay.
- [x] Deploy the advisory producer without changing qualified numerical model weights or equipment controls; verify actual scheduled output and UI.
- [x] Record confirmed operator glazing geometry (165° azimuth, 64.5° tilt from horizontal), overhang/night-insulation limitations and validation evidence.


Evidence (2026-10-29): 75 focused advice and native thermal tests pass. Immutable
advisory sources are artifacts/proactive-advice-20261029.local/sources-v2;
existing numerical source files remain byte-identical. Original-clock retained
forecast comparison replayed exactly; publication also verifies exact replay.
The first manual attempt returned code75 during concurrent scoring; after the
scorer completed, the normal service succeeded. The genuine 11:44:45 MDT timer
cycle and its advisory postprocessor both exited0. Fresh report
1c6c499918c04573d44c6eb702bbcbc854f9e9d522155a4f4abffd5f53125bf1
was evaluated at17:45:45.719708Z; browser/API readback17:45:48Z showed forecast-led
ventilation and no supported shade change, with geometry165°/64.5°, zero browser
errors, human_action_only=true and automatic_actuation=false. Existing source
expiry was retained (domains valid through17:45:56.764688Z); this is bounded live
verification, not a claim of continuous fresh advice or measured physical benefit.
Source manifests, real original inputs, replay report, scheduled browser JSON and
screenshots are retained in artifacts/proactive-advice-20261029.local/. Rollback:
remove only thermal-provisional-forecast.service.d/zzzzz-proactive-advice.conf,
reload systemd, and allow the original publisher's next normal cycle.


## No-overhang and historical-data follow-up

- [x] Confirm no front overhang and no historical shade-position data from the operator; preserve the existing thermal predictions as the advice basis.
- [x] Inspect live OpenHAB Items and fourteen days of JDBC persistence; retain original responses and reproducible exploratory nighttime analysis separately from production models.
- [x] Verify existing Thermal_Model_JSON publication: 24-hour v4 thermal forecast, artifact18a7d2fc..., trained through2026-10-29T12:00Z; source readback retained. No new predictor is deployed.
- [x] Update optional geometry to v2/front_overhang=false, remove overhang uncertainty from advice, and verify75 focused tests plus exact original-clock replay with confirmed geometry.
- [x] Verify the scheduled 11:59:45 MDT cycle: numerical main and advisory sources-v3 postprocessor exited0. Fresh18:00:45.717068Z report23932ec0... includes no front overhang,165°/64.5° geometry and automatic_actuation=false. Numerical forecast coefficients and original release remain unchanged. Readback: artifacts/nighttime-thermal-history-20261029.local/no-overhang-live.json.
