// @vitest-environment node
import { test, expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

test('default unit discovery owns maintained tests and excludes disposable copies', () => {
  const marker = `discovery-sentinel-${process.pid}`;
  const directories = [
    `artifacts/${marker}`, `tests/.worktrees/${marker}`, `tests/node_modules/${marker}`, `tests/e2e/${marker}`,
  ];
  try {
    for (const directory of directories) {
      mkdirSync(directory, { recursive: true });
      writeFileSync(`${directory}/${marker}.test.js`, "import { test } from 'vitest'; test('sentinel', () => {});\n");
    }
    const result = spawnSync(process.execPath, [resolve('node_modules/vitest/vitest.mjs'), 'list', '--filesOnly', '--configLoader', 'runner'], {
      cwd: process.cwd(), encoding: 'utf8', timeout: 20000,
      env: { ...process.env, UV_THREADPOOL_SIZE: '1', RAYON_NUM_THREADS: '1' },
    });
    expect(result.error).toBeUndefined();
    expect(result.status, result.stderr).toBe(0);
    const files = result.stdout.split('\n').filter(line => /\.(test|spec)\./.test(line));
    expect(files.length).toBeGreaterThan(100);
    expect(files.some(file => file.endsWith('tests/test-entrypoint-discovery.test.js'))).toBe(true);
    expect(files.filter(file => file.includes(marker))).toEqual([]);
    expect(files.every(file => file.startsWith('tests/'))).toBe(true);
    expect(files.some(file => file.includes('/e2e/'))).toBe(false);
  } finally {
    for (const directory of directories) rmSync(directory, { recursive: true, force: true });
  }
}, 30000);
