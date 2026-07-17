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

  async function loadAndRender(state) {
    noClient = false;
    noData = false;
    disposeChart();

    const client = getClientOnce();
    if (!client) {
      noClient = true;
      return;
    }
    const series = state.series || [];
    if (series.length === 0) {
      noData = true;
      return;
    }

    loading = true;
    const now = Date.now();
    const hours = state.hours || 24;
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
    loading = false;

    const anyData = results.some((r) => Array.isArray(r) && r.length > 0);
    if (!anyData) {
      noData = true;
      return;
    }

    await tick();
    if (!el) return;
    chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(series, results));
  }

  $effect(() => {
    const state = $chartStore;
    if (state.open) {
      tick().then(() => loadAndRender(state));
    } else {
      disposeChart();
    }
  });

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
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }
  .chart-title {
    font-size: 1rem;
    font-weight: 600;
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
