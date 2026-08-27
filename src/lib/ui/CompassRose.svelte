<script>
  import { onMount } from 'svelte';
  import { compassPresentation } from './compassPresentation.js';
  // SVG compass rose: needle points at `degrees` (0=N, clockwise), `speed`
  // shown centered, `gust` labeled on the outer ring.
  let { degrees = null, speed = null, gust = null, showGust = true, accent = '#22c55e' } = $props();

  let roseHost;
  let roseSize = $state(0);

  const presentation = $derived(compassPresentation(degrees, speed));
  const ticks = [0, 45, 90, 135, 180, 225, 270, 315];
  const dirLabels = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };

  function pt(deg, r) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: 50 + r * Math.cos(rad), y: 50 + r * Math.sin(rad) };
  }

  function fitRose(width, height) {
    roseSize = Math.max(0, Math.floor(Math.min(width, height)));
  }

  onMount(() => {
    const measure = () => {
      const { width, height } = roseHost.getBoundingClientRect();
      fitRose(width, height);
    };

    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      fitRose(width, height);
    });
    observer.observe(roseHost);
    return () => observer.disconnect();
  });
</script>

<div class="compass-wrap">
  <div class="rose-host" bind:this={roseHost}>
    <div class="compass-square" style="width: {roseSize}px; height: {roseSize}px;">
      <svg viewBox="0 0 100 100" class="compass-svg" role="img" aria-label={presentation.ariaLabel}>
        <circle cx="50" cy="50" r="46" fill="none" stroke="#334155" stroke-width="1.5" />
        <circle cx="50" cy="50" r="34" fill="none" stroke="#273244" stroke-width="1" />

        {#each ticks as t}
          {@const outer = pt(t, 46)}
          {@const inner = pt(t, 40)}
          <line
            x1={inner.x}
            y1={inner.y}
            x2={outer.x}
            y2={outer.y}
            stroke="#94a3b8"
            stroke-width={dirLabels[t] ? 1.5 : 1}
          />
          {#if dirLabels[t]}
            {@const lbl = pt(t, 37)}
            <text x={lbl.x} y={lbl.y} class="dir-label" text-anchor="middle" dominant-baseline="middle"
              >{dirLabels[t]}</text
            >
          {/if}
        {/each}

        {#if presentation.hasHeading}
          <g transform="rotate({presentation.heading} 50 50)">
            <polygon class="compass-needle" points="50,23 43.5,53 50,48 56.5,53" fill={accent} />
          </g>
          <circle class="compass-hub" cx="50" cy="50" r="3.5" fill={accent} />
        {/if}
      </svg>

      <div class="compass-center">
        <div class="compass-speed">{presentation.speedText}</div>
        <div class="compass-unit">mph</div>
        <div class="compass-heading">{presentation.headingText}</div>
      </div>
    </div>
  </div>

  {#if showGust && gust !== null && gust !== undefined && gust !== '—' && !Number.isNaN(gust)}
    <div class="compass-gust">gust {gust}</div>
  {/if}
</div>

<style>
  .compass-wrap {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    gap: 0.15rem;
    overflow: hidden;
  }
  .rose-host {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .compass-square {
    position: relative;
    flex: 0 0 auto;
    max-width: 100%;
    max-height: 100%;
  }
  .compass-svg {
    width: 100%;
    height: 100%;
  }
  .dir-label {
    font-size: 13px;
    fill: #d7dee6;
    font-weight: 800;
  }
  .compass-center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    pointer-events: none;
  }
  .compass-speed {
    font-size: 1.8rem;
    font-weight: 700;
    line-height: 0.95;
    font-variant-numeric: tabular-nums;
    color: #f8fafc;
  }
  .compass-unit {
    font-size: 0.72rem;
    color: #aab4c2;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .compass-heading {
    margin-top: 0.12rem;
    font-size: 0.68rem;
    font-weight: 700;
    color: #d7dee6;
    letter-spacing: 0.035em;
    white-space: nowrap;
  }
  .compass-gust {
    text-align: center;
    font-size: 0.7rem;
    color: #22c55e;
    white-space: nowrap;
  }
</style>
