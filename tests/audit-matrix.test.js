import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

const MATRIX_URL = new URL('../docs/qa/ui-audit-matrix.csv', import.meta.url);
const HEADER = [
  'id',
  'route',
  'component',
  'integration',
  'target',
  'state_fixture',
  'expected',
  'test_or_evidence',
  'status',
];

function parseCsvLine(line) {
  const fields = [];
  let field = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === ',' && !quoted) {
      fields.push(field);
      field = '';
    } else {
      field += char;
    }
  }
  fields.push(field);
  return fields;
}

async function loadMatrix() {
  const text = await readFile(MATRIX_URL, 'utf8');
  const lines = text.trim().split(/\r?\n/);
  const header = parseCsvLine(lines[0]);
  return {
    header,
    rows: lines.slice(1).map((line) => Object.fromEntries(
      header.map((name, index) => [name, parseCsvLine(line)[index]]),
    )),
  };
}

describe('canonical UI audit matrix', () => {
  it('has the exact schema, unique stable IDs, and evidence for every closed row', async () => {
    const { header, rows } = await loadMatrix();
    expect(header).toEqual(HEADER);
    expect(rows.length).toBeGreaterThanOrEqual(30);
    expect(new Set(rows.map(({ id }) => id)).size).toBe(rows.length);

    const allowed = new Set([
      'verified-automated',
      'verified-live',
      'pending-device-signoff',
      'pending-operator-approval',
      'deferred-future-feature',
    ]);
    for (const row of rows) {
      expect(row.id).toMatch(/^[A-Z]+-[A-Z0-9-]+$/);
      expect(allowed.has(row.status), `${row.id}: ${row.status}`).toBe(true);
      if (row.status.startsWith('verified-')) {
        expect(row.test_or_evidence.trim().length, row.id).toBeGreaterThan(0);
      }
    }
  });

  it('tracks every critical user requirement and remaining sign-off explicitly', async () => {
    const { rows } = await loadMatrix();
    const ids = new Set(rows.map(({ id }) => id));
    expect(ids).toEqual(expect.objectContaining(new Set([
      'GLOBAL-TARGETS',
      'GLOBAL-NOSCROLL',
      'HOME-SPARK-COLOR',
      'HOME-GOAT',
      'HOME-SEASON',
      'ENERGY-PREDICTED-TROUGH',
      'ENERGY-PV-PLOT',
      'CHART-PERIODS',
      'WEATHER-AQI',
      'EARTHSHIP-ORDER',
      'CONTROLS-SAFETY',
      'OPENHAB-MAINUI-ACTUATORS',
      'DEPLOY-USER-SERVICE',
      'SECURITY-TOKEN-ROTATION',
      'DEVICE-M9-SIGNOFF',
      'WEATHER-DETAIL-MODAL',
    ])));
  });
});
