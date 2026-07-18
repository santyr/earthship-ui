<script>
  import { onMount, onDestroy } from 'svelte';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { prepareSparklineSeries } from '../charts/historyPipeline.js';
  import { observeElementSize } from './observeElementSize.js';
  import { echartsTheme } from './tokens.js';

  let { data = [], color = '#22c55e', lineWidth = 2, smoothingAlpha = 0.25 } = $props();

  let el;
  let chart;
  let widthPx = $state(320);
  let stopObserving = () => {};
  const appliedSmoothingAlpha = $derived.by(() => {
    const alpha = Number(smoothingAlpha);
    return Number.isFinite(alpha) && alpha > 0 && alpha <= 1 ? alpha : 0.25;
  });

  function buildOption(points, lineColor, width, renderWidth, alpha) {
    let prepared = [];
    try {
      prepared = prepareSparklineSeries(points, { widthPx: renderWidth, alpha });
    } catch {
      // The compact card remains available even if one malformed persisted
      // row is encountered; full charts surface that validation as an error.
      prepared = [];
    }
    return {
      ...echartsTheme,
      grid: { left: 0, right: 0, top: 4, bottom: 0, containLabel: false },
      xAxis: {
        type: 'category',
        show: false,
        data: prepared.map((point) => point.time),
        boundaryGap: false,
      },
      yAxis: { type: 'value', show: false, scale: true },
      series: [{
        type: 'line',
        data: prepared.map((point) => point.value),
        showSymbol: false,
        smooth: false,
        connectNulls: true,
        lineStyle: { width, color: lineColor },
        areaStyle: { color: lineColor, opacity: 0.12 },
      }],
      tooltip: { show: false },
      animation: false,
    };
  }

  function update() {
    if (!chart) return;
    chart.setOption(buildOption(data ?? [], color, lineWidth, widthPx, appliedSmoothingAlpha), true);
  }

  onMount(() => {
    let cancelled = false;
    widthPx = el.clientWidth || 320;
    getEcharts().then((echarts) => {
      if (cancelled || !el) return;
      chart = echarts.init(el, null, { renderer: 'svg' });
      update();
      // observeElementSize owns the shared, debounced ResizeObserver.
      stopObserving = observeElementSize(el, ({ width, height }) => {
        if (width > 0) widthPx = width;
        if (width > 0 && height > 0) chart?.resize({ width, height });
      });
    });
    return () => { cancelled = true; };
  });

  $effect(() => {
    void data;
    void color;
    void lineWidth;
    void appliedSmoothingAlpha;
    void widthPx;
    update();
  });

  onDestroy(() => {
    stopObserving();
    chart?.dispose();
    chart = null;
  });
</script>

<div bind:this={el} class="sparkline" aria-hidden="true"></div>

<style>
  .sparkline {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    position: relative;
  }
</style>
