import { describe, expect, it } from 'vitest';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';

const ISSUE='2026-10-12T20:00:15+00:00';
const NOW=Date.parse(ISSUE);
function payload(native=true) {
  const artifact='a'.repeat(64),runtime='b'.repeat(64);
  return {schema:`earthship-provisional-thermal-publication/v${native?2:1}`,version:native?9:8,status:'provisional',
    generatedAt:ISSUE,validUntil:'2026-10-12T20:15:15+00:00',
    model:{artifactSha256:artifact,runtimeSha256:runtime,createdAt:'2026-10-12T19:00:00+00:00',trainedThrough:'2026-10-12T18:00:00+00:00',
      fitExecuted:true,independentOriginDates:3,horizonSupport:{'1':3,'6':3,'12':2,'24':2},regularizationStrength:1},
    forecast:{schema:`earthship-provisional-thermal-forecast/v${native?2:1}`,status:'provisional',generated_at:ISSUE,
      artifact_sha256:artifact,runtime_sha256:runtime,horizon_hours:1,initial:{air_f:74,mass_f:73,outdoor_f:65},
      origin_actions:{indoor_shade_closed:0,outdoor_shade_present:1,vent_open:1,vent_provenance:'operator_confirmation',mode:'warm',action_knowledge:'as_of_snapshot_not_outcome_confirmation'},
      trajectory:[{at:'2026-10-12T21:00:15+00:00',air_f:75,mass_f:73.1}],confidence:'low',prediction_intervals:null,advice:[],graduated:false,automatic_actuation:false,
      ...(native?{model_rule:'earthship-native-installed-shade-dynamics/v2',geometry_series_sha256:'c'.repeat(64)}:{})},
    confidence:{grade:'low',actionLabels:'withheld'},graduation:{forecastQualified:false,stabilityAssessed:false,calibrationAssessed:false},
    automaticActuation:false,reasons:['Provisional model; measured accuracy is pending.']};
}
const parse=(value,now=NOW)=>parseThermalModelResult(JSON.stringify(value),now);

describe('native provisional publication compatibility',()=>{
  it.each([false,true])('renders the original/native provisional contract %s with withheld authority',native=>{
    const result=parse(payload(native));
    expect(result.state).toBe('ready');expect(result.badge).toBe('PROVISIONAL');expect(result.mode).toBe('provisional');
    expect(result.actionConfidence).toBe('withheld');expect(result.confidence).toBe('low');expect(result.uncertaintyMode).toBe('uncalibrated');
    expect(result.trajectory[0].hallwayF).toBe(75);expect(result.ventWindow).toBeNull();expect(result.effect.morningMassDeltaF).toBeNull();
    expect(result.modelAgeHours).toBeCloseTo(1+15/3600);expect(result.trainingDataAgeHours).toBeCloseTo(2+15/3600);
  });
  it.each([
    ['earthship-native-joint-shade-dynamics/v3',0],
    ['earthship-native-joint-shade-dynamics/v3',1],
    ['earthship-native-irradiance-shade-dynamics/v4',0],
    ['earthship-native-irradiance-shade-dynamics/v4',1],
  ])('renders the preserved family %s with outdoor shade state %s', (rule,outdoor)=>{
    const value=payload();value.forecast.model_rule=rule;value.forecast.origin_actions.outdoor_shade_present=outdoor;
    const result=parse(value);expect(result.state).toBe('ready');expect(result.badge).toBe('PROVISIONAL');
    expect(result.actionConfidence).toBe('withheld');expect(result.uncertaintyMode).toBe('uncalibrated');
    expect(result.trajectory[0].hallwayF).toBe(75);
  });
  it('keeps the original installed-only family outside the removed-shade domain',()=>{
    const value=payload();value.forecast.origin_actions.outdoor_shade_present=0;
    expect(parse(value).state).toBe('unavailable');
  });
  it.each(['actuation','shade'])('rejects invalid irradiance-family %s',damage=>{
    const value=payload();value.forecast.model_rule='earthship-native-irradiance-shade-dynamics/v4';
    value.forecast.origin_actions.outdoor_shade_present=0;
    if(damage==='actuation')value.forecast.automatic_actuation=true;
    else value.forecast.origin_actions.outdoor_shade_present=.5;
    expect(parse(value).state).toBe('unavailable');
  });
  it('preserves explicit unavailable native output',()=>{
    const value=payload();value.status='unavailable';value.model=null;value.forecast=null;value.confidence.grade='unavailable';
    const result=parse(value);expect(result.state).toBe('unavailable');expect(result.mode).toBe('unavailable');expect(result.badge).toBe('UNAVAILABLE');
  });
  it.each(['geometry_missing','geometry_bad','rule','numeric_schema','publication_schema','version','artifact','runtime','actuation','advice','confidence','graduation','unknown_field'])('refuses native %s',damage=>{
    const value=payload();
    if(damage==='geometry_missing')delete value.forecast.geometry_series_sha256;
    if(damage==='geometry_bad')value.forecast.geometry_series_sha256='invalid';
    if(damage==='rule')value.forecast.model_rule='legacy-sine';
    if(damage==='numeric_schema')value.forecast.schema='earthship-provisional-thermal-forecast/v1';
    if(damage==='publication_schema')value.schema='earthship-provisional-thermal-publication/v1';
    if(damage==='version')value.version=10;
    if(damage==='artifact')value.forecast.artifact_sha256='d'.repeat(64);
    if(damage==='runtime')value.forecast.runtime_sha256='d'.repeat(64);
    if(damage==='actuation')value.automaticActuation=true;
    if(damage==='advice')value.forecast.advice=['open_windows'];
    if(damage==='confidence')value.confidence.grade='high';
    if(damage==='graduation')value.graduation.forecastQualified=true;
    if(damage==='unknown_field')value.forecast.extra=1;
    expect(parse(value).state).toBe('unavailable');
  });
  it('withholds native output at exact expiry and before its issued clock',()=>{
    expect(parse(payload(),NOW+15*60_000).badge).toBe('UNAVAILABLE');
    expect(parse(payload(),NOW-1).badge).toBe('UNAVAILABLE');
  });
  it('refuses native metadata attached to the legacy schema',()=>{
    const value=payload(false);value.forecast.model_rule='earthship-native-installed-shade-dynamics/v2';
    value.forecast.geometry_series_sha256='c'.repeat(64);expect(parse(value).state).toBe('unavailable');
  });
});
