<script>
  // 14-hour forecast strip for the Weather screen. Renders a per-hour icon
  // row (WMO code -> mdi icon, via wmo.js) above a combined ECharts panel:
  // temp line (left axis), precip% bars (right axis, 0-100), and a faint
  // solar-radiation "ribbon" along the bottom (hidden axis, low-opacity
  // area) so a sunny-but-cool hour is visually distinguishable from an
  // overcast one at a glance.
  //
  // hours: [{ h, t, p, r, w }] — hour label, temp, precip %, radiation
  // (W/m^2), WMO code. Already-sliced to the desired window by the caller
  // (Weather.svelte passes the first 14 entries of Forecast_Hourly_JSON).
  import { onMount, onDestroy } from 'svelte';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { echartsTheme, colors } from './tokens.js';
  import { num, rainAmountText } from '../openhab/values.js';
  import OhIcon from './OhIcon.svelte';
  import { wmoIcon, wmoColor } from './wmo.js';

  let { hours = [], height = 180 } = $props();

  let el = $state();
  let chart;

  const RADIATION_COLOR = '#fbbf24';

  function buildOption(rows) {
    const labels = rows.map((r) => r.h ?? '');
    const temps = rows.map((r) => num(r.t));
    const precip = rows.map((r) => num(r.p));
    const radiation = rows.map((r) => num(r.r));
    const maxRad = Math.max(1, ...radiation.map((v) => v ?? 0));

    return {
      ...echartsTheme,
      grid: { left: 36, right: 36, top: 12, bottom: 24 },
      xAxis: {
        type: 'category',
        data: labels,
        axisLine: echartsTheme.categoryAxis.axisLine,
        axisTick: { show: false },
        axisLabel: { color: colors.label, fontSize: 10 },
      },
      yAxis: [
        {
          type: 'value',
          scale: true,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: colors.temperature, fontSize: 10, formatter: '{value}°' },
          splitLine: { show: false },
        },
        {
          type: 'value',
          min: 0,
          max: 100,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: colors.rain, fontSize: 10, formatter: '{value}%' },
          splitLine: { show: false },
        },
        {
          type: 'value',
          min: 0,
          max: maxRad,
          show: false,
        },
      ],
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const i = params[0]?.dataIndex ?? 0;
          const row = rows[i] || {};
          const t = num(row.t);
          const p = num(row.p);
          const r = num(row.r);
          return [
            `<b>${row.h ?? ''}</b>`,
            `temp: ${t === null ? '—' : Math.round(t) + '°'}`,
            `precip: ${p === null ? '—' : Math.round(p) + '%'}`,
            `radiation: ${r === null ? '—' : Math.round(r) + ' W/m²'}`,
          ].join('<br/>');
        },
      },
      series: [
        {
          name: 'Radiation',
          type: 'bar',
          yAxisIndex: 2,
          data: radiation,
          barWidth: '100%',
          itemStyle: { color: RADIATION_COLOR, opacity: 0.14 },
          z: 0,
          silent: true,
        },
        {
          name: 'Precip %',
          type: 'bar',
          yAxisIndex: 1,
          data: precip,
          barWidth: '45%',
          itemStyle: { color: colors.rain, opacity: 0.55 },
          z: 1,
        },
        {
          name: 'Temp',
          type: 'line',
          yAxisIndex: 0,
          data: temps,
          smooth: false,
          showSymbol: false,
          lineStyle: { width: 2, color: colors.temperature },
          z: 2,
        },
      ],
      animation: false,
    };
  }

  async function render() {
    if (!el) return;
    const echarts = await getEcharts();
    if (!el) return;
    if (!chart) chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(hours ?? []), true);
    chart.resize();
  }

  onMount(() => {
    render();
    const onResize = () => chart?.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  });

  $effect(() => {
    void hours;
    render();
  });

  onDestroy(() => {
    chart?.dispose();
    chart = null;
  });
</script>

<div class="hourly-strip">
  {#if hours.length === 0}
    <div class="hs-empty">—</div>
  {:else}
    <div class="hs-icons">
      {#each hours as row, i (i)}
        <div class="hs-icon-col">
          <OhIcon icon={wmoIcon(row.w)} size="1.1rem" color={wmoColor(row.w) ?? 'currentColor'} />
          {#if rainAmountText(row.a)}
            <span class="hs-rain" data-testid="hour-rain-amount" style="color: {colors.rain}">{rainAmountText(row.a)}</span>
          {/if}
        </div>
      {/each}
    </div>
    <div bind:this={el} class="hs-chart" style="height: {height}px;"></div>
  {/if}
</div>

<style>
  .hourly-strip {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .hs-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b93a1;
  }
  .hs-icons {
    display: flex;
    padding: 0 36px;
    flex: 0 0 auto;
  }
  .hs-icon-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.05rem;
    color: #c7cfd9;
  }
  .hs-rain {
    font-size: 0.6rem;
    line-height: 1;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .hs-chart {
    flex: 1;
    min-height: 0;
    width: 100%;
  }
</style>
