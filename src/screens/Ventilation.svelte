<script>
 import DecisionRecommendations from "../lib/ui/DecisionRecommendations.svelte";
 import {onMount} from 'svelte';
 import {items,connection} from '../lib/openhab/index.js';
 import {sensorView,counts,since} from '../lib/sensors/view.js';
 let selectedId=$state(null);let detailDialog=$state(null);
 let now=$state(Date.now());let section=$state('ventilation');let zone=$state('all');let page=$state(0);
 const view=$derived(sensorView($items.Earthship_Sensor_View_JSON,now,$connection,$items.Earthship_Sensor_Service));
 const sensors=$derived(view.sensors.filter(s=>(section==='property'?['gate','perimeter'].includes(s.device_type):['window','skylight','door'].includes(s.device_type))&&(zone==='all'||s.zone===zone)));
 const summary=$derived(counts(sensors));
 const zones=$derived([...new Set(view.sensors.map(s=>s.zone))].sort());
 const visible=$derived(sensors.slice(page*15,(page+1)*15));
 const selected=$derived(view.sensors.find(s=>s.sensor_id===selectedId));
 $effect(()=>{if(selected&&detailDialog&&!detailDialog.open){if(detailDialog.showModal)detailDialog.showModal();else detailDialog.setAttribute('open','');}});
 const names=$derived(Object.fromEntries(view.sensors.map(s=>[s.sensor_id,s.name])));
 const events=$derived(view.recent_events.filter(e=>sensors.some(s=>s.sensor_id===e.sensor_id)).slice(0,7));
 const daily=$derived(view.daily_durations.filter(e=>sensors.some(s=>s.sensor_id===e.sensor_id)).slice(0,5));
 onMount(()=>{const timer=setInterval(()=>now=Date.now(),1000);return ()=>clearInterval(timer);});
 function changeSection(value){section=value;page=0;zone='all';}
 function stateLabel(value){return value==='OPEN'?'Open':value==='CLOSED'?'Closed':'Unknown';}
</script>
<DecisionRecommendations scope="ventilation" tiny compact />


