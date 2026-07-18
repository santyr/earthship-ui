#!/usr/bin/env node

export const OVERVIEW_PATH = '/rest/ui/components/ui_page/overview';
export const PROTECTED_ACTUATOR_ITEMS = Object.freeze([
  'Goat_Plugs_Outlet2_Switch',
  'SouthOutlet_Outlet2_Switch',
]);

const ALLOWED_REQUESTS = new Set([
  'GET /rest/ui/components/ui_page',
  `GET ${OVERVIEW_PATH}`,
  `PUT ${OVERVIEW_PATH}`,
]);

const DIRECT_CONTROL_COMPONENTS = new Set([
  'oh-toggle-card',
  'oh-slider-card',
  'oh-stepper-card',
  'oh-knob',
  'oh-button',
]);

export function assertAllowedMainUiRequest(method, path) {
  const key = `${String(method).toUpperCase()} ${path}`;
  if (!ALLOWED_REQUESTS.has(key)) {
    throw new Error(`Denied OpenHAB request: ${key}`);
  }
}

function visitComponents(node, visitor, path = []) {
  if (!node || typeof node !== 'object') return;
  if (typeof node.component === 'string') visitor(node, path);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'config') continue;
    if (Array.isArray(value)) {
      value.forEach((entry, index) => visitComponents(entry, visitor, [...path, key, index]));
    } else if (value && typeof value === 'object') {
      visitComponents(value, visitor, [...path, key]);
    }
  }
}

function isDirectProtectedControl(node) {
  const item = node?.config?.item;
  if (!PROTECTED_ACTUATOR_ITEMS.includes(item)) return false;
  return DIRECT_CONTROL_COMPONENTS.has(node.component) || node?.config?.action === 'command';
}

export function auditHouseholdPage(page) {
  const findings = [];
  visitComponents(page, (node, path) => {
    if (!isDirectProtectedControl(node)) return;
    findings.push({
      path,
      component: node.component,
      item: node.config.item,
      title: node.config.title ?? '',
    });
  });
  return findings;
}

function safeFountainCard(original) {
  return {
    component: 'oh-label-card',
    config: {
      ...structuredClone(original.config),
      action: 'analyzer',
      actionAnalyzerItems: ['SouthOutlet_Outlet2_Switch'],
      footer: "=(items.SouthOutlet_AutoStatus.state === 'NULL' || items.SouthOutlet_AutoStatus.state === 'UNDEF') ? 'Automation unavailable' : (items.SouthOutlet_AutoStatus.state+'').split(',')[0].replace('reason=','').replace(/_/g,' ')",
      iconColor: "=(items.SouthOutlet_Outlet2_Switch.state === 'ON') ? 'blue' : (items.SouthOutlet_Outlet2_Switch.state === 'OFF') ? 'gray' : '#f59e0b'",
      label: "=(items.SouthOutlet_Outlet2_Switch.state === 'ON') ? 'Running' : (items.SouthOutlet_Outlet2_Switch.state === 'OFF') ? 'Idle' : 'Unavailable'",
    },
  };
}

export function buildSafeOverview(page) {
  const desired = structuredClone(page);
  let changed = 0;
  visitComponents(desired, (node) => {
    if (!isDirectProtectedControl(node)) return;
    if (node.config.item !== 'SouthOutlet_Outlet2_Switch') {
      throw new Error(`No approved read-only replacement for ${node.config.item}`);
    }
    const replacement = safeFountainCard(node);
    for (const key of Object.keys(node)) delete node[key];
    Object.assign(node, replacement);
    changed += 1;
  });
  return { page: desired, changed };
}
