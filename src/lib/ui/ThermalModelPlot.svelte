<script>
  let { trajectory = [], observed = [] } = $props();

  const WIDTH = 720;
  const HEIGHT = 220;
  const LEFT = 34;
  const RIGHT = 12;
  const TOP = 20;
  const BOTTOM = 28;
  const OBSERVED_GAP_MS = 10 * 60_000;
  const FORECAST_GAP_MS = 2 * 60 * 60_000;
  const ACTIONS = new Set([
    'vent_open', 'vent_close', 'indoor_shade_open', 'indoor_shade_close',
    'outdoor_shade_installed', 'outdoor_shade_removed',
  ]);

  function splitGaps(rows, gapMs) {
    const segments = [];
    for (const row of rows) {
      const current = segments.at(-1);
      if (!current || row.atMs - current.at(-1).atMs >= gapMs) segments.push([row]);
      else current.push(row);
    }
    return segments;
  }

  function pointString(rows, x, y, field) {
    return rows.map((row) => `${x(row.atMs)},${y(row[field])}`).join(' ');
  }

  function intervalString(rows, x, y) {
    const upper = rows.map((row) => `${x(row.atMs)},${y(row.highF)}`);
    const lower = [...rows].reverse().map((row) => `${x(row.atMs)},${y(row.lowF)}`);
    return [...upper, ...lower].join(' ');
  }

  function clockLabel(atMs) {
    return new Date(atMs).toLocaleTimeString([], { hour: 'numeric' });
  }

  const plot = $derived.by(() => {
    const forecastRows = Array.isArray(trajectory) ? trajectory : [];
    const observedRows = Array.isArray(observed) ? observed : [];
    const allRows = [...observedRows, ...forecastRows];
    if (allRows.length === 0) return null;

    const times = allRows.map((row) => row.atMs);
    const temperatures = [
      ...observedRows.flatMap((row) => [row.hallwayF, row.massF]),
      ...forecastRows.flatMap((row) => [row.hallwayF, row.massF, row.lowF, row.highF]),
    ];
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);
    const minTemp = Math.min(...temperatures) - 1;
    const maxTemp = Math.max(...temperatures) + 1;
    const timeSpan = Math.max(1, maxTime - minTime);
    const tempSpan = Math.max(1, maxTemp - minTemp);
    const x = (atMs) => LEFT + ((atMs - minTime) / timeSpan) * (WIDTH - LEFT - RIGHT);
    const y = (temp) => TOP + ((maxTemp - temp) / tempSpan) * (HEIGHT - TOP - BOTTOM);
    const forecastSegments = splitGaps(forecastRows, FORECAST_GAP_MS);
    const observedSegments = splitGaps(observedRows, OBSERVED_GAP_MS);

    return {
      x,
      y,
      minTime,
      maxTime,
      minTemp,
      maxTemp,
      forecastRows,
      observedRows,
      forecastSegments,
      observedSegments,
      actions: forecastRows.flatMap((row) => row.actions
        .filter((action) => ACTIONS.has(action))
        .map((action) => ({ action, atMs: row.atMs }))),
    };
  });
</script>

{#if plot}
  <svg
    class="thermal-model-plot"
    viewBox="0 0 {WIDTH} {HEIGHT}"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Observed hallway and mass temperatures with forecast hallway and mass temperatures, forecast interval, and typed action markers"
  >
    <line class="axis" x1={LEFT} y1={HEIGHT - BOTTOM} x2={WIDTH - RIGHT} y2={HEIGHT - BOTTOM} />
    <line class="axis" x1={LEFT} y1={TOP} x2={LEFT} y2={HEIGHT - BOTTOM} />
    <text class="axis-label" x={LEFT} y={HEIGHT - 7}>{clockLabel(plot.minTime)}</text>
    <text class="axis-label end" x={WIDTH - RIGHT} y={HEIGHT - 7}>{clockLabel(plot.maxTime)}</text>
    <text class="axis-label" x="2" y={TOP + 4}>{Math.ceil(plot.maxTemp)}°</text>
    <text class="axis-label" x="2" y={HEIGHT - BOTTOM}>{Math.floor(plot.minTemp)}°</text>

    {#each plot.forecastSegments as segment}
      <polygon
        data-series="forecast-interval"
        points={intervalString(segment, plot.x, plot.y)}
        class="interval"
      />
    {/each}

    {#each plot.observedSegments as segment}
      <polyline data-series="observed-hallway" points={pointString(segment, plot.x, plot.y, 'hallwayF')} class="line observed hallway" />
      <polyline data-series="observed-mass" points={pointString(segment, plot.x, plot.y, 'massF')} class="line observed mass" />
    {/each}
    {#each plot.forecastSegments as segment}
      <polyline data-series="forecast-hallway" points={pointString(segment, plot.x, plot.y, 'hallwayF')} class="line forecast hallway" />
      <polyline data-series="forecast-mass" points={pointString(segment, plot.x, plot.y, 'massF')} class="line forecast mass" />
    {/each}

    {#each plot.observedRows as row}
      <circle data-point="observed" cx={plot.x(row.atMs)} cy={plot.y(row.hallwayF)} r="2.4" class="point observed" />
    {/each}
    {#each plot.forecastRows as row}
      <circle data-point="forecast" cx={plot.x(row.atMs)} cy={plot.y(row.hallwayF)} r="2.4" class="point forecast" />
    {/each}

    {#each plot.actions as marker, index (`${marker.atMs}-${marker.action}-${index}`)}
      <g data-action={marker.action} class="action-marker">
        <title>{marker.action.replaceAll('_', ' ')}</title>
        <line x1={plot.x(marker.atMs)} y1={TOP} x2={plot.x(marker.atMs)} y2={HEIGHT - BOTTOM} />
        <circle cx={plot.x(marker.atMs)} cy={TOP + 5} r="4" />
      </g>
    {/each}

    <g class="legend" aria-hidden="true">
      <text x={LEFT + 8} y={TOP + 13}>Hallway</text>
      <text x={LEFT + 72} y={TOP + 13}>Mass</text>
      <text x={LEFT + 112} y={TOP + 13}>solid observed · dashed forecast</text>
    </g>
  </svg>
{:else}
  <p class="empty">No thermal model series available</p>
{/if}

<style>
  .thermal-model-plot {
    display: block;
    width: 100%;
    max-height: 13rem;
    color: #6b7280;
  }
  .axis {
    stroke: #303846;
    stroke-width: 1;
  }
  .axis-label,
  .legend text {
    fill: #6b7280;
    font-size: 10px;
  }
  .axis-label.end {
    text-anchor: end;
  }
  .interval {
    fill: #38bdf8;
    opacity: 0.12;
  }
  .line {
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2;
  }
  .line.hallway {
    stroke: #e6edf3;
  }
  .line.mass {
    stroke: #c2703d;
  }
  .line.forecast {
    stroke-dasharray: 6 4;
  }
  .point.observed {
    fill: #e6edf3;
  }
  .point.forecast {
    fill: #38bdf8;
  }
  .action-marker line {
    stroke: #a78bfa;
    stroke-width: 1;
    stroke-dasharray: 2 3;
    opacity: 0.65;
  }
  .action-marker circle {
    fill: #a78bfa;
  }
  .empty {
    margin: 0;
    color: #6b7280;
    font-size: 0.72rem;
  }
</style>
