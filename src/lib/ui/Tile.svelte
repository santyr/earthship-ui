<script>
  // Base console tile chrome: rounded 1px border, small-caps label top-left.
  // All other tile primitives (StatTile, Arc, Sparkline, CompassRose) sit
  // inside one of these, or replicate this same chrome.
  let { label = '', accent = '#6b7280', span = 1, dim = false, children } = $props();
</script>

<div
  class="tile"
  style="grid-column: span {span}; opacity: {dim ? 0.5 : 1};"
>
  {#if label}
    <div class="tile-label" style="color: {accent}">{label}</div>
  {/if}
  <div class="tile-body">
    {@render children?.()}
  </div>
</div>

<style>
  .tile {
    border: 1px solid #1c2230;
    border-radius: 0.75rem;
    background: #11151c;
    padding: 0.9rem;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    box-sizing: border-box;
  }
  .tile-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    line-height: 1;
    margin-bottom: 0.4rem;
  }
  .tile-body {
    flex: 1;
    min-height: 0;
    min-width: 0;
  }
</style>
