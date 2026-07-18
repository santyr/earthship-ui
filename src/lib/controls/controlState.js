import { CURRENT_RELEASE_MODE, isDirectControlAllowed } from '../releaseMode.js';

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

function providerAvailability(raw) {
  const statusInfo = raw?.statusInfo ?? raw;
  const status = typeof statusInfo?.status === 'string'
    ? statusInfo.status.trim().toUpperCase()
    : null;
  const statusDetail = typeof statusInfo?.statusDetail === 'string'
    ? statusInfo.statusDetail.trim()
    : '';
  const description = typeof statusInfo?.description === 'string'
    ? statusInfo.description.trim()
    : '';
  const detail = description || (statusDetail !== 'NONE' ? statusDetail : '');

  if (!status) {
    return { online: false, reason: 'Provider Thing status unavailable — read-only', detail: '' };
  }
  if (status !== 'ONLINE') {
    return { online: false, reason: `Provider ${status} — read-only`, detail };
  }
  return { online: true, reason: '', detail: '' };
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
    releaseMode = CURRENT_RELEASE_MODE,
    providerOnline = {},
    capabilities = {},
    ownerTransitioning = false,
    ownerBusy = false,
  } = context;

  if (!control) return unavailable('Control unavailable');
  if (connection !== 'live') return unavailable('openHAB unavailable');

  const value = binaryValue(items[control.stateItem]);
  if (control.kind === 'binary') {
    const provider = providerAvailability(providerOnline[control.stateItem]);
    if (!provider.online) {
      return unavailable(provider.reason, provider.detail);
    }
    if (!value) return unavailable('State unavailable');
    if (!isDirectControlAllowed(control, releaseMode)) {
      return disabledStatus(value, 'Maintenance release — commands unavailable');
    }
    return enabledState(value);
  }

  if (!value) return unavailable('State unavailable');

  if (control.kind === 'binary-policy') {
    const health = circadianHealth(items[control.healthItem]);
    if (!isDirectControlAllowed(control, releaseMode)) {
      return disabledStatus(value, 'Maintenance release — commands unavailable', health);
    }
    return enabledState(value, health);
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
    const provider = providerAvailability(providerOnline[control.stateItem]);
    if (!provider.online) {
      return unavailable(provider.reason, provider.detail || detail);
    }
    return disabledStatus(value, 'Owner request submission unavailable — status only', { detail });
  }

  if (control.kind === 'action') {
    const reason = capabilities[control.capability] === true
      ? 'Feeder request submission unavailable — actuator status only'
      : 'Feeder request channel unavailable — actuator status only';
    return disabledStatus(value, reason);
  }

  if (control.kind === 'safety-request') {
    const reason = capabilities[control.capability] === true
      ? 'Circulation request submission unavailable — actuator status only'
      : 'Circulation request channel unavailable — actuator status only';
    return disabledStatus(value, reason);
  }

  if (control.kind === 'policy-status') {
    const reason = capabilities[control.capability] === true
      ? 'Owner request submission unavailable — status only'
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
