<script>
  import { onDestroy, tick } from 'svelte';
  import { parseProviderForecast } from '../weather/providerForecast.js';
  let { statusRaw, comparisonRaw, localRaw, nowMs = Date.now(), connected = true } = $props();
  let open = $state(false);
  let closeEl = $state();
  let panelEl = $state();
  let opener;
  const forecast = $derived(parseProviderForecast(comparisonRaw, statusRaw, localRaw, { nowMs, connected }));
  function close() { open = false; if (opener?.isConnected) opener.focus(); }
  async function show(event) { opener = event.currentTarget; open = true; await tick(); closeEl?.focus(); }
  function keydown(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key === 'Tab') { event.preventDefault(); closeEl?.focus(); }
  }
  function time(at) {
    if (!Number.isFinite(at)) return 'Unavailable';
    return new Intl.DateTimeFormat(undefined, { timeZone: forecast.source?.timezone || 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(at);
  }
  const temperature = (value) => value === null ? '—' : `${value.toFixed(1)}°F`;
  onDestroy(() => { if (open && opener?.isConnected) opener.focus(); });
</script>
<button class="comparison-entry" onclick={show}>WeatherNext comparison · {forecast.status === 'ready' ? 'shadow' : forecast.status}</button>
{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="comparison-backdrop" onclick={(event) => { if (event.target === event.currentTarget) close(); }}>
    <div bind:this={panelEl} class="comparison-panel" role="dialog" aria-modal="true" aria-labelledby="provider-comparison-title" tabindex="-1" onkeydown={keydown}>
      <header><div><h2 id="provider-comparison-title">WeatherNext comparison</h2><p>Shadow — not controlling equipment</p></div><button bind:this={closeEl} onclick={close} aria-label="Close forecast comparison">Close</button></header>
      {#if forecast.status !== 'ready'}
        <p role="status">{forecast.reason}</p>
      {/if}
      {#if forecast.source}
        <dl><div><dt>Source run</dt><dd>{time(forecast.source.initializedAtMs)} · {forecast.sourceAgeHours.toFixed(1)} hours old</dd></div>
          <div><dt>Decision</dt><dd>{time(forecast.decisionAtMs)}</dd></div></dl>
      {/if}
      {#if forecast.model?.status === 'SHADOW_ONLY'}
        <p>{forecast.model.sampleCount} training {forecast.model.sampleCount === 1 ? 'pair' : 'pairs'} across {forecast.model.targetDates} observed {forecast.model.targetDates === 1 ? 'date' : 'dates'}.</p>
      {:else}<p>No trained local candidate available.</p>{/if}
      <p class="validation">Validation unavailable; candidate not qualified.</p>
      {#if forecast.status === 'ready'}
        <p>Forecast horizon: {forecast.horizonHours.toFixed(1)} hours. Showing the first {Math.min(24, forecast.hours.length)} hours.</p>
        <div class="table-wrap"><table><thead><tr><th>Local time</th><th>Corrected Open-Meteo</th><th>Raw WeatherNext</th><th>Local candidate</th></tr></thead>
          <tbody>{#each forecast.hours.slice(0,24) as hour (hour.at)}<tr><th>{time(hour.atMs)}</th><td>{temperature(hour.incumbentF)}</td><td>{temperature(hour.rawF)}</td><td>{temperature(hour.localF)}</td></tr>{/each}</tbody>
        </table></div>
      {/if}
    </div>
  </div>
{/if}
<style>
  .comparison-entry { position: absolute; inset-block-start: .45rem; inset-inline-end: .7rem; border: 1px solid #334155; border-radius: .35rem; background: #17202d; color: #cbd5e1; padding: .18rem .4rem; font-size: .65rem; cursor: pointer; }
  .comparison-backdrop { position: fixed; inset: 0; z-index: 9500; display: grid; place-items: center; padding: 1rem; background: #000b; }
  .comparison-panel { width: min(56rem, 100%); max-height: 85dvh; box-sizing: border-box; overflow: auto; overscroll-behavior: contain; border: 1px solid #334155; border-radius: .75rem; background: #11151c; color: #dce3ee; padding: 1rem; }
  header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
  h2 { margin: 0; font-size: 1.1rem; } p, dl { font-size: .8rem; line-height: 1.5; } header p { margin-top: .3rem; color: #94a3b8; }
  header button { background: #1e293b; color: #e2e8f0; border: 1px solid #475569; border-radius: .3rem; padding: .4rem .7rem; cursor: pointer; }
  dl div { display: flex; gap: .7rem; } dt { min-width: 5rem; color: #94a3b8; } dd { margin: 0; }
  .validation { color: #fbbf24; } .table-wrap { overflow-x: auto; } table { width: 100%; border-collapse: collapse; font-size: .75rem; }
  th, td { padding: .45rem; border-bottom: 1px solid #263244; text-align: start; } thead th { color: #94a3b8; font-weight: 500; } tbody th { font-weight: 400; }
</style>
