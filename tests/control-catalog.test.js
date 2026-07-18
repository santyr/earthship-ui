import { describe, expect, it } from 'vitest';
import {
  CONTROL_CATALOG,
  DIRECT_COMMAND_ITEMS,
  UNSAFE_DIRECT_COMMAND_ITEMS,
  commandTargetFor,
  validateControlCatalog,
} from '../src/lib/controls/catalog.js';

describe('control catalog', () => {
  it('models every visible control with an explicit kind and truthful label', () => {
    expect(Object.fromEntries(
      Object.entries(CONTROL_CATALOG).map(([id, control]) => [
        id,
        [control.label, control.kind, control.stateItem],
      ]),
    )).toEqual({
      living1: ['Living Room 1', 'binary', 'living_room_1_Switch'],
      living2: ['Living Room 2', 'binary', 'living_room_2_Switch'],
      living3: ['Living Room 3', 'binary', 'LED_living_room_1_Switch'],
      circadian: ['Circadian', 'binary-policy', 'LivingRoomCircadian_Enable'],
      dishwasher: ['Dishwasher', 'owned-binary', 'Dish_Washer_Power'],
      shureflo: ['Shureflo Pump', 'owned-binary', 'ShurefloPump_Power'],
      goatCam: ['Goat Cam', 'owned-binary', 'Goat_Plugs_Outlet1_Switch'],
      feedOnce: ['Feed once', 'action', 'Goat_Plugs_Outlet2_Switch'],
      circulation: ['Request circulation', 'safety-request', 'SouthOutlet_Outlet2_Switch'],
      override: ['Night Load Override', 'policy-status', 'OverrideSwitch'],
    });
  });

  it('records the verified provider Thing for every physical control state', () => {
    expect(Object.fromEntries(
      Object.entries(CONTROL_CATALOG)
        .filter(([, control]) => control.providerThingUid)
        .map(([id, control]) => [id, control.providerThingUid]),
    )).toEqual({
      living1: 'tplinksmarthome:kl125:E7FA31',
      living2: 'tplinksmarthome:kl125:E62B6D',
      living3: 'tplinksmarthome:kl125:E7CAD9',
      dishwasher: 'tplinksmarthome:hs103:a34b4957dc',
      shureflo: 'tplinksmarthome:hs103:08482dd378',
      goatCam: 'tplinksmarthome:ep40:3cb500a208',
      feedOnce: 'tplinksmarthome:ep40:3cb500a208',
      circulation: 'tplinksmarthome:kp200:7BD449',
    });
  });

  it('keeps feeder, greywater, override, and owned-load actuators out of direct command paths', () => {
    expect(UNSAFE_DIRECT_COMMAND_ITEMS).toEqual(expect.arrayContaining([
      'Goat_Plugs_Outlet2_Switch',
      'SouthOutlet_Outlet2_Switch',
      'OverrideSwitch',
      'Dish_Washer_Power',
      'ShurefloPump_Power',
      'Goat_Plugs_Outlet1_Switch',
    ]));

    expect(DIRECT_COMMAND_ITEMS).toEqual([
      'living_room_1_Switch',
      'living_room_2_Switch',
      'LED_living_room_1_Switch',
      'LivingRoomCircadian_Enable',
    ]);
    expect(DIRECT_COMMAND_ITEMS)
      .not.toEqual(expect.arrayContaining(UNSAFE_DIRECT_COMMAND_ITEMS));

    for (const control of Object.values(CONTROL_CATALOG)) {
      const target = commandTargetFor(control);
      if (UNSAFE_DIRECT_COMMAND_ITEMS.includes(control.stateItem)) {
        expect(target).toBeNull();
      }
    }
  });

  it('records future correlated resources without enabling them prematurely', () => {
    expect(CONTROL_CATALOG.feedOnce).toMatchObject({
      requestItem: 'GoatFeeder_ManualRequest',
      resultItem: 'GoatFeeder_ManualResult',
      capability: 'feeder-request-v1',
    });
    expect(CONTROL_CATALOG.circulation).toMatchObject({
      requestItem: 'SouthOutlet_ManualRequest',
      resultItem: 'SouthOutlet_ManualResult',
      capability: 'greywater-request-v1',
    });
    expect(CONTROL_CATALOG.override).toMatchObject({
      requestItem: 'NightLoadOverride_Request',
      resultItem: 'NightLoadOverride_Result',
      capability: 'night-load-owner-v1',
    });
    expect(CONTROL_CATALOG.dishwasher.requestItem).toBe('NightLoadDevice_Request');
    expect(CONTROL_CATALOG.goatCam.resultItem).toBe('NightLoadDevice_Result');
  });

  it('passes its declarative safety validation', () => {
    expect(validateControlCatalog()).toEqual([]);
  });
});