<section class="ventilation" aria-label="Distributed sensor observations" data-ventilation-screen>
 <header class="heading">
  <div><h1>Ventilation &amp; sensors</h1><p>{view.environment==='simulation'?'Synthetic demonstration':'Observations · OpenHAB authority'}</p></div>
  <div class="tabs" aria-label="Sensor domains">
   <button class:chosen={section==='ventilation'} onclick={()=>changeSection('ventilation')}>Ventilation</button>
   <button class:chosen={section==='property'} onclick={()=>changeSection('property')}>Property</button>
   <button class:chosen={section==='environment'} onclick={()=>changeSection('environment')}>Environment</button>
   <button class:chosen={section==='infrastructure'} onclick={()=>changeSection('infrastructure')}>Health</button>
  </div>
  <label>Zone <select bind:value={zone} onchange={()=>page=0}><option value="all">All zones</option>{#each zones as name}<option value={name}>{name}</option>{/each}</select></label>
 </header>
 {#if !view.available}
  <div class="empty"><h2>Awaiting sensor commissioning</h2><p>Names, locations and device identities come from the sensor registry.</p><p>Live data arrives through OpenHAB. No physical sensors are assigned yet.</p></div>
 {:else}
  <div class="summary" aria-label="Ventilation overview">
   {#each [['Open windows',summary.windows],['Open skylights',summary.skylights],['Open doors',summary.doors],['Closed',summary.closed],['Unknown / stale',summary.unknown],['Offline',summary.offline]] as metric}
    <div><strong>{metric[1]}</strong><span>{metric[0]}</span></div>
   {/each}
  </div>
  {#if section==='infrastructure'}
   <div class="environment-grid" aria-label="Sensor infrastructure health">
    {#each [['MQTT',view.operations.mqtt_connected?'Connected':'Unavailable'],['ChirpStack',view.operations.chirpstack??'Not probed'],['Registered devices',view.operations.registered_devices??view.sensors.length],['Accepted uplinks',view.operations.accepted??0],['Decode failures',view.operations.decode_failures??0],['Integration failures',view.operations.integration_failures??0],['Last processing time',`${view.operations.processing_ms??0} ms`],['Battery warnings',view.sensors.filter(s=>s.battery.condition==='LOW').length],['Unknown contact evidence',counts(view.sensors).unknown]] as metric}
     <article class="sensor"><h2>{metric[0]}</h2><strong>{metric[1]}</strong></article>
    {/each}
    {#each view.gateways??[] as gateway}<article class="sensor"><h2>{gateway.name}</h2><strong>{view.sourceLive?gateway.health:'UNKNOWN'}</strong><small>Last stats {since(gateway.last_stats_received_at,now)}</small><small>Transport activity · RF unverified</small></article>{/each}
   </div>
  {:else if section==='environment'}
   <div class="environment-grid">
    {#each view.environmental.filter(p=>zone==='all'||p.zone===zone).slice(0,15) as point}
     <article class="sensor"><h2>{point.name??point.sensor_id}</h2><p>{point.observation_type.replaceAll('_',' ')}</p><strong>{view.sourceLive&&now<Date.parse(point.valid_until)?`${point.value} ${point.unit}`:'Unknown'}</strong><small>{point.synthetic?'Synthetic':'Observed'} · {since(point.observed_at,now)}</small></article>
    {:else}<div class="empty">Environmental sensors can be added through the registry.</div>{/each}
   </div>
  {:else}
   <div class="content">
    <div class="sensor-grid" aria-label="Sensor status">
     {#each visible as sensor (sensor.sensor_id)}
      <article class="sensor" class:open={sensor.current_state==='OPEN'} class:unknown={sensor.current_state==='UNKNOWN'} data-sensor={sensor.sensor_id}>
       <button class="details-button" aria-label={`Details for ${sensor.name}`} onclick={()=>selectedId=sensor.sensor_id}></button>
       <div class="sensor-title"><h2 title={sensor.name}>{sensor.name}</h2><span class="health">{sensor.health.toLowerCase()}</span></div>
       <p>{sensor.zone} · {sensor.location}</p>
       <div class="state"><strong>{stateLabel(sensor.current_state)}</strong><span>{sensor.battery?.percent!=null?`${sensor.battery.percent}%`:sensor.battery?.volts!=null?`${sensor.battery.volts.toFixed(2)}V`:'Battery unknown'}{sensor.battery?.condition==='LOW'?' · low':''}</span></div>
       <small>{sensor.current_state==='UNKNOWN'?`Last known ${sensor.contact_state?.toLowerCase()??'unknown'}`:sensor.last_transition_at?`Reported change ${since(sensor.last_transition_at,now)}`:'Transition not observed'}</small>
       <small>Observed {since(sensor.last_observed_at,now)}{sensor.tamper===true?' · Tamper reported':''}</small>
      </article>
     {:else}<div class="empty">No {section==='property'?'property':'opening'} sensors configured for this zone.</div>{/each}
    </div>
    <aside class="history" aria-label="Sensor history">
     <h2>Recent events</h2>
     {#each events as event}<div class="event"><span>{names[event.sensor_id]??event.sensor_id}</span><strong>{event.event_type.replaceAll('_',' ')}</strong><small>{since(event.observed_at,now)}</small></div>{:else}<p>No recorded transitions yet.</p>{/each}
     <h2 class="daily-title">Daily opening duration</h2>
     {#each daily as row}<div class="duration"><span>{names[row.sensor_id]??row.sensor_id}</span><strong>{(row.open_seconds/3600).toFixed(2)}h</strong><small>{row.date} · supervised estimate</small></div>{:else}<p>Waiting for observation history.</p>{/each}
     <p class="note">Gaps and freshness expiry interrupt duration estimates. Contact state does not measure airflow.</p>
    </aside>
   </div>
  {/if}
  <footer>
   <span class:warning={!view.sourceLive}>{view.sourceLive?'OpenHAB live':'Source stale / disconnected'} · MQTT {view.operations.mqtt_connected?'connected':'unknown'} · ChirpStack {view.operations.chirpstack??'unprobed'} · Gateway {view.operations.gateway??'unverified'}</span>
   {#if sensors.length>15}<div><button disabled={page===0} onclick={()=>page--}>Previous</button><span>{page+1}/{Math.ceil(sensors.length/15)}</span><button disabled={(page+1)*15>=sensors.length} onclick={()=>page++}>Next</button></div>{/if}
   <span>{section==='property'?'Property observations · no alarm certification':'Binary contact evidence · no control authority'}</span>
  </footer>
 {/if}
</section>
{#if selected}
 <div class="detail-overlay">
  <dialog bind:this={detailDialog} class="sensor-detail" aria-label={`Details for ${selected.name}`}>
   <header><h2>{selected.name}</h2><button onclick={()=>selectedId=null}>Close</button></header>
   <p>{selected.zone} · {selected.location}</p>
   <dl>
    {#each [['Current state',stateLabel(selected.current_state)],['Last known contact',stateLabel(selected.contact_state)],['Communication',selected.health],['Last observation',since(selected.last_observed_at,now)],['Last received',since(selected.last_received_at,now)],['Last reported transition',since(selected.last_transition_at,now)],['Battery',selected.battery.condition],['Signal strength',selected.rssi==null?'Unknown':`${selected.rssi} dBm`],['Signal / noise',selected.snr==null?'Unknown':`${selected.snr} dB`],['Tamper',selected.tamper==null?'Unsupported / unknown':selected.tamper?'Reported':'Clear'],['Missing frame estimate',selected.missing_frame_estimate??0]] as detail}<dt>{detail[0]}</dt><dd>{detail[1]}</dd>{/each}
   </dl>
   <h3>Recent events</h3>
   {#each view.recent_events.filter(e=>e.sensor_id===selected.sensor_id).slice(0,5) as e}<p>{e.event_type.replaceAll('_',' ')} · {since(e.observed_at,now)}</p>{/each}
  </dialog>
 </div>
{/if}
<svelte:window onkeydown={event=>{if(event.key==='Escape')selectedId=null;}} />

<style>
 .ventilation{height:100%;min-height:0;display:flex;flex-direction:column;gap:.7rem;color:#e6edf3;overflow:hidden}
 .heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.heading h1{font-size:1.2rem;margin:0}.heading p{color:#8b93a1;margin:.15rem 0 0;font-size:.8rem}
 button,select{background:#111722;border:1px solid #293245;border-radius:.5rem;color:#b7c1d0;font:inherit;padding:.55rem .8rem;min-height:44px}button{cursor:pointer}button.chosen{color:#e6edf3;border-color:#678cad}button:disabled{opacity:.4}label{color:#8b93a1;font-size:.8rem}.tabs{display:flex;gap:.4rem}
 .summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.65rem}.summary>div{background:#0b0e14;border:1px solid #1c2230;border-radius:.6rem;padding:.65rem;display:flex;align-items:baseline;gap:.6rem}.summary strong{font-size:1.6rem;font-variant-numeric:tabular-nums}.summary span{font-size:.75rem;color:#8b93a1}
 .content{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:.75rem}.sensor-grid,.environment-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:.6rem;min-height:0}.environment-grid{flex:1}
 .sensor{position:relative;background:#0b0e14;border:1px solid #1c2230;border-radius:.65rem;padding:.65rem .8rem;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:.15rem}.sensor.open{border-color:#386e68;background:#0a1719}.sensor.unknown{border-color:#655736;background:#181611}.sensor-title{display:flex;justify-content:space-between;align-items:center;gap:.25rem}.sensor h2{font-size:.86rem;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sensor p{font-size:.72rem;color:#8b93a1;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.health{font-size:.66rem;color:#8b93a1}.state{display:flex;justify-content:space-between;align-items:center;margin-top:.2rem;gap:.3rem}.state strong{font-size:1.15rem}.state span,small{font-size:.68rem;color:#8b93a1}.sensor.open .state strong{color:#7dd9c4}.sensor.unknown .state strong{color:#e3c178}
 .details-button{position:absolute;inset:0;width:100%;height:100%;background:transparent;border:0;padding:0;border-radius:.65rem}.details-button:focus-visible{outline:2px solid #678cad;outline-offset:-2px}
 .detail-overlay{position:fixed;inset:0;background:#000b;display:grid;place-items:center;z-index:100;padding:1rem}.sensor-detail{background:#0b0e14;border:1px solid #293245;border-radius:.8rem;padding:1.2rem;width:min(480px,90vw);max-height:90dvh;overflow:auto;color:#e6edf3}.sensor-detail header{display:flex;align-items:center;justify-content:space-between}.sensor-detail h2{margin:0;font-size:1.1rem}.sensor-detail p{color:#8b93a1;font-size:.8rem}.sensor-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;font-size:.85rem}.sensor-detail dd{margin:0;text-align:right}.sensor-detail dt{color:#8b93a1}.sensor-detail h3{font-size:.9rem}
 .history{min-height:0;overflow:auto;background:#0b0e14;border:1px solid #1c2230;border-radius:.65rem;padding:.9rem}.history h2{font-size:.85rem;margin:0 0 .6rem}.history p{font-size:.75rem;color:#8b93a1}.event,.duration{display:grid;grid-template-columns:1fr auto;gap:.2rem;padding:.45rem 0;border-bottom:1px solid #1c2230;font-size:.7rem}.event small,.duration small{grid-column:1/-1}.daily-title{margin-top:1rem!important}.note{line-height:1.4}
 footer{display:flex;justify-content:space-between;gap:1rem;color:#8b93a1;font-size:.7rem}footer>div{display:flex;gap:.4rem;align-items:center}.warning{color:#e3c178}.empty{display:flex;flex:1;flex-direction:column;justify-content:center;align-items:center;grid-column:1/-1;color:#8b93a1;text-align:center;padding:1rem}.empty h2{color:#e6edf3}.empty p{margin:.4rem}
 @media(max-width:1000px){.content{grid-template-columns:minmax(0,1fr) 220px}.sensor-grid{grid-template-columns:repeat(2,minmax(0,1fr));overflow:auto}.summary span{font-size:.65rem}.sensor{min-height:100px}.heading{flex-wrap:wrap}}
 @media(max-width:700px){.content{display:block;overflow:auto}.sensor-grid{grid-auto-rows:130px}.history{margin-top:.6rem}.summary{grid-template-columns:repeat(3,minmax(0,1fr))}footer{flex-wrap:wrap}.heading h1{font-size:1rem}}
</style>
