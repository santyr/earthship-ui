import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const INVENTORY_URL = new URL('../tools/qa/red-sentinel-inventory.mjs', import.meta.url);
const VITEST_REPORTER_URL = new URL('../tools/qa/red-vitest-reporter.mjs', import.meta.url);
const PLAYWRIGHT_REPORTER_URL = new URL('../tools/qa/red-playwright-reporter.mjs', import.meta.url);
const EXPECT_FAILURE_URL = new URL('../tools/qa/expect-failure.mjs', import.meta.url);

const EXPECTED_OWNERS = {
  'RED:T1A-1': 'tests/viewport-pwa.test.js',
  'RED:T1B-1': 'tests/device-profile.test.js',
  'RED:T2A-1': 'tests/safe-controls.test.js',
  'RED:T3A-1': 'tests/item-value.test.js',
  'RED:T4A-1': 'tests/reconcile.test.js',
  'RED:T5A-1': 'tests/history-periods.test.js',
  'RED:T6A-1': 'tests/history-request.test.js',
  'RED:T7A-1': 'tests/chart-options.test.js',
  'RED:T7A-2': 'tests/e2e/chart-activation.spec.js',
  'RED:T8A-1': 'tests/console-alerts.test.js',
  'RED:T8A-2': 'tests/e2e/header-alerts.spec.js',
  'RED:T9A-1': 'tests/e2e/home.spec.js',
  'RED:T10A-1': 'tests/weather-aqi-wiring.test.js',
  'RED:T10A-2': 'tests/e2e/energy.spec.js',
  'RED:T11A-1': 'tests/thermal-loop-order.test.js',
  'RED:T11A-2': 'tests/e2e/earthship.spec.js',
  'RED:T12A-1': 'tests/control-machine.test.js',
  'RED:T12A-2': 'tests/e2e/control-states.spec.js',
  'RED:T13A-1': 'tests/openhab/rest-manifest.test.js',
  'RED:T14A-1': 'tests/openhab/feeder-rule.test.js',
  'RED:T15A-1': 'tests/openhab/greywater-rule.test.js',
  'RED:T16A-1': 'tests/openhab/night-load-override-rule.test.js',
  'RED:T17A-1': 'tests/pwa-cache-policy.test.js',
  'RED:T17A-2': 'tests/e2e/offline-pwa.spec.js',
  'RED:T17A-3': 'tests/e2e-fixture-contract.test.js',
  'RED:T17A-4': 'tests/e2e/dim-mode.spec.js',
  'RED:T18A-1': 'tests/tablet-metrics-schema.test.js',
  'RED:T18A-2': 'tests/e2e/geometry.spec.js',
  'RED:T18A-3': 'tests/qa-gates.test.js',
  'RED:T18A-4': 'tests/qa-gates.test.js',
};

const roots = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'earthship-red-inventory-'));
  roots.push(root);
  return root;
}

async function writeSource(root, relativePath, source) {
  const target = join(root, relativePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, source);
}

function sentinelSource(sentinel, { duplicateTitle = false, duplicateError = false } = {}) {
  const title = `test('[${sentinel}] expected contract', () => {`;
  const error = `throw new Error('[${sentinel}] expected missing contract');`;
  return [
    "import { test } from 'vitest';",
    title,
    ...(duplicateTitle ? [title] : []),
    `  ${error}`,
    ...(duplicateError ? [`  ${error}`] : []),
    '});',
    ...(duplicateTitle ? ['});'] : []),
    '',
  ].join('\n');
}

async function inventoryModule() {
  return import(INVENTORY_URL);
}

function vitestReport(sentinel, overrides = {}) {
  return {
    schema: 'earthship-red-vitest-report/v1',
    status: 'failed',
    declaredTests: 1,
    tests: [{
      title: `[${sentinel}] expected missing owner`,
      status: 'failed',
      errors: [`[${sentinel}] expected missing contract`],
    }],
    errors: [],
    ...overrides,
  };
}

