import { describe, expect, it } from 'vitest';
import { forecastCondition, forecastDisplayDay } from '../src/lib/weather/presentation.js';
import { parseForecast10Day, hourlyForecastFromDetail } from '../src/lib/weather/forecastDetail.js';
import { rainAmountText } from '../src/lib/openhab/values.js';
import { energyForecastPresentation } from '../src/lib/energy/forecastPresentation.js';
import { energyObservation, ENERGY_NOW } from './fixtures/household-energy.js';

describe('WeatherNext presentation', () => {
  it('uses actual cloud cover and native daylight without manufacturing WMO codes', () => {
    expect(forecastCondition({ cloudPct: 12, isDay: true })).toMatchObject({ icon: 'mdi:weather-sunny', basis: 'cloud-cover' });
    expect(forecastCondition({ cloudPct: 12, isDay: false, at: '2026-10-19T22:00:00-06:00' }).icon).toBe('mdi:weather-night');
    expect(forecastCondition({ cloudPct: 50, isDay: null }).icon).toBe('mdi:weather-cloudy');
    expect(forecastCondition({ cloudPct: 50, isDay: false }).icon).toBe('mdi:weather-night-partly-cloudy');
    expect(forecastCondition({ cloudPct: 40, precipSumIn: 0.01 }).basis).toBe('cloud-cover');
    expect(forecastCondition({ cloudPct: 90 }).icon).toBe('mdi:weather-cloudy');
    expect(forecastCondition({ cloudPct: null, precipIn: null }).basis).toBe('unavailable');
    expect(forecastCondition({ weatherCode: 95, cloudPct: 0, isDay: true }).icon).toBe('mdi:weather-lightning');
  });
  it('distinguishes trace from material precipitation without asserting snow or thunderstorms', () => {
    expect(rainAmountText(0.0008)).toBe('<0.01″');
    expect(forecastCondition({ cloudPct: 10, precipIn: 0.0008, isDay: true }).basis).toBe('cloud-cover');
    expect(forecastCondition({ cloudPct: 10, precipIn: 0.02, tempF: 20 }).label).toMatch(/precipitation/i);
    expect(forecastCondition({ cloudPct: 10, precipIn: 0.02, tempF: 20 }).icon).not.toContain('snow');
  });
  it('labels a remaining-day range, without treating incomplete future days as full forecasts', () => {
    const day = {date:'2026-10-19',summary:{highF:null,lowF:null},hours:[{atMs:Date.parse('2026-10-19T18:00Z'),tempF:80},{atMs:Date.parse('2026-10-19T20:00Z'),tempF:65},{atMs:Date.parse('2026-10-19T23:00Z'),tempF:50}]};
    const nowMs=Date.parse('2026-10-19T19:00Z');
    expect(forecastDisplayDay(day,{nowMs})).toMatchObject({summary:{highF:65,lowF:50,temperatureScope:'remaining'}});
    expect(forecastDisplayDay({...day,date:'2026-10-20'},{nowMs}).summary.highF).toBeNull();
    expect(forecastDisplayDay({...day,summary:{highF:82,lowF:33}},{nowMs}).summary).toMatchObject({highF:82,lowF:33});
  });
  it('keeps optional cloud cover through parsing and hourly strip normalization', () => {
    const nowMs=Date.parse('2026-10-19T18:00Z');
    const raw=JSON.stringify({version:1,provider:'weathernext3',providerStatus:'AVAILABLE',generatedAt:'2026-10-19T18:00Z',timezone:'America/Denver',days:[{date:'2026-10-19',summary:{highF:null,lowF:null,precipPct:null,weatherCode:null,pvKwh:null,cloudPct:40},hours:[{at:'2026-10-19T13:00:00-06:00',tempF:65,precipPct:null,precipIn:0,cloudPct:40,radiationWm2:600,windMph:3,weatherCode:null,isDay:true}]}]});
    const result=parseForecast10Day(raw.replaceAll('18:00Z','18:00:00Z'),{nowMs});
    expect(result.status).toBe('ready');
    expect(result.days[0].summary.cloudPct).toBe(40);
    expect(hourlyForecastFromDetail(result,{nowMs})[0]).toMatchObject({c:40,w:null});
  });
});

describe('live PV potential presentation',()=>{
  it('uses a fresh validated potential view and preserves capture uncertainty',()=>{
    const raw=energyObservation();raw.storage_status='unavailable';raw.storage_reason='household_AC_load_unavailable';
    for(const key of ['captured_pv_24h_kwh','household_ac_load_w_assumption','initial_soc_pct','nominal_bank_kwh'])raw[key]=null;
    for(const row of raw.trajectory){row.captured_pv_kwh=null;row.nominal_soc_pct=null;}
    const view=energyForecastPresentation(JSON.stringify(raw),{nowMs:ENERGY_NOW});
    expect(view.potentialRemainingTodayKwh).toBe(raw.potential_pv_remaining_today_kwh);
    expect(view.potential24hKwh).toBe(raw.potential_pv_24h_kwh);
    expect(view.captured24hKwh).toBeNull();
    expect(view.periods).toHaveLength(8);
    expect(view.periods.reduce((sum,p)=>sum+p.pv,0)).toBeCloseTo(raw.potential_pv_24h_kwh);
    expect(energyForecastPresentation(JSON.stringify(raw),{nowMs:ENERGY_NOW+16*60000})).toBeNull();
  });
});
