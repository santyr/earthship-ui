<script>
  import {rainShadowRaw,marginalShadowRaw,forecastVerificationClock} from '../weather/verificationState.js';
  import {parseRainShadow} from '../weather/rainForecast.js';
  import {parseWeatherMarginals} from '../weather/marginalForecast.js';
  let {timezone='America/Denver'}=$props();
  let selected=$state('');
  const rain=$derived(parseRainShadow($rainShadowRaw,{nowMs:$forecastVerificationClock}));
  const marginal=$derived(parseWeatherMarginals($marginalShadowRaw,{nowMs:$forecastVerificationClock}));
  const interval=$derived(rain.rows.find(r=>r.issue_sha256===selected)??rain.rows[0]??null);
  const marginalRows=$derived(['temperature','wind','solar_proxy'].map(kind=>marginal.rows.find(r=>r.kind===kind)).filter(Boolean));
  const kinds={local_calendar_day:'Calendar day',rolling_24_hours:'Rolling 24 hours',remaining_day:'Remaining day'};
  const heads={total_precipitation_1hr:'Total',imerg_tp_1hr:'IMERG',experimental_tp_1hr:'Experimental'};
  const families={empirical:'Local median',temperature_normal:'Local mean',nonnegative:'Local mean'};
  const time=at=>new Date(at).toLocaleString('en-US',{timeZone:timezone,month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  const inches=value=>typeof value==='number'&&Number.isFinite(value)?`${(value/25.4).toFixed(2)}″`:'unavailable';
  const age=at=>`${Math.max(0,($forecastVerificationClock-Date.parse(at))/3600000).toFixed(1)}h`;
  function quantity(value,kind){
    if(typeof value!=='number'||!Number.isFinite(value))return 'unavailable';
    return kind==='temperature'?`${(value*1.8+32).toFixed(1)}°F`:kind==='wind'?`${(value*2.2369362921).toFixed(1)} mph`:`${value.toFixed(0)} W/m² proxy`;
  }
</script>

<div class="forecast-shadow-body">
  <p>Local experimental estimates; local coverage not yet verified.</p>
  {#if interval}
    <label>Rain target interval
      <select aria-label="Rain comparison interval" value={interval.issue_sha256} onchange={e=>selected=e.currentTarget.value}>
        {#each rain.rows as row (row.issue_sha256)}<option value={row.issue_sha256}>{kinds[row.interval_kind]} · {time(row.start)}–{time(row.end)}</option>{/each}
      </select>
    </label>
    <p class="target">{kinds[interval.interval_kind]}: {time(interval.start)}–{time(interval.end)} ({interval.hours} hours)</p>
    <strong>Raw rain interval means</strong>
    <dl>{#each Object.entries(interval.raw_means_mm) as [head,value]}<div><dt>{heads[head]}</dt><dd>{inches(value)}</dd></div>{/each}</dl>
    {#if interval.local.status==='experimental_prediction'}<p>Local experimental interval mean: {inches(interval.local.mean_depth_mm)}</p>{/if}
    <p>No supported local rain probability. Event definition and probability qualification remain unavailable for this display.</p>
    <p>Training-only climatology: unavailable for a qualified wet-event comparison.</p>
    <p class="source">Original source initialized {age(interval.initialized_at)} ago; acquired {age(interval.source_available_at)} ago. Original interval means retain their own source and duration.</p>
  {:else}<p role="status">Rain interval comparison unavailable</p>{/if}
  {#if marginal.state==='ready'}
    <strong>Local marginal comparisons · experimental</strong>
    {#each marginalRows as row (`${row.kind}:${row.target_end}`)}
      <p>{({temperature:'Temperature',wind:'Hourly wind',solar_proxy:'Hourly solar proxy'})[row.kind]} · {time(row.target_end)}: raw mean {quantity(row.raw.mean,row.kind)}.</p>
      {#each Object.entries(row.local) as [family,model]}
        {#if model}<p>{families[family]} {quantity(model.point_estimate,row.kind)}; local p10–p90 {quantity(model.quantiles[0],row.kind)}–{quantity(model.quantiles[4],row.kind)}.</p>{/if}
      {/each}
    {/each}
    <p>Marginal ranges describe individual targets. Interval rain and household trajectory probabilities remain separate products.</p>
  {:else}<p>Local marginal comparison unavailable</p>{/if}
</div>

<style>
  .forecast-shadow-body {max-height:12rem;overflow:auto;overscroll-behavior:contain;padding:0 .3rem .4rem;font-size:.73rem;color:#cbd5e1;line-height:1.4;}
  p {margin:.3rem 0;}.source {color:#94a3b8;}.target {color:#bfdbfe;}
  label {display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;}
  select {max-width:100%;min-height:2.75rem;border:1px solid #475569;border-radius:.25rem;background:#17202c;color:#e5e7eb;padding:.2rem;}
  select:focus-visible {outline:2px solid #a78bfa;outline-offset:1px;}
  dl {margin:.2rem 0;display:flex;flex-wrap:wrap;gap:.25rem 1rem;}dl div {display:flex;gap:.4rem;}dd {margin:0;font-variant-numeric:tabular-nums;}
</style>
