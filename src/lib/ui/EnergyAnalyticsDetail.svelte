<script>
  import { onDestroy, tick } from 'svelte';

  let { result } = $props();
  let open = $state(false);
  let opener = $state();
  let closeEl = $state();
  let panelEl = $state();
  let priorOverflow = '';
  let bodyLocked = false;

  const available = $derived(result?.state && result.state !== 'unavailable');
  const badge = $derived(
    result?.state === 'stale' ? 'STALE' : result?.state === 'ready' ? 'CURRENT' : 'PARTIAL'
  );

  function metric(value, suffix = '', digits = 1) {
    return typeof value === 'number' && Number.isFinite(value)
      ? `${value.toFixed(digits)}${suffix}`
      : 'Unavailable';
  }

  function count(value, suffix = '') {
    return Number.isInteger(value) ? `${value}${suffix}` : 'Unavailable';
  }

  function yesNo(value) {
    return value === true ? 'Yes' : value === false ? 'No' : 'Unavailable';
  }

  function shortDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value ?? '')) return 'date unavailable';
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', timeZone: 'UTC',
    }).format(new Date(`${value}T12:00:00Z`));
  }

  function openDetail(event) {
    opener = event.currentTarget;
    priorOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    bodyLocked = true;
    open = true;
    tick().then(() => closeEl?.focus());
  }

  function closeDetail() {
    open = false;
    if (bodyLocked) {
      document.body.style.overflow = priorOverflow;
      bodyLocked = false;
    }
    tick().then(() => opener?.isConnected && opener.focus());
  }

  function onBackdrop(event) {
    if (event.target === event.currentTarget) closeDetail();
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeDetail();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...panelEl.querySelectorAll('button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')];
    if (focusable.length === 1) {
      event.preventDefault();
      focusable[0].focus();
    }
  }

  onDestroy(() => {
    if (bodyLocked) document.body.style.overflow = priorOverflow;
  });
</script>

