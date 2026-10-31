<script>
 import {adviceState,refreshAdvice,adviceAge} from '../household/adviceState.js';
 import {parseAdvice,feedbackStatus} from '../household/advice.js';
 import {recommendationClock} from '../household/recommendationState.js';
 let {scope=null,tiny=false,compact=false,header=false}=$props();
 const detailsId=$props.id();
 let pending=$state(false),notice=$state(''),localEvents=$state([]),localDeclarations=$state([]);
 let target=$state(''),declaredValue=$state('');
 const model=$derived(parseAdvice($adviceState.raw,{nowMs:$recommendationClock}));
 const refreshFailed=$derived($adviceState.refreshStatus==='failed');
 const issueAge=$derived(model?adviceAge(model.report.evaluated_at,$recommendationClock):null);
 const events=$derived([...new Map([...localEvents,...$adviceState.events].map(event=>[event.event_id,event])).values()]);
 const declarations=$derived([...$adviceState.declarations,...localDeclarations]);
 const family={shades:'SHADE_POSITION',ventilation:'VENTILATION_WINDOW',energy:'FLEXIBLE_LOAD_TIMING'};
 const current=$derived((refreshFailed?[]:model?.current??[]).filter(r=>(!scope||r.kind===family[scope])&&!declarations.some(d=>d.target===r.target&&Date.parse(d.reported_at)>Date.parse(r.decision_at))));
 const visible=$derived(current.filter(r=>!['dismissed','snoozed'].includes(feedbackStatus(r,events,$recommendationClock))));
 const domains=$derived(Object.entries(model?.domains??{}).filter(([name])=>!scope||name===scope));
 const provisional=$derived(Object.entries(model?.report.domains??{}).filter(([domain,result])=>(!scope||domain===scope)&&result.reason.startsWith('provisional_')&&result.comparison.length>1).map(([domain,result])=>({domain,...result.comparison[1],expired:$recommendationClock>=Math.min(Date.parse(result.valid_until),Date.parse(result.comparison[1].horizon_end))})).sort((a,b)=>Number(a.expired)-Number(b.expired)||(a.domain==='ventilation'?-1:b.domain==='ventilation'?1:0)));
 const summaryExpired=$derived(refreshFailed||(!visible.length&&(provisional.length?provisional.every(r=>r.expired):Boolean(model?.expired))));
 const currentProvisional=$derived(refreshFailed||model?.expired?[]:provisional.filter(r=>!r.expired));
 const summaryText=$derived([...visible.map(r=>r.action),...currentProvisional.map(r=>r.alternative)].slice(0,2).join(' · ')||(!model||summaryExpired||refreshFailed?'Awaiting fresh evidence':'No current suggestion'));
 const time=value=>new Intl.DateTimeFormat('en-US',{timeZone:model?.report.timezone??'America/Denver',hour:'numeric',minute:'2-digit'}).format(Date.parse(value));
 const words=value=>value.replaceAll('_',' ');
 async function saveFeedback(payload,episodeId){
  if(pending)return;pending=true;notice='';
  try{
   const response=await fetch('/api/household-advice-feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!response.ok)throw Error();
   localEvents=[...localEvents,{...payload,episode_id:episodeId,at:new Date(Date.now()).toISOString(),origin:'operator'}];notice=payload.kind==='report_action_taken'?'Action recorded as self-reported. Position and benefit remain separate evidence.':'Feedback saved.';
   refreshAdvice();
  }catch{notice='Feedback could not be saved; refresh advice and retry.';}finally{pending=false;}
 }
 async function feedback(rec,kind){
  return saveFeedback({event_id:crypto.randomUUID(),report_id:model.report.report_id,recommendation_id:rec.recommendation_id,kind,snooze_until:kind==='snooze'?new Date(Date.now()+1800000).toISOString():null,corrects:null},rec.episode_id);
 }
 async function undoFeedback(event){
  if(event.kind==='target_observed'||event.kind==='undo')return;
  return saveFeedback({event_id:crypto.randomUUID(),report_id:event.report_id,recommendation_id:event.recommendation_id,kind:'undo',snooze_until:null,corrects:event.event_id},event.episode_id);
 }
 async function declare(){
  const selected=$adviceState.targets.find(t=>t.target===target);if(!selected||pending||declaredValue==='')return;
  const value=selected.kind==='shade'?Number(declaredValue):declaredValue;
  if(selected.kind==='shade'&&(!Number.isFinite(value)||value<0||value>100))return;
  pending=true;const event_id=crypto.randomUUID();
  try{
   const response=await fetch('/api/household-advice-state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id,target,kind:selected.kind,value,valid_minutes:30})});if(!response.ok)throw Error();
   localDeclarations=[...localDeclarations,{target,reported_at:new Date(Date.now()).toISOString()}];notice='Operator observation saved for 30 minutes. Advice will be reassessed on the household cycle.';
   refreshAdvice();
  }catch{notice='Observation could not be saved.';}finally{pending=false;}
 }
</script>
{#snippet adviceBody()}
<section class="decisions" class:tiny={tiny&&!compact} aria-label="Household decision support">
 <div class="heading"><strong>{scope?`${words(scope)} advice`:'Recommended now / Later today / Review needed'}</strong><span>Manual advice</span></div>
 {#if model}<p class="basis">Evaluated {issueAge} · {time(model.report.evaluated_at)} · updates every 5 minutes</p>{/if}
 {#if refreshFailed}<p class="status" role="status">Update failed · {model?'showing the last evaluation; awaiting fresh evidence.':'awaiting a verified household issue.'}</p>{/if}
 {#if !model}<p class="status">Current advice unavailable · awaiting a verified household issue.</p>
 {:else if model.expired}<p class="status">Last advice expired · awaiting fresh evidence.</p>
 {:else if refreshFailed}<p class="status">Last advice is stale until a successful update.</p>
 {:else}
  <div class="cards">
   {#each visible.slice(0,3) as rec (rec.recommendation_id)}
    <article aria-label={rec.action}>
     <strong class="action">{rec.action}</strong>
     <p class="when">{Date.parse(rec.start_at)>$recommendationClock?'Later today':'Recommended now'} · {time(rec.start_at)}–{time(rec.end_at)} · review {time(rec.review_at)}</p>
     <p>{rec.reason}</p><p class="basis">{words(rec.evidence_basis)} · {rec.conditions.length?'Check conditions first':'Evidence-limited comparison'}</p>
     <button class="detail-button" type="button" popovertarget={`${detailsId}-${rec.recommendation_id}`}>Baseline, alternatives and uncertainty</button>
     <div class="advice-details" popover="auto" id={`${detailsId}-${rec.recommendation_id}`} aria-label="Advice details">
      <h3>{rec.action}</h3><p>{rec.reason}</p>
      {#if rec.kind==='SHADE_POSITION'}<p>Required targets: {rec.action_spec.shade_ids.join(', ')}.</p>{/if}
      <p>Baseline: {JSON.stringify(rec.baseline.state)} · {words(rec.baseline.basis)}</p>
      {#each rec.comparison as alternative}<p><strong>{alternative.alternative}:</strong> {alternative.outcome}{alternative.value===null?'':` · ${alternative.value.toFixed(1)} ${alternative.unit}`}</p>{/each}
      {#each [...rec.conditions,...rec.limitations] as detail}<p>{detail}</p>{/each}
      <p>Source validity: {time(rec.source_valid_until)}. Advice validity: {time(rec.valid_until)}.</p>
      <p>Reassess on: {rec.invalidation_triggers.join('; ')}.</p>
      <p>Feedback: {words(feedbackStatus(rec,events,$recommendationClock))}. Observed position, user intent, and thermal benefit are distinct evidence.</p>
      {#if (tiny&&!compact)||header}<div class="feedback"><button disabled={pending} onclick={()=>feedback(rec,'acknowledge')}>Seen</button><button disabled={pending} onclick={()=>feedback(rec,'report_action_taken')}>Report action taken</button><button disabled={pending} onclick={()=>feedback(rec,'snooze')}>Snooze 30 min</button><button disabled={pending} onclick={()=>feedback(rec,'dismiss')}>Dismiss</button></div>{/if}
      <button type="button" popovertarget={`${detailsId}-${rec.recommendation_id}`} popovertargetaction="hide">Close details</button>
     </div>
     {#if (!tiny||compact)&&!header}<div class="feedback"><button disabled={pending} onclick={()=>feedback(rec,'acknowledge')}>Seen</button><button disabled={pending} onclick={()=>feedback(rec,'report_action_taken')}>Report action taken</button><button disabled={pending} onclick={()=>feedback(rec,'snooze')}>Snooze 30 min</button><button disabled={pending} onclick={()=>feedback(rec,'dismiss')}>Dismiss</button></div>{/if}
    </article>
   {/each}
  </div>
  {#if !visible.length&&!provisional.length}<p class="status">{current.length?'Advice dismissed or snoozed.':'No current actionable suggestion.'}</p>{/if}
  <details class="readiness"><summary>Decision evidence and human records</summary>
   {#each domains as [domain,result]}<p><strong>{words(domain)}:</strong> {words(result.status)} · {words(result.reason)}{result.missing.length?` · needed: ${result.missing.map(words).join(', ')}`:''}</p>{/each}
  </details>
 {/if}
 {#if provisional.length}
  <div class="provisional-comparisons" aria-label="Provisional suggestions">
   <p class="basis">Provisional · issued {time(model.report.evaluated_at)}{summaryExpired?' · stale':''}</p>
   {#each provisional as suggestion (suggestion.domain)}
    <article><strong>{suggestion.alternative}</strong>{#if suggestion.expired}<span class="expired-label"> · expired</span>{/if}<p>{suggestion.outcome}</p></article>
   {/each}
  </div>
 {/if}
 {#if events.length}<details class="history"><summary>Human feedback and observed targets</summary>
  {#each events.filter(e=>e.kind!=='undo'&&!events.some(u=>u.kind==='undo'&&u.corrects===e.event_id)) as event (event.event_id)}
   {#if event.kind==='target_observed'}<p>Target observed: {event.target} · {time(event.at)}. Motivation and thermal benefit remain unverified.</p>
   {:else}<p>{words(event.kind)} · {time(event.at)} <button disabled={pending} onclick={()=>undoFeedback(event)}>Undo feedback</button></p>{/if}
  {/each}
 </details>{/if}
 {#if $adviceState.targets.length}<details><summary>Record an observed shade or window state</summary>
  <p>Operator declaration, valid for 30 minutes. Preview sliders and desired targets are separate.</p>
  <label>Target <select bind:value={target} onchange={()=>declaredValue=''}><option value="">Select a target</option>{#each $adviceState.targets as t}<option value={t.target}>{t.target}</option>{/each}</select></label>
  {#if $adviceState.targets.find(t=>t.target===target)?.kind==='shade'}<label>Percent open <input type="number" min="0" max="100" step="any" bind:value={declaredValue}/></label>
  {:else if target}<label>Observed state <select bind:value={declaredValue}><option value="">Select state</option><option value="open">Open</option><option value="closed">Closed</option></select></label>{/if}
  <button disabled={pending||!target||declaredValue===''} onclick={declare}>Save observation</button>
 </details>{/if}
 {#if notice}<p role="status">{notice}</p>{/if}
</section>
{/snippet}
{#if header}
 <div class="header-suggestions" aria-label="Household decision support">
  <button class="header-summary" type="button" popovertarget={`${detailsId}-header`} aria-label={summaryText} title={summaryText}>
   <span class="summary-action">{summaryText}</span>
  </button>
  <div class="header-popover" popover="auto" id={`${detailsId}-header`}>{@render adviceBody()}<button type="button" popovertarget={`${detailsId}-header`} popovertargetaction="hide">Close suggestions</button></div>
 </div>
{:else if compact}
 <div class="compact-summary"><span title={visible[0]?.reason??''}>Manual advice · {visible[0]?.action??(model?.expired?'Last advice expired':domains[0]?words(domains[0][1].reason):'Awaiting a verified household issue')}</span><button type="button" popovertarget={`${detailsId}-all`}>Details</button></div>
 <div class="compact-popover" popover="auto" id={`${detailsId}-all`}>{@render adviceBody()}<button type="button" popovertarget={`${detailsId}-all`} popovertargetaction="hide">Close advice</button></div>
{:else}{@render adviceBody()}{/if}
<style>

 .header-suggestions{min-width:0;width:100%;height:100%;display:flex;align-items:center}.header-summary{display:flex;align-items:center;gap:.45rem;width:100%;height:100%;min-width:0;border:0;background:transparent;text-align:left;white-space:nowrap;padding:0 .25rem;font-size:.76rem}.summary-action{min-width:0;overflow:hidden;text-overflow:ellipsis;color:#deebf8}.header-popover{width:min(48rem,calc(100vw - 2rem));max-height:calc(100dvh - 4rem);overflow:auto;position:fixed;inset:48px 1rem auto auto;margin:0;padding:.65rem;background:#111d2c;color:#d7e3ef;border:1px solid #45617b;border-radius:.5rem;box-shadow:0 .7rem 2rem #0008}.header-popover::backdrop{background:transparent}.provisional-comparisons article{padding:.45rem 0;border-top:1px solid #34506b}

 .compact-summary{display:flex;align-items:center;gap:.4rem;min-width:0;color:#b9cce1;font-size:.65rem}.compact-summary span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.compact-summary button{min-height:22px;font-size:.65rem;padding:.1rem .3rem}.compact-popover{max-width:min(48rem,calc(100vw - 2rem));max-height:calc(100dvh - 3rem);overflow:auto;background:#111d2c;color:#d7e3ef;border:1px solid #45617b;border-radius:.5rem;padding:.7rem}.compact-popover::backdrop{background:#0008}

 .advice-details{max-width:min(44rem,calc(100vw - 2rem));max-height:calc(100dvh - 3rem);overflow:auto;background:#111d2c;color:#d7e3ef;border:1px solid #45617b;border-radius:.5rem;padding:1rem;font-size:.9rem}.advice-details::backdrop{background:#0008}.detail-button{font-size:.7rem;margin-top:.2rem}
 .decisions{min-width:0;max-height:100%;overflow:auto;color:#d7e3ef;font-size:.77rem;background:#111d2c;border:1px solid #34506b;border-radius:.45rem;padding:.4rem .55rem}.heading{display:flex;gap:.7rem;justify-content:space-between;align-items:baseline}.heading span,.basis,.when,.status{color:#a9bacd}.heading span{font-size:.68rem;white-space:nowrap}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.6rem}.action{display:block;margin-top:.35rem}p{margin:.25rem 0;line-height:1.3}summary{cursor:pointer;color:#b7d2ef;padding:.25rem 0}.feedback{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.4rem}button,select,input{font:inherit;background:#182d43;color:#e1eefa;border:1px solid #45617b;border-radius:.3rem;padding:.25rem .4rem;min-height:30px}button{cursor:pointer}button:focus-visible,summary:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #65b5ff;outline-offset:2px}button:disabled{opacity:.6}.readiness{margin-top:.3rem}.tiny{font-size:.68rem;padding:.18rem .4rem}.tiny .cards{display:block}.tiny .feedback{gap:.2rem}label{display:inline-flex;align-items:center;gap:.3rem;margin:.3rem}
</style>
