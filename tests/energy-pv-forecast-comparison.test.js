import { describe, expect, it } from 'vitest';
import { pvForecastComparison } from '../src/lib/energy/pvForecastComparison.js';

describe('Energy PV forecast comparison', () => {
  it('uses the dated morning forecast rather than implying a live revision', () => {
    expect(pvForecastComparison(4.2, 5.36)).toBe('of 5.4 kWh morning forecast');
    expect(pvForecastComparison(5.36, 5.36)).toBe('of 5.4 kWh morning forecast');
    expect(pvForecastComparison(8.4, 5.36)).toBe('above 5.4 kWh morning forecast');
  });

  it('does not invent a forecast from an unavailable receipt', () => {
    expect(pvForecastComparison(8.4, null)).toBe('morning forecast unavailable');
    expect(pvForecastComparison(null, 5.36)).toBe('of 5.4 kWh morning forecast');
  });
});