function playwrightReport(sentinel, overrides = {}) {
  return {
    schema: 'earthship-red-playwright-report/v1',
    status: 'failed',
    declaredTests: 1,
    tests: [{
      title: `[${sentinel}] expected missing owner`,
      titlePath: ['suite', `[${sentinel}] expected missing owner`],
      status: 'failed',
      errors: [`[${sentinel}] expected missing contract`],
    }],
    errors: [],
    ...overrides,
  };
}

function vitestArgs(sentinel = 'RED:T14A-1') {
  return [
    '--runner', 'vitest', '--sentinel', sentinel, '--',
    'npm', 'test', '--', 'tests/openhab/feeder-rule.test.js',
    '-t', `^\\[${sentinel}\\]`,
  ];
}

function playwrightArgs(sentinel = 'RED:T7A-2') {
  return [
    '--runner', 'playwright', '--sentinel', sentinel, '--',
    'npx', 'playwright', 'test', 'tests/e2e/chart-activation.spec.js',
    '--grep', `^\\[${sentinel}\\]`,
  ];
}

describe('RED sentinel inventory contract', () => {
  it('exports the exact frozen owner inventory and lexical validator', async () => {
    let inventory;
    try {
      inventory = await inventoryModule();
    } catch (error) {
      if (error?.code === 'ERR_MODULE_NOT_FOUND' && error.message.includes(INVENTORY_URL.pathname)) {
        expect.fail(`missing RED sentinel inventory module: ${INVENTORY_URL.pathname}`);
      }
      throw error;
    }

    expect(Object.isFrozen(inventory.RED_SENTINEL_OWNERS)).toBe(true);
    expect(inventory.RED_SENTINEL_OWNERS).toEqual(EXPECTED_OWNERS);
    expect(inventory.validateSentinelInventory).toBeTypeOf('function');
  });

  it('accepts one exact requested owner with one title and error marker', async () => {
    const rootDir = await fixture();
    await writeSource(rootDir, EXPECTED_OWNERS['RED:T14A-1'], sentinelSource('RED:T14A-1'));
    const { validateSentinelInventory } = await inventoryModule();

    expect(validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [EXPECTED_OWNERS['RED:T14A-1']],
    })).toMatchObject({
      valid: true,
      requestedSentinel: 'RED:T14A-1',
      ownerFile: EXPECTED_OWNERS['RED:T14A-1'],
    });
  });

  it('rejects unknown sentinels and missing or extra selected owners', async () => {
    const rootDir = await fixture();
    const owner = EXPECTED_OWNERS['RED:T14A-1'];
    await writeSource(rootDir, owner, sentinelSource('RED:T14A-1'));
    const { validateSentinelInventory } = await inventoryModule();

    expect(() => validateSentinelInventory({ rootDir }))
      .toThrow(/requested sentinel/i);
    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:UNKNOWN-1',
      selectedFiles: [owner],
    })).toThrow(/unknown sentinel/i);
    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T13A-1',
      selectedFiles: [EXPECTED_OWNERS['RED:T13A-1']],
    })).toThrow(/missing requested owner/i);
    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [owner, 'tests/another.test.js'],
    })).toThrow(/exactly one selected file/i);
    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: ['tests/another.test.js'],
    })).toThrow(/selected file.*owner/i);
  });

  it('requires the exact Error callee and rejects every bracketed unregistered ID', async () => {
    const { validateSentinelInventory } = await inventoryModule();

    const customErrorRoot = await fixture();
    const owner = EXPECTED_OWNERS['RED:T14A-1'];
    await writeSource(customErrorRoot, owner, [
      "import { test } from 'vitest';",
      "test('[RED:T14A-1] expected contract', () => {",
      "  throw new CustomError('[RED:T14A-1] not the approved error marker');",
      '});',
    ].join('\n'));
    expect(() => validateSentinelInventory({
      rootDir: customErrorRoot,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [owner],
    })).toThrow(/exactly one error marker.*found 0/i);

    const unregisteredRoot = await fixture();
    await writeSource(
      unregisteredRoot,
      owner,
      `${sentinelSource('RED:T14A-1')}\n${sentinelSource('RED:UNREGISTERED_1')}`,
    );
    expect(() => validateSentinelInventory({
      rootDir: unregisteredRoot,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [owner],
    })).toThrow(/unregistered sentinel.*RED:UNREGISTERED_1/i);
  });

  it('rejects moved, duplicated, and unregistered sentinel markers', async () => {
    const { validateSentinelInventory } = await inventoryModule();

    const movedRoot = await fixture();
    await writeSource(movedRoot, 'tests/wrong.test.js', sentinelSource('RED:T14A-1'));
    expect(() => validateSentinelInventory({
      rootDir: movedRoot,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [EXPECTED_OWNERS['RED:T14A-1']],
    })).toThrow(/non-owner|belongs to/i);

    const duplicateRoot = await fixture();
    await writeSource(
      duplicateRoot,
      EXPECTED_OWNERS['RED:T14A-1'],
      sentinelSource('RED:T14A-1', { duplicateTitle: true, duplicateError: true }),
    );
    expect(() => validateSentinelInventory({
      rootDir: duplicateRoot,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [EXPECTED_OWNERS['RED:T14A-1']],
    })).toThrow(/exactly one.*title|duplicate/i);

    const unknownRoot = await fixture();
    await writeSource(
      unknownRoot,
      EXPECTED_OWNERS['RED:T14A-1'],
      `${sentinelSource('RED:T14A-1')}\n${sentinelSource('RED:UNREGISTERED-1')}`,
    );
    expect(() => validateSentinelInventory({
      rootDir: unknownRoot,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [EXPECTED_OWNERS['RED:T14A-1']],
    })).toThrow(/unregistered sentinel/i);
  });

  it('ignores comments and unrelated strings containing marker-like text', async () => {
    const rootDir = await fixture();
    const owner = EXPECTED_OWNERS['RED:T14A-1'];
    await writeSource(rootDir, owner, [
      sentinelSource('RED:T14A-1'),
      "// test('[RED:T14A-1] commented duplicate', () => {});",
      "const example = \"test('[RED:T14A-1] string duplicate', () => {})\";",
      "const errorExample = \"throw new Error('[RED:T14A-1] string duplicate')\";",
    ].join('\n'));
    const { validateSentinelInventory } = await inventoryModule();

    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T14A-1',
      selectedFiles: [owner],
    })).not.toThrow();
  });

  it('supports both sentinels sharing the Task 18 QA-gates owner', async () => {
    const rootDir = await fixture();
    const owner = EXPECTED_OWNERS['RED:T18A-3'];
    await writeSource(
      rootDir,
      owner,
      `${sentinelSource('RED:T18A-3')}\n${sentinelSource('RED:T18A-4')}`,
    );
    const { validateSentinelInventory } = await inventoryModule();

    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T18A-3',
      selectedFiles: [owner],
    })).not.toThrow();
    expect(() => validateSentinelInventory({
      rootDir,
      requestedSentinel: 'RED:T18A-4',
      selectedFiles: [owner],
    })).not.toThrow();
  });

  it('requires every exact owner and marker pair in complete mode', async () => {
    const rootDir = await fixture();
    for (const [sentinel, owner] of Object.entries(EXPECTED_OWNERS)) {
      const target = join(rootDir, owner);
      let existing = '';
      try {
        existing = await readFile(target, 'utf8');
      } catch (error) {
        if (error?.code !== 'ENOENT') throw error;
      }
      await writeSource(rootDir, owner, `${existing}${sentinelSource(sentinel)}`);
    }
    const { validateSentinelInventory } = await inventoryModule();

    expect(() => validateSentinelInventory({ rootDir, mode: 'complete' })).not.toThrow();
    await rm(join(rootDir, EXPECTED_OWNERS['RED:T17A-1']));
    expect(() => validateSentinelInventory({ rootDir, mode: 'complete' }))
      .toThrow(/complete.*missing|missing.*complete/i);
  });
});

