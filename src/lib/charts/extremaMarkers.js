function shiftDecimal(value, places) {
  const [coefficient, exponent = '0'] = String(value).split('e');
  return Number(coefficient + 'e' + (Number(exponent) + places));
}

export function formatHistoryValue(value) {
  if (!Number.isFinite(value)) return '—';
  if (Number.isInteger(value)) return String(value);
  const magnitude = shiftDecimal(Math.round(shiftDecimal(Math.abs(value), 3)), -3);
  const rounded = Math.sign(value) * magnitude;
  return String(rounded);
}

function candidate(point) {
  const time = point?.time;
  const value = point?.value;
  if (!Number.isFinite(time) || !Number.isFinite(value)) return null;
  const rawValue = point?.rawValue;
  return {
    time,
    value,
    rawValue: Number.isFinite(rawValue) ? rawValue : value,
  };
}

export function findHistoryExtrema(points = []) {
  let min = null;
  let max = null;
  for (const point of points) {
    const next = candidate(point);
    if (!next) continue;
    if (!min || next.value < min.value || (next.value === min.value && next.time < min.time)) {
      min = next;
    }
    if (!max || next.value > max.value || (next.value === max.value && next.time < max.time)) {
      max = next;
    }
  }
  return { min, max };
}

function markerRecord(name, point, unit) {
  return {
    name,
    coord: [point.time, point.value],
    value: point.rawValue,
    markerUnit: unit,
  };
}

export function buildExtremaMarkPoint(points = [], {
  markers = [],
  unit = '',
  color,
} = {}) {
  const enabled = new Set(markers);
  const extrema = findHistoryExtrema(points);
  const data = [];
  if (enabled.has('max') && extrema.max) {
    data.push(markerRecord('High', extrema.max, unit));
  }
  if (enabled.has('min') && extrema.min) {
    data.push(markerRecord('Low', extrema.min, unit));
  }
  if (!data.length) return undefined;
  if (
    data.length === 2
    && data[0].coord[0] === data[1].coord[0]
    && data[0].coord[1] === data[1].coord[1]
  ) {
    data[0].symbolOffset = [0, -28];
    data[1].symbolOffset = [0, 28];
  }
  return {
    symbol: 'pin',
    symbolSize: 52,
    ...(color ? { itemStyle: { color } } : {}),
    label: {
      color: '#000',
      fontSize: 10,
      lineHeight: 12,
      formatter: ({ data: marker, name, value }) => (
        `${name}\n${formatHistoryValue(value)}${marker?.markerUnit ?? unit}`
      ),
    },
    data,
  };
}

export function describeExtremaMarkers(renderedSeries = []) {
  return renderedSeries.flatMap((series) => {
    const markers = series?.markPoint?.data;
    if (!Array.isArray(markers) || !markers.length) return [];
    const values = markers.map((marker) => (
      `${marker.name} ${formatHistoryValue(marker.value)}${marker.markerUnit || ''}`
    ));
    return [`${series.name}: ${values.join(', ')}.`];
  }).join(' ');
}
