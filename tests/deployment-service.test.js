import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

const SERVICE_PATH = 'deploy/earthship-ui.service';
const THERMAL_RUNBOOK_PATH = 'docs/operations/thermal-model-shadow.md';
const README_PATH = 'README.md';
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

describe('thermal model operations documentation', () => {
  it('routes operators to the first-install-only transactional runbook', () => {
    const readme = fs.readFileSync(README_PATH, 'utf8');
    expect(readme).toContain('first-install-only');
    expect(readme).toContain('durable transaction recovery');
    expect(readme).toContain('separately reviewed upgrade procedure');
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
        if (/\bjq\s/.test(trimmed)) {
          expect(trimmed).toMatch(/\bjq\b[^\n]*\s-e(?:\s|$)/);
        }
        if (trimmed.startsWith('curl ')) {
          expect(trimmed).toMatch(/^curl --fail --silent --show-error(?: |$)/);
        }
      }
      expect(block).not.toMatch(/printf[^\n]*"\$\(git /);
    }
  });

  it('uses checked assignments and executable fail-closed probe patterns', () => {
    for (const block of blocks) {
      expect(block).not.toMatch(/\btest\b[^\n]*\$\(/);
      expect(block).not.toMatch(/(?:if|elif) systemctl\b/);
    }
    const masked = spawnSync('bash', ['-c',
      'set -euo pipefail; test -z "$(false)"; printf unsafe',
    ]);
    expect(masked.status).toBe(0);
    const checked = spawnSync('bash', ['-c',
      'set -euo pipefail; VALUE="$(false)"; test -z "$VALUE"; printf safe',
    ]);
    expect(checked.status).not.toBe(0);
    expect(
      runbook.match(/thermal-systemd-state\.py first-install/g)?.length,
    ).toBeGreaterThanOrEqual(2);
    expect(runbook).toContain('thermal-systemd-state.py rollback-precheck');
    expect(runbook).toContain('thermal-systemd-state.py rollback-quiescent');
  });

  it('binds the attended runtime DSN and Gate C publication authority exactly', () => {
    const ordered = [
      "read -r -s -p 'THERMAL_DATABASE_URL:",
      "current_user <> 'thermal_intel_runtime'",
      'thermal_intel.py train',
      'thermal_intel.py backtest',
      'unset THERMAL_DATABASE_URL',
      'Gate B: sole observational Item and state writes',
      'Gate C: service and timer activation',
      'thermal-model-shadow.service',
      'post-service-readback.json',
      'validate_thermal_shadow.py',
      'enable --now thermal-model-train.timer thermal-model-shadow.timer',
    ];
    let previous = -1;
    for (const marker of ordered) {
      const current = runbook.indexOf(marker, previous + 1);
      expect(current, marker).toBeGreaterThan(previous);
      previous = current;
    }
    expect(runbook).toContain('future timer-driven PUTs to exact Thermal_Model_JSON');
    expect(runbook).toContain(
      'future timer-driven private training, backtest, and artifact replacement',
    );
    expect(runbook).toContain('immediate catch-up publication');
    expect(runbook).toContain("trap 'unset THERMAL_DATABASE_URL' EXIT HUP INT TERM");
  });

  it('documents recoverable transactions, secure directories, and exact database objects', () => {
    expect(runbook).toContain('thermal-model-files.py prepare');
    expect(runbook).toContain('phase-state.json');
    expect(runbook).toContain('thermal-model-files.py recover');
    expect(runbook).toContain('unowned target drift');
    for (const object of [
      'message_receipts',
      'action_events',
      'mode_events',
      'reject_journal_mutation',
      'reject_action_correction_cycle',
      'reject_mode_correction_cycle',
      'has_sequence_privilege',
      'has_function_privilege',
      'prosecdef',
      'prokind',
      'is_grantable',
      'attacl',
    ]) {
      expect(runbook).toContain(object);
    }
    expect(runbook).toMatch(/CONNECT.*TEMP.*CREATE/s);
    expect(runbook).toContain('system catalog visibility');
  });

  it('audits the exact five-trigger graph before, after, and at runtime', () => {
    const expected = [
      'action_events|reject_correction_cycle|thermal_intel|reject_action_correction_cycle|O|5|1|1|0|1|0|-',
      'action_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
      'message_receipts|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
      'mode_events|reject_correction_cycle|thermal_intel|reject_mode_correction_cycle|O|5|1|1|0|1|0|-',
      'mode_events|reject_mutation|thermal_intel|reject_journal_mutation|O|27|0|0|0|1|0|-',
    ];
    expect(runbook.match(/DECLARE actual_triggers text\[\];/g)?.length)
      .toBeGreaterThanOrEqual(3);
    for (const row of expected) {
      expect(runbook.match(new RegExp(row.replaceAll('|', '\\\\|'), 'g'))?.length)
        .toBeGreaterThanOrEqual(3);
    }
    for (const marker of [
      'pg_trigger', 'tgisinternal', 'tgenabled', 'tgtype', 'tgdeferrable',
      'tginitdeferred', 'tgnargs', 'tgqual IS NULL', 'tgattr',
      'thermal trigger graph is not exact',
    ]) {
      expect(runbook.match(new RegExp(marker.replaceAll('|', '\\\\|'), 'g'))?.length)
        .toBeGreaterThanOrEqual(3);
    }
  });

  it('binds all three exact ordinary persistent nonpartitioned non-RLS table OIDs', () => {
    const exactRelations = [
      'action_events|r|p|0|0|0',
      'message_receipts|r|p|0|0|0',
      'mode_events|r|p|0|0|0',
    ];
    expect(runbook.match(/DECLARE table_oids oid\[\];/g)?.length)
      .toBeGreaterThanOrEqual(3);
    for (const row of exactRelations) {
      expect(runbook.match(new RegExp(row.replaceAll('|', '\\\\|'), 'g'))?.length)
        .toBeGreaterThanOrEqual(3);
    }
    for (const marker of [
      'relkind', 'relpersistence', 'relispartition',
      'relrowsecurity', 'relforcerowsecurity', 'c.oid = ANY(table_oids)',
    ]) {
      expect(runbook.split(marker).length - 1).toBeGreaterThanOrEqual(3);
    }
    expect(runbook.match(/relkind NOT IN \('i','I'\)/g)?.length).toBe(3);
    expect(runbook).not.toContain("c.relnamespace=schema_oid AND c.relkind='r'");
    for (const rejectedKind of [
      /partitioned\s+table/, /view/, /materialized\s+view/, /sequence/, /foreign\s+table/,
    ]) {
      expect(runbook).toMatch(rejectedKind);
    }
  });

  it('requires empty trigger tgattr so UPDATE OF subsets cannot match', () => {
    expect(runbook.match(/COALESCE\(NULLIF\(t\.tgattr::text,''\), '-'\)/g)?.length)
      .toBeGreaterThanOrEqual(3);
    const wholeRow = 'reject_journal_mutation|O|27|0|0|0|1|0|-';
    const updateSubset = 'reject_journal_mutation|O|27|0|0|0|1|0|2';
    expect(wholeRow).not.toBe(updateSubset);
    expect(runbook).toContain(wholeRow);
    expect(runbook).not.toContain(updateSubset);
  });

  it('audits an existing schema before migration and revalidates private paths', () => {
    const migration = runbook.indexOf('from thermal_model.journal import migrate');
    const preInventory = runbook.indexOf('pre-migration thermal_intel inventory is not exact');
    expect(preInventory).toBeGreaterThan(-1);
    expect(preInventory).toBeLessThan(migration);
    expect((runbook.match(/actual_tables/g) || []).length).toBeGreaterThanOrEqual(6);

    const runtimePrompt = runbook.indexOf("read -r -s -p 'THERMAL_DATABASE_URL: '");
    const runtimeOwnership = runbook.indexOf('runtime role owns database or application objects', runtimePrompt);
    const runtimeSchemaCreate = runbook.indexOf('runtime role has schema CREATE', runtimePrompt);
    const train = runbook.indexOf('thermal_intel.py train', runtimePrompt);
    expect(runtimeOwnership).toBeGreaterThan(runtimePrompt);
    expect(runtimeSchemaCreate).toBeGreaterThan(runtimeOwnership);
    expect(train).toBeGreaterThan(runtimeSchemaCreate);

    for (const marker of [
      'THERMAL_DATABASE_URL: ',
      '.published-readback.XXXXXX',
      'systemctl --user start thermal-model-train.service',
      '.post-service-readback.XXXXXX',
    ]) {
      const position = runbook.indexOf(marker);
      const prepare = runbook.lastIndexOf('thermal-model-files.py prepare', position);
      expect(prepare, marker).toBeGreaterThan(-1);
    }
  });

  it('orders preliminary receipt facts, three non-reused gates, and evidence', () => {
    const ordered = [
      'Preliminary authorization: private receipt facts only',
      'thermal-model-config.mjs snapshot',
      'thermal-model-config.mjs plan',
      'thermal-model-config.mjs rehearse',
      'Gate A: code, database, and private model evidence',
      'thermal-model-files.py install-code',
      'thermal_intel.py train',
      'Review artifact and backtest evidence',
      'Gate B: sole observational Item and state writes',
      'thermal-model-config.mjs apply',
      'thermal-model-config.mjs close',
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

  it('requires offline rehearsal and exact receipt closure around Gate B and rollback', () => {
    const rehearsal = runbook.indexOf('thermal-model-config.mjs rehearse');
    const gateB = runbook.indexOf('Gate B: sole observational Item and state writes');
    const apply = runbook.indexOf('thermal-model-config.mjs apply', gateB);
    const closeDesired = runbook.indexOf('thermal-model-config.mjs close', apply);
    const publish = runbook.indexOf('thermal_intel.py shadow --publish', closeDesired);
    expect(rehearsal).toBeGreaterThan(-1);
    expect(rehearsal).toBeLessThan(gateB);
    expect(closeDesired).toBeGreaterThan(apply);
    expect(closeDesired).toBeLessThan(publish);
    expect(runbook).toContain('closed:rolled-back');
    expect(runbook).toMatch(/cannot construct a\s+REST client/);

    const rollback = runbook.indexOf('thermal-model-config.mjs rollback');
    const verifyOriginal = runbook.indexOf('.phase == "rolled-back"', rollback);
    const closeRolledBack = runbook.indexOf('thermal-model-config.mjs close', verifyOriginal);
    const fileRestore = runbook.indexOf('thermal-model-files.py restore', closeRolledBack);
    expect(closeRolledBack).toBeGreaterThan(verifyOriginal);
    expect(fileRestore).toBeGreaterThan(closeRolledBack);
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
    expect(runbook).toMatch(/sibling.*fsync.*SHA-256.*renameat2\(RENAME_EXCHANGE\).*parent/si);
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
