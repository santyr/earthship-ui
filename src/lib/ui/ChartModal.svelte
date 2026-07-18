<script>
  // Full-screen click-to-chart overlay. Mount once (in App.svelte); any
  // tile opens it via chartStore's openChart({ title, series, hours }).
  // series: [{ name, color, label }] — name is the openHAB item queried
  // via getClientOnce().getHistory(). Multiple series are overlaid on one
  // time-axis chart with a legend.
  import { onDestroy, tick } from 'svelte';
  import * as echarts from 'echarts';
  import { chartStore, closeChart } from './chartStore.js';
  import { buildHistoryOption } from '../charts/options.js';
  import {
    HISTORY_PERIOD_PRESETS,
    createHistoryWindow,
    snapHistoryPeriod,
  } from '../charts/periods.js';
  import { getClientOnce } from '../openhab/index.js';

  let el = $state();
  let chart;
  let loading = $state(false);
  let noData = $state(false);
  let noClient = $state(false);
  // Monotonic generation token: guards against a stale loadAndRender()
  // call (superseded by a newer openChart()) overwriting current state
  // once its awaited work finally resolves.
  let loadGen = 0;
  let observedOpenId = 0;
  let requestController;
  let resizeObserver;
  let activeHours = $state(24);

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

  async function loadAndRender(seriesList, hoursVal, expectedOpenId) {
    if (!$chartStore.open || $chartStore.openId !== expectedOpenId) return;
    cancelPending();
    const controller = new AbortController();
    requestController = controller;
    const myGen = ++loadGen;
    noClient = false;
    noData = false;
    disposeChart();

    const client = getClientOnce();
    if (!client) {
      loading = false;
      noClient = true;
      return;
    }
    const series = seriesList || [];
    if (series.length === 0) {
      loading = false;
      noData = true;
      return;
    }

    loading = true;
    const now = Date.now();
    const requestWindow = createHistoryWindow(hoursVal, { nowMs: now });

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
    chart = echarts.init(el, null, { renderer: 'svg' });
    const widthPx = el.parentElement?.clientWidth || el.clientWidth || 800;
    chart.setOption(buildHistoryOption({
      series,
      pointsPerSeries: results,
      widthPx,
      nowMs: now,
      grid: { left: 52, right: 24, top: 56, bottom: 40 },
      legendTop: 8,
      legendFontSize: 12,
    }));
    chart.resize();
    if (typeof ResizeObserver !== 'undefined' && el.parentElement) {
      resizeObserver = new ResizeObserver(() => chart?.resize());
      resizeObserver.observe(el.parentElement);
    }
  }

  $effect(() => {
    const state = $chartStore;
    if (state.open && state.openId !== observedOpenId) {
      // Seed once per open identity. activeHours is intentionally not read in
      // this effect, so a picker click cannot retrigger fresh-open setup.
      observedOpenId = state.openId;
      const openIdSnapshot = state.openId;
      const hoursSnapshot = snapHistoryPeriod(state.initialHours ?? state.hours ?? 24);
      activeHours = hoursSnapshot;
      const seriesSnapshot = state.series || [];
      tick().then(() => {
        if (!$chartStore.open || $chartStore.openId !== openIdSnapshot) return;
        loadAndRender(seriesSnapshot, hoursSnapshot, openIdSnapshot);
      });
    } else if (!state.open) {
      // Invalidate any in-flight load so its continuation bails instead
      // of resurrecting loading/chart state after the modal has closed.
      loadGen++;
      cancelPending();
      loading = false;
      disposeChart();
    }
  });

  function selectPeriod(h) {
    if (!$chartStore.open || h === activeHours) return;
    activeHours = h;
    loadAndRender($chartStore.series || [], h, $chartStore.openId);
  }

  function onResize() {
    chart?.resize();
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('resize', onResize);
  }

  onDestroy(() => {
    if (typeof window !== 'undefined') window.removeEventListener('resize', onResize);
    loadGen++;
    cancelPending();
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
          {#each HISTORY_PERIOD_PRESETS as p (p.hours)}
            <button
              type="button"
              class="chart-period-btn"
              class:active={activeHours === p.hours}
              aria-pressed={activeHours === p.hours}
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
    min-width: 0;
    overflow: hidden;
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
    min-width: 0;
    overflow: hidden;
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
