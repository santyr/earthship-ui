import { commandTargetFor } from './controls/catalog.js';

export const RELEASE_MODES = Object.freeze([
  'maintenance',
  'safe-compat',
  'full',
]);

const RELEASE_MODE_SET = new Set(RELEASE_MODES);

export function resolveReleaseMode(value) {
  return RELEASE_MODE_SET.has(value) ? value : 'maintenance';
}

export function isDirectControlAllowed(control, releaseMode) {
  const mode = resolveReleaseMode(releaseMode);
  if (!['safe-compat', 'full'].includes(mode)) return false;
  return commandTargetFor(control) !== null;
}

const configuredReleaseMode = typeof __EARTHSHIP_RELEASE_MODE__ === 'string'
  ? __EARTHSHIP_RELEASE_MODE__
  : 'maintenance';

export const CURRENT_RELEASE_MODE = resolveReleaseMode(configuredReleaseMode);
