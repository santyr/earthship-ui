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
  import { onMount, onDestroy, tick, untrack } from 'svelte';
  import * as echarts from 'echarts';
  import { echartsTheme, colors } from './tokens.js';
  import { getClientOnce, clientReady } from '../openhab/index.js';
  import { num } from '../openhab/values.js';

  // height: definite CSS pixel height for the chart container. ECharts
  // needs a sized element at init time — a flex child with no explicit
  // height (e.g. height:100% inside a flex column) can resolve to 0px
  // depending on ancestor sizing/timing, which makes echarts.init() render
  // nothing (0 canvas elements). So this is always applied as a literal
  // `px` height on the outer container rather than a percentage.
  let { series = [], hours = 24, height = 200 } = $props();

  // Period picker presets — 4h / 24h / 7d / 30d, mapped to hours.
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

  let el = $state();
  let chart;
  let loading = $state(false);
  let noData = $state(false);
  let noClient = $state(false);
  // Currently-selected history window, in hours. Initialized from the
  // `hours` prop (snapped to the nearest preset) and thereafter driven only
  // by the period picker buttons — the load() function reads this instead
  // of the raw `hours` prop.
  let activeHours = $state(untrack(() => snapToPreset(hours)));
  // Monotonic generation token: guards against a stale load() call
  // (superseded by a newer mount/refresh) overwriting current state once
  // its awaited work finally resolves — same pattern as ChartModal.
  let loadGen = 0;
  let refreshTimer;
  let resizeObserver;

  const REFRESH_MS = 300000; // 5 minutes

  function selectPeriod(h) {
    if (h === activeHours) return;
    activeHours = h;
  }

  function disposeChart() {
    resizeObserver?.disconnect();
    resizeObserver = null;
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
    const starttime = new Date(now - activeHours * 3600 * 1000).toISOString();
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
    // el is guaranteed a definite pixel height (see `height` prop / style
    // below) by the time this runs, so echarts.init() gets a real,
    // non-zero-size element to measure.
    chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(series, results));
    chart.resize();

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => chart?.resize());
      resizeObserver.observe(el);
    }
  }

  function onResize() {
    chart?.resize();
  }

  // Loads data once the openHAB client is ready, and re-loads whenever the
  // client (re)connects, or the hours window / series list change. On a
  // direct/reload page load, this component mounts before App.svelte's
  // onMount has run initOpenhab(), so clientReady is still false and
  // getClientOnce() would return null — waiting on $clientReady here (rather
  // than only loading once on mount) is what lets the chart populate as
  // soon as the client actually exists, instead of staying blank forever.
  $effect(() => {
    const ready = $clientReady;
    // Establish reactive dependencies so a change to either re-triggers load.
    void activeHours;
    void series;
    if (ready) {
      load();
    } else {
      noClient = true;
    }
  });

  onMount(() => {
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

<div class="history-chart" style="height: {height}px; width: 100%;">
  <div class="hc-periods" role="group" aria-label="History period">
    {#each PERIOD_PRESETS as p (p.hours)}
      <button
        type="button"
        class="hc-period-btn"
        class:active={activeHours === p.hours}
        onclick={() => selectPeriod(p.hours)}
      >{p.label}</button>
    {/each}
  </div>
  <div class="hc-content">
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
</div>

<style>
  .history-chart {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .hc-periods {
    display: flex;
    gap: 0.3rem;
    flex: 0 0 auto;
  }
  .hc-period-btn {
    background: #161b24;
    border: 1px solid #1c2230;
    color: #8b93a1;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 0.3rem 0.6rem;
    min-height: 1.6rem;
    border-radius: 999px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    -webkit-tap-highlight-color: transparent;
  }
  .hc-period-btn.active {
    background: #1c2230;
    color: #e6edf3;
    border-color: #2a3242;
  }
  .hc-period-btn:hover {
    color: #e6edf3;
  }
  .hc-content {
    flex: 1;
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
