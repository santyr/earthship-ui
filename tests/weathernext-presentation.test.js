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

describe('daily predominant conditions', () => {
  const hours = (rain = [], cloud = 45) => Array.from({ length: 24 }, (_, h) => ({
    at: `2026-10-23T${String(h).padStart(2, '0')}:00:00-06:00`,
    isDay: h >= 8 && h < 18, cloudPct: h >= 8 && h < 18 ? cloud : 100,
    precipIn: (rain[h] ?? 0) / 25.4,
  }));
  const daily = (rows, extra = {}) => ({ cloudPct: 90, precipSumIn: 3 / 25.4, isDay: true, hours: rows, ...extra });
  it('keeps the daytime sky when daily rain is mostly overnight or brief', () => {
    expect(forecastCondition(daily(hours({ 2: 2.5, 12: 0.5 })))).toMatchObject({ icon: 'mdi:weather-partly-cloudy', basis: 'cloud-cover' });
    expect(forecastCondition(daily(hours({ 2: 2.5, 12: 0.5 }))).label).toMatch(/outside daylight/i);
    expect(forecastCondition(daily(hours({ 12: 0.5 }), { precipSumIn: 0.5 / 25.4 })).icon).toBe('mdi:weather-partly-cloudy');
    expect(forecastCondition(daily(hours([], 10))).icon).toBe('mdi:weather-sunny');
  });
  it('distinguishes sustained from intermittent material daytime precipitation', () => {
    const sustained = Object.fromEntries([8, 9, 10, 11, 12, 13].map(h => [h, 0.3]));
    expect(forecastCondition(daily(hours(sustained, 90))).icon).toBe('mdi:weather-rainy');
    expect(forecastCondition(daily(hours({ 8: 0.4, 10: 0.4, 12: 0.4 }))).icon).toBe('mdi:weather-partly-cloudy');
    const mixed = hours({ 14: 0.3, 15: 0.3, 16: 0.3, 17: 0.3 }).map((h,i) => i>=8&&i<11 ? {...h,cloudPct:5} : i>=11&&i<14 ? {...h,cloudPct:95} : h);
    expect(forecastCondition(daily(mixed)).icon).toBe('mdi:weather-partly-rainy');
    expect(forecastCondition(daily(hours({ 12: 3 }))).icon).toBe('mdi:weather-partly-cloudy');
    expect(forecastCondition(daily(hours({ 8: 0.4, 10: 0.4, 12: 0.4 }, 90))).icon).toBe('mdi:weather-cloudy');
  });
  it('chooses the majority sky category rather than a misleading cloud average', () => {
    const sunny = hours([], 100).map((h, i) => i >= 8 && i < 14 ? { ...h, cloudPct: 5 } : h);
    expect(forecastCondition(daily(sunny, { precipSumIn: 0 })).icon).toBe('mdi:weather-sunny');
    sunny[16].precipIn = 1.5 / 25.4;
    expect(forecastCondition(daily(sunny)).icon).toBe('mdi:weather-sunny');
    const cloudy = hours([], 0).map((h, i) => i >= 8 && i < 14 ? { ...h, cloudPct: 95 } : h);
    expect(forecastCondition(daily(cloudy, { precipSumIn: 0 })).icon).toBe('mdi:weather-cloudy');
    const tied = hours([], 100).map((h, i) => i >= 8 && i < 13 ? { ...h, cloudPct: 0 } : h);
    expect(forecastCondition(daily(tied, { precipSumIn: 0 })).icon).toBe('mdi:weather-partly-cloudy');
  });
  it('does not turn many tiny traces into a rainy day', () => {
    const traces = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [i + 8, 0.09]));
    expect(forecastCondition(daily(hours(traces))).icon).toBe('mdi:weather-partly-cloudy');
  });
  it('keeps missing precipitation, missing daylight and timing gaps explicit', () => {
    const rows = hours({ 8: 0.5, 9: 0.5, 10: 0.5, 11: 0.5, 12: 0.5 });
    rows[13].precipIn = null;
    expect(forecastCondition(daily(rows))).toMatchObject({ icon: 'mdi:weather-partly-cloudy' });
    expect(forecastCondition(daily(rows)).label).toMatch(/timing unavailable/i);
    expect(forecastCondition(daily(hours().filter(h => !h.at.includes('T13:')))).label).toMatch(/timing unavailable/i);
    expect(forecastCondition(daily(hours().map(h => ({ ...h, isDay: null }))))).toMatchObject({ icon: 'mdi:weather-cloudy' });
    expect(forecastCondition(daily([], { cloudPct: null })).icon).toBe('mdi:weather-rainy');
  });
  it('uses only declared remaining complete intervals without altering source data', () => {
    const rows = hours({ 8: 3, 9: 3, 10: 3, 11: 3, 12: 3 });
    const row = daily(rows, { precipitationScope: 'remaining', precipitationFromAt: '2026-10-23T13:00:00-06:00', precipitationThroughAt: '2026-10-24T00:00:00-06:00', precipSumIn: 0 });
    const before = JSON.stringify(row);
    expect(forecastCondition(row).icon).toBe('mdi:weather-partly-cloudy');
    expect(JSON.stringify(row)).toBe(before);
  });
  it.each([1,2,3])('classifies a complete short remaining window of %i rainy periods', count => {
    const rows = hours(Object.fromEntries(Array.from({length:count},(_,i)=>[15+i,1])),5);
    expect(forecastCondition(daily(rows,{precipitationScope:'remaining',precipitationFromAt:'2026-10-23T14:00:00-06:00',precipitationThroughAt:`2026-10-23T${14+count}:00:00-06:00`,precipSumIn:count/25.4})).icon).toBe('mdi:weather-rainy');
  });
  it('preserves an actual source condition and leaves hourly classification unchanged', () => {
    expect(forecastCondition(daily(hours(), { weatherCode: 95 })).icon).toBe('mdi:weather-lightning');
    expect(forecastCondition({ cloudPct: 45, precipIn: 0.5 / 25.4, isDay: true }).icon).toBe('mdi:weather-rainy');
  });
});
