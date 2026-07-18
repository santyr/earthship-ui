<script>
  import { onDestroy, tick } from 'svelte';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { buildHistoryOption } from '../charts/options.js';
  import { loadHistorySeries } from '../charts/historyRequest.js';
  import { HISTORY_PERIOD_PRESETS, snapHistoryPeriod } from '../charts/periods.js';
  import { getClientOnce } from '../openhab/index.js';
  import { chartStore, closeChart } from './chartStore.js';
  import { observeElementSize } from './observeElementSize.js';

  const REFRESH_MS = 5 * 60 * 1_000;
  const TITLE_ID = 'history-chart-modal-title';
  const DESCRIPTION_ID = 'history-chart-modal-description';

  let el = $state();
  let panelEl = $state();
  let chart;
  let loadState = $state('idle');
  let errorMessage = $state('');
  let activeHours = $state(24);
  let pointsPerSeries = $state([]);
  let unavailableCount = $state(0);
  let latestNowMs = 0;
  let latestSeries = [];
  let latestWidthPx = 0;
  let loadGen = 0;
  let observedOpenId = 0;
  let restoredOpenId = 0;
  let requestController;
  let stopObserving = () => {};
  let refreshTimer;

  const description = $derived.by(() => {
    const labels = ($chartStore.series || []).map((source) => source.label || source.name).join(', ')
      || 'No series';
    const period = HISTORY_PERIOD_PRESETS.find((preset) => preset.hours === activeHours)?.label
      || `${activeHours} hours`;
    const stateText = {
      idle: 'Waiting to load',
      loading: 'Loading history',
      ready: 'History loaded',
      'partial-error': `${unavailableCount} ${unavailableCount === 1 ? 'series' : 'series'} unavailable`,
      error: 'History unavailable',
      empty: 'No data',
      'no-client': 'History client unavailable',
    }[loadState] || loadState;
    let latest = 'Most recent value unavailable';
    for (let index = 0; index < pointsPerSeries.length; index += 1) {
      const point = pointsPerSeries[index]?.at(-1);
      if (!point) continue;
      const label = latestSeries[index]?.label || latestSeries[index]?.name || `Series ${index + 1}`;
      latest = `Most recent ${label}: ${String(point.state)}`;
      break;
    }
    return `${labels}. ${period} selected. ${stateText}. ${latest}.`;
  });

  function stopRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
  }

  function startRefresh(openId) {
    stopRefresh();
    refreshTimer = setInterval(() => {
      if (!$chartStore.open || $chartStore.openId !== openId) return;
      loadAndRender($chartStore.series || [], activeHours, openId);
    }, REFRESH_MS);
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
        pointsPerSeries,
        widthPx,
        nowMs: latestNowMs,
        grid: { left: 52, right: 24, top: 56, bottom: 40 },
        legendTop: 8,
        legendFontSize: 12,
      }), true);
      chart.resize();
    } catch (error) {
      errorMessage = error?.message || 'History could not be rendered';
      loadState = 'error';
      disposeChart();
    }
  }

  async function loadAndRender(seriesList, hoursVal, expectedOpenId) {
    if (!$chartStore.open || $chartStore.openId !== expectedOpenId) return;
    cancelPending();
    const controller = new AbortController();
    requestController = controller;
    const myGen = ++loadGen;
    disposeChart();
    pointsPerSeries = [];
    unavailableCount = 0;
    errorMessage = '';
    loadState = 'loading';

    const client = getClientOnce();
    if (!client) {
      if (requestController === controller) requestController = null;
      loadState = 'no-client';
      return;
    }
    const series = seriesList || [];
    if (!series.length) {
      if (requestController === controller) requestController = null;
      loadState = 'empty';
      return;
    }

    const nowMs = Date.now();
    let result;
    try {
      result = await loadHistorySeries({
        client,
        series,
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

    pointsPerSeries = result.pointsPerSeries;
    unavailableCount = result.errors.length;
    latestSeries = series;
    latestNowMs = nowMs;
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
    renderLatest(parent?.clientWidth || el.clientWidth || 800);
    if (chart && parent) {
      stopObserving = observeElementSize(parent, ({ width }) => {
        if (width > 0 && Math.abs(width - latestWidthPx) >= 8) renderLatest(width);
        else chart?.resize();
      });
    }
  }

  function focusActivePeriod() {
    panelEl?.querySelector('[aria-pressed="true"]')?.focus();
  }

  $effect(() => {
    const state = $chartStore;
    if (state.open && state.openId !== observedOpenId) {
      observedOpenId = state.openId;
      activeHours = snapHistoryPeriod(state.initialHours ?? state.hours ?? 24);
      loadState = 'loading';
      startRefresh(state.openId);
      const openId = state.openId;
      const series = state.series || [];
      tick().then(() => {
        if (!$chartStore.open || $chartStore.openId !== openId) return;
        focusActivePeriod();
        loadAndRender(series, activeHours, openId);
      });
    } else if (!state.open) {
      loadGen += 1;
      cancelPending();
      stopRefresh();
      disposeChart();
      loadState = 'idle';
      if (state.openId && restoredOpenId !== state.openId) {
        restoredOpenId = state.openId;
        const opener = state.opener;
        tick().then(() => opener?.isConnected && opener.focus?.());
      }
    }
  });

  function selectPeriod(hours) {
    if (!$chartStore.open || hours === activeHours) return;
    activeHours = hours;
    loadAndRender($chartStore.series || [], hours, $chartStore.openId);
  }

  function onBackdropClick(event) {
    if (event.target === event.currentTarget) closeChart();
  }

  function onPanelKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeChart();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...panelEl.querySelectorAll(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    )];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  onDestroy(() => {
    loadGen += 1;
    cancelPending();
    stopRefresh();
    disposeChart();
  });
</script>

{#if $chartStore.open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="chart-backdrop" onclick={onBackdropClick}>
    <div
      bind:this={panelEl}
      class="chart-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby={TITLE_ID}
      aria-describedby={DESCRIPTION_ID}
      tabindex="-1"
      onkeydown={onPanelKeydown}
    >
      <div class="chart-header">
        <h2 id={TITLE_ID} class="chart-title">{$chartStore.title}</h2>
        <div class="chart-periods" role="group" aria-label="History period">
          {#each HISTORY_PERIOD_PRESETS as period (period.hours)}
            <button
              type="button"
              class="chart-period-btn"
              class:active={activeHours === period.hours}
              aria-pressed={activeHours === period.hours}
              onclick={() => selectPeriod(period.hours)}
            >{period.label}</button>
          {/each}
        </div>
        <button type="button" class="chart-close" onclick={closeChart} aria-label="Close chart">×</button>
      </div>
      <p id={DESCRIPTION_ID} class="sr-only" aria-live="polite">{description}</p>
      <div class="chart-body">
        {#if loadState === 'loading' || loadState === 'idle'}
          <div class="chart-message">Loading…</div>
        {:else if loadState === 'no-client' || loadState === 'error'}
          <div class="chart-message chart-error">
            <span>History unavailable</span>
            {#if errorMessage}<small>{errorMessage}</small>{/if}
          </div>
        {:else if loadState === 'empty'}
          <div class="chart-message">No data</div>
        {:else}
          {#if loadState === 'partial-error'}
            <div class="chart-warning" role="status">
              {unavailableCount} {unavailableCount === 1 ? 'series' : 'series'} unavailable
            </div>
          {/if}
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
    min-width: 0;
    overflow: hidden;
    outline: none;
  }
  .chart-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  .chart-title {
    margin: 0;
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
    min-width: 2.75rem;
    min-height: 2.75rem;
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
  .chart-period-btn:hover,
  .chart-close:hover { color: #e5e7eb; }
  .chart-close {
    min-width: 44px;
    min-height: 44px;
    display: grid;
    place-items: center;
    background: transparent;
    border: none;
    color: #8b93a1;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    padding: 0;
  }
  .chart-body {
    flex: 1;
    min-height: 0;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .chart-canvas {
    width: 100%;
    flex: 1;
    min-height: 0;
  }
  .chart-warning {
    flex: 0 0 auto;
    padding: 0.25rem 0.5rem;
    color: #f59e0b;
    font-size: 0.78rem;
    text-align: center;
  }
  .chart-message {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b93a1;
    font-size: 0.95rem;
  }
  .chart-error { color: #fca5a5; }
  .chart-error small { color: #8b93a1; }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  @media (max-height: 720px) {
    .chart-backdrop { padding: 1rem; }
    .chart-panel { padding: 0.75rem 1rem; }
  }
</style>
