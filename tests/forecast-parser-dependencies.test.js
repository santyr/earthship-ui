import { it, expect } from 'vitest';
import { mkdtempSync, cpSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

it('loads the Python publication contract parser without installed frontend packages', () => {
  const root = mkdtempSync(join(tmpdir(), 'earthship-forecast-parser-'));
  try {
    cpSync(new URL('../src/lib/', import.meta.url), join(root, 'lib'), { recursive: true });
    writeFileSync(join(root, 'package.json'), JSON.stringify({ type: 'module' }));
    const parser = pathToFileURL(join(root, 'lib/weather/forecastDetail.js')).href;
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', `const m = await import(${JSON.stringify(parser)}); if (m.parseForecast10Day('UNDEF').status !== 'unavailable') process.exit(2);`], { encoding: 'utf8', timeout: 5000 });
    expect(child.status, child.stderr).toBe(0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
