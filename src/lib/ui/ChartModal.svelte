<script>
  // Full-screen click-to-chart overlay. Mount once (in App.svelte); any
  // tile opens it via chartStore's openChart({ title, series, hours }).
  // series: [{ name, color, label }] — name is the openHAB item queried
  // via getClientOnce().getHistory(). Multiple series are overlaid on one
  // time-axis chart with a legend.
  import { onDestroy, tick } from 'svelte';
  import * as echarts from 'echarts';
  import { chartStore, closeChart } from './chartStore.js';
  import { echartsTheme, colors } from './tokens.js';
  import { getClientOnce } from '../openhab/index.js';
  import { num } from '../openhab/values.js';

  let el = $state();
  let chart;
  let loading = $state(false);
  let noData = $state(false);
  let noClient = $state(false);
  // Monotonic generation token: guards against a stale loadAndRender()
  // call (superseded by a newer openChart()) overwriting current state
  // once its awaited work finally resolves.
  let loadGen = 0;

  // Period picker presets — 4h / 24h / 7d / 30d, mapped to hours. The modal
  // reads chartStore's `hours` only as the initial value for whichever
  // chart was just opened; from then on the picker owns the active window
  // locally, same pattern as HistoryChart.
  const PERIOD_PRESETS = [
    { label: '4h', hours: 4 },
    { label: '24h', hours: 24 },
    { label: '7d', hours: 168 },
    { label: '30d', hours: 720 },
  ];

  function snapToPreset(h) {
    if (!Number.isFinite(h)) return 24;
    let best = PERIOD_PRESETS[0];
    let bestDiff = Math.abs(h - best.hours);
    for (const p of PERIOD_PRESETS) {
      const diff = Math.abs(h - p.hours);
      if (diff < bestDiff) {
        best = p;
        bestDiff = diff;
      }
    }
    return best.hours;
  }

  let activeHours = $state(24);

  function disposeChart() {
    chart?.dispose();
    chart = null;
  }

  function buildOption(series, pointsPerSeries) {
    return {
      ...echartsTheme,
      grid: { left: 52, right: 24, top: 56, bottom: 40 },
      legend: {
        data: series.map((s) => s.label || s.name),
        textStyle: { color: colors.label },
        top: 8,
      },
      tooltip: { trigger: 'axis' },
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
      series: series.map((s, i) => ({
        name: s.label || s.name,
        type: 'line',
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: s.color },
        itemStyle: { color: s.color },
        data: (pointsPerSeries[i] || [])
          .map((p) => [new Date(p.time).getTime(), num(p.state)])
          .filter((pt) => pt[1] !== null),
      })),
      animation: false,
    };
  }

  async function loadAndRender(seriesList, hoursVal) {
    const myGen = ++loadGen;
    noClient = false;
    noData = false;
    disposeChart();

    const client = getClientOnce();
    if (!client) {
      noClient = true;
      return;
    }
    const series = seriesList || [];
    if (series.length === 0) {
      noData = true;
      return;
    }

    loading = true;
    const now = Date.now();
    const hours = hoursVal || 24;
    const starttime = new Date(now - hours * 3600 * 1000).toISOString();
    // Pad a little into the future so forecast rows (e.g. tomorrow's
    // outlook) are included, not just the trailing history.
    const endtime = new Date(now + 30 * 60 * 1000).toISOString();

    let results;
    try {
      results = await Promise.all(
        series.map((s) => client.getHistory(s.name, { starttime, endtime }).catch(() => []))
      );
    } catch {
      results = series.map(() => []);
    }
    if (myGen !== loadGen) return;
    loading = false;

    const anyData = results.some((r) => Array.isArray(r) && r.length > 0);
    if (!anyData) {
      noData = true;
      return;
    }

    await tick();
    if (myGen !== loadGen) return;
    if (!el) return;
    chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(series, results));
  }

  $effect(() => {
    const state = $chartStore;
    if (state.open) {
      // A fresh openChart() call — snap the picker to that tile's initial
      // window and (re)load with it.
      activeHours = snapToPreset(state.hours || 24);
      const seriesSnapshot = state.series || [];
      const hoursSnapshot = activeHours;
      tick().then(() => loadAndRender(seriesSnapshot, hoursSnapshot));
    } else {
      // Invalidate any in-flight load so its continuation bails instead
      // of resurrecting loading/chart state after the modal has closed.
      loadGen++;
      disposeChart();
    }
  });

  function selectPeriod(h) {
    if (!$chartStore.open || h === activeHours) return;
    activeHours = h;
    loadAndRender($chartStore.series || [], h);
  }

  function onResize() {
    chart?.resize();
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('resize', onResize);
  }

  onDestroy(() => {
    if (typeof window !== 'undefined') window.removeEventListener('resize', onResize);
    disposeChart();
  });

  function onBackdropClick() {
    closeChart();
  }

  function onBackdropKeydown(e) {
    if (e.key === 'Escape') closeChart();
  }
</script>

{#if $chartStore.open}
  <div
    class="chart-backdrop"
    role="button"
    tabindex="0"
    onclick={onBackdropClick}
    onkeydown={onBackdropKeydown}
  >
    <div
      class="chart-panel"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="chart-header">
        <div class="chart-title">{$chartStore.title}</div>
        <div class="chart-periods" role="group" aria-label="History period">
          {#each PERIOD_PRESETS as p (p.hours)}
            <button
              type="button"
              class="chart-period-btn"
              class:active={activeHours === p.hours}
              onclick={() => selectPeriod(p.hours)}
            >{p.label}</button>
          {/each}
        </div>
        <button class="chart-close" onclick={closeChart} aria-label="Close chart">×</button>
      </div>
      <div class="chart-body">
        {#if noClient}
          <div class="chart-message"></div>
        {:else if loading}
          <div class="chart-message">Loading…</div>
        {:else if noData}
          <div class="chart-message">No data</div>
        {:else}
          <div bind:this={el} class="chart-canvas"></div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .chart-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(4, 6, 10, 0.82);
    z-index: 200;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    box-sizing: border-box;
  }
  .chart-panel {
    background: #11151c;
    border: 1px solid #1c2230;
    border-radius: 0.9rem;
    width: min(1100px, 100%);
    height: min(640px, 100%);
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    padding: 1rem 1.25rem;
  }
  .chart-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  .chart-title {
    font-size: 1rem;
    font-weight: 600;
    color: #e5e7eb;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chart-periods {
    display: flex;
    gap: 0.35rem;
    flex: 0 0 auto;
  }
  .chart-period-btn {
    background: #161b24;
    border: 1px solid #1c2230;
    color: #8b93a1;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 0.35rem 0.75rem;
    min-height: 1.9rem;
    border-radius: 999px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    -webkit-tap-highlight-color: transparent;
  }
  .chart-period-btn.active {
    background: #1c2230;
    color: #e5e7eb;
    border-color: #2a3242;
  }
  .chart-period-btn:hover {
    color: #e5e7eb;
  }
  .chart-close {
    background: transparent;
    border: none;
    color: #8b93a1;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
  }
  .chart-close:hover {
    color: #e5e7eb;
  }
  .chart-body {
    flex: 1;
    min-height: 0;
  }
  .chart-canvas {
    width: 100%;
    height: 100%;
  }
  .chart-message {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b93a1;
    font-size: 0.95rem;
  }
</style>
