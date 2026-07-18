<script>
  // Base console tile chrome: rounded 1px border, small-caps label top-left.
  // All other tile primitives (StatTile, Arc, Sparkline, CompassRose) sit
  // inside one of these, or replicate this same chrome.
  let {
    label = '',
    accent = '#6b7280',
    span = 1,
    dim = false,
    hideLabel = false,
    accessibleLabel = label,
    fill = false,
    clip = false,
    centerBody = false,
    padding = '',
    styleVars = '',
    statTile = false,
    children,
  } = $props();

  const rootStyle = $derived([
    `grid-column: span ${span}`,
    `opacity: ${dim ? 0.5 : 1}`,
    padding ? `padding: ${padding}` : '',
    styleVars,
  ].filter(Boolean).join('; '));
</script>

<div
  class="tile"
  style={rootStyle}
  role={hideLabel ? 'group' : undefined}
  aria-label={hideLabel ? accessibleLabel || label : undefined}
  data-tile-label-hidden={hideLabel ? '' : undefined}
  data-tile-fill={fill ? '' : undefined}
  data-tile-clip={clip ? '' : undefined}
  data-tile-center-body={centerBody ? '' : undefined}
  data-stat-tile={statTile ? '' : undefined}
>
  {#if label && !hideLabel}
    <div class="tile-label" style="color: {accent}">{label}</div>
  {/if}
  <div class="tile-body" class:centered={centerBody}>
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
  .tile[data-tile-fill] {
    height: 100%;
  }
  .tile[data-tile-clip] {
    overflow: hidden;
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
  .tile-body.centered {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
</style>
