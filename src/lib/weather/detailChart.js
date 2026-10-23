import { precipitationMetric } from './presentation.js';
import { temperatureCapabilityAt } from './capabilityForecast.js';
const AXIS_COLOR = '#8b93a1';
const GRID_COLOR = '#242b38';

function hourLabel(at) {
  const hour = Number(String(at ?? '').slice(11, 13));
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) return '—';
  if (hour === 0) return '12 AM';
  if (hour === 12) return '12 PM';
  return `${hour % 12} ${hour < 12 ? 'AM' : 'PM'}`;
}

function display(value, suffix) {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${Math.round(value)}${suffix}`
    : `—${suffix}`;
}

function tooltipFormatter(params, precipitation, nativeHours, hours) {
  const values = Object.fromEntries(
    (Array.isArray(params) ? params : []).map(({ seriesName, value }) => [seriesName, value]),
  );
  const label = params?.[0]?.axisValue ?? 'Forecast';
  const index=(Array.isArray(params)?params:[])[0]?.dataIndex;
  const native=nativeHours?.[index],hour=hours?.[index];
  return [
    `<strong>${label}</strong>`,
    `Temperature: ${display(values.Temperature, '°F')}`,
    `Precipitation: ${precipitation.format(values.Precipitation)}`,
    `Radiation: ${display(values.Radiation, ' W/m²')}`,
    hour?.windStatistic === 'native_instantaneous'
      ? `Native instantaneous wind: ${display(values['Native wind'], ' mph')}`
      : hour?.windStatistic === 'local_hour_mean' ? `Local hourly mean wind: ${display(values.Wind, ' mph')}`
        : `Wind: ${display(values.Wind, ' mph')}`,
    ...(native ? [`WeatherNext raw mean: ${display(native.meanF,'°F')}`,
      native.rangeStatus==='available' ? `WeatherNext p10–p90: ${display(native.p10F,'°F')}–${display(native.p90F,'°F')} (local coverage unverified)` : 'WeatherNext range unavailable',
      ...(native.p50F===null?[]:[`WeatherNext median: ${display(native.p50F,'°F')}`])] : []),
  ].join('<br>');
}

export function buildWeatherDetailOption({ hours = [], widthPx = 900, capabilities = null } = {}) {
  const wide = Number(widthPx) >= 760;
  const scopedWind = hours.some(hour => hour.windStatistic != null);
  const precipitation = precipitationMetric(hours);
  const nativeHours=hours.map(hour=>temperatureCapabilityAt(capabilities,hour.at));
  const nativeSeries=nativeHours.some(Boolean)?[
    {
      name:'WeatherNext p10–p90',type:'custom',yAxisIndex:0,silent:true,
      encode:{x:0,y:[1,2]},
      data:nativeHours.flatMap((h,index)=>h?.rangeStatus==='available'?[[index,h.p10F,h.p90F]]:[]),
      renderItem:(_params,api)=>{
        const low=api.coord([api.value(0),api.value(1)]),high=api.coord([api.value(0),api.value(2)]);
        const width=Math.abs(api.size([1,0])[0]);
        return {type:'rect',shape:{x:low[0]-width/2,y:Math.min(low[1],high[1]),width,height:Math.abs(low[1]-high[1])},style:{fill:'#a78bfa',opacity:.18}};
      },
    },
    {name:'WeatherNext raw mean',type:'line',yAxisIndex:0,data:nativeHours.map(h=>h?.meanF??null),smooth:false,showSymbol:false,connectNulls:false,lineStyle:{width:1,type:'dashed',color:'#c4b5fd'}},
    ...(nativeHours.some(h=>h?.p50F!=null)?[{name:'WeatherNext median',type:'line',yAxisIndex:0,data:nativeHours.map(h=>h?.p50F??null),smooth:false,showSymbol:false,connectNulls:false,lineStyle:{width:1,type:'dotted',color:'#94a3b8'}}]:[]),
  ]:[];
  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: {
      left: wide ? 56 : 42,
      right: wide ? 100 : 76,
      top: 28,
      bottom: wide ? 38 : 32,
      containLabel: false,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: params => tooltipFormatter(params, precipitation, nativeHours, hours),
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: hours.map(({ at }) => hourLabel(at)),
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisTick: { show: false },
      axisLabel: {
        color: AXIS_COLOR,
        fontSize: wide ? 11 : 10,
        interval: 0,
      },
    },
    yAxis: [
      {
        name: '°F',
        type: 'value',
        position: 'left',
        scale: true,
        axisLabel: { color: '#f59e0b', fontSize: 10 },
        nameTextStyle: { color: '#f59e0b' },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
      {
        name: precipitation.unit,
        show: precipitation.hasValues,
        type: 'value',
        position: 'right',
        min: 0,
        max: precipitation.max,
        axisLabel: { color: '#38bdf8', fontSize: 10, formatter: value => precipitation.probability ? `${Math.round(value)}` : `${Number(value.toPrecision(2))}` },
        nameTextStyle: { color: '#38bdf8' },
        splitLine: { show: false },
      },
      {
        type: 'value',
        show: false,
        min: 0,
      },
      {
        name: 'mph',
        type: 'value',
        position: 'right',
        offset: 42,
        min: 0,
        axisLabel: { color: '#22d3ee', fontSize: 10 },
        nameTextStyle: { color: '#22d3ee' },
        splitLine: { show: false },
      },
    ],
    series: [
      ...nativeSeries,
      {
        name: 'Radiation',
        type: 'bar',
        yAxisIndex: 2,
        data: hours.map(({ radiationWm2 }) => radiationWm2),
        itemStyle: { color: '#fbbf24', opacity: 0.14 },
        silent: true,
      },
      {
        name: 'Precipitation',
        type: 'bar',
        yAxisIndex: 1,
        data: precipitation.values,
        itemStyle: { color: '#38bdf8', opacity: 0.55 },
      },
      {
        name: 'Temperature',
        type: 'line',
        yAxisIndex: 0,
        data: hours.map(({ tempF }) => tempF),
        smooth: false,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
      },
      {
        name: 'Wind',
        type: 'line',
        yAxisIndex: 3,
        data: hours.map(hour => !scopedWind || hour.windStatistic === 'local_hour_mean' ? hour.windMph : null),
        connectNulls: false,
        smooth: false,
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2, color: '#22d3ee' },
        itemStyle: { color: '#22d3ee' },
      },
      ...(scopedWind ? [{ name: 'Native wind', type: 'line', yAxisIndex: 3, smooth: false, connectNulls: false, lineStyle: { width: 0 },
        data: hours.map(hour => hour.windStatistic === 'native_instantaneous' ? hour.windMph : null),
        symbol: 'diamond', symbolSize: 7, itemStyle: { color: '#67e8f9' } }] : []),
    ],
  };
}
