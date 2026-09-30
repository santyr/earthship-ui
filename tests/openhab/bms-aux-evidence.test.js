import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { harness, specs } from './helpers/bms-aux-harness.js';

const source = readFileSync(new URL('../../openhab/rules/bms-aux-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/bms-aux-evidence-resources.json', import.meta.url), 'utf8'));
const itemSource = readFileSync(new URL('../../openhab/file-config/items/bms-aux-evidence.items', import.meta.url), 'utf8');
function ready() {
  const h = harness(); h.run(); h.advance();
  h.run(h.event('capacity')); h.run(h.event('temperature')); return h;
}

describe('Discover BMS auxiliary evidence producer', () => {
  it('requires post-start original native events and preserves each field separately', () => {
    const h = harness(); h.run(h.event('capacity'));
    expect(h.latest.fields[specs.capacity.field].status).toBe('unavailable');
    h.advance(); h.run(h.event('capacity'));
    expect(h.latest.fields[specs.capacity.field]).toEqual({ status: 'valid', reason: 'ok',
      observedAt: h.now, validUntil: h.now + 120000, value: 320 });
    expect(h.latest.fields[specs.temperature.field].status).toBe('unavailable');
    h.run(h.event('temperature'));
    expect(h.latest.fields[specs.temperature.field].value).toBe(29300);
  });

  it.each(['getSource', 'getType', 'getTopic', 'getItemState'])('rejects spoofed %s', key => {
    const h = ready(); h.advance();
    h.run(h.event('capacity', specs.capacity.value, { [key]: () => 'spoofed' }));
    expect(h.latest.fields[specs.capacity.field].reason).toBe('invalid_input');
    expect(h.latest.fields[specs.temperature.field].status).toBe('valid');
  });

  it.each(['-1', '320.0', '451', 'NULL', ''])('rejects invalid capacity %s', value => {
    const h = ready(); h.advance(); h.run(h.event('capacity', value));
    expect(h.latest.fields[specs.capacity.field].reason).toBe('invalid_input');
  });

  it('ignores an Item-level update, expires missing polls and keeps the other field', () => {
    const h = ready(); h.advance(60000);
    h.run({ itemName: specs.capacity.item, itemState: '321' });
    expect(h.latest.fields[specs.capacity.field].reason).toBe('invalid_input');
    h.advance(30000);
    h.run(h.event('capacity'));
    h.advance(60000); h.run();
    expect(h.latest.fields[specs.capacity.field].status).toBe('valid');
    expect(h.latest.fields[specs.temperature.field].reason).toBe('input_stale');
  });

  it('barriers a Thing outage and restart before requiring new native events', () => {
    const h = ready(); h.online.set(specs.temperature.thing, 'OFFLINE'); h.run();
    expect(h.latest.fields[specs.temperature.field].reason).toBe('source_unavailable');
    h.online.set(specs.temperature.thing, 'ONLINE'); h.advance(); h.run();
    expect(h.latest.fields[specs.temperature.field].reason).toBe('input_unavailable');
    h.advance(); h.run(h.event('temperature'));
    expect(h.latest.fields[specs.temperature.field].status).toBe('valid');
    const epoch = h.latest.streamEpoch;
    h.cache.clear(); h.run();
    expect(h.latest.streamEpoch).not.toBe(epoch);
    expect(h.latest.fields[specs.capacity.field].status).toBe('unavailable');
  });

  it('accepts unchanged 30-second native polls without increasing heartbeat writes', () => {
    const h = ready();
    const initialPosts = h.posts.length;
    for (let poll = 1; poll <= 6; poll += 1) {
      h.advance(30000);
      h.run(h.event('capacity'));
      h.run(h.event('temperature'));
      expect(h.posts.length).toBe(initialPosts + Math.floor(poll / 2));
    }
    h.advance(119999); h.run();
    expect(h.latest.fields[specs.capacity.field].status).toBe('valid');
    expect(h.latest.fields[specs.temperature.field].status).toBe('valid');
    h.advance(1); h.run();
    expect(h.latest.fields[specs.capacity.field].reason).toBe('input_stale');
    expect(h.latest.fields[specs.temperature.field].reason).toBe('input_stale');
  });

  it('consumes sequence identity on ambiguous persistence enqueue', () => {
    const h = ready(); const before = h.latest.sequence;
    h.advance(); h.failAfterEnqueue(true); h.run(h.event('capacity', '319'));
    h.failAfterEnqueue(false); h.run();
    expect(h.latest.sequence).toBe(before + 2);
  });

  it('is staged disabled, file-owned, and cannot command a device', () => {
    expect(resources.rule.enabled).toBe(false);
    expect(resources.rule.triggers.map(trigger => trigger.type).slice(0, 2))
      .toEqual(['core.GenericEventTrigger', 'core.GenericEventTrigger']);
    expect(resources.persistenceExclusion).toBe('!BMS_Aux_Evidence_JSON');
    expect(itemSource).toContain('String BMS_Aux_Evidence_JSON');
    expect(source).not.toMatch(/sendCommand|sendHttp|executeCommandLine/);
  });
});
