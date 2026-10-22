// Current station products have a separate identity from historical aliases.
const REPORT = 'WeatherStation_Quality_JSON';
const PRESSURE = 'WeatherStation_PressureAbsoluteV2';
const finite = value => typeof value === 'number' && Number.isFinite(value);
const clock = value => typeof value === 'string' ? Date.parse(value) : NaN;

function unavailable(mode = 'v2') {
  return { mode, status:'unavailable', pressure:{value:null,trend:null,label:'Station pressure',trendLabel:'3h trend unavailable'},
    rain:{day:null,week:null,month:null,event:null,hour:null,rate:null,partialDay:null} };
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
      const trend = bounds[0] > .01 ? 'rising' : bounds[1] < -.01 ? 'falling'
        : bounds[0] >= -.01 && bounds[1] <= .01 ? 'steady' : null;
      if (trend && trend === report.flat?.AmbientWeatherWS2902A_PressureTrend) {
        result.pressure.trend = trend;
        result.pressure.trendLabel = `3h ${trend}`;
      }
    }
  }
  const rain = report.rain;
  if (rain?.schema === 'earthship-station-rain-products/v2' && rain.status === 'fresh') {
    for (const [target,key,unit,duration] of [['day','day','in'],['week','week','in'],['month','month','in'],
      ['event','event','in'],['hour','rolling_hour','in',3600000],['rate','rate_10min','in/h',600000]]) {
      const p = rain.products?.[key], start=clock(p?.start), end=clock(p?.end);
      if (p?.unit !== unit || !Number.isFinite(start) || !Number.isFinite(end)
          || end < start || end > nowMs+5000 || nowMs-end >= 120000 || (duration && end-start !== duration)) continue;
      if (target === 'day' && finite(p.partial_lower_bound) && p.partial_lower_bound >= 0 && p.partial_lower_bound <= 100000) {
        result.rain.partialDay = p.partial_lower_bound;
      }
      if (finite(p.value) && finite(p.lower) && finite(p.upper) && p.lower >= 0
          && p.lower <= p.value && p.value <= p.upper && p.upper <= 100000) result.rain[target] = p.value;
    }
  }
  result.status = result.pressure.value !== null || Object.values(result.rain).some(finite) ? 'partial' : 'unavailable';
  return result;
}
