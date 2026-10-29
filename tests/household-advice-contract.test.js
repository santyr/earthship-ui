import {expect,it} from 'vitest';
import fixture from './fixtures/household-advice-v1.json';
import {parseAdvice,feedbackStatus} from '../src/lib/household/advice.js';
const at=Date.parse(fixture.evaluated_at);
it('accepts the same Python report with structured actions and no actuation',()=>{
 const r=parseAdvice(JSON.stringify(fixture),{nowMs:at});expect(r).not.toBeNull();
 expect(r.current).toHaveLength(1);expect(r.current[0].action).toContain('100% open');expect(r.report.automatic_actuation).toBe(false);
});
it.each(['kind','excluded','extra','future','source','effect','command'])('rejects invalid public advice: %s',damage=>{
 const v=structuredClone(fixture);const rec=v.recommendations[0];
 if(damage==='kind')rec.kind='RUN_GREYWATER_CYCLE';if(damage==='excluded')rec.target='greywater';
 if(damage==='extra')v.raw_source='private';if(damage==='future')v.evaluated_at='2099-01-01T00:00:00Z';
 if(damage==='source')rec.snapshot_id='f'.repeat(64);if(damage==='effect')rec.effects.thermal_f='hot';if(damage==='command')rec.action_spec.command='ON';
 expect(parseAdvice(JSON.stringify(v),{nowMs:at})).toBeNull();
});
it('expires on the clock without a new stream event',()=>{
 const expired=parseAdvice(JSON.stringify(fixture),{nowMs:at+121000});expect(expired.current).toEqual([]);expect(expired.expired).toBe(true);
});
it('dismiss survives equivalent refresh and undo restores without declaring action',()=>{
 const rec=fixture.recommendations[0],events=[{event_id:'one',episode_id:rec.episode_id,kind:'dismiss',at:fixture.evaluated_at,snooze_until:null,corrects:null}];
 expect(feedbackStatus(rec,events,at)).toBe('dismissed');events.push({...events[0],event_id:'two',kind:'undo',corrects:'one'});
 expect(feedbackStatus(rec,events,at)).toBe('unseen');
});
it.each(['rule_effect','private_baseline','partial_rule','no_comparison'])('rejects unsupported or private nested advice: %s',damage=>{
 const v=structuredClone(fixture),rec=v.recommendations[0];
 if(damage==='rule_effect')rec.effects.thermal_f=-5;if(damage==='private_baseline')rec.baseline.state={private_path:'private'};
 if(damage==='partial_rule')rec.action_spec.position_open_pct=47.5;if(damage==='no_comparison')rec.comparison=[];
 expect(parseAdvice(JSON.stringify(v),{nowMs:at})).toBeNull();
});
