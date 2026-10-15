<script>
  import { onMount } from 'svelte';
  import Tile from './Tile.svelte';
  import { parseEnergyObservation, parseEnergyPerformance } from '../household/energyObservation.js';
  import { loadEnergyObservation, loadEnergyPerformance } from '../household/observationClient.js';
  let raw = $state(null), performanceRaw = $state(null), nowMs = $state(Date.now()), selectedHour = $state(1);
  const energy = $derived(parseEnergyObservation(raw, { nowMs }));
  const performance = $derived(parseEnergyPerformance(performanceRaw, { nowMs }));
  const sameModel = $derived(!energy?.cohort_id || energy.cohort_id === performance?.cohort_id);
  const selected = $derived(energy?.trajectory[selectedHour - 1]);
  const maxPv = $derived(Math.max(0.1, ...(energy?.trajectory.map(row => row.potential_pv_kwh) ?? [])));
  const socLine = $derived(energy?.storage_status !== 'conditional' ? '' : energy.trajectory.map((row, i) => `${42 + (i + 0.5) * 26},${180 - row.nominal_soc_pct * 1.5}`).join(' '));
  const kwh = value => value == null ? 'Unavailable' : `${Math.max(0, value).toFixed(2)} kWh`;
  const soc = value => value == null ? 'Unavailable' : `${value.toFixed(1)}%`;
  const date = value => new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(Date.parse(value));
  onMount(() => {
    let stopped = false, controller, deadline;
    async function refresh() {
      controller?.abort(); clearTimeout(deadline); const current = new AbortController(); controller = current;
      deadline = setTimeout(() => current.abort(), 10000);
      const results = await Promise.allSettled([loadEnergyObservation(current.signal), loadEnergyPerformance(current.signal)]);
      if (!stopped && controller === current) {
        raw = results[0].status === 'fulfilled' ? results[0].value : null;
        performanceRaw = results[1].status === 'fulfilled' ? results[1].value : null;
        nowMs = Date.now(); clearTimeout(deadline);
      }
    }
    refresh(); const poll = setInterval(refresh, 30000), clock = setInterval(() => { nowMs = Date.now(); }, 1000);
    return () => { stopped = true; clearInterval(poll); clearInterval(clock); clearTimeout(deadline); controller?.abort(); };
  });
</script>

