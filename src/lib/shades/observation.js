// Current adapter v2 observations. Retained v1 data remains readable as history;
// only reconciled composite liveness can expose a current reported position.
export const SHADE_HEALTH_MAX_AGE_MS = 90_000;
const MAX_REPORT_AGE_MS = 30 * 60 * 1000;
const text = value => typeof value === 'string' && value.length > 0 && value.length <= 256;
const position = value => Number.isInteger(value) && value >= 0 && value <= 100;
const timestamp = value => typeof value === 'number' && Number.isFinite(value);
const generation = value => Number.isSafeInteger(value) && value >= 0;
function object(raw) {
  if (typeof raw !== 'string' || raw.length > 8192) return null;
  try { const value = JSON.parse(raw); return value && typeof value === 'object' && !Array.isArray(value) ? value : null; }
  catch { return null; }
}
const sameSession = (a, b) => text(a?.adapter_session_id) && a.adapter_session_id === b?.adapter_session_id
  && generation(a.source_generation) && a.source_generation === b?.source_generation;
const recent = (at, now, maximum) => timestamp(at) && now - at * 1000 >= -5000 && now - at * 1000 <= maximum;

export function currentShadeObservation(slot, states, connection, nowMs = Date.now(), providers = {}) {
  const mapping = ['sourceIdentity','commissionedEpoch','positionItem', 'availabilityItem', 'stateItem', 'serviceAvailabilityItem',
    'bridgeAvailabilityItem', 'serviceStateItem', 'bridgeStateItem', 'serviceThingUID'];
  if (!mapping.every(key => text(slot?.[key]))) return { state: 'unmapped', label: 'Awaiting Item mapping', position: null };
  const report = object(states?.[slot.stateItem]);
  const known = report?.source === 'motor_report' && [1, 2].includes(report.schema_version)
    && position(report.reported_position) && timestamp(report.report_received_at);
  const lastKnownPosition = known ? report.reported_position : null;
  const base = { position: null, lastKnownPosition, requestedTarget: report?.requested_target ?? null,
    movementState: text(report?.movement_state) ? report.movement_state : 'unknown', actionQualified: false,
    observationId: null, measurementTimeKnown: false, actor: 'unknown' };
  const unavailable = reason => ({ ...base, state: known ? 'last_known' : 'unavailable',
    label: known ? `Last known ${100-lastKnownPosition}% open · ${reason}` : reason });
  if (connection !== 'live' || !Number.isFinite(nowMs)) return unavailable('openHAB unavailable');
  if (providers?.[slot.serviceThingUID]?.status !== 'ONLINE') return unavailable('Adapter provider unavailable');
  for (const [key, label] of [['serviceAvailabilityItem','Adapter unavailable'],['bridgeAvailabilityItem','Bridge unavailable'],['availabilityItem','Shade unavailable']]) {
    if (states?.[slot[key]] !== 'ON') return unavailable(label);
  }
  const service = object(states?.[slot.serviceStateItem]), bridge = object(states?.[slot.bridgeStateItem]);
  if (service?.schema_version !== 2 || bridge?.schema_version !== 2 || !sameSession(service, bridge)
      || service.ready !== true || bridge.reachable !== true
      || !recent(service.emitted_at, nowMs, SHADE_HEALTH_MAX_AGE_MS)
      || !recent(bridge.emitted_at, nowMs, SHADE_HEALTH_MAX_AGE_MS)) return unavailable('Current adapter session unavailable');
  if (!known || report.schema_version !== 2 || !sameSession(report, service)) return unavailable('Awaiting current-session report');
  const observation = report.observation;
  if (!sameSession(observation, report) || !text(observation?.id)
      || !/^[0-9a-f]{64}$/.test(slot.sourceIdentity) || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(slot.commissionedEpoch)
      || observation.source_identity_sha256 !== slot.sourceIdentity || observation.commissioned_epoch !== slot.commissionedEpoch
      || !text(observation.device_id) || !text(observation.bridge_id) || observation.bridge_id !== bridge.bridge_id
      || observation.device_type !== '10000000'
      || observation.received_at !== report.report_received_at
      || !timestamp(observation.validated_at) || observation.validated_at < observation.received_at
      || observation.measurement_time_known !== false || observation.hardware_boot_known !== false
      || observation.origin !== 'unknown') return unavailable('Unqualified report identity');
  if (report.usable !== true || report.stale !== false || report.current_position !== report.reported_position
      || report.movement_state !== 'stationary_reported'
      || !recent(report.report_received_at, nowMs, MAX_REPORT_AGE_MS)) return unavailable('Position uncertain or stale');
  const scalar = typeof states?.[slot.positionItem] === 'string' && /^(?:100|[1-9]?\d)$/.test(states[slot.positionItem])
    ? Number(states[slot.positionItem]) : null;
  if (scalar !== report.reported_position) return unavailable('Position sources disagree');
  const value = report.reported_position;
  return { ...base, state: 'reported', position: value, openPercent: 100-value,
    label: value === 0 ? 'Open' : value === 100 ? 'Closed' : `${100-value}% open`,
    observedAtMs: report.report_received_at * 1000, observationId: observation.id,
    adapterSession: report.adapter_session_id, sourceGeneration: report.source_generation };
}
