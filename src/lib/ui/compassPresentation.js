const POINTS = [
  'N', 'NNE', 'NE', 'ENE',
  'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW',
  'W', 'WNW', 'NW', 'NNW',
];

function finiteTelemetry(value) {
  if (
    value === null
    || value === undefined
    || value === ''
    || value === 'NULL'
    || value === 'UNDEF'
  ) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function compassPresentation(degrees, speed) {
  const rawHeading = finiteTelemetry(degrees);
  const rawSpeed = finiteTelemetry(speed);
  const hasSpeed = rawSpeed !== null && rawSpeed >= 0;
  const calm = hasSpeed && rawSpeed === 0;
  const normalized = rawHeading === null ? null : ((rawHeading % 360) + 360) % 360;
  const hasHeading = normalized !== null && !calm;
  const point = hasHeading
    ? POINTS[Math.floor((normalized + 11.25) / 22.5) % POINTS.length]
    : null;
  const roundedHeading = hasHeading ? Math.round(normalized) % 360 : 0;
  const speedText = hasSpeed ? String(rawSpeed) : '—';
  const headingText = calm ? 'CALM' : hasHeading ? `${point} · ${roundedHeading}°` : 'DIR —';

  let ariaLabel;
  if (calm) {
    ariaLabel = `Wind calm, speed ${speedText} mph`;
  } else {
    const direction = hasHeading
      ? `Wind direction ${point}, ${roundedHeading} degrees`
      : 'Wind direction unavailable';
    const speedLabel = hasSpeed ? `speed ${speedText} mph` : 'speed unavailable';
    ariaLabel = `${direction}, ${speedLabel}`;
  }

  return {
    hasHeading,
    heading: hasHeading ? normalized : 0,
    point,
    headingText,
    hasSpeed,
    speedText,
    calm,
    ariaLabel,
  };
}
