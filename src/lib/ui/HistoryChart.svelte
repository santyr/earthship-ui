<script>
  import { onMount, onDestroy, tick, untrack } from 'svelte';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { buildHistoryOption } from '../charts/options.js';
  import { loadHistorySeries } from '../charts/historyRequest.js';
  import { HISTORY_PERIOD_PRESETS, snapHistoryPeriod } from '../charts/periods.js';
  import { getClientOnce, clientReady } from '../openhab/index.js';
  import { observeElementSize } from './observeElementSize.js';

  let { series = [], initialHours, hours = 24 } = $props();

  const REFRESH_MS = 5 * 60 * 1_000;
  let el = $state();
  let chart;
  let loadState = $state('idle');
  let errorMessage = $state('');
  let unavailableCount = $state(0);
  let activeHours = $state(untrack(() => snapHistoryPeriod(initialHours ?? hours)));
  let loadGen = 0;
  let refreshTimer;
  let requestController;
  let stopObserving = () => {};
  let latestResults = [];
  let latestSeries = [];
  let latestNowMs = 0;
  let latestWidthPx = 0;

  function selectPeriod(selectedHours) {
    if (selectedHours !== activeHours) activeHours = selectedHours;
  }

  function disposeChart() {
    stopObserving();
    stopObserving = () => {};
    chart?.dispose();
    chart = null;
  }

  function cancelPending() {
    requestController?.abort();
    requestController = null;
  }

  function renderLatest(widthPx) {
    if (!chart || widthPx <= 0) return;
    latestWidthPx = widthPx;
    try {
      chart.setOption(buildHistoryOption({
        series: latestSeries,
        pointsPerSeries: latestResults,
        widthPx,
        nowMs: latestNowMs,
      }), true);
      chart.resize();
    } catch (error) {
      errorMessage = error?.message || 'History could not be rendered';
      loadState = 'error';
      disposeChart();
    }
  }

  async function load(seriesList = series, hoursVal = activeHours) {
    cancelPending();
    const controller = new AbortController();
    requestController = controller;
    const myGen = ++loadGen;
    disposeChart();
    unavailableCount = 0;
    errorMessage = '';
    loadState = 'loading';

    const client = getClientOnce();
    if (!client) {
      if (requestController === controller) requestController = null;
      loadState = 'no-client';
      return;
    }
    if (!seriesList.length) {
      if (requestController === controller) requestController = null;
      loadState = 'empty';
      return;
    }

    const nowMs = Date.now();
    let result;
    try {
      result = await loadHistorySeries({
        client,
        series: seriesList,
        hours: hoursVal,
        nowMs,
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted || myGen !== loadGen) return;
      if (requestController === controller) requestController = null;
      errorMessage = error?.message || 'History request failed';
      loadState = 'error';
      return;
    }
    if (controller.signal.aborted || myGen !== loadGen) return;
    if (requestController === controller) requestController = null;

    latestResults = result.pointsPerSeries;
    latestSeries = seriesList;
    latestNowMs = nowMs;
    unavailableCount = result.errors.length;
    loadState = result.state;
    if (result.state === 'error') {
      errorMessage = result.errors[0]?.error?.message || 'History request failed';
      return;
    }
    if (result.state === 'empty') return;

    await tick();
    if (controller.signal.aborted || myGen !== loadGen || !el) return;
    const echarts = await getEcharts();
    if (controller.signal.aborted || myGen !== loadGen || !el) return;
    chart = echarts.init(el, null, { renderer: 'svg' });
    const parent = el.parentElement;
    renderLatest(parent?.clientWidth || el.clientWidth || 320);
    if (chart && parent) {
      stopObserving = observeElementSize(parent, ({ width }) => {
        if (width > 0 && Math.abs(width - latestWidthPx) >= 8) renderLatest(width);
        else chart?.resize();
      });
    }
  }

  $effect(() => {
    const ready = $clientReady;
    const hoursSnapshot = activeHours;
    const seriesSnapshot = series;
    if (ready) untrack(() => load(seriesSnapshot, hoursSnapshot));
    else loadState = 'no-client';
  });

  onMount(() => {
    refreshTimer = setInterval(() => untrack(() => load(series, activeHours)), REFRESH_MS);
  });

  onDestroy(() => {
    loadGen += 1;
    cancelPending();
    if (refreshTimer) clearInterval(refreshTimer);
    disposeChart();
  });
</script>

<div class="history-chart">
  <div class="hc-periods" role="group" aria-label="History period">
    {#each HISTORY_PERIOD_PRESETS as period (period.hours)}
      <button
        type="button"
        class="hc-period-btn"
        class:active={activeHours === period.hours}
        aria-pressed={activeHours === period.hours}
        onclick={() => selectPeriod(period.hours)}
      >{period.label}</button>
    {/each}
  </div>
  <div class="hc-content">
    {#if loadState === 'loading' || loadState === 'idle'}
      <div class="hc-message">Loading…</div>
    {:else if loadState === 'no-client' || loadState === 'error'}
      <div class="hc-message hc-error">
        <span>History unavailable</span>
        {#if errorMessage}<small>{errorMessage}</small>{/if}
      </div>
    {:else if loadState === 'empty'}
      <div class="hc-message">No data</div>
    {:else}
      {#if loadState === 'partial-error'}
        <div class="hc-warning" role="status">
          {unavailableCount} {unavailableCount === 1 ? 'series' : 'series'} unavailable
        </div>
      {/if}
      <div bind:this={el} class="hc-canvas" role="img" aria-label="History chart"></div>
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
  .hc-period-btn:hover { color: #e6edf3; }
  .hc-content {
    flex: 1;
    min-height: 0;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .hc-canvas {
    width: 100%;
    flex: 1;
    min-height: 0;
  }
  .hc-warning {
    flex: 0 0 auto;
    padding: 0.15rem 0.4rem;
    color: #f59e0b;
    font-size: 0.72rem;
    text-align: center;
  }
  .hc-message {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 3rem;
    color: #8b93a1;
    font-size: 0.85rem;
  }
  .hc-error { color: #fca5a5; }
  .hc-error small { color: #8b93a1; }
</style>
