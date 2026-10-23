<script>
  import {productionWeatherRaw,productionWeatherClock} from '../weather/productionState.js';
  import {parseProductionWeather,productionWeatherAt} from '../weather/productionForecast.js';
  let {issueSha256,timezone='America/Denver',hours=[]}=$props();
  let selected=$state('');
  const product=$derived(parseProductionWeather($productionWeatherRaw,{nowMs:$productionWeatherClock,issueSha256}));
  const allowed=$derived(new Set(hours.map(h=>Date.parse(h.at))));
  const targets=$derived([...new Set(product.rows.filter(r=>!allowed.size||allowed.has(Date.parse(r.target_end))).map(r=>r.target_end))]);
  const at=$derived(targets.includes(selected)?selected:targets[0]??null);
  const rows=$derived(at?['temperature','wind'].map(kind=>productionWeatherAt(product,at,kind)):[]);
  const time=at=>new Date(at).toLocaleString('en-US',{timeZone:timezone,month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  const quantity=(v,kind)=>typeof v==='number'&&Number.isFinite(v)?kind==='temperature'?`${(v*1.8+32).toFixed(1)}°F`:`${(v*2.2369362921).toFixed(1)} mph`:'unavailable';
</script>

<div class="production-forecast-details">
  {#if product.state==='ready' && at}
    <p><strong>Active production forecast · experimental</strong></p>
    <label>Forecast hour
      <select aria-label="Production forecast hour" value={at} onchange={e=>selected=e.currentTarget.value}>
        {#each targets as target (target)}<option value={target}>{time(target)}</option>{/each}
      </select>
    </label>
    {#each rows as row,index (index)}
      {#if row}
        <p>{row.kind==='temperature'?'Native temperature point mean':'Native boundary-mean hourly approximation'}: {quantity(row.raw.mean,row.kind)}.</p>
        {#if row.kind==='temperature' && row.raw.p10!==null && row.raw.p90!==null}
          <p>Native p10–p90: {quantity(row.raw.p10,row.kind)}–{quantity(row.raw.p90,row.kind)}.</p>
        {/if}
        {#if row.local}
          {@const model=product.models[row.local.model_sha256]}
          <p>{row.kind==='temperature'?`Local temperature ${row.local.point_estimate_kind==='model_median'?'median':'mean'}`:'Local station hourly wind mean'}: {quantity(row.local.point_estimate,row.kind)}.</p>
          <p>Local p10–p90: {quantity(row.local.quantiles[0],row.kind)}–{quantity(row.local.quantiles[4],row.kind)}.</p>
          <p class="source" title={`Model ${row.local.model_sha256}; procedure ${model.procedure_sha256}`}>Fitted {time(model.actual_completed_at)}; training used {model.support.targets} targets over {model.support.local_dates} local target dates.</p>
        {:else}
          <p>Raw fallback: {row.reason.replaceAll('_',' ')}.</p>
        {/if}
      {:else}
        <p>Hourly wind estimate unavailable for this interval; the main forecast retains native instantaneous wind.</p>
      {/if}
    {/each}
    <p>Local interval coverage is unverified. Each range describes one target; it is not a daily or trajectory probability.</p>
    <p class="source">Issued {time(product.publishedAt)}. These values match the original confirmed production forecast.</p>
  {:else}
    <p role="status">Production ranges unavailable for the current forecast.</p>
  {/if}
</div>

<style>
  .production-forecast-details {max-height:12rem;overflow:auto;overscroll-behavior:contain;padding:0 .3rem .4rem;font-size:.73rem;color:#cbd5e1;line-height:1.4;}
  p {margin:.3rem 0;}.source {color:#94a3b8;}
  label {display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;}
  select {max-width:100%;min-height:2.75rem;border:1px solid #475569;border-radius:.25rem;background:#17202c;color:#e5e7eb;padding:.2rem;}
  select:focus-visible {outline:2px solid #a78bfa;outline-offset:1px;}
</style>