<div class="analytics-compact" data-state={result?.state ?? 'unavailable'}>
  {#if available}
    <div class="analytics-copy">
      <div class="analytics-label">Analytics <span class="analytics-badge">{badge}</span></div>
      <div class="analytics-meta">
        <span class="analytics-value">{metric(result.lifecycle?.endingCumulativeEfc, ' EFC', 2)}</span>
        <span class="analytics-through">through {shortDate(result.throughDate)}</span>
      </div>
    </div>
    <button class="analytics-open" type="button" aria-label="Open energy analytics details" onclick={openDetail}>
      Details
    </button>
  {:else}
    <div class="analytics-copy unavailable">
      <div class="analytics-label">Analytics unavailable</div>
      <div class="analytics-through">No validated summary</div>
    </div>
  {/if}
</div>

{#if open && available}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="analytics-backdrop" onclick={onBackdrop}>
    <div
      bind:this={panelEl}
      class="analytics-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="energy-analytics-title"
      tabindex="-1"
      onkeydown={onKeydown}
    >
      <header>
        <div>
          <h2 id="energy-analytics-title">Energy analytics details</h2>
          <p>{badge} · through {shortDate(result.throughDate)} · {result.epochId}</p>
        </div>
        <button bind:this={closeEl} type="button" aria-label="Close energy analytics details" onclick={closeDetail}>×</button>
      </header>

      <div class="analytics-sections">
        <section>
          <h3>Battery</h3>
          <dl>
            <div><dt>Latest daily low</dt><dd>{metric(result.battery.latestMinSocPct, '%')}</dd></div>
            <div><dt>Daily SoC range (DoD)</dt><dd class="metric-value">{metric(result.battery.latestDepthOfDischargePct, ' pp')}</dd></div>
            <div><dt>Daily estimated EFC</dt><dd>{metric(result.battery.latestEfc, '', 3)}</dd></div>
            <div><dt>Reached 99%</dt><dd>{yesNo(result.battery.latestReached99)}</dd></div>
            <div><dt>Days since full</dt><dd>{count(result.battery.daysSinceFull)}</dd></div>
            <div><dt>Current no-full run</dt><dd>{count(result.battery.currentNoFullDays, ' d')}</dd></div>
          </dl>
        </section>
        <section>
          <h3>Energy</h3>
          <dl>
            <div><dt>PV</dt><dd>{metric(result.energy.latest?.pvKwh, ' kWh')}</dd></div>
            <div><dt>Load</dt><dd>{metric(result.energy.latest?.loadKwh, ' kWh')}</dd></div>
            <div><dt>Charge</dt><dd>{metric(result.energy.latest?.chargeKwh, ' kWh')}</dd></div>
            <div><dt>Observed curtailment</dt><dd>{metric(result.energy.observedCurtailmentKwh, ' kWh')}</dd></div>
          </dl>
        </section>
        <section>
          <h3>Winter</h3>
          <dl>
            <div><dt>Observation days</dt><dd>{count(result.winter.observationDays)}</dd></div>
            <div><dt>Lowest SoC</dt><dd>{metric(result.winter.lowestSocPct, '%')}</dd></div>
            <div><dt>Median daily low</dt><dd>{metric(result.winter.medianMinSocPct, '%')}</dd></div>
            <div><dt>Longest no-full run</dt><dd>{count(result.winter.longestNoFullDays, ' d')}</dd></div>
          </dl>
        </section>
        <section>
          <h3>Lifecycle</h3>
          <dl>
            <div><dt>Ending estimated EFC</dt><dd>{metric(result.lifecycle.endingCumulativeEfc, '', 2)}</dd></div>
            <div><dt>Charge throughput</dt><dd>{metric(result.lifecycle.chargeKwh, ' kWh')}</dd></div>
            <div><dt>Above 95% SoC</dt><dd>{metric(result.lifecycle.highSocHoursAbove95, ' h')}</dd></div>
            <div><dt>State of health</dt><dd>{metric(result.lifecycle.stateOfHealthPct, '%')}</dd></div>
          </dl>
        </section>
        <section>
          <h3>Forecast</h3>
          <dl>
            <div><dt>PV forecast day</dt><dd>{metric(result.forecast.pv24hKwh, ' kWh')}</dd></div>
            <div><dt>Next morning SoC</dt><dd>{metric(result.forecast.nextMorningSocPct, '%')}</dd></div>
            <div><dt>Full today</dt><dd>{yesNo(result.forecast.fullToday)}</dd></div>
            <div><dt>Full tomorrow</dt><dd>{yesNo(result.forecast.fullTomorrow)}</dd></div>
          </dl>
        </section>
        <section>
          <h3>Health</h3>
          <dl>
            <div><dt>Analytics</dt><dd>{result.health.analytics}</dd></div>
            <div><dt>BMS</dt><dd>{result.health.bms}</dd></div>
            <div><dt>Schneider</dt><dd>{result.health.schneider}</dd></div>
            <div><dt>Weather / forecast</dt><dd>{result.health.weather} / {result.health.forecast}</dd></div>
            <div><dt>Collector / publisher</dt><dd>{result.health.collector} / {result.health.publisher}</dd></div>
          </dl>
        </section>
      </div>
      <p class="analytics-note">EFC uses measured charge/discharge energy over available bank-epoch history, not the BMS lifetime cycle count. Daily SoC range does not count repeated partial cycles.</p>
      {#if result.battery.status === 'degraded'}
        <p class="analytics-note">The latest day is incomplete; daily battery values may change.</p>
      {/if}
      <p class="analytics-note">Observed summaries only. Unavailable values are not estimated.</p>
    </div>
  </div>
{/if}

<style>
  .analytics-compact { display: flex; align-items: center; justify-content: space-between; gap: .45rem; min-width: 0; }
  .analytics-copy { display: flex; flex-direction: column; gap: .15rem; min-width: 0; }
  .analytics-label { color: #8b93a1; font-size: .68rem; text-transform: uppercase; letter-spacing: .03em; }
  .analytics-value { color: #e6edf3; font-size: 1rem; font-weight: 650; font-variant-numeric: tabular-nums; }
  .analytics-meta { display: flex; align-items: baseline; gap: .35rem; white-space: nowrap; }
  .analytics-through { color: #8b93a1; font-size: .65rem; white-space: nowrap; }
  .analytics-badge { color: #f59e0b; font-size: .55rem; margin-left: .2rem; }
  .analytics-open { border: 1px solid #334155; border-radius: .45rem; background: #18202b; color: #dbeafe; padding: .35rem .5rem; font: inherit; font-size: .68rem; cursor: pointer; }
  .analytics-open:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
  .analytics-backdrop { position: fixed; inset: 0; z-index: 3000; display: grid; place-items: center; padding: 1rem; background: rgb(2 6 23 / .82); }
  .analytics-panel { width: min(70rem, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); overflow: auto; box-sizing: border-box; border: 1px solid #334155; border-radius: .9rem; background: #0d1118; color: #e6edf3; padding: 1rem; box-shadow: 0 1.5rem 5rem rgb(0 0 0 / .55); }
  header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; margin-bottom: .8rem; }
  h2 { margin: 0; font-size: 1.15rem; }
  header p { margin: .2rem 0 0; color: #8b93a1; font-size: .72rem; }
  header button { border: 1px solid #334155; border-radius: .45rem; background: #18202b; color: #e6edf3; width: 2rem; height: 2rem; font-size: 1.3rem; cursor: pointer; }
  .analytics-sections { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
  section { border: 1px solid #1f2937; border-radius: .65rem; background: #11151c; padding: .7rem; }
  h3 { margin: 0 0 .45rem; color: #93c5fd; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
  dl { margin: 0; display: grid; gap: .3rem; }
  dl div { display: flex; justify-content: space-between; gap: .6rem; border-bottom: 1px solid #1c2230; padding-bottom: .2rem; }
  dt { color: #8b93a1; font-size: .7rem; }
  dd { margin: 0; font-size: .72rem; font-weight: 600; text-transform: capitalize; text-align: right; }
  dd.metric-value { text-transform: none; }
  .analytics-note { margin: .75rem 0 0; color: #8b93a1; font-size: .68rem; }
  @media (max-width: 760px) { .analytics-sections { grid-template-columns: 1fr; } }
</style>
