const AXIS_COLOR = '#8b93a1';
const GRID_COLOR = '#242b38';

function hourLabel(at) {
  const hour = Number(String(at ?? '').slice(11, 13));
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) return '—';
  if (hour === 0) return '12 AM';
  if (hour === 12) return '12 PM';
  return `${hour % 12} ${hour < 12 ? 'AM' : 'PM'}`;
}

function display(value, suffix) {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${Math.round(value)}${suffix}`
    : `—${suffix}`;
}

function tooltipFormatter(params) {
  const values = Object.fromEntries(
    (Array.isArray(params) ? params : []).map(({ seriesName, value }) => [seriesName, value]),
  );
  const label = params?.[0]?.axisValue ?? 'Forecast';
  return [
    `<strong>${label}</strong>`,
    `Temperature: ${display(values.Temperature, '°F')}`,
    `Precipitation: ${display(values.Precipitation, '%')}`,
    `Radiation: ${display(values.Radiation, ' W/m²')}`,
    `Wind: ${display(values.Wind, ' mph')}`,
  ].join('<br>');
}

export function buildWeatherDetailOption({ hours = [], widthPx = 900 } = {}) {
  const wide = Number(widthPx) >= 760;
  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: {
      left: wide ? 56 : 42,
      right: wide ? 100 : 76,
      top: 28,
      bottom: wide ? 38 : 32,
      containLabel: false,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: tooltipFormatter,
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: hours.map(({ at }) => hourLabel(at)),
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisTick: { show: false },
      axisLabel: {
        color: AXIS_COLOR,
        fontSize: wide ? 11 : 10,
        interval: 0,
      },
    },
    yAxis: [
      {
        name: '°F',
        type: 'value',
        position: 'left',
        scale: true,
        axisLabel: { color: '#f59e0b', fontSize: 10 },
        nameTextStyle: { color: '#f59e0b' },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
      {
        name: '%',
        type: 'value',
        position: 'right',
        min: 0,
        max: 100,
        axisLabel: { color: '#38bdf8', fontSize: 10 },
        nameTextStyle: { color: '#38bdf8' },
        splitLine: { show: false },
      },
      {
        type: 'value',
        show: false,
        min: 0,
      },
      {
        name: 'mph',
        type: 'value',
        position: 'right',
        offset: 42,
        min: 0,
        axisLabel: { color: '#22d3ee', fontSize: 10 },
        nameTextStyle: { color: '#22d3ee' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Radiation',
        type: 'bar',
        yAxisIndex: 2,
        data: hours.map(({ radiationWm2 }) => radiationWm2),
        itemStyle: { color: '#fbbf24', opacity: 0.14 },
        silent: true,
      },
      {
        name: 'Precipitation',
        type: 'bar',
        yAxisIndex: 1,
        data: hours.map(({ precipPct }) => precipPct),
        itemStyle: { color: '#38bdf8', opacity: 0.55 },
      },
      {
        name: 'Temperature',
        type: 'line',
        yAxisIndex: 0,
        data: hours.map(({ tempF }) => tempF),
        smooth: false,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
      },
      {
        name: 'Wind',
        type: 'line',
        yAxisIndex: 3,
        data: hours.map(({ windMph }) => windMph),
        smooth: false,
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2, color: '#22d3ee' },
        itemStyle: { color: '#22d3ee' },
      },
    ],
  };
}