describe('RED Playwright reporter contract', () => {
  it('writes one normalized report only to its configured path', async () => {
    let Reporter;
    try {
      ({ default: Reporter } = await import(PLAYWRIGHT_REPORTER_URL));
    } catch (error) {
      if (error?.code === 'ERR_MODULE_NOT_FOUND'
        && error.message.includes(PLAYWRIGHT_REPORTER_URL.pathname)) {
        expect.fail(`missing RED Playwright reporter module: ${PLAYWRIGHT_REPORTER_URL.pathname}`);
      }
      throw error;
    }

    const root = await fixture();
    const outputFile = join(root, 'playwright-report.json');
    const reporter = new Reporter({ outputFile });
    const test = {
      title: '[RED:T14A-1] expected missing owner',
      titlePath: () => ['suite', '[RED:T14A-1] expected missing owner'],
    };

    reporter.onBegin({}, { allTests: () => [test] });
    reporter.onTestEnd(test, {
      status: 'failed',
      errors: [{ message: '[RED:T14A-1] expected missing contract' }],
    });
    reporter.onStepEnd(test, {}, {
      category: 'hook',
      error: { message: '[RED:T14A-1] beforeEach failed' },
    });
    reporter.onError({ message: 'collection problem' });
    await reporter.onEnd({ status: 'failed' });

    expect(await readdir(root)).toEqual(['playwright-report.json']);
    expect(JSON.parse(await readFile(outputFile, 'utf8'))).toEqual({
      schema: 'earthship-red-playwright-report/v1',
      status: 'failed',
      declaredTests: 1,
      tests: [{
        title: '[RED:T14A-1] expected missing owner',
        titlePath: ['suite', '[RED:T14A-1] expected missing owner'],
        status: 'failed',
        errors: ['[RED:T14A-1] expected missing contract'],
      }],
      errors: [
        { phase: 'hook', message: '[RED:T14A-1] beforeEach failed' },
        { phase: 'runner', message: 'collection problem' },
      ],
    });
  });

  it('marks a Playwright timed-out test as a forbidden timeout phase', async () => {
    const { default: Reporter } = await import(PLAYWRIGHT_REPORTER_URL);
    const root = await fixture();
    const outputFile = join(root, 'playwright-timeout.json');
    const reporter = new Reporter({ outputFile });
    const test = { title: '[RED:T7A-2] expected missing chart' };

    reporter.onBegin({}, { allTests: () => [test] });
    reporter.onTestEnd(test, {
      status: 'timedOut',
      errors: [{ message: 'Test timeout of 5ms exceeded' }],
    });
    await reporter.onEnd({ status: 'timedout' });

    expect(JSON.parse(await readFile(outputFile, 'utf8')).errors).toEqual([
      { phase: 'timeout', message: 'Test timeout of 5ms exceeded' },
    ]);
  });

  it('counts only Playwright tests that reached a result', async () => {
    const { default: Reporter } = await import(PLAYWRIGHT_REPORTER_URL);
    const root = await fixture();
    const outputFile = join(root, 'playwright-filtered.json');
    const reporter = new Reporter({ outputFile });
    const selected = { title: '[RED:T7A-2] expected missing chart' };
    const filtered = { title: 'ordinary chart simulation' };

    reporter.onBegin({}, { allTests: () => [selected, filtered] });
    reporter.onTestEnd(selected, {
      status: 'failed',
      errors: [{ message: '[RED:T7A-2] expected missing contract' }],
    });
    await reporter.onEnd({ status: 'failed' });

    expect(JSON.parse(await readFile(outputFile, 'utf8'))).toMatchObject({
      declaredTests: 1,
      tests: [{ title: '[RED:T7A-2] expected missing chart', status: 'failed' }],
    });
  });
});

