// Current station products have a separate identity from historical aliases.
const REPORT = 'WeatherStation_Quality_JSON';
const PRESSURE = 'WeatherStation_PressureAbsoluteV2';
const finite = value => typeof value === 'number' && Number.isFinite(value);
const clock = value => typeof value === 'string' ? Date.parse(value) : NaN;
const A = 'AmbientWeatherWS2902A_';
const FIELD_SPECS = [
  [A+'WeatherDataWs2902a_Temperature','outdoor',-40,149],
  [A+'WeatherDataWs2902a_RelativeHumidity','outdoor',0,100],
  ...[['WindSpeed',112],['WindGust',112],['WindDirectionDegrees',360],['RainFallTotal',100000],['SolarRadiation',1200],['UVIndex',15],['OutdoorBatteryStatus',1]]
    .map(([name,max])=>[A+name,'outdoor',0,max]),
  ['WeatherStation_LightLuxV2','outdoor',0,200000],['WeatherStation_SolarProxyV2','outdoor',0,1600],
  [PRESSURE,'indoor',300*.02953,1100*.02953],
  [A+'IndoorSensor_Temperature','indoor',-40,140],[A+'IndoorSensor_RelativeHumidity','indoor',0,100],
  ...[[193,'north_wall'],[223,'bedroom']].flatMap(([sid,role])=>[
    [A+`WH31E_${sid}_Temperature`,role,-40,140],[A+`WH31E_${sid}_RelativeHumidity`,role,0,100],
    [A+`WH31E_${sid}_BatteryStatus`,role,0,1]]),
];
const DERIVED = ['DewPointTemperature','HeatIndex','WindChill','ApparentTemperature','WindDirectionCardinal','UVDanger',
  'MaxDailyOutdoorTemp','MinDailyOutdoorTemp','MaxDailyOutdoorHumidity','MinDailyOutdoorHumidity','MaxDailyWindGust',
  'PressureTrend','WeatherDataWs2902a_PressureRelative','WeatherDataWs2902A_PressureRelative',
  'RainFallHourlyRate','RainFallDay','RainFallWeek','RainFallMonth','RainFallEvent','WindDirection'];

function unavailable(mode = 'v2') {
  return { mode, status:'unavailable', current:Object.fromEntries([...FIELD_SPECS.map(([name])=>name),...DERIVED.map(name=>A+name)].map(name=>[name,null])),
    pressure:{value:null,trend:null,label:'Station pressure',trendLabel:'3h trend unavailable'},
    rain:{day:null,week:null,month:null,event:null,hour:null,rate:null,partialDay:null,partialWeek:null,partialMonth:null} };
}