<section class="energy-monitoring" aria-label="Solar and battery forecast monitoring">
  <Tile label="Solar and battery forecast">
    <p>Next 24 hours · provisional</p>
    {#if energy?.status === 'available'}
      {#if energy.expired}<p class="notice">Forecast is stale</p>{/if}
      <dl class="totals">
        <div><dt>Potential PV</dt><dd>{kwh(energy.potential_pv_24h_kwh)}</dd></div>
        <div><dt>Modeled capture</dt><dd>{kwh(energy.captured_pv_24h_kwh)}</dd></div>
        <div><dt>Nominal SoC at 24h</dt><dd>{soc(energy.trajectory.at(-1)?.nominal_soc_pct)}</dd></div>
      </dl>
      <svg viewBox="0 0 710 215" role="img" aria-label="Next 24 hour potential PV generation and nominal battery SoC">
        <text x="4" y="20">kWh/h</text><text x="665" y="20">SoC</text>
        <line x1="42" y1="180" x2="666" y2="180" class="axis" />
        <text x="10" y="40">{maxPv.toFixed(1)}</text><text x="12" y="180">0</text><text x="670" y="40">100%</text><text x="670" y="180">0%</text>
        {#each energy.trajectory as row, i}
          <rect data-series="potential-pv" x={44 + i * 26} y={180 - row.potential_pv_kwh / maxPv * 150} width="20" height={row.potential_pv_kwh / maxPv * 150} class="pv-bar">
            <title>{date(row.at)}: {kwh(row.potential_pv_kwh)} potential PV; {soc(row.nominal_soc_pct)} nominal SoC</title>
          </rect>
        {/each}
        {#if socLine}<polyline data-series="nominal-soc" points={socLine} class="soc-line" />{/if}
        <text x="42" y="205">{date(energy.issued_at)}</text><text x="666" y="205" text-anchor="end">{date(energy.trajectory.at(-1).at)}</text>
      </svg>
      <p class="legend"><span class="pv-key">■ Potential PV</span> <span class="soc-key">— Nominal SoC</span></p>
      <label class="hour">Forecast hour <input aria-label="Forecast hour" type="range" min="1" max="24" step="1" bind:value={selectedHour} /></label>
      {#if selected}<p>Hour {selectedHour} · ending {date(selected.at)}: {kwh(selected.potential_pv_kwh)} potential, {kwh(selected.captured_pv_kwh)} modeled capture, {soc(selected.nominal_soc_pct)} nominal SoC.</p>{/if}
      {#if energy.storage_status === 'conditional'}<p>Assumes {energy.household_ac_load_w_assumption.toFixed(0)} W household load stays constant, from {soc(energy.initial_soc_pct)} SoC.</p>
      {:else}<p>Storage forecast unavailable; current load or battery evidence is missing.</p>{/if}
      <p>Issued {date(energy.issued_at)}. Potential PV includes energy the system may not capture. Losses and the mountain skyline remain provisional.</p>
    {:else}<p>Solar and storage forecast unavailable</p>{/if}
  </Tile>
  <Tile label="Solar/load scenario accuracy">
    {#if performance && sameModel}
      {#if performance.expired}<p class="notice">Accuracy report is stale</p>{/if}
      <p>Matched battery SoC errors in percentage points; lower is better.</p>
      <div class="table"><table><thead><tr><th>Horizon</th><th>Solar/load scenario</th><th>Constant power</th><th>Hold SoC</th><th>Samples / attempts</th><th>Origin days</th></tr></thead>
        <tbody>{#each ['1', '6', '12', '24'] as h}
          {@const row = performance.by_horizon[h]}
          <tr><td>{h}h</td>{#each ['pv_load_scenario', 'constant_power', 'hold_soc'] as model}<td>{row.count ? row.mae_soc_pct[model].toFixed(2) : 'Collecting'}</td>{/each}<td>{row.count} / {row.attempted_count}</td><td>{row.unique_origin_days}</td></tr>
        {/each}</tbody>
      </table></div>
      <p>One original per hour over seven days, compared with the same measured endpoints under actual household use.</p>
      <p>Last measured endpoint: {performance.last_target_at ? date(performance.last_target_at) : 'Collecting'}. Updated {date(performance.generated_at)}.</p>
    {:else if performance}<p>Collecting comparisons for this model</p>
    {:else}<p>Scenario accuracy report unavailable</p>{/if}
    <p>PV energy accuracy awaits a comparable production measurement. These comparisons do not establish action benefits or calibrated usable energy.</p>
  </Tile>
</section>

<style>
  .energy-monitoring { display: grid; grid-template-columns: minmax(0, 1fr); gap: .7rem; min-width: 0; }
  p, label, table { font-size: .85rem; line-height: 1.45; } p { margin: .5rem 0; }
  .totals { display: flex; flex-wrap: wrap; gap: .6rem 1.4rem; } dt, th { color: #8b93a1; text-align: left; } dd { margin: .25rem 0; font-size: 1.1rem; }
  svg { width: 100%; height: auto; } svg text { fill: #aeb7c6; font-size: 11px; } .axis { stroke: #394455; }
  .pv-bar { fill: #eabf43; opacity: .8; } .soc-line { fill: none; stroke: #67c6f5; stroke-width: 2.5; }
  .pv-key { color: #eabf43; } .soc-key { color: #67c6f5; margin-left: 1rem; } .notice { color: #fbbf24; }
  .hour { display: flex; align-items: center; gap: 1rem; } input { flex: 1; min-width: 0; } .table { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; } td, th { padding: .35rem .5rem; border-bottom: 1px solid #1c2230; vertical-align: top; }
  @media (min-width: 1050px) { .energy-monitoring { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
