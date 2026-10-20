import {expect,it} from 'vitest';
import {parseCalibratedPerformance} from '../src/lib/household/calibratedEnergy.js';
import {calibratedPerformance,CALIBRATED_NOW} from './fixtures/calibrated-energy.js';
it('keeps calibrated/raw SoC errors and actual AC coverage counts separate',()=>{
 const raw=JSON.stringify(calibratedPerformance()),v=parseCalibratedPerformance(raw,{nowMs:CALIBRATED_NOW});
 expect(v.by_horizon['1'].soc.mae_soc_pct.calibrated_pv).toBe(1);
 expect(v.by_horizon['1'].load.mae_kwh.current_ac).toBeNull();
 expect(v.by_horizon['6'].soc.count).toBe(0);
 expect(parseCalibratedPerformance(raw,{nowMs:CALIBRATED_NOW+3600000}).expired).toBe(true);
});
it.each(['authority','private','count','current','zero','future','digest','horizon','duplicate'])('refuses malformed %s outcome report',damage=>{
 const v=calibratedPerformance();
 if(damage==='authority')v.automatic_actuation=true;
 if(damage==='private')v.path='/private';
 if(damage==='count')v.by_horizon['1'].soc.attempted_count=0;
 if(damage==='current')v.by_horizon['1'].load.current_count=1;
 if(damage==='zero')v.by_horizon['6'].soc.mae_soc_pct.calibrated_pv=0;
 if(damage==='future')v.last_issue=new Date(CALIBRATED_NOW+1000).toISOString();
 if(damage==='digest')v.calibration_model_sha256='bad';
 if(damage==='horizon')v.by_horizon['2']=v.by_horizon['1'];
 let raw=JSON.stringify(v);if(damage==='duplicate')raw=raw.replace('{','{"graduated":false,');
 expect(parseCalibratedPerformance(raw,{nowMs:CALIBRATED_NOW})).toBeNull();
});
