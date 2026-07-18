import { afterEach, describe, expect, it, vi } from 'vitest';
import viteConfig from '../vite.config.js';
import {
  isAllowedProxyRequest,
  openhabProxyAuthorization,
} from '../src/lib/openhab/proxyPolicy.js';

describe('household Vite OpenHAB proxy policy', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('allows read-only REST and SSE requests', () => {
    for (const path of [
      '/rest/items?fields=name,state,type',
      '/rest/things',
      '/rest/events?topics=openhab%2Fitems%2F*%2Fstatechanged',
      '/rest/persistence/items/BMS_SOC?starttime=a&endtime=b',
    ]) {
      expect(isAllowedProxyRequest('GET', path)).toBe(true);
    }
  });

  it('allows POST only to the four implemented direct controls', () => {
    for (const item of [
      'living_room_1_Switch',
      'living_room_2_Switch',
      'LED_living_room_1_Switch',
      'LivingRoomCircadian_Enable',
    ]) {
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'safe-compat')).toBe(true);
    }
  });

  it('denies unsafe actuators, unrelated writes, state injection, and rule execution', () => {
    for (const [method, path] of [
      ['POST', '/rest/items/Goat_Plugs_Outlet2_Switch'],
      ['POST', '/rest/items/SouthOutlet_Outlet2_Switch'],
      ['POST', '/rest/items/OverrideSwitch'],
      ['POST', '/rest/items/Dish_Washer_Power'],
      ['PUT', '/rest/items/Current_US_AQI/state'],
      ['POST', '/rest/rules/example/runnow'],
      ['DELETE', '/rest/items/BMS_SOC'],
      ['PATCH', '/rest/things/example'],
    ]) {
      expect(isAllowedProxyRequest(method, path, 'safe-compat')).toBe(false);
    }
  });

  it('fails every write closed in maintenance or an unknown release mode', () => {
    const path = '/rest/items/living_room_1_Switch';
    expect(isAllowedProxyRequest('POST', path)).toBe(false);
    expect(isAllowedProxyRequest('POST', path, 'maintenance')).toBe(false);
    expect(isAllowedProxyRequest('POST', path, 'unknown')).toBe(false);
  });

  it('installs a Vite middleware that blocks denied writes before proxying', () => {
    vi.stubEnv('RELEASE_MODE', 'safe-compat');
    const config = viteConfig({ command: 'serve', mode: 'development' });
    const guard = config.plugins.find((plugin) => plugin.name === 'earthship-openhab-proxy-guard');
    let middleware;
    guard.configureServer({ middlewares: { use: (fn) => { middleware = fn; } } });

    const response = {
      setHeader: vi.fn(),
      end: vi.fn(),
    };
    const deniedNext = vi.fn();
    middleware({ method: 'POST', url: '/rest/items/Goat_Plugs_Outlet2_Switch' }, response, deniedNext);

    expect(response.statusCode).toBe(403);
    expect(deniedNext).not.toHaveBeenCalled();
    expect(response.end).toHaveBeenCalledWith(expect.stringContaining('blocked'));

    const readNext = vi.fn();
    middleware({ method: 'GET', url: '/rest/items' }, {}, readNext);
    expect(readNext).toHaveBeenCalledOnce();
  });

  it('injects the server-owned Basic header on proxied requests', () => {
    vi.stubEnv('RELEASE_MODE', 'safe-compat');
    vi.stubEnv('OPENHAB_TOKEN', 'fixture-token');
    const config = viteConfig({ command: 'serve', mode: 'development' });
    let proxyRequestListener;
    const proxy = { on: vi.fn((event, listener) => {
      expect(event).toBe('proxyReq');
      proxyRequestListener = listener;
    }) };
    config.server.proxy['/rest'].configure(proxy);
    const proxyRequest = { setHeader: vi.fn() };
    proxyRequestListener(proxyRequest);

    expect(proxyRequest.setHeader).toHaveBeenCalledWith(
      'Authorization', openhabProxyAuthorization('fixture-token'));
  });
  it('builds one server-side Basic header and rejects a missing token', () => {
    expect(openhabProxyAuthorization('fixture-token'))
      .toBe(`Basic ${Buffer.from('fixture-token:').toString('base64')}`);
    expect(() => openhabProxyAuthorization('')).toThrow(/token/i);
  });
});
