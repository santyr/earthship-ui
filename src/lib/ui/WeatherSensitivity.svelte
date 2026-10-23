<script>
  import {onMount} from 'svelte';
  import {parseWeatherSensitivity} from '../weather/sensitivity.js';
  import {loadWeatherSensitivity} from '../household/observationClient.js';
  let raw=$state(null),nowMs=$state(Date.now()),hour=$state(24);
  const view=$derived(parseWeatherSensitivity(raw,{nowMs}));
  const names={central:'Central',reduced_solar:'Half solar',warm_high_gain:'Warmer (+3°C), 1.2× solar'};
  const reading=(v,unit,places=1)=>v===null?'—':`${v.toFixed(places)}${unit}`;
  const date=v=>new Intl.DateTimeFormat('en-US',{timeZone:'America/Denver',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(Date.parse(v));
  onMount(()=>{
    let stopped=false,controller,deadline;
    async function refresh(){
      controller?.abort();clearTimeout(deadline);const current=new AbortController();controller=current;deadline=setTimeout(()=>current.abort(),10000);
      try{const value=await loadWeatherSensitivity(current.signal);if(!stopped&&controller===current)raw=value;}
      catch{if(!stopped&&controller===current)raw=null;}
      finally{if(controller===current)clearTimeout(deadline);}
      if(!stopped)nowMs=Date.now();
    }
    refresh();const poll=setInterval(refresh,60000),clock=setInterval(()=>{nowMs=Date.now();},1000);
    return()=>{stopped=true;clearInterval(poll);clearInterval(clock);clearTimeout(deadline);controller?.abort();};
  });
</script>
<section class="weather-sensitivity" aria-label="Weather sensitivity">
  <details>
    <summary>Weather sensitivity</summary>
    {#if view.state==='ready'}
      <p>Next {(Date.parse(view.through)-Date.parse(view.origin))/3600000} hours · issued {date(view.origin)}.</p>
      <p>Weather cases have no assigned probabilities. Load, initial state, model parameters and actions stay fixed. Storage uses nominal capacity.</p>
      <p class="state">Initial SoC {reading(view.initialSocPct,'%')} · {reading(view.nominalBankKwh,' kWh')} nominal bank · {reading(view.fixedLoadAcW,' W',0)} fixed AC load</p>
      <div class="table-wrap">
        <table>
          <caption>PV before electrical correction; temperatures at forecast hour {hour}</caption>
          <thead><tr><th scope="col">Weather case</th><th scope="col">PV potential</th><th scope="col">Nominal SoC minimum</th><th scope="col">Room air</th><th scope="col">North mass</th></tr></thead>
          <tbody>{#each view.cases as row}
            {@const point=row.trajectory[Math.min(hour,row.trajectory.length)-1]}
            <tr><th scope="row">{names[row.name]}</th><td>{reading(row.raw_potential_pv_kwh,' kWh',2)}</td><td>{reading(row.minimum_nominal_soc_pct,'%')}</td><td>{reading(point.air_f,'°F')}</td><td>{reading(point.north_wall_f,'°F')}</td></tr>
          {/each}</tbody>
        </table>
      </div>
      <label>Forecast hour <input aria-label="Sensitivity forecast hour" type="range" min="1" max={view.cases[0].trajectory.length} step="1" bind:value={hour} /> {Math.min(hour,view.cases[0].trajectory.length)}</label>
    {:else}<p>Weather sensitivity unavailable</p>{/if}
  </details>
</section>
<style>
  .weather-sensitivity{border:1px solid #30363d;border-radius:12px;padding:16px;background:#161b22;color:#e6edf3;margin-top:16px;min-width:0}
  summary{cursor:pointer;font-weight:600;font-size:1rem}p{font-size:.875rem;line-height:1.5;color:#abb6c2}p.state{font-variant-numeric:tabular-nums}
  .table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.85rem;font-variant-numeric:tabular-nums}caption{text-align:left;color:#abb6c2;margin:12px 0}th,td{padding:12px 8px;text-align:right;border-bottom:1px solid #30363d}th:first-child{text-align:left}thead th{color:#abb6c2;font-weight:500}label{display:flex;align-items:center;gap:12px;margin-top:16px;font-size:.875rem}input{flex:1;max-width:460px}summary:focus-visible,input:focus-visible{outline:2px solid #38bdf8;outline-offset:4px}
</style>
