<script>
  import { onDestroy, onMount } from 'svelte';
  import {
    aggregateBitcoinCandles,
    buildBitcoinCandleOption,
  } from '../charts/bitcoinCandles.js';
  import { getEcharts } from '../charts/loadEcharts.js';
  import { observeElementSize } from './observeElementSize.js';

  let {
    points = [],
    startMs,
    endMs,
    interval = { unit: 'minutes', value: 60 },
  } = $props();

  let el;
  let chart;
  let stopObserving = () => {};

  function update() {
    if (!chart) return;
    const candles = aggregateBitcoinCandles(points ?? [], {
      startMs,
      endMs,
      interval,
    });
    chart.setOption(buildBitcoinCandleOption({ candles, compact: true, interval }), true);
  }

  onMount(() => {
    let cancelled = false;
    getEcharts().then((echarts) => {
      if (cancelled || !el) return;
      chart = echarts.init(el, null, { renderer: 'svg' });
      update();
      // observeElementSize owns the shared, debounced ResizeObserver.
      stopObserving = observeElementSize(el, ({ width, height }) => {
        if (width > 0 && height > 0) chart?.resize({ width, height });
      });
    });
    return () => { cancelled = true; };
  });

  $effect(() => {
    void points;
    void startMs;
    void endMs;
    void interval;
    update();
  });

  onDestroy(() => {
    stopObserving();
    chart?.dispose();
    chart = null;
  });
</script>

<div bind:this={el} class="bitcoin-candles" aria-hidden="true"></div>

<style>
  .bitcoin-candles {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
</style>
