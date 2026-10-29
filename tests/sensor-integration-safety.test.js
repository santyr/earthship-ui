// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest';
const execFileSync = vi.hoisted(() => vi.fn());
vi.mock('node:child_process', () => ({ execFileSync }));
import { assertIsolatedSensorStack, runSensorPython } from './e2e/sensor-integration.js';

afterEach(() => { vi.unstubAllEnvs(); execFileSync.mockReset(); });
test('sensor integration refuses absent opt-in without Python, Docker or network', () => {
  vi.stubEnv('SENSOR_INTEGRATION', '');
  expect(() => assertIsolatedSensorStack()).toThrow('SENSOR_INTEGRATION=1');
  expect(execFileSync).not.toHaveBeenCalled();
});
test('browser entrypoint verifies its acknowledged phase before authentication or stimuli', () => {
  vi.stubEnv('SENSOR_INTEGRATION', '1');
  assertIsolatedSensorStack();
  expect(execFileSync).toHaveBeenCalledTimes(1);
  const [python, args, options] = execFileSync.mock.calls[0];
  expect(typeof python).toBe('string');
  expect(args).toEqual(['-B', '-m', 'services.lorawan.tests.stack_ownership', '--browser']);
  expect(options.timeout).toBe(20000);
  expect({ bytecode: options.env.PYTHONDONTWRITEBYTECODE, optIn: options.env.SENSOR_INTEGRATION,
    inspector: options.env.SENSOR_BROWSER_INSPECTION }).toEqual({ bytecode: '1', optIn: '1', inspector: '1' });
});
test('shared preflight refusal propagates to browser before authentication or stimuli', () => {
  vi.stubEnv('SENSOR_INTEGRATION', '1');
  execFileSync.mockImplementation(() => { throw new Error('sensor fixture ownership refused'); });
  expect(() => assertIsolatedSensorStack()).toThrow('sensor fixture ownership refused');
  expect(execFileSync).toHaveBeenCalledTimes(1);
});
test('sensor Python stimuli disable bytecode in fixture subprocesses', () => {
  runSensorPython('services.lorawan.tests.integration_probe', ['--state', '1']);
  expect(execFileSync).toHaveBeenCalledWith(expect.any(String), ['-B', '-m', 'services.lorawan.tests.integration_probe', '--state', '1'],
    expect.objectContaining({ env: expect.objectContaining({ PYTHONDONTWRITEBYTECODE: '1' }) }));
});
