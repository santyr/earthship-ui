import { describe, expect, it } from 'vitest';
import {
  OVERVIEW_PATH,
  PROTECTED_ACTUATOR_ITEMS,
  assertAllowedMainUiRequest,
  auditHouseholdPage,
  buildSafeOverview,
} from '../../scripts/openhab-mainui-safety.mjs';

const unsafeOverview = {
  uid: 'overview',
  component: 'oh-layout-page',
  config: { label: 'Overview' },
  slots: {
    default: [{
      component: 'oh-grid-row',
      slots: {
        default: [
          {
            component: 'oh-toggle-card',
            config: {
              item: 'SouthOutlet_Outlet2_Switch',
              title: 'Fountain',
              icon: 'iconify:mdi:fountain',
              noBorder: true,
              noShadow: true,
            },
          },
          {
            component: 'oh-toggle-card',
            config: { item: 'living_room_1_Switch', title: 'Living Room 1' },
          },
        ],
      },
    }],
  },
};

describe('OpenHAB household MainUI safety migration', () => {
  it('detects a direct protected-actuator toggle without flagging ordinary lights', () => {
    expect(PROTECTED_ACTUATOR_ITEMS).toContain('Goat_Plugs_Outlet2_Switch');
    expect(PROTECTED_ACTUATOR_ITEMS).toContain('SouthOutlet_Outlet2_Switch');
    expect(auditHouseholdPage(unsafeOverview)).toEqual([
      expect.objectContaining({
        component: 'oh-toggle-card',
        item: 'SouthOutlet_Outlet2_Switch',
      }),
    ]);
  });

  it('replaces only the Fountain toggle with a truthful read-only analyzer card', () => {
    const { page, changed } = buildSafeOverview(unsafeOverview);
    const cards = page.slots.default[0].slots.default;

    expect(changed).toBe(1);
    expect(cards[0]).toMatchObject({
      component: 'oh-label-card',
      config: {
        action: 'analyzer',
        actionAnalyzerItems: ['SouthOutlet_Outlet2_Switch'],
        item: 'SouthOutlet_Outlet2_Switch',
        title: 'Fountain',
        icon: 'iconify:mdi:fountain',
        noBorder: true,
        noShadow: true,
      },
    });
    expect(cards[0].config.label).toContain('SouthOutlet_Outlet2_Switch');
    expect(cards[1]).toEqual(unsafeOverview.slots.default[0].slots.default[1]);
    expect(auditHouseholdPage(page)).toEqual([]);
  });

  it('is idempotent after the protected control is read-only', () => {
    const first = buildSafeOverview(unsafeOverview);
    const second = buildSafeOverview(first.page);

    expect(second.changed).toBe(0);
    expect(second.page).toEqual(first.page);
  });

  it('allows only exact Overview GET/PUT requests and no item commands', () => {
    expect(OVERVIEW_PATH).toBe('/rest/ui/components/ui_page/overview');
    expect(() => assertAllowedMainUiRequest('GET', OVERVIEW_PATH)).not.toThrow();
    expect(() => assertAllowedMainUiRequest('PUT', OVERVIEW_PATH)).not.toThrow();
    expect(() => assertAllowedMainUiRequest(
      'GET',
      '/rest/ui/components/ui_page',
    )).not.toThrow();

    expect(() => assertAllowedMainUiRequest(
      'POST',
      '/rest/items/SouthOutlet_Outlet2_Switch',
    )).toThrow(/denied/i);
    expect(() => assertAllowedMainUiRequest(
      'POST',
      '/rest/rules/example/runnow',
    )).toThrow(/denied/i);
    expect(() => assertAllowedMainUiRequest(
      'PUT',
      '/rest/ui/components/ui_page/earthship',
    )).toThrow(/denied/i);
  });
});
