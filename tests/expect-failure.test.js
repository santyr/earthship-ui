import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const INVENTORY_URL = new URL('../tools/qa/red-sentinel-inventory.mjs', import.meta.url);

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
