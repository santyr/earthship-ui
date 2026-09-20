// Narrow managed-rule transformation: no script, actuator or hydrology changes.
export const DAYLIGHT_TRIGGERS = [
  { id: 'earthship-greywater-sun', type: 'core.ItemStateChangeTrigger',
    configuration: { itemName: 'Sun_Position_Elevation' } },
  { id: 'cron', type: 'timer.GenericCronTrigger',
    configuration: { cronExpression: '0 * * * * ?' } },
];

export function withoutFixedGreywaterWindow(conditions = []) {
  const fixed = conditions.filter(c => c.type === 'core.TimeOfDayCondition');
  if (fixed.length > 1 || fixed.some(c => c.configuration?.startTime !== '08:00'
      || c.configuration?.endTime !== '20:00')) {
    throw new Error('unreviewed greywater time condition');
  }
  return structuredClone(conditions.filter(c => c.type !== 'core.TimeOfDayCondition'));
}

export function buildGreywaterDaylightRule(rule, expectedSource) {
  if (rule?.uid !== 'hex_southoutlet_cycle' || !Array.isArray(rule.triggers)
      || rule.actions?.length !== 1 || typeof expectedSource !== 'string'
      || !expectedSource.includes('EARTHSHIP_SOUTHOUTLET_VERSION')
      || rule.actions[0].configuration?.script !== expectedSource) {
    throw new Error('reviewed live greywater source required');
  }
  const result = structuredClone(rule);
  result.conditions = withoutFixedGreywaterWindow(rule.conditions);
  for (const trigger of DAYLIGHT_TRIGGERS) {
    const index = result.triggers.findIndex(t => t.id === trigger.id);
    if (index < 0) result.triggers.push(structuredClone(trigger));
    else {
      const existing = result.triggers[index];
      const allowed = existing.type === trigger.type && (trigger.id === 'cron'
        ? ['0 */5 * * * ?', '0 * * * * ?'].includes(existing.configuration?.cronExpression)
        : existing.configuration?.itemName === 'Sun_Position_Elevation');
      if (!allowed) throw new Error('conflicting greywater trigger');
      result.triggers[index] = structuredClone(trigger);
    }
  }
  return result;
}
