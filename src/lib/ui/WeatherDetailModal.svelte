<script>
  import { onDestroy, tick } from 'svelte';
  import { currentRoute } from '../../routes.js';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { items } from '../openhab/store.js';
  import { buildWeatherDetailOption } from '../weather/detailChart.js';
  import {
    parseForecast10Day,
    selectForecastWindow,
  } from '../weather/forecastDetail.js';
  import {
    closeWeatherDetail,
    weatherDetailStore,
  } from '../weather/detailStore.js';
  import OhIcon from './OhIcon.svelte';
  import { observeElementSize } from './observeElementSize.js';
  import { wmoIcon, wmoLabel } from './wmo.js';

  const TITLE_ID = 'weather-detail-modal-title';
  const DESCRIPTION_ID = 'weather-detail-modal-description';

  let panelEl = $state();
  let closeEl = $state();
  let chartEl = $state();
  let chart;
  let stopObserving = () => {};
  let observedOpenId = 0;
  let observedHourSignature = '';
  let restoredOpenId = 0;
  let routeAtOpen = null;
  let chartGeneration = 0;
  let bodyLocked = false;
  let priorBodyOverflow = '';
  let latestWidthPx = 0;

  const forecast = $derived(parseForecast10Day(
    $items.Forecast_10Day_JSON,
    { nowMs: $weatherDetailStore.openedAtMs || Date.now() },
  ));
  const selectedDay = $derived(
    forecast.days.find(({ date }) => date === $weatherDetailStore.date) ?? null,
  );
  const selectedWindow = $derived(
    selectedDay
      ? selectForecastWindow(forecast, selectedDay.date, {
        nowMs: $weatherDetailStore.openedAtMs || Date.now(),
      })
      : { mode: 'unavailable', hours: [], expectedHours: 10, missingHours: 10 },
  );
  const hourSignature = $derived(
    selectedWindow.hours.map((hour) => [
      hour.at,
      hour.tempF,
      hour.precipPct,
      hour.radiationWm2,
      hour.windMph,
      hour.weatherCode,
    ].join(':')).join('|'),
  );
  const warnings = $derived([
    forecast.status === 'stale' ? 'Forecast data may be stale' : '',
    selectedDay && selectedWindow.missingHours > 0
      ? `${selectedWindow.hours.length} of 10 hours available`
      : '',
  ].filter(Boolean));
  const summaryText = $derived(selectedDay ? [
    wmoLabel(selectedDay.summary.weatherCode),
    `high ${metric(selectedDay.summary.highF, ' degrees')}`,
    `low ${metric(selectedDay.summary.lowF, ' degrees')}`,
    `precipitation ${metric(selectedDay.summary.precipPct, ' percent')}`,
    `modeled PV ${metric(selectedDay.summary.pvKwh, ' kilowatt-hours')}`,
  ].join(', ') : 'Hourly detail unavailable');
  const description = $derived(
    `${$weatherDetailStore.label || 'Selected day'} forecast. ${summaryText}. `
    + (selectedDay
      ? `${selectedWindow.hours.length} of 10 hourly periods shown.`
      : 'No hourly forecast periods are available.'),
  );

  function metric(value, suffix = '') {
    return typeof value === 'number' && Number.isFinite(value)
      ? `${Math.round(value)}${suffix}`
      : 'unavailable';
  }

  function hourLabel(at) {
    const hour = Number(String(at ?? '').slice(11, 13));
    if (!Number.isInteger(hour) || hour < 0 || hour > 23) return '—';
    if (hour === 0) return '12 AM';
    if (hour === 12) return '12 PM';
    return `${hour % 12} ${hour < 12 ? 'AM' : 'PM'}`;
  }

  function disposeChart() {
    stopObserving();
    stopObserving = () => {};
    chart?.dispose();
    chart = null;
    latestWidthPx = 0;
  }

  function lockBody() {
    if (bodyLocked || typeof document === 'undefined') return;
    priorBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    bodyLocked = true;
  }

  function restoreBody() {
    if (!bodyLocked || typeof document === 'undefined') return;
    document.body.style.overflow = priorBodyOverflow;
    bodyLocked = false;
  }

  function renderChart(widthPx) {
    if (!chart || widthPx <= 0) return;
    latestWidthPx = widthPx;
    chart.setOption(buildWeatherDetailOption({
      hours: selectedWindow.hours,
      widthPx,
    }), true);
    chart.resize();
  }

  async function initializeChart(openId, signature) {
    const generation = ++chartGeneration;
    disposeChart();
    await tick();
    if (!$weatherDetailStore.open
      || $weatherDetailStore.openId !== openId
      || observedHourSignature !== signature
      || !chartEl
      || selectedWindow.hours.length === 0) return;
    const echarts = await getEcharts();
    if (generation !== chartGeneration
      || !$weatherDetailStore.open
      || $weatherDetailStore.openId !== openId
      || !chartEl) return;
    chart = echarts.init(chartEl, null, { renderer: 'svg' });
    renderChart(chartEl.clientWidth || chartEl.parentElement?.clientWidth || 900);
    stopObserving = observeElementSize(chartEl, ({ width }) => {
      if (width > 0 && Math.abs(width - latestWidthPx) >= 8) renderChart(width);
      else chart?.resize();
    });
  }

  function finishClose(state) {
    chartGeneration += 1;
    disposeChart();
    restoreBody();
    routeAtOpen = null;
    observedHourSignature = '';
    if (state.openId && restoredOpenId !== state.openId) {
      restoredOpenId = state.openId;
      const opener = state.opener;
      tick().then(() => opener?.isConnected && opener.focus?.());
    }
  }

  $effect(() => {
    const state = $weatherDetailStore;
    const route = $currentRoute;
    const signature = hourSignature;
    if (state.open && state.openId !== observedOpenId) {
      observedOpenId = state.openId;
      observedHourSignature = signature;
      routeAtOpen = route;
      lockBody();
      const openId = state.openId;
      tick().then(() => {
        if (!$weatherDetailStore.open || $weatherDetailStore.openId !== openId) return;
        closeEl?.focus();
        initializeChart(openId, signature);
      });
    } else if (state.open && routeAtOpen !== null && route !== routeAtOpen) {
      closeWeatherDetail();
    } else if (state.open && signature !== observedHourSignature) {
      observedHourSignature = signature;
      initializeChart(state.openId, signature);
    } else if (!state.open) {
      finishClose(state);
    }
  });

  function onBackdropClick(event) {
    if (event.target === event.currentTarget) closeWeatherDetail();
  }

  function onPanelKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeWeatherDetail();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...panelEl.querySelectorAll(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    )];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (focusable.length === 1) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  onDestroy(() => {
    const state = $weatherDetailStore;
    chartGeneration += 1;
    disposeChart();
    restoreBody();
    if (state.open) {
      state.opener?.isConnected && state.opener.focus?.();
      closeWeatherDetail();
    }
  });
