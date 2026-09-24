import { buildExtremaMarkPoint, formatHistoryValue } from './extremaMarkers.js';
import { normalizeHistory, prepareHistorySeries, smoothSocDisplay } from './historyPipeline.js';
import { getSeriesPolicy } from './seriesPolicy.js';
import { colors, echartsTheme } from '../ui/tokens.js';
import { atomicSocFreshness } from '../alerts/atomicSoc.js';

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

function flattenSegments(segments, { breakGaps = false } = {}) {
  const data = [];
  for (const segment of segments) {
    if (!segment.length) continue;
    if (breakGaps && data.length) {
      const previousTime = data.at(-1)[0];
      data.push([previousTime + (segment[0].time - previousTime) / 2, null, null]);
    }
    data.push(...segment.map((point) => [point.time, point.value, point.rawValue]));
  }
  return data;
}

function lineOption(source, data, {
  name,
  dashed = false,
  markPoint,
} = {}) {
  return {
    name: name || source.label || source.name,
    type: 'line',
    // Keep the actual change-only samples visible along the smoothed trend.
    showSymbol: source.name === 'BMS_SOC',
    ...(source.name === 'BMS_SOC' ? { symbolSize: 3 } : {}),
    smooth: source.name === 'BMS_SOC' ? 0.2 : false,
    ...(source.name === 'BMS_SOC' ? { smoothMonotone: 'x' } : {}),
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

function withFreshSocEndpoint(source, rows, policy, rawEvidence, nowMs) {
  if (source.name !== 'BMS_SOC') return rows;
  const receipt = atomicSocFreshness(rawEvidence, nowMs);
  if (!receipt) return rows;
  const normalized = normalizeHistory(rows, { allowedUnits: policy.allowedUnits });
  const last = normalized.at(-1);
  if (!last || last.time > receipt.recordedAt || last.time >= nowMs) return rows;
  const endpoint = [];
  if (last.value !== receipt.soc && last.time < receipt.recordedAt) {
    endpoint.push({ time: receipt.recordedAt, state: receipt.soc });
  }
  endpoint.push({ time: nowMs, state: receipt.soc });
  return [...rows, ...endpoint];
}

export function buildHistoryOption({
  series = [],
  pointsPerSeries = [],
  widthPx = 0,
  nowMs = Date.now(),
  grid = { left: 44, right: 16, top: 28, bottom: 28 },
  legendTop = 0,
  legendFontSize = 10,
  socEvidenceRaw = null,
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
    const rows = withFreshSocEndpoint(source, pointsPerSeries[index] || [], policy, socEvidenceRaw, nowMs);
    const prepared = prepareHistorySeries(rows, {
      ...policy,
      widthPx,
      pointBudget: perSeriesBudget,
    });
    const displaySegments = source.name === 'BMS_SOC'
      ? prepared.displaySegments.map((segment) => smoothSocDisplay(segment))
      : prepared.displaySegments;
    const markPoint = buildExtremaMarkPoint(prepared.raw, {
      markers: source.markers,
      unit: source.markerUnit,
      color: source.color,
    });
    if (source.dashedFromNow) {
      const split = splitForecastSegments(displaySegments, nowMs);
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
          { name: source.forecastLabel || `${source.label || source.name} (forecast)`, dashed: true },
        ));
      }
    } else {
      renderedSeries.push(lineOption(
        source,
        flattenSegments(displaySegments, { breakGaps: policy.gapPolicy === 'break' }),
        { markPoint },
      ));
    }
  });

  return {
    ...echartsTheme,
    grid,
    legend: {
      data: [...new Set(renderedSeries.filter((source) => source.data.length).map((source) => source.name))],
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
