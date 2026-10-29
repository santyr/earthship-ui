// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { assertIsolatedSensorStack, runSensorPython } from './e2e/sensor-integration.js';

afterEach(() => vi.unstubAllEnvs());
test('real browser preflight and standalone Python auth/stimulus refuse a foreign checkout', () => {
  const checkout = process.cwd();
  const foreign = mkdtempSync(join(tmpdir(), 'sensor-foreign-worktree-'));
  const privatePath = join(foreign, '.superpowers/lorawan-private');
  mkdirSync(privatePath, { recursive: true });
  writeFileSync(join(privatePath, 'ingest.json'), JSON.stringify({ environment: 'simulation', mqtt_host: 'mqtt', mqtt_port: 1883,
    mqtt_username: 'fixture', mqtt_password: 'fixture', database_dsn: 'sqlite:fixture' }), { mode: 0o600 });
  vi.stubEnv('SENSOR_INTEGRATION', '1');
  vi.stubEnv('SENSOR_TEST_PYTHON', process.env.EARTHSHIP_TEST_PYTHON || process.env.SENSOR_TEST_PYTHON || '/usr/bin/python3');
  vi.stubEnv('PYTHONPATH', checkout);
  try {
    process.chdir(foreign);
    for (const entrypoint of [
      assertIsolatedSensorStack,
      () => runSensorPython('services.lorawan.tests.browser_auth'),
      () => runSensorPython('services.lorawan.tests.integration_probe', ['--state', '1']),
    ]) {
      expect(entrypoint).toThrow(/sensor fixture ownership refused/);
    }
    expect(existsSync(join(privatePath, 'browser-auth.json'))).toBe(false);
  } finally {
    process.chdir(checkout);
    rmSync(foreign, { recursive: true, force: true });
  }
});
