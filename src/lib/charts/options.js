import { buildExtremaMarkPoint, formatHistoryValue } from './extremaMarkers.js';
import { prepareHistorySeries } from './historyPipeline.js';
import { getSeriesPolicy } from './seriesPolicy.js';
import { colors, echartsTheme } from '../ui/tokens.js';

// Shared HTML escaping for ECharts tooltip formatters (ECharts renders
// formatter strings as HTML, so any item-derived text must pass through
// here before interpolation).
export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function formatHistoryTooltip(params) {
  const entries = Array.isArray(params) ? params : [params];
  const firstTime = entries.find((entry) => Number.isFinite(entry?.data?.[0]))?.data?.[0];
  const heading = Number.isFinite(firstTime)
    ? `<div>${escapeHtml(new Date(firstTime).toLocaleString())}</div>`
    : '';
  return heading + entries
    .filter((entry) => Number.isFinite(entry?.data?.[2]))
    .map((entry) => (
      `<div>${entry.marker || ''}${escapeHtml(entry.seriesName)}: `
      + `${escapeHtml(formatHistoryValue(entry.data[2]))}</div>`
    ))
    .join('');
}

function flattenSegments(segments) {
  return segments.flatMap((segment) => (
    segment.map((point) => [point.time, point.value, point.rawValue])
  ));
}

function lineOption(source, data, {
  name,
  dashed = false,
  markPoint,
} = {}) {
  return {
    name: name || source.label || source.name,
    type: 'line',
    showSymbol: false,
    smooth: false,
    connectNulls: false,
    dimensions: ['time', 'display', 'raw'],
    encode: { x: 'time', y: 'display' },
    lineStyle: {
      width: 2,
      color: source.color,
      ...(dashed ? { type: 'dashed' } : {}),
    },
    itemStyle: { color: source.color },
    ...(markPoint ? { markPoint } : {}),
    data,
  };
}

function splitForecastSegments(segments, nowMs) {
  const solid = [];
  const future = [];
  for (const segment of segments) {
    const past = segment.filter((point) => point.time <= nowMs);
    const ahead = segment.filter((point) => point.time > nowMs);
    if (past.length) solid.push(past);
    if (ahead.length) future.push(past.length ? [past.at(-1), ...ahead] : ahead);
  }
  return { solid, future };
}

function scalarProjection(source, nowMs) {
  if (source.projectionValue == null) return [];
  const value = Number(source.projectionValue);
  const hours = Number(source.projectionHours);
  if (!Number.isFinite(value) || !Number.isFinite(hours) || hours <= 0) return [];
  const endMs = nowMs + hours * 60 * 60 * 1_000;
  if (!Number.isFinite(endMs)) return [];
  return [[nowMs, value, value], [endMs, value, value]];
}

export function buildHistoryOption({
  series = [],
  pointsPerSeries = [],
  widthPx = 0,
  nowMs = Date.now(),
  grid = { left: 44, right: 16, top: 28, bottom: 28 },
  legendTop = 0,
  legendFontSize = 10,
} = {}) {
  const perSeriesBudget = series.length
    ? Math.min(
      Math.max(1, Math.floor(widthPx * 2)),
      Math.max(1, Math.floor((widthPx * 4) / series.length)),
    )
    : 0;
  const renderedSeries = [];

  series.forEach((source, index) => {
    const policy = getSeriesPolicy(source);
    const prepared = prepareHistorySeries(pointsPerSeries[index] || [], {
      ...policy,
      widthPx,
      pointBudget: perSeriesBudget,
    });
    const markPoint = buildExtremaMarkPoint(prepared.raw, {
      markers: source.markers,
      unit: source.markerUnit,
      color: source.color,
    });
    if (source.dashedFromNow) {
      const split = splitForecastSegments(prepared.displaySegments, nowMs);
      const persistedFuture = flattenSegments(split.future);
      const projectedFuture = scalarProjection(source, nowMs);
      const futureData = persistedFuture.length ? persistedFuture : projectedFuture;
      renderedSeries.push(lineOption(
        source,
        flattenSegments(split.solid),
        { markPoint },
      ));
      if (futureData.length) {
        renderedSeries.push(lineOption(
          source,
          futureData,
          { name: `${source.label || source.name} (forecast)`, dashed: true },
        ));
      }
    } else {
      renderedSeries.push(lineOption(
        source,
        flattenSegments(prepared.displaySegments),
        { markPoint },
      ));
    }
  });

  return {
    ...echartsTheme,
    grid,
    legend: {
      data: series.map((source) => source.label || source.name),
      top: legendTop,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: { color: colors.label, fontSize: legendFontSize },
    },
    tooltip: { trigger: 'axis', formatter: formatHistoryTooltip },
    xAxis: {
      type: 'time',
      axisLine: echartsTheme.categoryAxis.axisLine,
      axisLabel: echartsTheme.categoryAxis.axisLabel,
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: echartsTheme.valueAxis.axisLine,
      axisLabel: echartsTheme.valueAxis.axisLabel,
      splitLine: echartsTheme.valueAxis.splitLine,
    },
    series: renderedSeries,
    animation: false,
  };
}
