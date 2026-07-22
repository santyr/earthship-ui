import { afterEach, describe, expect, it, vi } from 'vitest';
import viteConfig from '../vite.config.js';
import {
  isAllowedProxyRequest,
  openhabProxyAuthorization,
  sanitizeThingDto,
  sanitizeThingsResponse,
} from '../src/lib/openhab/proxyPolicy.js';

describe('household Vite OpenHAB proxy policy', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

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

  it('denies GET outside the four read surfaces the UI uses', () => {
    for (const path of [
      '/rest/',
      '/rest/rules',
      '/rest/rules/example',
      '/rest/services/org.openhab.core.example/config',
      '/rest/addons',
      '/rest/bindings',
      '/rest/config-descriptions',
      '/rest/systeminfo',
      '/rest/persistence',
      '/rest/itemsandmore',
    ]) {
      expect(isAllowedProxyRequest('GET', path)).toBe(false);
    }
  });

  it('projects Thing DTOs down to UID, label, and status fields only', () => {
    const raw = {
      UID: 'tplinksmarthome:kl125:E7FA31',
      label: 'Living Room 1',
      statusInfo: { status: 'ONLINE', statusDetail: 'NONE', description: '', extra: 'x' },
      configuration: { username: 'admin', password: 'hunter2', ipAddress: '192.168.1.130' },
      properties: { macAddress: 'aa:bb' },
      channels: [{ uid: 'x' }],
    };
    expect(sanitizeThingDto(raw)).toEqual({
      UID: 'tplinksmarthome:kl125:E7FA31',
      label: 'Living Room 1',
      statusInfo: { status: 'ONLINE', statusDetail: 'NONE', description: '' },
    });
    expect(sanitizeThingDto(null)).toBeNull();
    expect(sanitizeThingsResponse([raw, null, 'junk'])).toEqual([sanitizeThingDto(raw)]);
    expect(sanitizeThingsResponse(raw)).toEqual(sanitizeThingDto(raw));
  });

  it('intercepts GET /rest/things and serves the sanitized projection', async () => {
    vi.stubEnv('RELEASE_MODE', 'safe-compat');
    vi.stubEnv('OPENHAB_TOKEN', 'fixture-token');
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{
        UID: 'a:b:c',
        label: 'L',
        statusInfo: { status: 'ONLINE' },
        configuration: { password: 's3cret' },
      }],
    });
    vi.stubGlobal('fetch', fetchMock);

    const config = viteConfig({ command: 'serve', mode: 'development' });
    const guard = config.plugins.find((plugin) => plugin.name === 'earthship-openhab-proxy-guard');
    let middleware;
    guard.configureServer({ middlewares: { use: (fn) => { middleware = fn; } } });

    const response = { setHeader: vi.fn(), end: vi.fn() };
    const next = vi.fn();
    middleware({ method: 'GET', url: '/rest/things' }, response, next);
    await vi.waitFor(() => expect(response.end).toHaveBeenCalled());

    expect(next).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/rest/things'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: openhabProxyAuthorization('fixture-token'),
        }),
      }),
    );
    const body = JSON.parse(response.end.mock.calls[0][0]);
    expect(body).toEqual([{ UID: 'a:b:c', label: 'L', statusInfo: { status: 'ONLINE' } }]);
    expect(response.end.mock.calls[0][0]).not.toContain('s3cret');
  });

  it('returns 502 without leaking upstream detail when the things fetch fails', async () => {
    vi.stubEnv('RELEASE_MODE', 'safe-compat');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED 192.168.1.5')));

    const config = viteConfig({ command: 'serve', mode: 'development' });
    const guard = config.plugins.find((plugin) => plugin.name === 'earthship-openhab-proxy-guard');
    let middleware;
    guard.configureServer({ middlewares: { use: (fn) => { middleware = fn; } } });

    const response = { setHeader: vi.fn(), end: vi.fn() };
    const next = vi.fn();
    middleware({ method: 'GET', url: '/rest/things' }, response, next);
    await vi.waitFor(() => expect(response.end).toHaveBeenCalled());

    expect(next).not.toHaveBeenCalled();
    expect(response.statusCode).toBe(502);
    expect(response.end.mock.calls[0][0]).not.toContain('ECONNREFUSED');
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

  it('allows POST to exactly the four correlated request items', () => {
    for (const item of [
      'GoatFeeder_ManualRequest',
      'SouthOutlet_ManualRequest',
      'NightLoadDevice_Request',
      'NightLoadOverride_Request',
    ]) {
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'safe-compat')).toBe(true);
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'full')).toBe(true);
    }
  });

  it('denies unsafe actuators, unrelated writes, state injection, rule execution, and result items', () => {
    for (const [method, path] of [
      ['POST', '/rest/items/Goat_Plugs_Outlet2_Switch'],
      ['POST', '/rest/items/SouthOutlet_Outlet2_Switch'],
      ['POST', '/rest/items/OverrideSwitch'],
      ['POST', '/rest/items/Dish_Washer_Power'],
      ['POST', '/rest/items/ShurefloPump_Power'],
      ['POST', '/rest/items/Goat_Plugs_Outlet1_Switch'],
      ['POST', '/rest/items/GoatFeeder_ManualResult'],
      ['POST', '/rest/items/SouthOutlet_ManualResult'],
      ['POST', '/rest/items/NightLoadDevice_Result'],
      ['POST', '/rest/items/NightLoadOverride_Result'],
      ['PUT', '/rest/items/Current_US_AQI/state'],
      ['POST', '/rest/rules/example/runnow'],
      ['DELETE', '/rest/items/BMS_SOC'],
      ['PATCH', '/rest/things/example'],
    ]) {
      expect(isAllowedProxyRequest(method, path, 'safe-compat')).toBe(false);
    }
  });

  it('fails the request items closed in maintenance mode', () => {
    for (const item of [
      'GoatFeeder_ManualRequest',
      'SouthOutlet_ManualRequest',
      'NightLoadDevice_Request',
      'NightLoadOverride_Request',
    ]) {
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'maintenance')).toBe(false);
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
