<script>
  import {items} from '../openhab/store.js';
  import {parseHouseholdObservation} from '../household/observation.js';
  import {recommendationPreview,climatePreview} from '../household/recommendations.js';
  import {householdObservationRaw,recommendationClock} from '../household/recommendationState.js';
  let {group, tiny=false}=$props();
  const id=$props.id();
  const names={'night-policy':'Night-load override',devices:'Load devices',greywater:'Greywater',loads:'Household loads',feeding:'Feeding',ventilation:'Ventilation',shades:'Shades'};
  const name=$derived(names[group]??'Model');
  const climate=$derived(group==='ventilation'||group==='shades');
  const model=$derived(climate?climatePreview($items.Thermal_Model_JSON,group,$recommendationClock)
    :recommendationPreview(parseHouseholdObservation($householdObservationRaw,{nowMs:$recommendationClock}),group,$recommendationClock));
  const emptyText=$derived(group==='shades'?'Model shade advice unavailable':group==='ventilation'?'Model ventilation advice unavailable'
    :model.state==='none'?'Not proposed in this issue':model.state==='expired'?'Last issue expired · no current suggestion':'Recommendation unavailable');
  const summary=$derived(model.rows.length?model.rows.map(r=>`${r.status} · ${r.action}`).join('; '):emptyText);
  const date=value=>value?new Intl.DateTimeFormat('en-US',{timeZone:'America/Denver',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit'}).format(Date.parse(value)):'Not provided';
</script>
<section class="recommendation" class:tiny aria-label={`${name} recommendations`} data-recommendation-group={group}>
  <div class="preview-line">
    <span class="label">{tiny?'Preview':`${name} · preview only`}</span>
    <span class="summary" title={summary}>{summary}</span>
    <button type="button" popovertarget={id} aria-label={`${name} recommendation details (preview only)`}>Details</button>
  </div>
  {#if !tiny}<div class="disabled">Automatic actuation disabled</div>{/if}
  <div id={id} popover="auto" class="recommendation-details" aria-label={`${name} recommendation details`}>
    <h2>{name} recommendations · preview only</h2>
    <p>Automatic actuation disabled. Suggestions do not grant permission to operate equipment.</p>
    {#if model.state==='expired'}<p class="notice">Last proposal expired; historical evidence only.</p>{/if}
    {#if !model.rows.length}<p>{emptyText}</p>{/if}
    {#each model.rows as row (row.id)}
      <article>
        <h3>{row.action}</h3>
        <p><strong>{row.status}</strong> · Confidence: {row.confidence}</p>
        <p>Original reasons:</p><ul>{#each row.reasons as reason}<li>{reason}</li>{/each}</ul>
        {#if row.blockers.length}<p>Original blocks / unknowns:</p><ul>{#each row.blockers as blocker}<li>{blocker}</li>{/each}</ul>{/if}
        <dl><dt>Original decision</dt><dd>{date(row.createdAt)}</dd>
          {#if row.scheduledAt}<dt>Scheduled action</dt><dd>{date(row.scheduledAt)}</dd>{/if}
          <dt>Proposal expires</dt><dd>{date(row.expiresAt)}</dd>
          <dt>Source expires</dt><dd>{date(row.sourceExpiresAt)}</dd>
        </dl>
      </article>
    {/each}
    <button type="button" popovertarget={id} popovertargetaction="hide">Close details</button>
  </div>
</section>
<style>
  .recommendation { min-width:0; padding:.28rem 0; }
  .preview-line { display:flex; align-items:center; flex-wrap:wrap; gap:.18rem .4rem; min-width:0; }
  .label { color:#9caec5; font-size:.65rem; }
  .summary { flex:1 1 8rem; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#d3dbe8; font-size:.7rem; }
  button { border:1px solid #334155; border-radius:.3rem; padding:.13rem .32rem; background:#172131; color:#b8cef1; font:inherit; font-size:.65rem; cursor:pointer; }
  button:focus-visible { outline:2px solid #60a5fa; outline-offset:2px; }
  .disabled { color:#8b93a1; font-size:.6rem; margin-top:.12rem; }
  .tiny { padding:.06rem 0 0; }
  .tiny .preview-line { flex-wrap:nowrap; gap:.25rem; }
  .tiny .label,.tiny .summary,.tiny button { font-size:.56rem; }
  .tiny button { padding:.04rem .15rem; }
  .tiny .summary { flex-basis:0; }
  .recommendation-details { box-sizing:border-box; max-width:min(34rem,calc(100vw - 2rem)); max-height:calc(100dvh - 3rem); overflow:auto; padding:1rem; border:1px solid #42546b; border-radius:.7rem; background:#111827; color:#d3dbe8; font-size:.85rem; }
  .recommendation-details::backdrop { background:#0008; }
  h2 { font-size:1rem; margin:0 0 .6rem; } h3 { font-size:.92rem; margin:.7rem 0 .3rem; }
  p { margin:.45rem 0; } ul { margin:.25rem 0 .7rem; padding-left:1.1rem; }
  article { border-top:1px solid #334155; padding:.2rem 0 .6rem; }
  dt { color:#93a4bb; } dd { margin:0 0 .35rem; }
  .notice { color:#fbbf24; }
</style>
