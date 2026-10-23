<script>
  import { onMount } from 'svelte';
  import Tile from './Tile.svelte';
  import PvPotentialAccuracy from './PvPotentialAccuracy.svelte';
  import { parseProfiledObservation, parseProfiledPerformance } from '../household/profiledObservation.js';
  import { loadProfiledObservation, loadProfiledPerformance } from '../household/observationClient.js';
  import { parseCalibratedEnergy, parseCalibratedPerformance } from '../household/calibratedEnergy.js';
  import { loadCalibratedEnergy, loadCalibratedPerformance } from '../household/observationClient.js';
  let calibratedRaw = $state(null), calibratedReportRaw = $state(null);
  const calibratedReport = $derived(parseCalibratedPerformance(calibratedReportRaw, { nowMs }));
  const sameCalibratedModel = $derived(Boolean(calibrated && calibratedReport?.calibration_model_sha256 === calibrated.calibration_model_sha256 && calibratedReport?.calibration_policy_sha256 === calibrated.calibration_policy_sha256
    && (calibrated.schema !== 'earthship-household-calibrated-energy-observation/v4' || calibratedReport.procedure_sha256 === calibrated.procedure_sha256
      && calibratedReport.baseline_rule === calibrated.baseline_rule && calibratedReport.measurement_cohort_sha256 === calibrated.measurement_cohort_sha256 && calibratedReport.cohort_id === calibrated.cohort_id)));
  const error = (v, places) => v === null ? "—" : v.toFixed(places);
  const calibrated = $derived(parseCalibratedEnergy(calibratedRaw, { nowMs }));
  let raw = $state(null), reportRaw = $state(null), nowMs = $state(Date.now()), selectedHour = $state(1);
  const forecast = $derived(parseProfiledObservation(raw, { nowMs }));
  const report = $derived(parseProfiledPerformance(reportRaw, { nowMs }));
  const sameModel = $derived(forecast?.cohort_id && forecast.cohort_id === report?.cohort_id);
  const selected = $derived(forecast?.trajectory[selectedHour - 1]);
  const maxLoad = $derived(Math.max(1, ...(forecast?.trajectory.flatMap(r => [r.profiled_ac_w, r.constant_ac_w]) ?? [])));
  const line = (rows, key, scale) => rows.map((r, i) => `${42 + (i + .5) * 26},${180 - r[key] / scale * 150}`).join(' ');
  const date = v => new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(Date.parse(v));
  const kwh = v => `${v.toFixed(2)} kWh`;
  onMount(() => {
    let stopped = false, controller, deadline;
    async function refresh() {
      controller?.abort(); clearTimeout(deadline); const current = new AbortController(); controller = current;
      deadline = setTimeout(() => current.abort(), 10000);
      const results = await Promise.allSettled([loadProfiledObservation(current.signal), loadProfiledPerformance(current.signal), loadCalibratedEnergy(current.signal), loadCalibratedPerformance(current.signal)]);
      if (!stopped && controller === current) {
        raw = results[0].status === 'fulfilled' ? results[0].value : null;
        reportRaw = results[1].status === 'fulfilled' ? results[1].value : null;
        calibratedRaw = results[2].status === 'fulfilled' ? results[2].value : null;
        calibratedReportRaw = results[3].status === 'fulfilled' ? results[3].value : null;
        nowMs = Date.now(); clearTimeout(deadline);
      }
    }
    refresh(); const poll = setInterval(refresh, 30000), clock = setInterval(() => { nowMs = Date.now(); }, 1000);
    return () => { stopped = true; clearInterval(poll); clearInterval(clock); clearTimeout(deadline); controller?.abort(); };
  });
</script>