describe('RED Vitest reporter contract', () => {
  it('exports a dedicated reporter that requires an isolated output path', async () => {
    let Reporter;
    try {
      ({ default: Reporter } = await import(VITEST_REPORTER_URL));
    } catch (error) {
      if (error?.code === 'ERR_MODULE_NOT_FOUND'
        && error.message.includes(VITEST_REPORTER_URL.pathname)) {
        expect.fail(`missing RED Vitest reporter module: ${VITEST_REPORTER_URL.pathname}`);
      }
      throw error;
    }

    expect(Reporter).toBeTypeOf('function');
    expect(() => new Reporter()).toThrow(/output path/i);
  });

  it('records assertion, hook, suite, and runner failures in separate channels', async () => {
    const { default: Reporter } = await import(VITEST_REPORTER_URL);
    const root = await fixture();
    const outputFile = join(root, 'vitest-report.json');
    const reporter = new Reporter({ outputFile });
    const assertionError = { message: '[RED:T14A-1] expected missing contract' };
    const hookError = { message: '[RED:T14A-1] beforeEach failed' };
    let testErrors = [assertionError];
    const testCase = {
      name: '[RED:T14A-1] expected missing owner',
      fullName: '[RED:T14A-1] expected missing owner',
      result: () => ({ state: 'failed', errors: testErrors }),
    };
    const module = {
      children: { allTests: () => [testCase][Symbol.iterator]() },
      errors: () => [{ message: 'import failed' }],
    };

    reporter.onTestModuleCollected(module);
    reporter.onHookStart({ name: 'beforeEach', entity: testCase });
    testErrors = [assertionError, hookError];
    reporter.onHookEnd({ name: 'beforeEach', entity: testCase });
    reporter.onTestCaseResult(testCase);
    await reporter.onTestRunEnd(
      [module],
      [{ message: 'setup worker failed' }],
      'failed',
    );

    expect(await readdir(root)).toEqual(['vitest-report.json']);
    expect(JSON.parse(await readFile(outputFile, 'utf8'))).toEqual({
      schema: 'earthship-red-vitest-report/v1',
      status: 'failed',
      declaredTests: 1,
      tests: [{
        title: '[RED:T14A-1] expected missing owner',
        status: 'failed',
        errors: [
          '[RED:T14A-1] expected missing contract',
          '[RED:T14A-1] beforeEach failed',
        ],
      }],
      errors: [
        { phase: 'hook', message: '[RED:T14A-1] beforeEach failed' },
        { phase: 'suite', message: 'import failed' },
        { phase: 'runner', message: 'setup worker failed' },
      ],
    });
  });

  it('marks a Vitest timed-out test as a forbidden timeout phase', async () => {
    const { default: Reporter } = await import(VITEST_REPORTER_URL);
    const root = await fixture();
    const outputFile = join(root, 'vitest-timeout.json');
    const reporter = new Reporter({ outputFile });
    const testCase = {
      name: '[RED:T14A-1] expected missing owner',
      result: () => ({
        state: 'failed',
        errors: [{ name: 'Error', message: 'Test timed out in 5ms.' }],
      }),
    };
    const module = {
      children: { allTests: () => [testCase][Symbol.iterator]() },
      errors: () => [],
    };

    reporter.onTestModuleCollected(module);
    reporter.onTestCaseResult(testCase);
    await reporter.onTestRunEnd([module], [], 'failed');

    expect(JSON.parse(await readFile(outputFile, 'utf8')).errors).toEqual([
      { phase: 'timeout', message: 'Test timed out in 5ms.' },
    ]);
  });

  it('counts only executed tests after the exact name filter', async () => {
    const { default: Reporter } = await import(VITEST_REPORTER_URL);
    const root = await fixture();
    const outputFile = join(root, 'vitest-filtered.json');
    const reporter = new Reporter({ outputFile });
    const failed = {
      name: '[RED:T14A-1] expected missing owner',
      result: () => ({
        state: 'failed',
        errors: [{ message: '[RED:T14A-1] expected missing contract' }],
      }),
    };
    const skipped = {
      name: 'ordinary feeder simulation',
      result: () => ({ state: 'skipped', errors: undefined }),
    };
    const module = {
      children: { allTests: () => [failed, skipped][Symbol.iterator]() },
      errors: () => [],
    };

    reporter.onTestModuleCollected(module);
    reporter.onTestCaseResult(skipped);
    reporter.onTestCaseResult(failed);
    await reporter.onTestRunEnd([module], [], 'failed');

    expect(JSON.parse(await readFile(outputFile, 'utf8'))).toMatchObject({
      declaredTests: 1,
      tests: [{
        title: '[RED:T14A-1] expected missing owner',
        status: 'failed',
      }],
    });
  });
});

