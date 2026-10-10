// Synthetic publication contract fixture, not evidence of model qualification.
export function installedPublication(mode = 'forecast_active') {
  const issued = Date.parse('2026-12-19T07:05:00Z');
  const trajectory = Array.from({ length: 24 }, (_, index) => ({
    at: new Date(issued + (index + 1) * 3600000).toISOString(), air_f: 74 - index / 10, mass_f: 76 - index / 20,
  }));
  const bands = [1, 6, 12, 24].map((horizon_hours) => ({
    at: trajectory[horizon_hours - 1].at, horizon_hours,
    lower_air_f: trajectory[horizon_hours - 1].air_f - 1,
    upper_air_f: trajectory[horizon_hours - 1].air_f + 1,
    nominal_coverage: .9, regime: 'warm', calibration_sha256: 'c'.repeat(64),
  }));
  return {
    schema: 'earthship-installed-shade-publication/v1', version: 4, status: mode,
    generatedAt: new Date(issued).toISOString(), validUntil: new Date(issued + 5 * 60000).toISOString(),
    model: { createdAt: '2026-11-02T18:10:00Z', trainedThrough: '2026-11-02T18:00:00Z', codeRevision: 'd'.repeat(64) },
    forecast: {
      schema: 'earthship-installed-shade-forecast/v2', status: 'shadow', generated_at: new Date(issued).toISOString(),
      artifact_sha256: 'a'.repeat(64), runtime_sha256: 'b'.repeat(64), horizon_hours: 24,
      initial: { air_f: 74, mass_f: 76, outdoor_f: 59 },
      origin_actions: { indoor_shade_closed: 0, outdoor_shade_present: 1, vent_open: 0,
        vent_provenance: 'operator_default_no_vent', mode: 'warm', action_knowledge: 'as_of_snapshot_not_outcome_confirmation' },
      trajectory, confidence: 'unqualified', prediction_intervals: bands, advice: [], release_authorized: false, automatic_actuation: false,
    },
    confidence: { grade: mode === 'shadow' ? 'low' : 'high', actionLabels: 'withheld' },
    release: { schema: 'earthship-installed-shade-release/v1', qualifiedAt: new Date(issued).toISOString(),
      expiresAt: mode === 'shadow' ? null : new Date(issued + 5 * 60000).toISOString(),
      artifactSha256: 'a'.repeat(64), runtimeSha256: 'b'.repeat(64), policySha256: 'd'.repeat(64),
      reportSha256: 'e'.repeat(64), originCaptureSha256: 'f'.repeat(64), calibrationSha256: 'c'.repeat(64),
      sensorEpochs: { air: '864142d5-99ee-4b7a-b5fc-e6a96e7274d8', mass: '864142d5-99ee-4b7a-b5fc-e6a96e7274d8', outdoor: '864142d5-99ee-4b7a-b5fc-e6a96e7274d8' },
      sensorEpochSemantics: 'declared_hardware_phase', forecastQualified: mode !== 'shadow', advisoryQualified: false, automaticActuation: false },
    reasons: [mode === 'shadow' ? 'Predictive qualification incomplete; action advice withheld' : 'Forecast qualified; action advice withheld'],
  };
}

// Raw-calibrated publication shape only; this fixture proves no source cohort.
export function rawInstalledPublication(mode = 'forecast_active') {
  const value = installedPublication(mode === 'unavailable' ? 'shadow' : mode);
  value.schema = 'earthship-installed-shade-publication/v2';
  value.version = 5;
  value.release.schema = 'earthship-installed-shade-release/v2';
  value.forecast.schema = 'earthship-installed-shade-forecast/v3';
  if (mode === 'unavailable') {
    value.status = mode; value.model = {}; value.forecast = null;
    value.confidence = { grade: 'unavailable', actionLabels: 'withheld' };
    for (const key of ['qualifiedAt','expiresAt','artifactSha256','runtimeSha256','policySha256','reportSha256','originCaptureSha256','calibrationSha256']) value.release[key] = null;
    value.release.sensorEpochs = {}; value.release.forecastQualified = false;
    value.reasons = ['Thermal forecast evidence unavailable'];
  }
  return value;
}
