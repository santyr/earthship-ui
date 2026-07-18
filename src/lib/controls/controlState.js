export const CONTROL_PHASES = Object.freeze([
  'confirmed',
  'unavailable',
  'holding',
  'pending',
  'accepted',
  'error',
  'unknown',
]);

const INVALID_STATES = new Set(['', 'NULL', 'UNDEF']);

export function binaryValue(value) {
  if (value === undefined || value === null) return null;
  const normalized = String(value).trim().toUpperCase();
  if (INVALID_STATES.has(normalized)) return null;
  return normalized === 'ON' || normalized === 'OFF' ? normalized : null;
}

function unavailable(reason, detail = '') {
  return {
    phase: 'unavailable',
    enabled: false,
    value: null,
    valueLabel: 'Unavailable',
    reason,
    detail,
  };
}

function circadianHealth(raw) {
  if (raw === undefined || raw === null || INVALID_STATES.has(String(raw).trim().toUpperCase())) {
    return { healthLabel: 'Health unavailable', detail: 'No circadian result reported' };
  }
  const detail = String(raw);
  const degraded = /(skip|backoff|degrad|fail|error|offline|unavailable)/i.test(detail);
  return { healthLabel: degraded ? 'Degraded' : 'Healthy', detail };
}

function couplingDetail(value) {
  const state = binaryValue(value);
  return state ? `Feeder policy override ${state}` : 'Feeder policy override unavailable';
}

function enabledState(value, extras = {}) {
  return {
    phase: 'confirmed',
    enabled: true,
    value,
    valueLabel: value,
    reason: '',
    detail: '',
    ...extras,
  };
}

function disabledStatus(value, reason, extras = {}) {
  return {
    phase: 'confirmed',
    enabled: false,
    value,
    valueLabel: value,
    reason,
    detail: '',
    ...extras,
  };
}

export function deriveControlState(control, context = {}) {
  const {
    items = {},
    connection = 'connecting',
    providerOnline = {},
    capabilities = {},
    ownerTransitioning = false,
    ownerBusy = false,
  } = context;

  if (!control) return unavailable('Control unavailable');
  if (connection !== 'live') return unavailable('openHAB unavailable');

  const value = binaryValue(items[control.stateItem]);
  if (!value) return unavailable('State unavailable');

  if (control.kind === 'binary-policy') {
    return enabledState(value, circadianHealth(items[control.healthItem]));
  }

  if (control.kind === 'binary') {
    if (providerOnline[control.stateItem] !== true) {
      return unavailable('Provider health unavailable');
    }
    return enabledState(value);
  }

  if (control.kind === 'owned-binary') {
    const detail = control.couplingItem ? couplingDetail(items[control.couplingItem]) : '';
    const override = binaryValue(items.OverrideSwitch);

    if (override === 'ON') {
      return disabledStatus(value, 'Owned by Night Load Override', { detail });
    }
    if (!override) {
      return disabledStatus(value, 'Override status unavailable — read-only', { detail });
    }
    if (ownerTransitioning) {
      return disabledStatus(value, 'Night Load Override transition in progress', { detail });
    }
    if (ownerBusy) {
      return disabledStatus(value, 'Night Load Override owner busy', { detail });
    }
    if (capabilities[control.capability] !== true) {
      return disabledStatus(value, 'Owner request channel unavailable — status only', { detail });
    }
    if (providerOnline[control.stateItem] !== true) {
      return unavailable('Provider health unavailable', detail);
    }
    return enabledState(value, { detail });
  }

  if (control.kind === 'action') {
    const reason = capabilities[control.capability] === true
      ? 'Ready'
      : 'Feeder request channel unavailable — actuator status only';
    return disabledStatus(value, reason);
  }

  if (control.kind === 'safety-request') {
    const reason = capabilities[control.capability] === true
      ? 'Ready'
      : 'Circulation request channel unavailable — actuator status only';
    return disabledStatus(value, reason);
  }

  if (control.kind === 'policy-status') {
    const reason = capabilities[control.capability] === true
      ? 'Ready'
      : 'Owner request channel unavailable — status only';
    return disabledStatus(value, reason);
  }

  return unavailable('Control kind unavailable');
}

const OUTCOME_PRESENTATIONS = Object.freeze({
  confirmed: { label: 'Confirmed', tone: 'success' },
  unavailable: { label: 'Unavailable', tone: 'muted' },
  holding: { label: 'Hold…', tone: 'active' },
  pending: { label: 'Sending…', tone: 'active' },
  accepted: { label: 'Accepted', tone: 'success' },
  error: { label: 'Failed', tone: 'error' },
  unknown: { label: 'Outcome unknown', tone: 'warning' },
});

export function outcomePresentation(phase) {
  return OUTCOME_PRESENTATIONS[phase] ?? OUTCOME_PRESENTATIONS.unknown;
}
