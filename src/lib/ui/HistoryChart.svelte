<script>
  // Reusable inline history chart (ECharts line, dark console theme). Used
  // by Energy (and any future screen) for multi-series history — unlike
  // ChartModal, this renders inline on the page rather than as an overlay.
  //
  // series: [{ name, color, label, dashedFromNow? }] — name is the openHAB
  // item queried via getClientOnce().getHistory(). dashedFromNow marks a
  // series whose points AFTER "now" (forecast/prediction rows persisted
  // ahead of time, e.g. Forecast_Daily_High) should render with a dashed
  // line style instead of the normal solid one.
  import { onMount, onDestroy, tick } from 'svelte';
  import * as echarts from 'echarts';
  import { echartsTheme, colors } from './tokens.js';
  import { getClientOnce } from '../openhab/index.js';
  import { num } from '../openhab/values.js';

  let { series = [], hours = 24, height = '100%' } = $props();

  let el = $state();
  let chart;
  let loading = $state(false);
  let noData = $state(false);
  let noClient = $state(false);
  // Monotonic generation token: guards against a stale load() call
  // (superseded by a newer mount/refresh) overwriting current state once
  // its awaited work finally resolves — same pattern as ChartModal.
  let loadGen = 0;
  let refreshTimer;

  const REFRESH_MS = 300000; // 5 minutes

  function disposeChart() {
    chart?.dispose();
    chart = null;
  }

  // Splits one series' raw history points into a solid segment (<= now) and
  // a dashed segment (> now, for forecast rows). The dashed segment starts
  // one point early (last solid point repeated) so the two line pieces
  // visually connect with no gap.
  function splitAtNow(points, nowMs) {
    const pts = (points || [])
      .map((p) => [new Date(p.time).getTime(), num(p.state)])
      .filter((pt) => Number.isFinite(pt[0]) && pt[1] !== null)
      .sort((a, b) => a[0] - b[0]);
    const solid = pts.filter((p) => p[0] <= nowMs);
    const future = pts.filter((p) => p[0] > nowMs);
    if (solid.length && future.length) {
      future.unshift(solid[solid.length - 1]);
    }
    return { solid, future };
  }

  function buildOption(seriesList, pointsPerSeries) {
    const nowMs = Date.now();
    const echartsSeries = [];
    seriesList.forEach((s, i) => {
      const raw = pointsPerSeries[i] || [];
      if (s.dashedFromNow) {
        const { solid, future } = splitAtNow(raw, nowMs);
        echartsSeries.push({
          name: s.label || s.name,
          type: 'line',
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 2, color: s.color },
          itemStyle: { color: s.color },
          data: solid,
        });
        if (future.length) {
          echartsSeries.push({
            name: `${s.label || s.name} (forecast)`,
            type: 'line',
            showSymbol: false,
            smooth: true,
            lineStyle: { width: 2, color: s.color, type: 'dashed' },
            itemStyle: { color: s.color },
            data: future,
          });
        }
      } else {
        const pts = raw
          .map((p) => [new Date(p.time).getTime(), num(p.state)])
          .filter((pt) => Number.isFinite(pt[0]) && pt[1] !== null);
        echartsSeries.push({
          name: s.label || s.name,
          type: 'line',
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 2, color: s.color },
          itemStyle: { color: s.color },
          data: pts,
        });
      }
    });

    return {
      ...echartsTheme,
      grid: { left: 44, right: 16, top: 28, bottom: 28 },
      legend: {
        data: seriesList.map((s) => s.label || s.name),
        top: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: colors.label, fontSize: 10 },
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
      series: echartsSeries,
      animation: false,
    };
  }

  async function load() {
    const myGen = ++loadGen;
    noClient = false;
    noData = false;

    const client = getClientOnce();
    if (!client) {
      noClient = true;
      return;
    }
    if (!series.length) {
      noData = true;
      return;
    }

    loading = true;
    const now = Date.now();
    const starttime = new Date(now - hours * 3600 * 1000).toISOString();
    // Pad well into the future so persisted forecast rows (e.g.
    // Forecast_Daily_High / Predicted_SoC_Trough_Tomorrow) are included.
    const endtime = new Date(now + 18 * 3600 * 1000).toISOString();

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
    disposeChart();
    chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(series, results));
  }

  function onResize() {
    chart?.resize();
  }

  onMount(() => {
    load();
    if (typeof window !== 'undefined') window.addEventListener('resize', onResize);
    refreshTimer = setInterval(load, REFRESH_MS);
  });

  onDestroy(() => {
    loadGen++; // invalidate any in-flight load
    if (refreshTimer) clearInterval(refreshTimer);
    if (typeof window !== 'undefined') window.removeEventListener('resize', onResize);
    disposeChart();
  });
</script>

<div class="history-chart" style="height: {height}">
  {#if noClient}
    <div class="hc-message"></div>
  {:else if loading}
    <div class="hc-message">Loading…</div>
  {:else if noData}
    <div class="hc-message">No data</div>
  {:else}
    <div bind:this={el} class="hc-canvas"></div>
  {/if}
</div>

<style>
  .history-chart {
    width: 100%;
    min-height: 0;
  }
  .hc-canvas {
    width: 100%;
    height: 100%;
  }
  .hc-message {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 3rem;
    color: #8b93a1;
    font-size: 0.85rem;
  }
</style>