describe('structured RED wrapper contract', () => {
  it('exports invocation parsing, report validation, and execution', async () => {
    let wrapper;
    try {
      wrapper = await import(EXPECT_FAILURE_URL);
    } catch (error) {
      if (error?.code === 'ERR_MODULE_NOT_FOUND'
        && error.message.includes(EXPECT_FAILURE_URL.pathname)) {
        expect.fail(`missing structured RED wrapper: ${EXPECT_FAILURE_URL.pathname}`);
      }
      throw error;
    }

    expect(wrapper.parseExpectedFailureArgs).toBeTypeOf('function');
    expect(wrapper.validateExpectedFailureReport).toBeTypeOf('function');
    expect(wrapper.executeExpectedFailure).toBeTypeOf('function');
  });

  it('requires an exact runner, sentinel, producer, and anchored filter', async () => {
    const { parseExpectedFailureArgs } = await import(EXPECT_FAILURE_URL);

    expect(parseExpectedFailureArgs(vitestArgs())).toMatchObject({
      runner: 'vitest',
      sentinel: 'RED:T14A-1',
      command: expect.arrayContaining(['tests/openhab/feeder-rule.test.js']),
      selectedFiles: ['tests/openhab/feeder-rule.test.js'],
    });
    expect(parseExpectedFailureArgs(playwrightArgs())).toMatchObject({
      runner: 'playwright',
      sentinel: 'RED:T7A-2',
      selectedFiles: ['tests/e2e/chart-activation.spec.js'],
    });

    expect(() => parseExpectedFailureArgs(vitestArgs().toSpliced(1, 1, 'jest')))
      .toThrow(/runner/i);
    expect(() => parseExpectedFailureArgs(vitestArgs().toSpliced(3, 1, 'RED:UNKNOWN-1')))
      .toThrow(/unknown sentinel/i);
    expect(() => parseExpectedFailureArgs(vitestArgs().filter((value) => value !== '--')))
      .toThrow(/separator|command/i);
    expect(() => parseExpectedFailureArgs(vitestArgs().toSpliced(-1, 1, 'RED:T14A-1')))
      .toThrow(/anchored.*filter|filter.*anchored/i);
    expect(() => parseExpectedFailureArgs([
      ...vitestArgs().slice(0, -2),
      'tests/another.test.js',
      ...vitestArgs().slice(-2),
    ])).toThrow(/exactly one.*producer|selected file/i);
  });

  it('rejects every alternate or conflicting runner name filter', async () => {
    const { parseExpectedFailureArgs } = await import(EXPECT_FAILURE_URL);

    for (const extra of [
      ['--testNamePattern', '^wrong$'],
      ['--testNamePattern=^wrong$'],
      ['--test-name-pattern', '^wrong$'],
    ]) {
      expect(() => parseExpectedFailureArgs([...vitestArgs(), ...extra]))
        .toThrow(/alternate|conflicting|filter/i);
    }

    for (const extra of [
      ['-g', '^wrong$'],
      ['-g=^wrong$'],
      ['--grep-invert', '^wrong$'],
      ['--grep-invert=^wrong$'],
    ]) {
      expect(() => parseExpectedFailureArgs([...playwrightArgs(), ...extra]))
        .toThrow(/alternate|conflicting|filter/i);
    }
  });

  it('accepts only one sentinel-prefixed failed test from either report shape', async () => {
    const { validateExpectedFailureReport } = await import(EXPECT_FAILURE_URL);

    expect(validateExpectedFailureReport({
      runner: 'vitest',
      report: vitestReport('RED:T14A-1'),
      sentinel: 'RED:T14A-1',
      exitCode: 1,
      signal: null,
    })).toMatchObject({ valid: true, title: '[RED:T14A-1] expected missing owner' });
    expect(validateExpectedFailureReport({
      runner: 'playwright',
      report: playwrightReport('RED:T7A-2'),
      sentinel: 'RED:T7A-2',
      exitCode: 1,
      signal: null,
    })).toMatchObject({ valid: true, title: '[RED:T7A-2] expected missing owner' });
  });

  it('rejects success, signals, wrong markers, extra tests, and runner errors', async () => {
    const { validateExpectedFailureReport } = await import(EXPECT_FAILURE_URL);
    const base = {
      runner: 'vitest',
      report: vitestReport('RED:T14A-1'),
      sentinel: 'RED:T14A-1',
      exitCode: 1,
      signal: null,
    };

    expect(() => validateExpectedFailureReport({ ...base, exitCode: 0 }))
      .toThrow(/exit.*1|unexpected success/i);
    expect(() => validateExpectedFailureReport({ ...base, exitCode: null, signal: 'SIGTERM' }))
      .toThrow(/signal|crash/i);
    expect(() => validateExpectedFailureReport({
      ...base,
      report: vitestReport('RED:T14A-1', {
        tests: [{
          title: 'wrong title', status: 'failed',
          errors: ['[RED:T14A-1] expected missing contract'],
        }],
      }),
    })).toThrow(/title.*sentinel/i);
    expect(() => validateExpectedFailureReport({
      ...base,
      report: vitestReport('RED:T14A-1', {
        tests: [{
          title: '[RED:T14A-1] expected missing owner', status: 'failed',
          errors: ['timeout exceeded'],
        }],
      }),
    })).toThrow(/error.*sentinel/i);
    expect(() => validateExpectedFailureReport({
      ...base,
      report: vitestReport('RED:T14A-1', { declaredTests: 2 }),
    })).toThrow(/exactly one.*test/i);
    expect(() => validateExpectedFailureReport({
      runner: 'playwright',
      report: playwrightReport('RED:T7A-2', { errors: ['collection problem'] }),
      sentinel: 'RED:T7A-2',
      exitCode: 1,
      signal: null,
    })).toThrow(/runner error|collection/i);
  });

  it('rejects every non-assertion phase, timeout, and additional same-test error', async () => {
    const { validateExpectedFailureReport } = await import(EXPECT_FAILURE_URL);
    const base = {
      runner: 'vitest',
      sentinel: 'RED:T14A-1',
      exitCode: 1,
      signal: null,
    };

    for (const phase of ['collection', 'import', 'setup', 'hook', 'suite']) {
      expect(() => validateExpectedFailureReport({
        ...base,
        report: vitestReport('RED:T14A-1', {
          errors: [{ phase, message: `${phase} failed` }],
        }),
      })).toThrow(new RegExp(`${phase}|runner error`, 'i'));
    }

    expect(() => validateExpectedFailureReport({
      ...base,
      report: vitestReport('RED:T14A-1', {
        tests: [{
          title: '[RED:T14A-1] expected missing owner',
          status: 'timedout',
          errors: ['[RED:T14A-1] timeout exceeded'],
        }],
      }),
    })).toThrow(/timed?out|failed.*test/i);

    expect(() => validateExpectedFailureReport({
      ...base,
      report: vitestReport('RED:T14A-1', {
        tests: [{
          title: '[RED:T14A-1] expected missing owner',
          status: 'failed',
          errors: [
            '[RED:T14A-1] expected missing contract',
            '[RED:T14A-1] afterEach also failed',
          ],
        }],
      }),
    })).toThrow(/exactly one.*error/i);
  });

  it('injects reporters, validates inventory, and always removes report artifacts', async () => {
    const rootDir = await fixture();
    await writeSource(
      rootDir,
      EXPECTED_OWNERS['RED:T14A-1'],
      sentinelSource('RED:T14A-1'),
    );
    const { executeExpectedFailure } = await import(EXPECT_FAILURE_URL);
    let reportPath;
    const spawn = (_command, args, options) => {
      reportPath = options.env.EARTHSHIP_RED_REPORT_PATH;
      expect(args.some((arg) => arg.includes('red-vitest-reporter.mjs'))).toBe(true);
      writeFileSync(reportPath, JSON.stringify(vitestReport('RED:T14A-1')));
      return { status: 1, signal: null, stdout: 'untrusted output', stderr: '' };
    };

    expect(executeExpectedFailure({ argv: vitestArgs(), cwd: rootDir, spawn }))
      .toMatchObject({ valid: true });
    expect(reportPath).toBeTruthy();
    expect(existsSync(dirname(reportPath))).toBe(false);

    await writeSource(
      rootDir,
      EXPECTED_OWNERS['RED:T7A-2'],
      sentinelSource('RED:T7A-2'),
    );
    let playwrightPath;
    const playwrightSpawn = (_command, args, options) => {
      playwrightPath = options.env.EARTHSHIP_RED_REPORT_PATH;
      expect(args.some((arg) => arg.includes('red-playwright-reporter.mjs'))).toBe(true);
      writeFileSync(playwrightPath, JSON.stringify(playwrightReport('RED:T7A-2')));
      return { status: 1, signal: null, stdout: '', stderr: '' };
    };
    expect(executeExpectedFailure({ argv: playwrightArgs(), cwd: rootDir, spawn: playwrightSpawn }))
      .toMatchObject({ valid: true });
    expect(existsSync(dirname(playwrightPath))).toBe(false);
  });

  it('rejects missing, malformed, and duplicate report output while cleaning up', async () => {
    const rootDir = await fixture();
    await writeSource(
      rootDir,
      EXPECTED_OWNERS['RED:T14A-1'],
      sentinelSource('RED:T14A-1'),
    );
    const { executeExpectedFailure } = await import(EXPECT_FAILURE_URL);
    const attempts = [];

    const missing = (_command, _args, options) => {
      attempts.push(options.env.EARTHSHIP_RED_REPORT_PATH);
      return { status: 1, signal: null, stdout: '', stderr: '' };
    };
    expect(() => executeExpectedFailure({ argv: vitestArgs(), cwd: rootDir, spawn: missing }))
      .toThrow(/missing report/i);

    const malformed = (_command, _args, options) => {
      const path = options.env.EARTHSHIP_RED_REPORT_PATH;
      attempts.push(path);
      writeFileSync(path, '{not-json');
      return { status: 1, signal: null, stdout: '', stderr: '' };
    };
    expect(() => executeExpectedFailure({ argv: vitestArgs(), cwd: rootDir, spawn: malformed }))
      .toThrow(/malformed report/i);

    const duplicate = (_command, _args, options) => {
      const path = options.env.EARTHSHIP_RED_REPORT_PATH;
      attempts.push(path);
      writeFileSync(path, JSON.stringify(vitestReport('RED:T14A-1')));
      writeFileSync(join(dirname(path), 'extra.json'), '{}');
      return { status: 1, signal: null, stdout: '', stderr: '' };
    };
    expect(() => executeExpectedFailure({ argv: vitestArgs(), cwd: rootDir, spawn: duplicate }))
      .toThrow(/duplicate|unexpected report artifact/i);
    expect(attempts.every((path) => path && !existsSync(dirname(path)))).toBe(true);
  });
});