</script>

{#if $weatherDetailStore.open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="weather-detail-backdrop" onclick={onBackdropClick}>
    <div
      bind:this={panelEl}
      class="weather-detail-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby={TITLE_ID}
      aria-describedby={DESCRIPTION_ID}
      tabindex="-1"
      onkeydown={onPanelKeydown}
    >
      <header class="weather-detail-header">
        <div class="weather-detail-heading">
          <h2 id={TITLE_ID}>{$weatherDetailStore.label || 'Selected day'} Forecast</h2>
          {#if selectedDay}
            <p class="weather-detail-summary">
              <OhIcon icon={wmoIcon(selectedDay.summary.weatherCode)} size="1.15rem" />
              <span>{wmoLabel(selectedDay.summary.weatherCode)}</span>
              <span>{metric(selectedDay.summary.highF, '°')} / {metric(selectedDay.summary.lowF, '°')}</span>
              <span>{metric(selectedDay.summary.precipPct, '%')} precip</span>
              <span>PV {metric(selectedDay.summary.pvKwh, ' kWh')}</span>
            </p>
          {/if}
        </div>
        <button
          bind:this={closeEl}
          type="button"
          class="weather-detail-close"
          onclick={closeWeatherDetail}
          aria-label="Close weather detail"
        >×</button>
      </header>

      <p id={DESCRIPTION_ID} class="sr-only" aria-live="polite">{description}</p>

      <div class="weather-detail-warning" role={warnings.length > 0 ? 'status' : undefined}>
        {#each warnings as warning, index (warning)}
          {#if index > 0}<span aria-hidden="true"> · </span>{/if}
          <span>{warning}</span>
        {/each}
      </div>

      {#if !selectedDay}
        <div class="weather-detail-unavailable">Hourly detail unavailable</div>
      {:else}
        <div class="weather-detail-content">
          <div class="weather-detail-hours">
            {#each selectedWindow.hours as hour (hour.at)}
              <div
                class="weather-detail-hour"
                data-testid="weather-detail-hour"
                aria-label={`${hourLabel(hour.at)}, ${wmoLabel(hour.weatherCode)}`}
              >
                <span class="hour-time">{hourLabel(hour.at)}</span>
                <OhIcon icon={wmoIcon(hour.weatherCode)} size="1.2rem" />
                <span class="hour-temp">{metric(hour.tempF, '°')}</span>
                <span class="hour-precip">{metric(hour.precipPct, '%')}</span>
                <span class="hour-radiation">{metric(hour.radiationWm2, ' W/m²')}</span>
                <span class="hour-wind">{metric(hour.windMph, ' mph')}</span>
              </div>
            {/each}
          </div>
          {#if selectedWindow.hours.length > 0}
            <div bind:this={chartEl} class="weather-detail-chart" aria-hidden="true"></div>
          {:else}
            <div class="weather-detail-unavailable">Hourly detail unavailable</div>
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .weather-detail-backdrop {
    position: fixed;
    inset: 0;
    z-index: 210;
    box-sizing: border-box;
    padding: 1.25rem;
    display: grid;
    place-items: center;
    background: rgba(4, 6, 10, 0.86);
  }

  .weather-detail-panel {
    width: min(1160px, 100%);
    height: min(680px, 100%);
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    box-sizing: border-box;
    padding: 1rem 1.25rem;
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    background: #11151c;
    border: 1px solid #242b38;
    border-radius: 0.9rem;
    outline: none;
  }

  .weather-detail-header {
    min-width: 0;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .weather-detail-heading {
    min-width: 0;
    flex: 1;
  }

  h2 {
    margin: 0;
    color: #e5e7eb;
    font-size: 1.05rem;
    font-weight: 650;
  }

  .weather-detail-summary {
    min-width: 0;
    margin: 0.3rem 0 0;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.35rem 0.75rem;
    color: #9ca3af;
    font-size: 0.78rem;
    font-variant-numeric: tabular-nums;
  }

  .weather-detail-close {
    min-width: 44px;
    min-height: 44px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    background: transparent;
    color: #8b93a1;
    font: inherit;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
  }

  .weather-detail-close:hover,
  .weather-detail-close:focus-visible {
    color: #e5e7eb;
    outline: 1px solid #8b5cf6;
    outline-offset: 2px;
  }

  .weather-detail-warning {
    min-height: 1.4rem;
    padding: 0.2rem 0;
    color: #fbbf24;
    font-size: 0.76rem;
    text-align: center;
  }

  .weather-detail-content {
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    display: grid;
    grid-template-rows: minmax(6.5rem, auto) minmax(0, 1fr);
  }

  .weather-detail-hours {
    min-width: 0;
    display: grid;
    grid-template-columns: repeat(10, minmax(0, 1fr));
    border-block: 1px solid #242b38;
  }

  .weather-detail-hour {
    min-width: 0;
    padding: 0.45rem 0.18rem;
    display: grid;
    place-items: center;
    gap: 0.12rem;
    color: #9ca3af;
    font-size: 0.66rem;
    font-variant-numeric: tabular-nums;
  }

  .weather-detail-hour + .weather-detail-hour {
    border-left: 1px solid #1d2430;
  }

  .hour-time {
    color: #d1d5db;
    font-size: 0.72rem;
    font-weight: 650;
  }

  .hour-temp { color: #f59e0b; }
  .hour-precip { color: #38bdf8; }
  .hour-radiation { color: #fbbf24; }
  .hour-wind { color: #22d3ee; }

  .weather-detail-chart {
    width: 100%;
    min-width: 0;
    min-height: 0;
  }

  .weather-detail-unavailable {
    min-height: 0;
    display: grid;
    place-items: center;
    color: #8b93a1;
    font-size: 0.95rem;
  }

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
    .weather-detail-backdrop { padding: 0.75rem; }
    .weather-detail-panel { padding: 0.75rem 1rem; }
    .weather-detail-content { grid-template-rows: minmax(5.75rem, auto) minmax(0, 1fr); }
    .weather-detail-hour { padding-block: 0.25rem; }
  }
</style>
