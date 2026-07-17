<script>
  // Pure-SVG 270° sweep arc gauge. value is 0..100. No chart library.
  let { value = 0, color = '#22c55e', label = '', sublabel = '' } = $props();

  const clamped = $derived(Math.max(0, Math.min(100, Number(value) || 0)));

  const R = 40;
  const CIRC = 2 * Math.PI * R;
  const SWEEP = 270; // degrees of total gauge travel
  const START_ROTATE = -225; // leaves a 90deg gap centered at the bottom

  const trackDash = `${(SWEEP / 360) * CIRC} ${CIRC}`;
  const valueDash = $derived(`${(SWEEP / 360) * CIRC * (clamped / 100)} ${CIRC}`);
</script>

<div class="arc-wrap">
  <svg viewBox="0 0 100 100" class="arc-svg">
    <circle
      cx="50"
      cy="50"
      r={R}
      fill="none"
      stroke="#1c2230"
      stroke-width="8"
      stroke-dasharray={trackDash}
      stroke-linecap="round"
      transform="rotate({START_ROTATE} 50 50)"
    />
    <circle
      cx="50"
      cy="50"
      r={R}
      fill="none"
      stroke={color}
      stroke-width="8"
      stroke-dasharray={valueDash}
      stroke-linecap="round"
      transform="rotate({START_ROTATE} 50 50)"
    />
  </svg>
  <div class="arc-center">
    <div class="arc-value" style="color:{color}">{Math.round(clamped)}%</div>
    {#if label}<div class="arc-label">{label}</div>{/if}
    {#if sublabel}<div class="arc-sublabel">{sublabel}</div>{/if}
  </div>
</div>

<style>
  .arc-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .arc-svg {
    width: 100%;
    height: 100%;
  }
  .arc-center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    pointer-events: none;
  }
  .arc-value {
    font-size: 1.8rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .arc-label {
    margin-top: 0.25rem;
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    color: #8b93a1;
  }
  .arc-sublabel {
    font-size: 0.75rem;
    color: #6b7280;
  }
</style>
