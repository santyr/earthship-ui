import { describe, expect, it } from 'vitest';
import {
  CURRENT_AQI_CHANNEL,
  CURRENT_AQI_ITEM,
  assertAllowedRequest,
  buildDesiredThingConfig,
  buildReceipt,
  verifyDesiredState,
} from '../../scripts/openhab-aqi.mjs';

const beforeThing = {
  UID: 'openmeteo:air-quality:local:aq',
  statusInfo: { status: 'ONLINE', statusDetail: 'NONE' },
  configuration: {
    location: '38.3739919,-105.7744931',
    current: false,
    airQualityIndicatorsAsNumber: false,
    airQualityIndicatorsAsString: true,
    hourlyTimeSeries: true,
    includePM2_5: true,
  },
  channels: [],
};

describe('reversible current AQI migration', () => {
  it('preserves unrelated Thing keys while enabling current numeric AQI', () => {
    expect(buildDesiredThingConfig(beforeThing.configuration)).toEqual({
      location: '38.3739919,-105.7744931',
      current: true,
      airQualityIndicatorsAsNumber: true,
      airQualityIndicatorsAsString: true,
      hourlyTimeSeries: true,
      includePM2_5: true,
    });
  });

  it('uses the exact Number item and dynamic current US AQI channel', () => {
    expect(CURRENT_AQI_ITEM).toEqual({
      type: 'Number',
      name: 'Current_US_AQI',
      label: 'Current US AQI',
      category: 'airquality',
      tags: ['Measurement'],
      groupNames: [],
    });
    expect(CURRENT_AQI_CHANNEL)
      .toBe('openmeteo:air-quality:local:aq:current#us-aqi');
  });

  it('allows only the exact read/config/item/link endpoints and never commands items or rules', () => {
    expect(() => assertAllowedRequest('GET', '/rest/')).not.toThrow();
    expect(() => assertAllowedRequest(
      'PUT',
      '/rest/things/openmeteo%3Aair-quality%3Alocal%3Aaq/config',
    )).not.toThrow();
    expect(() => assertAllowedRequest('PUT', '/rest/items/Current_US_AQI')).not.toThrow();
    expect(() => assertAllowedRequest(
      'PUT',
      '/rest/links/Current_US_AQI/openmeteo%3Aair-quality%3Alocal%3Aaq%3Acurrent%23us-aqi',
    )).not.toThrow();
    expect(() => assertAllowedRequest('DELETE', '/rest/items/Current_US_AQI')).not.toThrow();

    expect(() => assertAllowedRequest('POST', '/rest/items/Current_US_AQI')).toThrow(/denied/i);
    expect(() => assertAllowedRequest('PUT', '/rest/items/Current_US_AQI/state')).toThrow(/denied/i);
    expect(() => assertAllowedRequest('POST', '/rest/rules/example/runnow')).toThrow(/denied/i);
    expect(() => assertAllowedRequest('DELETE', '/rest/items/Forecast_AQI')).toThrow(/denied/i);
    expect(() => assertAllowedRequest('PUT', '/rest/things/other/config')).toThrow(/denied/i);
  });

  it('records exact originals and runtime version in a token-free open receipt', () => {
    const receipt = buildReceipt({
      runtimeInfo: { version: '5.2.0', buildString: 'Release Build' },
      thing: beforeThing,
      currentItem: null,
      currentLink: null,
      forecastItem: { name: 'Forecast_AQI', type: 'String', state: 'REFRESH' },
      forecastLink: {
        itemName: 'Forecast_AQI',
        channelUID: 'openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string',
        configuration: {},
      },
      createdAt: '2026-07-18T15:00:00.000Z',
    });

    expect(receipt.state).toBe('open');
    expect(receipt.runtimeInfo.version).toBe('5.2.0');
    expect(receipt.original.thingConfiguration.current).toBe(false);
    expect(receipt.original.currentItem).toBeNull();
    expect(receipt.original.forecastItem.state).toBe('REFRESH');
    expect(JSON.stringify(receipt)).not.toMatch(/authorization|token/i);
  });

  it('requires online Thing, exact channel/item/link, and a numeric provider state', () => {
    const desiredThing = {
      ...beforeThing,
      configuration: buildDesiredThingConfig(beforeThing.configuration),
      channels: [{ uid: CURRENT_AQI_CHANNEL }],
    };
    const desiredLink = {
      itemName: CURRENT_AQI_ITEM.name,
      channelUID: CURRENT_AQI_CHANNEL,
      configuration: {},
    };

    expect(verifyDesiredState({
      runtimeInfo: { version: '5.2.0' },
      thing: desiredThing,
      currentItem: { ...CURRENT_AQI_ITEM, state: '42' },
      currentLink: desiredLink,
    })).toMatchObject({ ok: true, numericState: 42 });

    expect(verifyDesiredState({
      runtimeInfo: { version: '5.2.0' },
      thing: desiredThing,
      currentItem: { ...CURRENT_AQI_ITEM, state: 'UNDEF' },
      currentLink: desiredLink,
    })).toMatchObject({ ok: false, reasons: expect.arrayContaining([expect.stringMatching(/numeric/i)]) });
  });
});
