<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';
  import { echartsTheme } from './tokens.js';
  import { num } from '../openhab/values.js';

  // Tiny trend line — no axes/grid, just the line. data: [{time, state}]
  let { data = [], color = '#22c55e' } = $props();

  let el;
  let chart;

  function buildOption(points, lineColor) {
    const xs = points.map((p) => p.time);
    const ys = points.map((p) => num(p.state));
    return {
      ...echartsTheme,
      grid: { left: 0, right: 0, top: 4, bottom: 0, containLabel: false },
      xAxis: { type: 'category', show: false, data: xs, boundaryGap: false },
      yAxis: { type: 'value', show: false, scale: true },
      series: [
        {
          type: 'line',
          data: ys,
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 2, color: lineColor },
          areaStyle: { color: lineColor, opacity: 0.12 },
        },
      ],
      tooltip: { show: false },
      animation: false,
    };
  }

  onMount(() => {
    chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(buildOption(data ?? [], color));
    const onResize = () => chart?.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  });

  $effect(() => {
    chart?.setOption(buildOption(data ?? [], color));
  });

  onDestroy(() => {
    chart?.dispose();
    chart = null;
  });
</script>

<div bind:this={el} class="sparkline"></div>

<style>
  .sparkline {
    width: 100%;
    height: 100%;
    min-height: 2.5rem;
  }
</style>
