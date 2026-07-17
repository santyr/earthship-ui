<script>
  import Tile from './Tile.svelte';

  // The common big-number tile: label top, big value+unit, small footer.
  let {
    label = '',
    value = null,
    unit = '',
    accent = '#8b93a1',
    footer = '',
    icon = '',
    dim = false,
    span = 1,
  } = $props();

  const display = $derived(
    value === null || value === undefined || value === '—' ? '—' : `${value}${unit}`
  );
</script>

<Tile {label} {accent} {span} {dim}>
  <div class="stat">
    {#if icon}<span class="icon">{icon}</span>{/if}
    <span class="value">{display}</span>
  </div>
  {#if footer}
    <div class="footer">{footer}</div>
  {/if}
</Tile>

<style>
  .stat {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }
  .icon {
    font-size: 1.1rem;
    line-height: 1;
  }
  .value {
    font-size: 2.4rem;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #e6edf3;
    white-space: nowrap;
  }
  .footer {
    margin-top: 0.35rem;
    font-size: 0.8rem;
    color: #8b93a1;
  }
</style>
