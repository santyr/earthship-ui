// Lightweight shared contract verification; no browser or Vitest worker pool.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';
import { compressedInstalledCases } from '../tests/fixtures/compressed-installed-cases.js';
if (process.argv.includes('--publication')) {
  const input=JSON.parse(readFileSync(0,'utf8'));
  const result=parseThermalModelResult(JSON.stringify(input.publication),input.now);
  console.log(JSON.stringify({state:result.state,mode:result.mode,badge:result.badge,uncertaintyMode:result.uncertaintyMode}));
  process.exit(0);
}
for (const [name, check] of compressedInstalledCases) {
  try { check(assert); } catch (error) { console.error(name); throw error; }
}
console.log(`${compressedInstalledCases.length} compressed UI contract checks passed`);
