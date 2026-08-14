import fs from 'node:fs';
import { describe, expect, it } from 'vitest';

const SERVICE_PATH = 'deploy/earthship-ui.service';
const THERMAL_UNIT_PATHS = {
  trainService: 'deploy/thermal-model-train.service',
  trainTimer: 'deploy/thermal-model-train.timer',
  shadowService: 'deploy/thermal-model-shadow.service',
  shadowTimer: 'deploy/thermal-model-shadow.timer',
};

describe('household UI user service', () => {
  it('runs the explicit safe-compat Vite server on the one production port', () => {
    expect(fs.existsSync(SERVICE_PATH)).toBe(true);
    if (!fs.existsSync(SERVICE_PATH)) return;

    const source = fs.readFileSync(SERVICE_PATH, 'utf8');
    expect(source).toMatch(/^WorkingDirectory=\/home\/sat\/earthship-ui$/m);
    expect(source).toMatch(/^Environment=RELEASE_MODE=safe-compat$/m);
    expect(source).toMatch(
      /^EnvironmentFile=\/home\/sat\/\.config\/hex\/openhab\.env$/m,
    );
    expect(source).toMatch(
      /^ExecStart=\/home\/sat\/\.npm-global\/bin\/npm run dev -- --host 0\.0\.0\.0 --port 5190 --strictPort$/m,
    );
    expect(source).toMatch(/^Restart=(?:on-failure|always)$/m);
    expect(source).toMatch(/^WantedBy=default\.target$/m);
    expect(source).not.toMatch(/nginx/i);
    expect(source).not.toMatch(/vite\s+preview/i);
  });
});

describe('thermal model shadow user units', () => {
  it('stages bounded oneshot training and publication services', () => {
    for (const path of [
      THERMAL_UNIT_PATHS.trainService,
      THERMAL_UNIT_PATHS.shadowService,
    ]) {
      expect(fs.existsSync(path), `${path} must exist`).toBe(true);
    }
    if (!fs.existsSync(THERMAL_UNIT_PATHS.trainService)
        || !fs.existsSync(THERMAL_UNIT_PATHS.shadowService)) return;

    const train = fs.readFileSync(THERMAL_UNIT_PATHS.trainService, 'utf8');
    const shadow = fs.readFileSync(THERMAL_UNIT_PATHS.shadowService, 'utf8');

    for (const source of [train, shadow]) {
      expect(source).toMatch(/^Type=oneshot$/m);
      expect(source).toMatch(
        /^WorkingDirectory=\/home\/sat\/openhab\/scripts$/m,
      );
      expect(source).toMatch(
        /^EnvironmentFile=\/home\/sat\/\.config\/hex\/openhab\.env$/m,
      );
    }
    expect(train).toMatch(
      /^ExecStart=\/usr\/bin\/python3 \/home\/sat\/openhab\/scripts\/thermal_intel\.py train$/m,
    );
    expect(shadow).toMatch(
      /^ExecStart=\/usr\/bin\/python3 \/home\/sat\/openhab\/scripts\/thermal_intel\.py shadow --publish$/m,
    );
    expect(train).toMatch(/^TimeoutStartSec=900$/m);
    expect(shadow).toMatch(/^TimeoutStartSec=180$/m);
    expect(train + shadow).not.toMatch(
      /Thermal_Advisory|sendCommand|\/rest\/rules/i,
    );
  });

  it('stages persistent daily training after the forecast job', () => {
    expect(
      fs.existsSync(THERMAL_UNIT_PATHS.trainTimer),
      `${THERMAL_UNIT_PATHS.trainTimer} must exist`,
    ).toBe(true);
    if (!fs.existsSync(THERMAL_UNIT_PATHS.trainTimer)) return;

    const timer = fs.readFileSync(THERMAL_UNIT_PATHS.trainTimer, 'utf8');
    expect(timer).toMatch(/^OnCalendar=\*-\*-\* 06:50:00$/m);
    expect(timer).toMatch(/^Persistent=true$/m);
    expect(timer).toMatch(/^WantedBy=timers\.target$/m);
    expect(timer).not.toMatch(/06:40:00/);
  });

  it('stages a persistent shadow run 15 minutes after boot and every two hours', () => {
    expect(
      fs.existsSync(THERMAL_UNIT_PATHS.shadowTimer),
      `${THERMAL_UNIT_PATHS.shadowTimer} must exist`,
    ).toBe(true);
    if (!fs.existsSync(THERMAL_UNIT_PATHS.shadowTimer)) return;

    const timer = fs.readFileSync(THERMAL_UNIT_PATHS.shadowTimer, 'utf8');
    expect(timer).toMatch(/^OnBootSec=15min$/m);
    expect(timer).toMatch(/^OnUnitActiveSec=2h$/m);
    expect(timer).toMatch(/^Persistent=true$/m);
    expect(timer).toMatch(/^WantedBy=timers\.target$/m);
  });
});
