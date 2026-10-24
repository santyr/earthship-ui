<script>
  import { onDestroy } from 'svelte';
  import { manualResultPresentation, manualShadeRequest, manualShadeTargets } from './installation.js';
  import { manualOutcomePresentation } from './manualResult.js';
  import { items } from '../openhab/store.js';
  let { installation, available = false } = $props();
  const targets = $derived(available ? manualShadeTargets(installation) : []);
  const context = $derived(JSON.stringify(installation));
  let dialog;
  let targetId = $state('');
  let openPercent = $state();
  let sending = $state(false);
  let inFlightCommand = $state(null);
  let message = $state('');
  let resultRows = $state([]);
  let acceptedResult = $state(null);
  const adapterResult = $derived(acceptedResult ? manualOutcomePresentation(acceptedResult.response,acceptedResult.request,
    acceptedResult.slots,$items,acceptedResult.contexts) : null);
  const resultMessage = $derived(adapterResult?.summary ?? message);
  const displayedRows = $derived(adapterResult?.rows ?? resultRows);
  let dialogContext = '';
  let controller;
  let timer;
  let mounted = true;
  const target = $derived(targets.find(row=>row.id===targetId));
  const percentValid = $derived(Number.isInteger(openPercent) && openPercent>=0 && openPercent<=100
    && target?.slots.every(slot=>slot.percentage));
  const supports = command => Boolean(target?.slots.length && target.slots.every(slot=>slot.operations.includes(command)));

  function cancel() {
    controller?.abort(); controller=null; clearTimeout(timer); sending=false;acceptedResult=null;
    dialog?.close();
  }
  $effect(()=>{ if (context !== dialogContext || !available) cancel(); });
  onDestroy(()=>{mounted=false;cancel();});

  function open() {
    if (!targets.length || sending) return;
    targetId=targets.find(row=>row.individual)?.id ?? targets[0].id;
    openPercent=undefined;message='';resultRows=[];acceptedResult=null;dialogContext=context;
    dialog.showModal();
  }

  async function send(command) {
    if (!mounted || !available || dialogContext!==context || !target) return;
    if (sending) {
      if (command!=='STOP' || inFlightCommand==='STOP') return;
      controller?.abort(); clearTimeout(timer);
    }
    let body;
    try { body=manualShadeRequest(target,command,{requestId:crypto.randomUUID(),requestedAtMs:Date.now()}); }
    catch { message='This operation is unavailable for the selected shades.';return; }
    const selected=target.slots.map(slot=>({number:slot.number,resultItem:slot.resultItem??null,
      commissionedEpoch:slot.commissionedEpoch,adapterShadeId:slot.adapterShadeId??null}));
    const contexts=Object.fromEntries(target.slots.map(slot=>{
      let health;try{health=JSON.parse($items[slot.serviceStateItem]);}catch{/* optional diagnostic context unavailable */}
      return [slot.number,health?.schema_version===2&&typeof health.adapter_session_id==='string'
        &&Number.isSafeInteger(health.source_generation)&&health.source_generation>=0
        ?{adapterSession:health.adapter_session_id,sourceGeneration:health.source_generation}:{}];
    }));
    controller=new AbortController();
    const request=controller; sending=true;inFlightCommand=body.command;message='Sending manual request…';resultRows=[];acceptedResult=null;
    const deadline=setTimeout(()=>request.abort(),30_000);
    timer=deadline;
    try {
      const response=await fetch('/api/shades/manual',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),signal:request.signal,cache:'no-store'});
      const data=await response.json().catch(()=>null);
      if (!mounted || request!==controller || request.signal.aborted || dialogContext!==context) return;
      if (response.status===401) {message='Manual authentication required.';return;}
      if (!response.ok) {message='Manual request was not accepted. Check current installation and permissions.';return;}
      const presentation=manualResultPresentation(data,body);
      message=presentation.summary;resultRows=presentation.rows;
      acceptedResult={response:data,request:body,slots:selected,contexts};
    } catch {
      if (mounted && request===controller && dialogContext===context)
        message=request.signal.aborted ? 'Request timed out or cancelled · outcome unknown. No retry was sent.' : 'Request failed · outcome unknown. No retry was sent.';
    } finally {
      clearTimeout(deadline);
      if (mounted && request===controller) {sending=false;inFlightCommand=null;}
    }
  }
