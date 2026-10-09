// Structural display validation only. The backend must freshly qualify sources.
const HOUR_US = 3_600_000_000n;
const sha = (value) => { if (typeof value !== 'string' || !/^[0-9a-f]{64}$/.test(value)) throw new TypeError('invalid source revision'); return value; };
const fields = (...values) => new Set(values);
export function validateInstalledPublication(payload, { exactObject, finiteNumber, timestamp }) {
  exactObject(payload, fields('schema','version','status','generatedAt','validUntil','model','forecast','confidence','release','reasons'));
  if (payload.version !== 4 || payload.schema !== 'earthship-installed-shade-publication/v1'
    || !['unavailable','shadow','forecast_active'].includes(payload.status)) throw new TypeError('unsupported installed publication');
  const issue = timestamp(payload.generatedAt); const valid = timestamp(payload.validUntil);
  if (!(issue.epochMicros < valid.epochMicros && valid.epochMicros <= issue.epochMicros + 600_000_000n)) throw new TypeError('invalid publication deadline');
  const release = exactObject(payload.release, fields('schema','qualifiedAt','expiresAt','artifactSha256','runtimeSha256','policySha256',
    'reportSha256','originCaptureSha256','calibrationSha256','sensorEpochs','sensorEpochSemantics','forecastQualified','advisoryQualified','automaticActuation'));
  const confidence = exactObject(payload.confidence, fields('grade','actionLabels')); const active = payload.status === 'forecast_active';
  if (release.schema !== 'earthship-installed-shade-release/v1' || release.sensorEpochSemantics !== 'declared_hardware_phase'
    || release.forecastQualified !== active || release.advisoryQualified !== false || release.automaticActuation !== false
    || confidence.actionLabels !== 'withheld' || confidence.grade !== ({ unavailable:'unavailable', shadow:'low', forecast_active:'high' })[payload.status]) throw new TypeError('invalid mode authority');
  if (!Array.isArray(payload.reasons) || payload.reasons.length < 1 || payload.reasons.length > 8
    || payload.reasons.some((r) => typeof r !== 'string' || !r.length || new TextEncoder().encode(r).length > 256)) throw new TypeError('invalid status reasons');
  const parsed = { generatedAtMs: issue.epochMs, generatedAtMicros: issue.epochMicros, validUntilMicros: valid.epochMicros,
    mode:payload.status, confidence:confidence.grade, reasons:payload.reasons, actionConfidence:'withheld',
    artifactRevision:release.artifactSha256, qualifiedAtMs:null, expiresAtMs:null };
  if (payload.status === 'unavailable') {
    exactObject(payload.model, fields());exactObject(release.sensorEpochs, fields());
    if (payload.forecast !== null || Object.entries(release).some(([key,value]) => !['schema','sensorEpochs','sensorEpochSemantics','forecastQualified','advisoryQualified','automaticActuation'].includes(key) && value !== null)) throw new TypeError('fabricated unavailable evidence');
    return parsed;
  }
  exactObject(release.sensorEpochs, fields('air','mass','outdoor'));
  for (const epoch of Object.values(release.sensorEpochs)) if (typeof epoch !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(epoch)
    || epoch === '00000000-0000-0000-0000-000000000000') throw new TypeError('invalid declared hardware phase');
  for (const key of ['artifactSha256','runtimeSha256','policySha256','reportSha256','originCaptureSha256','calibrationSha256']) if (release[key] !== null) sha(release[key]);
  for (const key of ['artifactSha256','runtimeSha256','reportSha256','originCaptureSha256']) if (release[key] === null) throw new TypeError('missing original identity');
  const assessed = timestamp(release.qualifiedAt);parsed.qualifiedAtMs = assessed.epochMs;parsed.qualifiedAtMicros = assessed.epochMicros;
  if (active) {
    const expires = timestamp(release.expiresAt);parsed.expiresAtMs = expires.epochMs;
    if (release.policySha256 === null || release.calibrationSha256 === null || !(assessed.epochMicros < expires.epochMicros && valid.epochMicros <= expires.epochMicros)
      || expires.epochMicros - assessed.epochMicros > 24n * HOUR_US) throw new TypeError('invalid qualification deadline');
  } else if (release.expiresAt !== null) throw new TypeError('shadow claims release expiry');
  exactObject(payload.model, fields('createdAt','trainedThrough','codeRevision'));sha(payload.model.codeRevision);
  const created = timestamp(payload.model.createdAt);const trained = timestamp(payload.model.trainedThrough);
  if (!(trained.epochMicros <= created.epochMicros && created.epochMicros <= issue.epochMicros)) throw new TypeError('invalid frozen chronology');
  const numeric = exactObject(payload.forecast, fields('schema','status','generated_at','artifact_sha256','runtime_sha256','horizon_hours',
    'initial','origin_actions','trajectory','confidence','prediction_intervals','advice','release_authorized','automatic_actuation'));
  if (!['earthship-installed-shade-forecast/v1','earthship-installed-shade-forecast/v2'].includes(numeric.schema) || numeric.status !== 'shadow'
    || numeric.confidence !== 'unqualified' || numeric.release_authorized !== false || numeric.automatic_actuation !== false
    || !Array.isArray(numeric.advice) || numeric.advice.length || timestamp(numeric.generated_at).epochMicros !== issue.epochMicros
    || numeric.artifact_sha256 !== release.artifactSha256 || numeric.runtime_sha256 !== release.runtimeSha256) throw new TypeError('numeric source changed');
  const physical = (value) => { finiteNumber(value); if (value < -40 || value > 140) throw new TypeError('physical temperature exceeded');return value; };
  exactObject(numeric.initial, fields('air_f','mass_f','outdoor_f'));Object.values(numeric.initial).forEach(physical);
  const actions = exactObject(numeric.origin_actions, fields('indoor_shade_closed','outdoor_shade_present','vent_open','vent_provenance','mode','action_knowledge'));
  if (finiteNumber(actions.outdoor_shade_present) !== 1 || ![0,1].includes(finiteNumber(actions.indoor_shade_closed))
    || ![0,1].includes(finiteNumber(actions.vent_open)) || actions.action_knowledge !== 'as_of_snapshot_not_outcome_confirmation'
    || !['warm','spring','fall_charge','winter','unknown'].includes(actions.mode)
    || typeof actions.vent_provenance !== 'string' || !actions.vent_provenance.length || actions.vent_provenance.length > 80) throw new TypeError('unsupported source actions');
  if (!Number.isInteger(numeric.horizon_hours) || numeric.horizon_hours < 1 || numeric.horizon_hours > 72 || !Array.isArray(numeric.trajectory)
    || numeric.trajectory.length !== numeric.horizon_hours) throw new TypeError('incomplete original trajectory');
  const trajectory = numeric.trajectory.map((point,index) => {
    exactObject(point, fields('at','air_f','mass_f'));const at = timestamp(point.at);
    if (at.epochMicros !== issue.epochMicros + BigInt(index + 1) * HOUR_US) throw new TypeError('original target differs');
    return { atMs:at.epochMs, hallwayF:physical(point.air_f), massF:physical(point.mass_f), lowF:null, highF:null, actions:[] };
  });
  let uncertaintyMode = 'none';
  if (numeric.schema.endsWith('/v1')) {
    if (active || numeric.prediction_intervals !== null || release.calibrationSha256 !== null) throw new TypeError('uncalibrated release');
  } else {
    if (!Array.isArray(numeric.prediction_intervals) || numeric.prediction_intervals.length !== 4 || release.calibrationSha256 === null) throw new TypeError('original uncertainty missing');
    [1,6,12,24].forEach((hours,index) => {
      const band = exactObject(numeric.prediction_intervals[index], fields('at','horizon_hours','lower_air_f','upper_air_f','nominal_coverage','regime','calibration_sha256'));
      if (band.horizon_hours !== hours || hours > trajectory.length || timestamp(band.at).epochMicros !== issue.epochMicros + BigInt(hours)*HOUR_US
        || band.nominal_coverage !== .9 || band.calibration_sha256 !== release.calibrationSha256 || band.regime !== ({ warm:'warm',winter:'winter',spring:'shoulder',fall_charge:'shoulder' })[actions.mode]
        || !(finiteNumber(band.lower_air_f) <= trajectory[hours-1].hallwayF && trajectory[hours-1].hallwayF <= finiteNumber(band.upper_air_f))) throw new TypeError('invalid original interval');
      finiteNumber(band.upper_air_f - band.lower_air_f);trajectory[hours-1].lowF = band.lower_air_f;trajectory[hours-1].highF = band.upper_air_f;
    });
    uncertaintyMode = 'calibrated_targets';
  }
  const air = trajectory.map((p) => p.hallwayF);
  const localHour = new Intl.DateTimeFormat('en-US', { timeZone:'America/Denver', hour:'2-digit', hourCycle:'h23' });
  const morning = trajectory.find((p) => localHour.format(p.atMs) === '06');
  return { ...parsed, modelCreatedAtMs:created.epochMs, trainedThroughMs:trained.epochMs,
    modelAgeHours:(issue.epochMs-created.epochMs)/3600000, trainingDataAgeHours:(issue.epochMs-trained.epochMs)/3600000,
    forecast:{ hallwayHighF:Math.max(...air), hallwayLowF:Math.min(...air), morningMassF:morning?.massF ?? null },
    trajectory, observed:[], baselineWindow:{ opened:null, closed:null }, candidateWindow:null,
    effect:{ morningMassDeltaF:null, hallwayPeakDeltaF:null }, uncertaintyMode,
    baselineVentAssumption:actions.vent_open === 0 ? 'No venting assumed' : 'Venting assumed from origin state' };
}