export function stationPresentation(states, { nowMs = Date.now() } = {}) {
  if (!Object.prototype.hasOwnProperty.call(states ?? {}, REPORT)) return unavailable('legacy');
  const result = unavailable();
  const raw = states[REPORT];
  if (typeof raw !== 'string' || raw.length > 32768 || !finite(nowMs)) return result;
  let report;
  try { report = JSON.parse(raw); } catch { return result; }
  if (report?.schema !== 'earthship-station-ingestion/v2') return result;
  const generated = clock(report.generatedAt);
  if (!Number.isFinite(generated) || generated > nowMs+5000 || nowMs-generated >= 90000) return result;
  for (const [name,role,min,max] of FIELD_SPECS) {
    const f=report.fields?.[name],received=clock(f?.receivedAt),deadline=clock(f?.validUntil);
    const value=name.endsWith('BatteryStatus') ? f?.value===1 ? 'OK' : f?.value===0 ? 'Low' : null : f?.value;
    if (f?.status==='fresh' && f.role===role && finite(f.value) && f.value>=min && f.value<=max
        && value===report.flat?.[name] && received<=nowMs+5000 && deadline>nowMs
        && deadline>received && deadline-received<=120000) result.current[name]=value;
  }
  const available = name => result.current[A+name] !== null;
  for (const [name,required] of [['DewPointTemperature',['WeatherDataWs2902a_Temperature','WeatherDataWs2902a_RelativeHumidity']],
    ['HeatIndex',['WeatherDataWs2902a_Temperature','WeatherDataWs2902a_RelativeHumidity']],
    ['WindChill',['WeatherDataWs2902a_Temperature','WindSpeed']],
    ['ApparentTemperature',['WeatherDataWs2902a_Temperature','WeatherDataWs2902a_RelativeHumidity','WindSpeed']]]) {
    const value=report.flat?.[A+name];
    if (required.every(available) && finite(value)) result.current[A+name]=value;
  }
  for (const [name,required,values] of [['WindDirectionCardinal','WindDirectionDegrees',['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']],
    ['UVDanger','UVIndex',['low','moderate','high','very high','extreme']]]) {
    if (available(required) && values.includes(report.flat?.[A+name])) result.current[A+name]=report.flat[A+name];
  }
  result.current[A+'WindDirection']=result.current[A+'WindDirectionDegrees'];
  for (const [source,high,low] of [['WeatherDataWs2902a_Temperature','MaxDailyOutdoorTemp','MinDailyOutdoorTemp'],
    ['WeatherDataWs2902a_RelativeHumidity','MaxDailyOutdoorHumidity','MinDailyOutdoorHumidity'],['WindGust','MaxDailyWindGust',null]]) {
    const e=report.dailyExtrema?.[A+source];
    if (!available(source) || e?.complete!==true || !(clock(e.periodValidUntil)>nowMs)) continue;
    if (finite(e.high) && e.high===report.flat?.[A+high]) result.current[A+high]=e.high;
    if (low && finite(e.low) && e.low===report.flat?.[A+low]) result.current[A+low]=e.low;
  }
  const field = report.fields?.[PRESSURE];
  const received = clock(field?.receivedAt), deadline = clock(field?.validUntil);
  if (field?.status === 'fresh' && field.role === 'indoor' && finite(field.value)
      && field.value >= 300*.02953 && field.value <= 1100*.02953
      && field.value === report.flat?.[PRESSURE] && received <= nowMs+5000
      && deadline > nowMs && deadline > received && deadline-received <= 120000) {
    result.pressure.value = field.value;
    const p = report.pressure;
    const bounds = p?.changeBoundsInHg;
    if (p?.identity === 'station_absolute' && p.method === 'three_hour_boundary_bracket_change_0.01inHg/v1'
        && finite(p.supportSeconds) && p.supportSeconds >= 10800 && p.supportSeconds <= 10920
        && Array.isArray(bounds) && bounds.length === 2 && bounds.every(finite) && bounds[0] <= bounds[1]) {
      const trend = bounds[0] > .01+1e-9 ? 'rising' : bounds[1] < -.01-1e-9 ? 'falling'
        : bounds[0] >= -.01-1e-9 && bounds[1] <= .01+1e-9 ? 'steady' : null;
      if (trend && trend === report.flat?.WeatherStation_PressureTrendV2) {
        result.pressure.trend = trend;
        result.pressure.trendLabel = `3h ${trend}`;
      }
    }
  }
  const rain = report.rain;
  if (rain?.schema === 'earthship-station-rain-products/v2' && rain.status === 'fresh' && available('RainFallTotal')) {
    for (const [target,key,unit,duration] of [['day','day','in'],['week','week','in'],['month','month','in'],
      ['event','event','in'],['hour','rolling_hour','in',3600000],['rate','rate_10min','in/h',600000]]) {
      const p = rain.products?.[key], start=clock(p?.start), end=clock(p?.end);
      if (p?.unit !== unit || !Number.isFinite(start) || !Number.isFinite(end)
          || (['day','week','month'].includes(target) && !(clock(p.periodValidUntil)>nowMs))
          || end < start || end > nowMs+5000 || nowMs-end >= 120000 || (duration && end-start !== duration)) continue;
      if (['day','week','month'].includes(target) && finite(p.partial_lower_bound)
          && p.partial_lower_bound >= 0 && p.partial_lower_bound <= 100000) {
        result.rain['partial'+target[0].toUpperCase()+target.slice(1)] = p.partial_lower_bound;
      }
      if (finite(p.value) && finite(p.lower) && finite(p.upper) && p.lower >= 0
          && p.lower <= p.value && p.value <= p.upper && p.upper <= 100000) result.rain[target] = p.value;
    }
  }
  result.status = result.pressure.value !== null || Object.values(result.rain).some(finite) ? 'partial' : 'unavailable';
  return result;
}

/** Complete totals and observed lower bounds retain distinct visible meanings. */
export function rainPeriodText(rain, period) {
  const value=rain?.[period];
  if (finite(value) && value>=0) return `${value.toFixed(2)}″`;
  const partial=rain?.['partial'+period[0].toUpperCase()+period.slice(1)];
  return finite(partial) && partial>=0 ? `≥${partial.toFixed(2)}″ · partial` : '—';
}
