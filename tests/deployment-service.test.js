import fs from 'node:fs';
import { describe, expect, it } from 'vitest';

const SERVICE_PATH = 'deploy/earthship-ui.service';
const THERMAL_RUNBOOK_PATH = 'docs/operations/thermal-model-shadow.md';
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
      expect(source).toMatch(/^UMask=0077$/m);
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


function bashBlocks(source) {
  return [...source.matchAll(/```bash\n([\s\S]*?)\n```/g)].map((match) => match[1]);
}

describe('thermal model attended runbook safety', () => {
  const runbook = fs.readFileSync(THERMAL_RUNBOOK_PATH, 'utf8');
  const blocks = bashBlocks(runbook);

  it('makes every executable Bash fence independently fail closed', () => {
    expect(blocks.length).toBeGreaterThan(40);
    for (const block of blocks) {
      expect(block.split('\n').find((line) => line.trim())).toBe('set -euo pipefail');
      for (const line of block.split('\n')) {
        const trimmed = line.trim();
        if (trimmed.startsWith('jq ') || trimmed.startsWith('| jq ')) {
          expect(trimmed).toMatch(/^(?:\| )?jq\b[^\n]*\s-e(?:\s|$)/);
        }
        if (trimmed.startsWith('curl ')) {
          expect(trimmed).toMatch(/^curl --fail --silent --show-error(?: |$)/);
        }
      }
      expect(block).not.toMatch(/printf[^\n]*"\$\(git /);
    }
  });

  it('orders preliminary receipt facts, three non-reused gates, and evidence', () => {
    const ordered = [
      'Preliminary authorization: private receipt facts only',
      'thermal-model-config.mjs snapshot',
      'thermal-model-config.mjs plan',
      'Gate A: code, database, and private model evidence',
      'thermal-model-files.py install-code',
      'thermal_intel.py train',
      'Review artifact and backtest evidence',
      'Gate B: sole observational Item and state writes',
      'thermal-model-config.mjs apply',
      'thermal_intel.py shadow --publish',
      'Gate C: service and timer activation',
      'thermal-model-files.py install-units',
    ];
    let previous = -1;
    for (const marker of ordered) {
      const current = runbook.indexOf(marker);
      expect(current, marker).toBeGreaterThan(previous);
      previous = current;
    }
  });

  it('stops timers and both services before receipt or file rollback', () => {
    const ordered = [
      'disable --now thermal-model-train.timer thermal-model-shadow.timer',
      'stop thermal-model-train.service thermal-model-shadow.service',
      'oneshot services are inactive',
      'thermal-model-config.mjs rollback',
      'thermal-model-files.py restore',
    ];
    let previous = -1;
    for (const marker of ordered) {
      const current = runbook.indexOf(marker);
      expect(current, marker).toBeGreaterThan(previous);
      previous = current;
    }
  });

  it('requires atomic manifests, exact role authority, provenance, and private modes', () => {
    expect(runbook).toMatch(/sibling.*temporary.*fsync.*SHA-256.*os\.replace.*parent/si);
    expect(runbook).toContain('explicit absent markers');
    expect(runbook).toContain('rolsuper');
    expect(runbook).toContain('rolcreaterole');
    expect(runbook).toContain('rolcreatedb');
    expect(runbook).toContain('rolreplication');
    expect(runbook).toContain('rolbypassrls');
    expect(runbook).toContain('role memberships');
    expect(runbook).toContain('effective privileges outside `thermal_intel`');
    expect(runbook).toContain('runtime-manifest SHA-256');
    expect(runbook).toContain('reviewed Git commit');
    expect(runbook).toContain('umask 077');
    expect(runbook).toContain('mode `0700`');
    expect(runbook).toContain('mode `0600`');
    expect(runbook).toContain('stat -c %a');
  });
});
