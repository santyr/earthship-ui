<script>
  import { onMount } from 'svelte';
  import Tile from './Tile.svelte';
  import { loadPvPerformance } from '../household/observationClient.js';
  import { parsePvPerformance } from '../energy/pvPerformance.js';
  let raw = $state(null), nowMs = $state(Date.now());
  const report = $derived(parsePvPerformance(raw, { nowMs }));
  const metric = v => v === null ? '—' : v.toFixed(1);
  const date = v => new Intl.DateTimeFormat('en-US', { timeZone:'America/Denver', month:'short', day:'numeric', hour:'numeric', minute:'2-digit' }).format(Date.parse(v));
  onMount(() => {
    let stopped=false, controller, deadline;
    async function refresh() {
      controller?.abort(); clearTimeout(deadline); const current=new AbortController(); controller=current;
      deadline=setTimeout(()=>current.abort(),10000);
      try { const value=await loadPvPerformance(current.signal); if(!stopped&&controller===current)raw=value; }
      catch { if(!stopped&&controller===current)raw=null; }
      finally { if(controller===current){clearTimeout(deadline);nowMs=Date.now();} }
    }
    refresh(); const poll=setInterval(refresh,30000), clock=setInterval(()=>{nowMs=Date.now();},1000);
    return ()=>{stopped=true;clearInterval(poll);clearInterval(clock);clearTimeout(deadline);controller?.abort();};
  });
</script>

<Tile label="PV potential accuracy">
  <p>Measured controller input during low-SoC charging, in five-minute intervals. Mean absolute error in watts; lower is better.</p>
  {#if report}
    {#if report.expired}<p class="notice">PV accuracy report is stale</p>{/if}
    {#if report.status === 'collecting'}<p>Collecting eligible daylight observations. No qualified error estimate yet.</p>{/if}
    {#if report.cohorts.some(c=>c.metric_population==='constituent_five_minute_power_of_published_daily_totals')}
      <p>Constituent power intervals of published daily totals are compared with qualified controller input. These errors do not measure observed daily energy.</p>
    {/if}
    {#if report.cohorts.length}
      <div class="table"><table aria-label="PV potential forecast accuracy">
        <thead><tr><th>Forecast version</th><th>Raw error (W)</th><th>Adjusted error (W)</th><th>Intervals / adjusted</th><th>Eligible days</th></tr></thead>
        <tbody>{#each report.cohorts as row (row.cohort_id)}
          <tr><td title={`Model ${row.model_sha256}; policy ${row.calibration_policy_sha256 ?? 'legacy short-horizon'}; method ${row.scoring_runtime_sha256}`}>
              {row.model_sha256.slice(0,8)}{#if row.baseline_rule}<small>Native components</small>{/if}<small>Policy {row.calibration_policy_sha256?.slice(0,8) ?? 'legacy'} · method {row.scoring_runtime_sha256.slice(0,8)}</small>
              <small>{date(row.first_window_start)}–{date(row.last_window_end)}</small>
            </td><td>{metric(row.baseline_mae_w)}</td><td>{metric(row.candidate_mae_w)}</td><td>{row.eligible_bins} / {row.adjusted_bins}</td><td>{row.local_target_dates ?? row.independent_target_days}</td></tr>
          <tr><td colspan="5" class="coverage">Excluded: {row.censored_bins} charging/clipping proxy, {row.low_generation_bins} low-generation, {row.unqualified_bins} missing/unqualified measurement, {row.missing_forecast_bins} missing forecast, {row.unknown_coverage_bins} unknown older coverage.</td></tr>
        {/each}</tbody>
      </table></div>
      <p>A dash means unavailable. Each version uses its original forecasts, model and scoring method. Charging exclusions are provisional; these measurements do not certify unrestricted array output.</p>
    {/if}
    <p>Seven-day window: {report.scored_hours} recorded hours; {report.unscored_hours} hours without a recorded score. Updated {date(report.generated_at)}.</p>
    {#if report.omitted_cohort_count}<p>{report.omitted_cohort_count} older versions omitted from this view; original scores remain retained.</p>{/if}
  {:else}<p>PV potential accuracy is collecting or unavailable.</p>{/if}
  <p>PV potential, battery capture and storage errors measure different quantities.</p>
</Tile>

<style>
  p, table { font-size:.85rem; line-height:1.45; } p { margin:.5rem 0; } .notice { color:#fbbf24; }
  .table { overflow-x:auto; } table { width:100%; border-collapse:collapse; } th,td { padding:.35rem .5rem; text-align:left; vertical-align:top; border-bottom:1px solid #1c2230; }
  th,small,.coverage { color:#94a3b8; } small { display:block; font-size:.7rem; } .coverage { font-size:.75rem; }
</style>
