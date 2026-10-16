import {expect,it} from 'vitest';
import {parseChronologicalSummary} from '../src/lib/household/chronology.js';
import summary from './fixtures/household-chronology.json';
const AT=Date.parse(summary.generated_at),parse=(v,nowMs=AT)=>parseChronologicalSummary(JSON.stringify(v),{nowMs});
it('keeps raw decisions, days, forecast windows and version groups distinct without release permission',()=>{
 const r=parse(summary);expect(r).not.toBeNull();expect(r.counts.raw_decisions).toBe(3);
 expect(r.counts.non_overlapping_windows).toBe(2);expect(r.counts.origin_days).toBe(2);
 expect(r.families.RUN_FEEDER_CYCLE.raw_decisions).toBe(0);expect(r.release_authorized).toBe(false);
 expect(parse(summary,AT+16*60000).expired).toBe(true);
});
it.each(['private','promote','counts','groups','family','time','duplicate','models'])('withholds malformed or promoted chronology: %s',damage=>{
 const r=structuredClone(summary);
 if(damage==='private')r.version_groups[0].versions.private_path='/private';
 if(damage==='promote')r.release_authorized=true;
 if(damage==='counts')r.counts.non_overlapping_windows=4;
 if(damage==='groups')r.version_groups[0].counts.raw_decisions=1;
 if(damage==='family')r.families.RUN_FEEDER_CYCLE.raw_decisions=1;
 if(damage==='time')r.generated_at='2099-01-01T00:00:00Z';
 if(damage==='models')r.version_groups[0].versions.models[0].raw='private';
 if(damage==='duplicate'){const raw=JSON.stringify(r).replace('{','{"schema":"private",');expect(parseChronologicalSummary(raw,{nowMs:AT})).toBeNull();return;}
 expect(parse(r)).toBeNull();
});
