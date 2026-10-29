import { execFileSync } from 'node:child_process';

// Browser, standalone Python stimuli and Python integration share the same
// ownership checks. The browser additionally verifies completed retirements.
export function assertIsolatedSensorStack() {
  if (process.env.SENSOR_INTEGRATION !== '1') throw new Error('sensors requires SENSOR_INTEGRATION=1 and the isolated Compose stack');
  return runSensorPython('services.lorawan.tests.stack_ownership', ['--browser']);
}

export function runSensorPython(module, args = []) {
  return execFileSync(process.env.SENSOR_TEST_PYTHON || '/tmp/earthship-sensor-test-venv/bin/python',
    ['-B', '-m', module, ...args], { timeout: 20000,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', SENSOR_BROWSER_INSPECTION: '1' } });
}