</script>

{#if targets.length}
  <button type="button" class="manual-launch" onclick={open}>Manual control</button>
{/if}
<dialog bind:this={dialog} class="manual-dialog" aria-labelledby="shade-manual-title" oncancel={cancel}>
  <h2 id="shade-manual-title">Manual shade request</h2>
  <p>Only commissioned, individually released shades are included. Automatic actuation remains disabled. 100% open, 0% closed.</p>
  <label for="shade-manual-target">Shades to control</label>
  <select id="shade-manual-target" bind:value={targetId} disabled={sending}>
    {#each targets as choice (choice.id)}<option value={choice.id}>{choice.label}</option>{/each}
  </select>
  <p class="members">{target?.slots.length ?? 0} eligible · uncommissioned and unreleased slots excluded</p>
  <div class="operations">
    <button type="button" disabled={sending || !supports('UP')} onclick={()=>send('UP')}>Open</button>
    <button type="button" disabled={sending || !supports('DOWN')} onclick={()=>send('DOWN')}>Close</button>
    <button type="button" disabled={(sending && inFlightCommand==='STOP') || !supports('STOP')} onclick={()=>send('STOP')}>Stop</button>
  </div>
  <label for="shade-manual-percent">Percent open</label>
  <input id="shade-manual-percent" type="number" min="0" max="100" step="1" inputmode="numeric" bind:value={openPercent} disabled={sending || !target?.slots.every(slot=>slot.percentage)} />
  <button type="button" class="percent-submit" disabled={sending || !percentValid} onclick={()=>send({openPercent})}>Request percentage</button>
  {#if resultMessage}<p role="status" class="result">{resultMessage}</p>{/if}
  {#if displayedRows.length}<ul aria-label="Per-shade request results">{#each displayedRows as row}<li>Shade {row.slot}: {row.label}</li>{/each}</ul>{/if}
  <div class="footer"><button type="button" onclick={cancel}>Cancel</button></div>
</dialog>

<style>
 .manual-launch { margin-top:.3rem; min-height:44px; border:1px solid #98bbcc; border-radius:.3rem; background:#4c7184; color:white; padding:.35rem .65rem; cursor:pointer; font:inherit; }
 .manual-dialog { width:min(420px,calc(100vw - 40px)); max-height:calc(100dvh - 40px); overflow:auto; box-sizing:border-box; border:1px solid #7798aa; border-radius:.5rem; background:#182632; color:#edf3f8; padding:1rem; }
 .manual-dialog::backdrop { background:rgb(0 0 0 / 65%); }
 h2 { margin:0 0 .5rem; font-size:1.1rem; } p,li { font-size:.82rem; line-height:1.4; color:#c4d2dd; }
 label { display:block; margin:.7rem 0 .3rem; font-size:.85rem; } select,input { width:100%; min-height:44px; box-sizing:border-box; background:#101b24; color:#edf3f8; border:1px solid #7798aa; border-radius:.3rem; padding:.4rem; font:inherit; }
 button { min-height:44px; border:1px solid #98bbcc; border-radius:.3rem; background:#4c7184; color:white; padding:.4rem .6rem; cursor:pointer; font:inherit; font-size:.85rem; }
 button:disabled { opacity:.5; cursor:not-allowed; } button:focus-visible,input:focus-visible,select:focus-visible { outline:2px solid #b6e9f0; outline-offset:2px; }
 .operations { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.4rem; } .percent-submit { width:100%; margin-top:.5rem; } .footer { display:flex; justify-content:flex-end; margin-top:1rem; } .members { color:#9eafbc; } .result { border:1px solid #668495; padding:.5rem; border-radius:.3rem; }
</style>
