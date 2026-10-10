import { describe, it } from 'vitest';
import assert from 'node:assert/strict';
import { compressedInstalledCases } from './fixtures/compressed-installed-cases.js';
describe('compressed installed publication display', () => {
  for (const [name, check] of compressedInstalledCases) it(name, () => check(assert));
});
