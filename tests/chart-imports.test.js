import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

const COMPONENTS = [
  'src/lib/ui/ChartModal.svelte',
  'src/lib/ui/HistoryChart.svelte',
  'src/lib/ui/Sparkline.svelte',
  'src/lib/ui/HourlyStrip.svelte',
];

describe('modular ECharts bundle', () => {
  it('has one tree-shakeable adapter and no full-package component imports', async () => {
    const adapter = await readFile('src/lib/charts/echarts.js', 'utf8');
    expect(adapter).toMatch(/echarts\/core/);
    expect(adapter).toMatch(/LineChart/);
    expect(adapter).toMatch(/BarChart/);

    for (const path of COMPONENTS) {
      const source = await readFile(path, 'utf8');
      expect(source).not.toMatch(/from ['"]echarts['"]/);
      expect(source).toMatch(/charts\/loadEcharts\.js/);
    }
  });
});
