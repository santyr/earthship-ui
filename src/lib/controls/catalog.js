const directBinary = (label, stateItem, extra = {}) => ({
  label,
  kind: 'binary',
  stateItem,
  commandItem: stateItem,
  requiresProviderHealth: true,
  ...extra,
});

const ownedBinary = (label, stateItem, device, extra = {}) => ({
  label,
  kind: 'owned-binary',
  stateItem,
  device,
  requestItem: 'NightLoadDevice_Request',
  resultItem: 'NightLoadDevice_Result',
  capability: 'night-load-owner-v1',
  requiresProviderHealth: true,
  ...extra,
});

export const CONTROL_CATALOG = Object.freeze({
  living1: directBinary('Living Room 1', 'living_room_1_Switch'),
  living2: directBinary('Living Room 2', 'living_room_2_Switch'),
  living3: directBinary('Living Room 3', 'LED_living_room_1_Switch'),
  circadian: {
    label: 'Circadian',
    kind: 'binary-policy',
    stateItem: 'LivingRoomCircadian_Enable',
    commandItem: 'LivingRoomCircadian_Enable',
    healthItem: 'LivingRoomCircadian_LastResult',
  },
  dishwasher: ownedBinary('Dishwasher', 'Dish_Washer_Power', 'dishwasher'),
  shureflo: ownedBinary('Shureflo Pump', 'ShurefloPump_Power', 'shureflo'),
  goatCam: ownedBinary('Goat Cam', 'Goat_Plugs_Outlet1_Switch', 'goat-cam', {
    couplingItem: 'FeederOverride',
  }),
  feedOnce: {
    label: 'Feed once',
    kind: 'action',
    stateItem: 'Goat_Plugs_Outlet2_Switch',
    requestItem: 'GoatFeeder_ManualRequest',
    resultItem: 'GoatFeeder_ManualResult',
    capability: 'feeder-request-v1',
  },
  circulation: {
    label: 'Request circulation',
    kind: 'safety-request',
    stateItem: 'SouthOutlet_Outlet2_Switch',
    requestItem: 'SouthOutlet_ManualRequest',
    resultItem: 'SouthOutlet_ManualResult',
    capability: 'greywater-request-v1',
  },
  override: {
    label: 'Night Load Override',
    kind: 'policy-status',
    stateItem: 'OverrideSwitch',
    requestItem: 'NightLoadOverride_Request',
    resultItem: 'NightLoadOverride_Result',
    capability: 'night-load-owner-v1',
  },
});

export const UNSAFE_DIRECT_COMMAND_ITEMS = Object.freeze([
  'Goat_Plugs_Outlet2_Switch',
  'SouthOutlet_Outlet2_Switch',
  'OverrideSwitch',
  'Dish_Washer_Power',
  'ShurefloPump_Power',
  'Goat_Plugs_Outlet1_Switch',
]);

export function commandTargetFor(control) {
  if (!control?.commandItem) return null;
  if (!['binary', 'binary-policy'].includes(control.kind)) return null;
  if (UNSAFE_DIRECT_COMMAND_ITEMS.includes(control.commandItem)) return null;
  return control.commandItem;
}

export const DIRECT_COMMAND_ITEMS = Object.freeze(
  Object.values(CONTROL_CATALOG)
    .map(commandTargetFor)
    .filter(Boolean),
);

export function validateControlCatalog() {
  const errors = [];
  const required = ['label', 'kind', 'stateItem'];

  for (const [id, control] of Object.entries(CONTROL_CATALOG)) {
    for (const field of required) {
      if (!control[field]) errors.push(`${id}: missing ${field}`);
    }
    const target = commandTargetFor(control);
    if (target && UNSAFE_DIRECT_COMMAND_ITEMS.includes(target)) {
      errors.push(`${id}: unsafe direct target ${target}`);
    }
    if (
      ['owned-binary', 'action', 'safety-request', 'policy-status'].includes(control.kind)
      && (!control.requestItem || !control.resultItem || !control.capability)
    ) {
      errors.push(`${id}: correlated request contract incomplete`);
    }
  }

  return errors;
}

export function controlById(id) {
  return CONTROL_CATALOG[id] ?? null;
}
