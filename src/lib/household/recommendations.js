/** Human-readable previews of validated original output; never a request builder. */
import {parseThermalModelResult} from '../thermal/modelResult.js';
const TYPES={'night-policy':['SET_NIGHT_LOAD_OVERRIDE'],devices:['SET_NIGHT_LOAD_DEVICE'],greywater:[],feeding:[],loads:['SET_NIGHT_LOAD_OVERRIDE','SET_NIGHT_LOAD_DEVICE']};
// Feeder triggering belongs exclusively to manual and Lightning-payment flows.
export const isAutomatedIntent=type=>['SET_NIGHT_LOAD_DEVICE'].includes(type);
const DEVICES={dishwasher:'Dishwasher',shureflo:'Shureflo pump','goat-cam':'Goat camera'};
const REASONS={low_soc:'Low forecast battery SoC',unqualified_effect:'Action effects are unqualified',source_unavailable:'Source evidence is unavailable',
 source_stale:'Source evidence is stale',after_dark:'Outside daylight hours',cooldown:'Cooldown has not elapsed',no_optional_action:'No optional action preferred'};
const GATES={owner_idle:'Owner idle state',cooldown_ready:'Cooldown',curfew_allowed:'Allowed operating hours',operator_unlocked:'Operator permission',
 manual_override_clear:'Manual override',battery_reserve:'Battery reserve',source_evidence:'Source evidence'};
export const reasonText=value=>REASONS[value]??String(value??'unknown').replaceAll('_',' ');
const empty=(state)=>({state,rows:[],current:false,automaticActuation:false});
function action(p){
 if(p.type==='RUN_GREYWATER_CYCLE')return 'Run greywater circulation cycle';
 if(p.type==='SET_NIGHT_LOAD_OVERRIDE')return p.parameters?`Night-load override: ${p.parameters.command}`:'Night-load override · action details unavailable';
 return p.parameters?`${DEVICES[p.parameters.device]}: ${p.parameters.command}`:'Household load · action details unavailable';
}
export function recommendationPreview(view,scope,nowMs=Date.now()){
 if(!view||!TYPES[scope])return empty('unavailable');
 const proposals=view.proposals.filter(p=>TYPES[scope].includes(p.type));
 if(!proposals.length)return empty(view.expired?'expired':'none');
 const rows=proposals.map(p=>{
  const expired=view.expired||nowMs>=Date.parse(view.valid_until)||(p.expires_at&&nowMs>=Date.parse(p.expires_at));
  const checks=p.hard_checks.filter(c=>c.status!=='pass');
  const blockers=[...new Set(checks.map(c=>c.reason==='unqualified_effect'?reasonText(c.reason):`${GATES[c.rule]??reasonText(c.rule)}: ${c.status==='unknown'?'unknown':reasonText(c.reason??'blocked')}`))];
  if(!p.selected&&!blockers.length)blockers.push(reasonText(p.decision_reason??'not_selected'));
  return {id:p.intent_id,action:action(p),status:expired?'Expired':p.selected?'Shadow selected':'Blocked',
   reasons:p.reasons.map(reasonText),blockers,confidence:p.confidence,createdAt:p.created_at??view.decision_at,
   expiresAt:p.expires_at??view.valid_until,sourceExpiresAt:view.valid_until,effectsQualified:false};
 });
 return {state:rows.every(r=>r.status==='Expired')?'expired':'available',rows,current:rows.some(r=>r.status!=='Expired'),automaticActuation:false};
}
export function climatePreview(raw,scope,nowMs=Date.now()){
 const result=parseThermalModelResult(raw,nowMs);
 if(!result||result.state==='unavailable')return empty('unavailable');
 const expired=result.state!=='ready';
 const published=JSON.parse(raw),sourceExpiry=published.validUntil??published.release?.expiresAt??null;
 const ventClose=published.schedule?.candidate?.ventCloseAt??null;
 const rows=[];
 if(scope==='ventilation'&&result.ventWindow&&published.schedule?.candidate?.ventOpenAt&&ventClose){
  rows.push({id:'vent-window',action:`Candidate ventilation window: ${result.ventWindow}`,status:expired||(ventClose&&nowMs>=Date.parse(ventClose))?'Expired':result.mode==='advisory_active'&&result.actionConfidence==='confirmed'?'Model suggestion':'Blocked',
   reasons:result.reasons.map(reasonText),blockers:result.actionConfidence==='confirmed'?[]:['Thermal action advice is unqualified'],confidence:result.confidence,
   createdAt:new Date(result.generatedAtMs).toISOString(),expiresAt:ventClose,sourceExpiresAt:sourceExpiry,effectsQualified:false});
 }
 // Trajectory markers may describe the baseline and are rounded into hourly buckets.
 // Shade advice needs an explicit candidate action/timing contract.
 return rows.length?{state:rows.every(r=>r.status==='Expired')?'expired':'available',rows,current:rows.some(r=>r.status!=='Expired'),automaticActuation:false}:empty('unavailable');
}
