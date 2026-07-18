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
  import { buildHistoryOption } from '../charts/options.js';
  import {
    HISTORY_PERIOD_PRESETS,
    createHistoryWindow,
    snapHistoryPeriod,
  } from '../charts/periods.js';
  import { getClientOnce, clientReady } from '../openhab/index.js';

  // `hours` remains as a compatibility alias while callers migrate to the
  // clearer one-shot `initialHours` name.
  let { series = [], initialHours, hours = 24 } = $props();

  let el = $state();
  let chart;
  let loading = $state(false);
  let noData = $state(false);
  let noClient = $state(false);
  // Currently-selected history window, in hours. Initialized from the
  // `hours` prop (snapped to the nearest preset) and thereafter driven only
  // by the period picker buttons — the load() function reads this instead
  // of the raw `hours` prop.
  let activeHours = $state(untrack(() => snapHistoryPeriod(initialHours ?? hours)));
  // Monotonic generation token: guards against a stale load() call
  // (superseded by a newer mount/refresh) overwriting current state once
  // its awaited work finally resolves — same pattern as ChartModal.
  let loadGen = 0;
  let refreshTimer;
  let resizeObserver;
  let requestController;
  let latestResults = [];
  let latestNowMs = 0;
  let latestWidthPx = 0;

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

  function cancelPending() {
    requestController?.abort();
    requestController = null;
  }

  function renderLatest(widthPx) {
    if (!chart || !latestResults.length || widthPx <= 0) return;
    latestWidthPx = widthPx;
    chart.setOption(buildHistoryOption({
      series,
      pointsPerSeries: latestResults,
      widthPx,
      nowMs: latestNowMs,
    }), true);
    chart.resize();
  }

  async function load() {
    cancelPending();
    const controller = new AbortController();
    requestController = controller;
    const myGen = ++loadGen;
    noClient = false;
    noData = false;

    const client = getClientOnce();
    if (!client) {
      loading = false;
      noClient = true;
      return;
    }
    if (!series.length) {
      loading = false;
      noData = true;
      return;
    }

    loading = true;
    const now = Date.now();
    const requestWindow = createHistoryWindow(activeHours, { nowMs: now });

    let results;
    try {
      results = await Promise.all(
        series.map(async (source) => {
          try {
            return await client.getHistory(source.name, {
              starttime: requestWindow.starttime,
              endtime: requestWindow.endtime,
              signal: controller.signal,
            });
          } catch (error) {
            if (controller.signal.aborted) throw error;
            return [];
          }
        }),
      );
    } catch {
      if (controller.signal.aborted || myGen !== loadGen) return;
      results = series.map(() => []);
    }
    if (controller.signal.aborted || myGen !== loadGen) return;
    if (requestController === controller) requestController = null;
    loading = false;

    const anyData = results.some((r) => Array.isArray(r) && r.length > 0);
    if (!anyData) {
      noData = true;
      return;
    }

    await tick();
    if (controller.signal.aborted || myGen !== loadGen) return;
    if (!el) return;
    disposeChart();
    chart = echarts.init(el, null, { renderer: 'svg' });
    latestResults = results;
    latestNowMs = now;
    renderLatest(el.parentElement?.clientWidth || el.clientWidth || 320);

    if (typeof ResizeObserver !== 'undefined' && el.parentElement) {
      resizeObserver = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect?.width
          || el.parentElement?.clientWidth
          || el.clientWidth;
        if (width > 0 && Math.abs(width - latestWidthPx) >= 1) renderLatest(width);
        else chart?.resize();
      });
      resizeObserver.observe(el.parentElement);
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
    cancelPending();
    if (refreshTimer) clearInterval(refreshTimer);
    if (typeof window !== 'undefined') window.removeEventListener('resize', onResize);
    disposeChart();
  });
</script>

<div class="history-chart">
  <div class="hc-periods" role="group" aria-label="History period">
    {#each HISTORY_PERIOD_PRESETS as p (p.hours)}
      <button
        type="button"
        class="hc-period-btn"
        class:active={activeHours === p.hours}
        aria-pressed={activeHours === p.hours}
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
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    overflow: hidden;
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
    min-width: 2.75rem;
    min-height: 2.75rem;
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
    min-width: 0;
    overflow: hidden;
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