<section class="profiled-energy" aria-label="Learned AC demand and storage comparisons">
  <Tile label="Learned AC demand">
    {#if calibrated?.load_status === 'projected'}
      {#if calibrated.expired}<p class="notice">Calibrated forecast is stale</p>{/if}
      <p>Next 24 hours: {kwh(calibrated.load_total_ac_kwh)} learned AC demand.</p>
      <svg viewBox="0 0 710 215" role="img" aria-label="Next 24 hour learned household AC demand">
        <text x="5" y="20">Watts</text>
        <line x1="42" y1="180" x2="666" y2="180" class="axis" />
        <polyline points={line(calibrated.trajectory, 'mean_ac_w', Math.max(1, ...calibrated.trajectory.map(r => r.mean_ac_w)))} class="learned" />
        <text x="42" y="205">{date(calibrated.issued_at)}</text><text x="666" y="205" text-anchor="end">{date(calibrated.trajectory.at(-1).at)}</text>
      </svg>
      <p>Training data through {date(calibrated.load_trained_through)}. Issued {date(calibrated.issued_at)}.</p>
      <p>Forecast uncertainty has not been calibrated.</p>
    {:else if forecast?.status === 'conditional'}
      {#if forecast.expired}<p class="notice">Demand forecast is stale</p>{/if}
      <p>Next 24 hours: {kwh(forecast.total_ac_kwh)} AC demand. Current-load comparison holds {forecast.current_ac_w.toFixed(0)} W constant.</p>
      <svg viewBox="0 0 710 215" role="img" aria-label="Next 24 hour learned AC load and current-load persistence">
        <text x="5" y="20">Watts</text><text x="5" y="40">{maxLoad.toFixed(0)}</text><text x="14" y="180">0</text>
        <line x1="42" y1="180" x2="666" y2="180" class="axis" />
        <polyline points={line(forecast.trajectory, 'profiled_ac_w', maxLoad)} class="learned" />
        <polyline points={line(forecast.trajectory, 'constant_ac_w', maxLoad)} class="reference" />
        <text x="42" y="205">{date(forecast.issued_at)}</text><text x="666" y="205" text-anchor="end">{date(forecast.trajectory.at(-1).at)}</text>
      </svg>
      <p class="legend"><span>— Learned profile</span> <span>┄ Current load held constant</span></p>
      <label class="hour">Forecast hour <input aria-label="Demand forecast hour" type="range" min="1" max="24" step="1" bind:value={selectedHour} /></label>
      {#if selected}<p>Hour {selectedHour} · ending {date(selected.at)}: {selected.profiled_ac_w.toFixed(0)} W learned demand, from {selected.minimum_support_days} independent days. Past observed range: {selected.training_spread_ac_w[0].toFixed(0)}–{selected.training_spread_ac_w[1].toFixed(0)} W.</p>{/if}
      <p>Training data through {date(forecast.trained_through)}. Issued {date(forecast.issued_at)}.</p>
      <p>The observed range describes training data. Forecast uncertainty has not been calibrated.</p>
    {:else if forecast?.reason === 'load_model_expired'}<p>Load model is stale; waiting for the next daily refresh.</p>
    {:else}<p>Hourly demand profile is collecting. The existing solar and battery forecast remains available above.</p>{/if}
    <p>Based on inverter AC output. Battery charging and DC solar-system loads remain separate.</p>
  </Tile>
  <Tile label="Learned-load storage scenario">
    {#if calibrated?.status === 'projected_provisional_calibrated_potential'}
      {#if calibrated.expired}<p class="notice">Calibrated forecast is stale</p>{/if}
      {#if calibrated.schema === 'earthship-household-calibrated-energy-observation/v4'}
        <p>Next 24 hours PV potential: {kwh(calibrated.calibrated_potential_kwh)} from native solar components; {kwh(calibrated.raw_potential_kwh)} before the electrical correction.</p>
        <p>{calibrated.source_support.native_hours} native component source intervals; {calibrated.source_support.fallback_hours} raw fallback source intervals. {calibrated.calibration_mode === 'experimental_production' ? 'The fitted gain applies to supported native components.' : 'The projection uses raw physics.'}</p>
      {:else}<p>Next 24 hours PV potential: {kwh(calibrated.calibrated_potential_kwh)} with the empirical correction; {kwh(calibrated.raw_potential_kwh)} from raw physics.</p>{/if}
      {#if calibrated.profiled_storage_status === 'conditional_nominal_simulation'}
        <p>Modeled PV capture with learned demand: {kwh(calibrated.profiled_captured_pv_kwh)}.</p>
        <svg viewBox="0 0 710 215" role="img" aria-label="Battery SoC with calibrated and uncalibrated PV">
          <text x="5" y="20">SoC</text><text x="5" y="40">100%</text><text x="8" y="180">0%</text>
          <line x1="42" y1="180" x2="666" y2="180" class="axis" />
          <polyline points={line(calibrated.trajectory, 'calibrated_soc_pct', 100)} class="learned" />
          <polyline points={line(calibrated.trajectory, 'raw_soc_pct', 100)} class="reference" />
          <text x="42" y="205">{date(calibrated.issued_at)}</text><text x="666" y="205" text-anchor="end">{date(calibrated.trajectory.at(-1).at)}</text>
        </svg>
        <p class="legend"><span>— Calibrated PV</span> <span>┄ Raw physics PV</span></p>
        <p>Conditional nominal storage from {calibrated.initial_soc_pct.toFixed(1)}% SoC; conversion losses and usable capacity remain provisional.</p>
      {:else}<p>Storage forecast is unavailable; the PV potential remains independent.</p>{/if}
    {:else if forecast?.status === 'conditional'}
      <p>Modeled PV capture: {kwh(forecast.profiled_captured_pv_24h_kwh)} with learned demand; {kwh(forecast.constant_captured_pv_24h_kwh)} with current demand held constant.</p>
      <svg viewBox="0 0 710 215" role="img" aria-label="Nominal battery SoC with learned and constant AC demand">
        <text x="5" y="20">SoC</text><text x="5" y="40">100%</text><text x="8" y="180">0%</text>
        <line x1="42" y1="180" x2="666" y2="180" class="axis" />
        <polyline points={line(forecast.trajectory, 'profiled_soc_pct', 100)} class="learned" />
        <polyline points={line(forecast.trajectory, 'constant_soc_pct', 100)} class="reference" />
        <text x="42" y="205">{date(forecast.issued_at)}</text><text x="666" y="205" text-anchor="end">{date(forecast.trajectory.at(-1).at)}</text>
      </svg>
      <p class="legend"><span>— Learned demand</span> <span>┄ Constant demand</span></p>
      <p>Conditional nominal storage from {forecast.initial_soc_pct.toFixed(1)}% SoC; conversion losses and usable capacity remain provisional.</p>
    {:else}<p>Learned-load storage scenario is collecting.</p>{/if}
    {#if calibrated && sameCalibratedModel}
      {#if calibratedReport.expired}<p class="notice">Calibrated accuracy report is stale</p>{/if}
      <p>Mean absolute forecast error; lower is better. SoC errors are percentage points. AC energy compares the hour ending at each lead time.</p>
      <div class="table"><table aria-label="Calibrated PV and storage forecast accuracy"><thead><tr><th>Lead</th><th>Learned AC<br />(kWh)</th><th>Current AC<br />(kWh)</th><th>AC samples<br />(current)</th><th>Calibrated PV SoC</th><th>Raw PV SoC</th><th>Hold SoC</th><th>SoC samples</th></tr></thead><tbody>
        {#each ['1', '6', '12', '24'] as h}
          {@const row = calibratedReport.by_horizon[h]}
          <tr><td>{h}h</td><td>{error(row.load.mae_kwh.learned_ac, 3)}</td><td>{error(row.load.mae_kwh.current_ac, 3)}</td><td>{row.load.count} / {row.load.attempted_count} ({row.load.current_count})</td>
            {#each ['calibrated_pv', 'raw_pv', 'hold_soc'] as model}<td>{error(row.soc.mae_soc_pct[model], 2)}</td>{/each}<td>{row.soc.count} / {row.soc.attempted_count}</td></tr>
        {/each}
      </tbody></table></div>
      <p>Samples / mature forecasts; a dash means unavailable. AC samples require at least 99% measured coverage.</p>
      {#if calibratedReport.first_issue}<p>Forecasts issued {date(calibratedReport.first_issue)}–{date(calibratedReport.last_issue)} across {calibratedReport.independent_origin_days} issue date(s). Updated {date(calibratedReport.generated_at)}.</p>{/if}
    {:else if calibrated}<p>Calibrated scenario accuracy is collecting.</p>{/if}
    {#if !calibrated && report && sameModel}
      {#if report.expired}<p class="notice">Demand accuracy report is stale</p>{/if}
      <p>Mean absolute error; lower is better. AC energy compares the hour ending at each lead time.</p>
      <div class="table"><table><thead><tr><th>Lead</th><th>Learned AC<br />(kWh)</th><th>Current AC<br />(kWh)</th><th>AC samples</th><th>Learned SoC<br />(points)</th><th>Constant-load SoC<br />(points)</th><th>Constant power<br />(points)</th><th>Hold SoC<br />(points)</th><th>SoC samples</th></tr></thead><tbody>
        {#each ['1', '6', '12', '24'] as h}
          {@const load = report.by_horizon[h].load}{@const soc = report.by_horizon[h].soc}
          <tr><td>{h}h</td><td>{load.count ? load.mae_kwh.profiled_load.toFixed(3) : 'Collecting'}</td><td>{load.count ? load.mae_kwh.current_load.toFixed(3) : 'Collecting'}</td><td>{load.count} / {load.attempted_count}</td>
            {#each ['profiled_load_pv', 'constant_load_pv', 'constant_power', 'hold_soc'] as model}<td>{soc.count ? soc.mae_soc_pct[model].toFixed(2) : 'Collecting'}</td>{/each}<td>{soc.count} / {soc.attempted_count}</td></tr>
        {/each}
      </tbody></table></div>
      <p>Rolling comparisons across {report.model_version_count} as-issued daily models. Each scored AC hour has at least 99% coverage; both predictions use the same observed duration.</p>
    {:else if !calibrated}<p>Collecting comparisons for this model</p>{/if}
    <p>These observations do not establish calibrated storage or benefits from equipment actions.</p>
  </Tile>
  <PvPotentialAccuracy />
</section>

<style>
  .profiled-energy { display: grid; grid-template-columns: minmax(0, 1fr); gap: .7rem; margin-top: .7rem; min-width: 0; }
  p, label, table { font-size: .85rem; line-height: 1.45; } p { margin: .5rem 0; }
  svg { width: 100%; height: auto; } svg text { fill: #aeb7c6; font-size: 11px; } .axis { stroke: #394455; }
  .learned { fill: none; stroke: #6bd6ad; stroke-width: 2.5; } .reference { fill: none; stroke: #eabf43; stroke-width: 2; stroke-dasharray: 6 4; }
  .legend { display: flex; gap: 1rem; flex-wrap: wrap; } .legend span:first-child { color: #6bd6ad; } .legend span:last-child { color: #eabf43; }
  .hour { display: flex; align-items: center; gap: 1rem; } input { flex: 1; min-width: 0; } .table { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; } td, th { padding: .35rem .5rem; border-bottom: 1px solid #1c2230; text-align: left; vertical-align: top; } th { color: #8b93a1; } .notice { color: #fbbf24; }
  @media (min-width: 1050px) { .profiled-energy { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
