<script>
  // SVG compass rose: needle points at `degrees` (0=N, clockwise), `speed`
  // shown centered, `gust` labeled on the outer ring.
  let { degrees = 0, speed = null, gust = null } = $props();

  const heading = $derived(((Number(degrees) || 0) % 360 + 360) % 360);
  const ticks = [0, 45, 90, 135, 180, 225, 270, 315];
  const dirLabels = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };

  function pt(deg, r) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: 50 + r * Math.cos(rad), y: 50 + r * Math.sin(rad) };
  }
</script>

<div class="compass-wrap">
  <svg viewBox="0 0 100 100" class="compass-svg">
    <circle cx="50" cy="50" r="46" fill="none" stroke="#1c2230" stroke-width="1.5" />
    <circle cx="50" cy="50" r="34" fill="none" stroke="#1c2230" stroke-width="1" />

    {#each ticks as t}
      {@const outer = pt(t, 46)}
      {@const inner = pt(t, 40)}
      <line
        x1={inner.x}
        y1={inner.y}
        x2={outer.x}
        y2={outer.y}
        stroke="#8b93a1"
        stroke-width={dirLabels[t] ? 1.5 : 1}
      />
      {#if dirLabels[t]}
        {@const lbl = pt(t, 37)}
        <text x={lbl.x} y={lbl.y} class="dir-label" text-anchor="middle" dominant-baseline="middle"
          >{dirLabels[t]}</text
        >
      {/if}
    {/each}

    <!-- needle -->
    <g transform="rotate({heading} 50 50)">
      <polygon points="50,14 45,52 50,46 55,52" fill="#22c55e" />
    </g>
    <circle cx="50" cy="50" r="3" fill="#22c55e" />
  </svg>

  <div class="compass-center">
    <div class="compass-speed">{speed ?? '—'}</div>
    <div class="compass-unit">mph</div>
  </div>

  {#if gust !== null && gust !== undefined && gust !== '—'}
    <div class="compass-gust">gust {gust}</div>
  {/if}
</div>

<style>
  .compass-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .compass-svg {
    width: 100%;
    height: 100%;
  }
  .dir-label {
    font-size: 7px;
    fill: #8b93a1;
    font-weight: 600;
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
    font-size: 1.6rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #e6edf3;
  }
  .compass-unit {
    font-size: 0.65rem;
    color: #8b93a1;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .compass-gust {
    position: absolute;
    bottom: -0.1rem;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.7rem;
    color: #22c55e;
    white-space: nowrap;
  }
</style>
