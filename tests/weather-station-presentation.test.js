import { describe, expect, it } from 'vitest';
import { stationPresentation } from '../src/lib/weather/stationPresentation.js';

const now = Date.parse('2026-10-22T17:00:00Z');
function report() {
  const name='WeatherStation_PressureAbsoluteV2';
  return { schema:'earthship-station-ingestion/v2',generatedAt:new Date(now).toISOString(),
    flat:{[name]:23.89,WeatherStation_PressureTrendV2:'rising'},
    fields:{[name]:{value:23.89,receivedAt:new Date(now-60000).toISOString(),validUntil:new Date(now+60000).toISOString(),role:'indoor',status:'fresh'}},
    pressure:{identity:'station_absolute',method:'three_hour_boundary_bracket_change_0.01inHg/v1',supportSeconds:10800,changeBoundsInHg:[.04,.05]},
    rain:{schema:'earthship-station-rain-products/v2',status:'fresh',products:{
      day:{value:.1,unit:'in',start:'2026-10-22T06:00:00Z',end:new Date(now).toISOString(),lower:.1,upper:.1,partial_lower_bound:0},
      rate_10min:{value:.6,unit:'in/h',start:new Date(now-600000).toISOString(),end:new Date(now).toISOString(),lower:.6,upper:.6,partial_lower_bound:0}}}};
}
const states = payload => ({ WeatherStation_Quality_JSON:JSON.stringify(payload) });

describe('versioned station presentation',()=>{
  it('distinguishes legacy absence from an unavailable deployed report',()=>{
    expect(stationPresentation({}, {nowMs:now}).mode).toBe('legacy');
    for(const raw of ['NULL','UNDEF','{broken']) {
      const v=stationPresentation({WeatherStation_Quality_JSON:raw},{nowMs:now});
      expect(v.mode).toBe('v2');expect(v.pressure.value).toBeNull();expect(v.pressure.trend).toBeNull();
    }
  });
  it('exposes absolute station pressure and supported three-hour trend',()=>{
    const v=stationPresentation(states(report()),{nowMs:now});
    expect(v.pressure).toMatchObject({value:23.89,trend:'rising',label:'Station pressure',trendLabel:'3h rising'});
    expect(v.rain.day).toBe(.1);expect(v.rain.rate).toBe(.6);
  });
  it('never displays steady for a cold or gapped pressure history',()=>{
    const r=report();r.pressure.supportSeconds=720;
    r.flat.WeatherStation_PressureTrendV2='steady';
    expect(stationPresentation(states(r),{nowMs:now}).pressure.trendLabel).toBe('3h trend unavailable');
  });
  it('expires both report and individual fields without falling back to legacy values',()=>{
    const r=report();r.fields.WeatherStation_PressureAbsoluteV2.validUntil=new Date(now-1).toISOString();
    expect(stationPresentation(states(r),{nowMs:now}).pressure.value).toBeNull();
    expect(stationPresentation(states(report()),{nowMs:now+91000}).rain.day).toBeNull();
  });
  it('requires bracket support consistent with the declared trend',()=>{
    const r=report();r.pressure.changeBoundsInHg=[-.02,.03];r.flat.WeatherStation_PressureTrendV2='steady';
    expect(stationPresentation(states(r),{nowMs:now}).pressure.trend).toBeNull();
  });
  it('handles binary rounding at the one-hundredth inHg threshold consistently',()=>{
    const r=report();r.pressure.changeBoundsInHg=[.010000000000001,.010000000000001];
    r.flat.WeatherStation_PressureTrendV2='steady';
    expect(stationPresentation(states(r),{nowMs:now}).pressure.trend).toBe('steady');
  });
  it('withholds incomplete or malformed rain rather than inventing zero',()=>{
    const r=report();r.rain.products.day.value=null;r.rain.products.day.partial_lower_bound=.02;
    let v=stationPresentation(states(r),{nowMs:now});expect(v.rain.day).toBeNull();expect(v.rain.partialDay).toBe(.02);
    r.rain.products.rate_10min.unit='in';
    expect(stationPresentation(states(r),{nowMs:now}).rain.rate).toBeNull();
  });
  it('masks cached current fields unless their own original evidence is fresh',()=>{
    const r=report(),name='AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature';
    let v=stationPresentation(states(r),{nowMs:now});expect(v.current[name]).toBeNull();
    r.flat[name]=68;r.fields[name]={value:68,role:'outdoor',status:'fresh',receivedAt:new Date(now-1000).toISOString(),validUntil:new Date(now+60000).toISOString()};
    v=stationPresentation(states(r),{nowMs:now});expect(v.current[name]).toBe(68);
    r.fields[name].validUntil=new Date(now-1).toISOString();
    expect(stationPresentation(states(r),{nowMs:now}).current[name]).toBeNull();
  });
});
