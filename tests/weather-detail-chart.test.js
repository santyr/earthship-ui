import { describe, expect, it } from 'vitest';
import { buildWeatherDetailOption } from '../src/lib/weather/detailChart.js';

const hours = Array.from({ length: 10 }, (_, index) => ({
  at: `2026-07-19T${String(index + 8).padStart(2, '0')}:00:00-06:00`,
  tempF: 60 + index,
  precipPct: index * 5,
  radiationWm2: index * 80,
  windMph: 5 + index,
  weatherCode: 1,
}));

describe('weather detail chart', () => {
  it('renders ten aligned temperature, precipitation, radiation, and wind values', () => {
    const option = buildWeatherDetailOption({ hours, widthPx: 900 });

    expect(option.xAxis.data).toHaveLength(10);
    expect(option.xAxis.data[0]).toBe('8 AM');
    expect(option.series.map(({ name }) => name)).toEqual([
      'Radiation',
      'Precipitation',
      'Temperature',
      'Wind',
    ]);
    expect(option.series.every(({ data }) => data.length === 10)).toBe(true);
    expect(option.series.filter(({ type }) => type === 'line')
      .every(({ smooth }) => smooth === false)).toBe(true);
    expect(option.animation).toBe(false);
  });

  it('uses dedicated bounded axes, measured margins, and a complete tooltip', () => {
    const compact = buildWeatherDetailOption({ hours, widthPx: 520 });
    const wide = buildWeatherDetailOption({ hours, widthPx: 1100 });

    expect(compact.yAxis).toHaveLength(4);
    expect(compact.yAxis[1]).toMatchObject({ min: 0, max: 100 });
    expect(compact.yAxis[2].show).toBe(false);
    expect(compact.yAxis[3]).toMatchObject({ position: 'right', offset: 42 });
    expect(compact.grid.left).toBeLessThan(wide.grid.left);
    expect(compact.grid.right).toBeLessThan(wide.grid.right);

    const tooltip = compact.tooltip.formatter([
      { axisValue: '8 AM', seriesName: 'Radiation', value: 0 },
      { axisValue: '8 AM', seriesName: 'Precipitation', value: 0 },
      { axisValue: '8 AM', seriesName: 'Temperature', value: 60 },
      { axisValue: '8 AM', seriesName: 'Wind', value: 5 },
    ]);
    expect(tooltip).toContain('60°F');
    expect(tooltip).toContain('0%');
    expect(tooltip).toContain('0 W/m²');
    expect(tooltip).toContain('5 mph');
  });
});


it('plots forecast depth in inches when no precipitation probability exists',()=>{
 const option=buildWeatherDetailOption({hours:hours.map(h=>({...h,precipPct:null,precipIn:0.02}))});
 expect(option.yAxis[1].name).toBe('in');
 expect(option.yAxis[1].max).not.toBe(100);
 expect(option.series.find(s=>s.name==='Precipitation').data).toEqual(Array(10).fill(0.02));
 expect(option.tooltip.formatter([{axisValue:'8 AM',seriesName:'Precipitation',value:0.02}])).toContain('0.02 in');
});

it('keeps the native instantaneous wind fallback separate from the local hourly-mean curve',()=>{
 const option=buildWeatherDetailOption({hours:[
  {...hours[0],windMph:3,windStatistic:'native_instantaneous'},
  {...hours[1],windMph:1,windStatistic:'local_hour_mean'},
  {...hours[2],windMph:1.2,windStatistic:'local_hour_mean'},
 ]});
 expect(option.series.find(s=>s.name==='Wind').data).toEqual([null,1,1.2]);
 expect(option.series.find(s=>s.name==='Native wind')).toMatchObject({data:[3,null,null],lineStyle:{width:0}});
 expect(option.tooltip.formatter([{dataIndex:0,axisValue:'8 AM',seriesName:'Native wind',value:3}])).toContain('Native instantaneous wind: 3 mph');
 expect(option.tooltip.formatter([{dataIndex:1,axisValue:'9 AM',seriesName:'Wind',value:1}])).toContain('Local hourly mean wind: 1 mph');
});

it('bounds real decimal rain-axis tick labels without changing the plotted depth',()=>{
 const depth=.06301885866743373;
 const option=buildWeatherDetailOption({hours:[{...hours[0],precipPct:null,precipIn:depth}]});
 expect(option.series.find(s=>s.name==='Precipitation').data).toEqual([depth]);
 expect(option.yAxis[1].axisLabel.formatter(depth)).toBe('0.063');
});
