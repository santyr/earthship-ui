// Explicit provisional production contract; no calibrated or control authority.
export function validateProvisionalPublication(payload, { exactObject, finiteNumber, timestamp }) {
  const fields = (...keys) => new Set(keys);
  const sha = value => { if (typeof value !== 'string' || !/^[0-9a-f]{64}$/.test(value)) throw new TypeError('invalid provisional identity'); return value; };
  const physical = value => { finiteNumber(value); if (value < -40 || value > 140) throw new TypeError('physical temperature exceeded'); return value; };
  const HOUR = 3600000000n;
  exactObject(payload, fields('schema','version','status','generatedAt','validUntil','model','forecast','confidence','graduation','automaticActuation','reasons'));
  if (payload.schema !== 'earthship-provisional-thermal-publication/v1' || payload.version !== 8 || !['provisional','unavailable'].includes(payload.status)) throw new TypeError('unsupported provisional contract');
  const issued = timestamp(payload.generatedAt), valid = timestamp(payload.validUntil);
  if (valid.epochMicros - issued.epochMicros !== 900000000n) throw new TypeError('bounded provisional expiry required');
  exactObject(payload.confidence, fields('grade','actionLabels'));
  exactObject(payload.graduation, fields('forecastQualified','stabilityAssessed','calibrationAssessed'));
  if (payload.automaticActuation !== false || Object.values(payload.graduation).some(x => x !== false) || payload.confidence.actionLabels !== 'withheld'
      || payload.confidence.grade !== (payload.status === 'provisional' ? 'low' : 'unavailable')) throw new TypeError('provisional authority changed');
  if (!Array.isArray(payload.reasons) || payload.reasons.length > 32 || payload.reasons.some(x => typeof x !== 'string' || !x.length || x.length > 240)) throw new TypeError('bounded provisional reasons required');
  const parsed = { mode:payload.status, confidence:payload.confidence.grade, generatedAtMs:issued.epochMs, generatedAtMicros:issued.epochMicros, validUntilMicros:valid.epochMicros,
    qualifiedAtMs:null, expiresAtMs:null, reasons:payload.reasons, actionConfidence:'withheld' };
  if (payload.status === 'unavailable') {
    if (payload.model !== null || payload.forecast !== null) throw new TypeError('fabricated unavailable forecast');
    return parsed;
  }
  const model = exactObject(payload.model, fields('artifactSha256','runtimeSha256','createdAt','trainedThrough','fitExecuted','independentOriginDates','horizonSupport','regularizationStrength'));
  sha(model.artifactSha256);sha(model.runtimeSha256);
  const created = timestamp(model.createdAt), trained = timestamp(model.trainedThrough);
  if (!(trained.epochMicros <= created.epochMicros && created.epochMicros <= issued.epochMicros) || model.fitExecuted !== true
      || !Number.isInteger(model.independentOriginDates) || model.independentOriginDates < 1 || model.independentOriginDates > 256 || model.regularizationStrength !== 1) throw new TypeError('invalid provisional learning evidence');
  exactObject(model.horizonSupport, fields('1','6','12','24'));
  if (Object.values(model.horizonSupport).some(x => !Number.isInteger(x) || x < 0 || x > 64) || Object.values(model.horizonSupport).reduce((a,b) => a+b,0) < 1) throw new TypeError('invalid provisional support');
  const numeric = exactObject(payload.forecast, fields('schema','status','generated_at','artifact_sha256','runtime_sha256','horizon_hours','initial','origin_actions','trajectory','confidence','prediction_intervals','advice','graduated','automatic_actuation'));
  if (numeric.schema !== 'earthship-provisional-thermal-forecast/v1' || numeric.status !== 'provisional' || numeric.confidence !== 'low' || numeric.graduated !== false || numeric.automatic_actuation !== false
      || numeric.prediction_intervals !== null || !Array.isArray(numeric.advice) || numeric.advice.length || timestamp(numeric.generated_at).epochMicros !== issued.epochMicros
      || numeric.artifact_sha256 !== model.artifactSha256 || numeric.runtime_sha256 !== model.runtimeSha256) throw new TypeError('provisional numeric source changed');
  exactObject(numeric.initial, fields('air_f','mass_f','outdoor_f'));Object.values(numeric.initial).forEach(physical);
  const actions = exactObject(numeric.origin_actions, fields('indoor_shade_closed','outdoor_shade_present','vent_open','vent_provenance','mode','action_knowledge'));
  if (actions.outdoor_shade_present !== 1 || ![0,1].includes(actions.indoor_shade_closed) || ![0,1].includes(actions.vent_open) || actions.action_knowledge !== 'as_of_snapshot_not_outcome_confirmation'
      || !['warm','spring','fall_charge','winter','unknown'].includes(actions.mode) || typeof actions.vent_provenance !== 'string' || !actions.vent_provenance.length || actions.vent_provenance.length > 80) throw new TypeError('unsupported provisional actions');
  if (!Number.isInteger(numeric.horizon_hours) || numeric.horizon_hours < 1 || numeric.horizon_hours > 72 || !Array.isArray(numeric.trajectory) || numeric.trajectory.length !== numeric.horizon_hours) throw new TypeError('complete provisional trajectory required');
  const trajectory = numeric.trajectory.map((point,index) => {
    exactObject(point, fields('at','air_f','mass_f'));const at = timestamp(point.at);
    if (at.epochMicros !== issued.epochMicros + BigInt(index+1)*HOUR) throw new TypeError('provisional target differs');
    return { atMs:at.epochMs,hallwayF:physical(point.air_f),massF:physical(point.mass_f),lowF:null,highF:null,actions:[] };
  });
  const air = trajectory.map(x => x.hallwayF), localHour = new Intl.DateTimeFormat('en-US',{timeZone:'America/Denver',hour:'2-digit',hourCycle:'h23'});
  const morning = trajectory.find(x => localHour.format(x.atMs) === '06');
  return { ...parsed,artifactRevision:model.artifactSha256,modelCreatedAtMs:created.epochMs,trainedThroughMs:trained.epochMs,
    modelAgeHours:(issued.epochMs-created.epochMs)/3600000,trainingDataAgeHours:(issued.epochMs-trained.epochMs)/3600000,
    forecast:{hallwayHighF:Math.max(...air),hallwayLowF:Math.min(...air),morningMassF:morning?.massF ?? null},trajectory,observed:[],
    uncertaintyMode:'uncalibrated',baselineWindow:{opened:null,closed:null},candidateWindow:null,effect:{morningMassDeltaF:null,hallwayPeakDeltaF:null},
    baselineVentAssumption:actions.vent_open === 0 ? 'No venting assumed' : 'Venting assumed from origin state' };
}
