import { describe, it, expect } from 'vitest';
import { parseSSEMessage } from '../src/lib/openhab/sse.js';

describe('parseSSEMessage', () => {
  it('extracts item name and value from statechanged event', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: JSON.stringify({ value: '54', oldValue: '55' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'BMS_SOC', value: '54' });
  });

  it('returns null for non-item events (e.g. thing status)', () => {
    expect(parseSSEMessage(JSON.stringify({ topic: 'openhab/things/x/status', payload: '{}' }))).toBeNull();
  });

  it('returns null for malformed json', () => {
    expect(parseSSEMessage('not json')).toBeNull();
  });

  it('returns null when payload is missing value', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: JSON.stringify({ oldValue: '55' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null when payload itself is malformed json', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: 'not json',
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null when topic is missing entirely', () => {
    const raw = JSON.stringify({ payload: JSON.stringify({ value: '1' }) });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null for an empty string input', () => {
    expect(parseSSEMessage('')).toBeNull();
  });

  it('returns null for other item event types on a non-statechanged topic suffix', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/added',
      payload: JSON.stringify({ value: '54' }),
      type: 'ItemAddedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('coerces a numeric value to a string', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/Grid_Power/statechanged',
      payload: JSON.stringify({ value: 1234 }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'Grid_Power', value: '1234' });
  });

  it('handles item names containing underscores and digits', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/Solar_Panel_2_Voltage/statechanged',
      payload: JSON.stringify({ value: '48.2' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'Solar_Panel_2_Voltage', value: '48.2' });
  });
});
