// Console design tokens — shared across all screens/primitives.
// Signature accent colors per the approved design doc (Ambient Weather
// WS-2000 console aesthetic, modernized: dark instrument panel, crisp tiles).

export const colors = {
  temperature: '#f59e0b', // amber
  wind: '#22c55e', // cyan/green
  water: '#3b82f6', // blue — rain/water
  rain: '#3b82f6',
  solar: '#eab308', // yellow
  forecast: '#8b5cf6', // violet
  advisory: '#f97316', // orange
  label: '#8b93a1', // neutral label
};

export const tileSizes = {
  gap: '0.75rem',
  radius: '0.75rem',
  border: '#1c2230',
  bg: '#11151c',
  padding: '0.9rem',
};

// Shared ECharts dark theme — transparent background, muted grid/axis,
// tabular numerals. Reused by any chart primitive (Sparkline, etc).
export const echartsTheme = {
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: 'Inter, system-ui, sans-serif',
    color: colors.label,
  },
  color: [colors.temperature],
  categoryAxis: {
    axisLine: { lineStyle: { color: '#1c2230' } },
    axisTick: { show: false },
    axisLabel: { color: colors.label },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: colors.label },
    splitLine: { lineStyle: { color: '#1c2230' } },
  },
  line: {
    smooth: false,
    symbol: 'none',
    lineStyle: { width: 2 },
  },
};
