<script>
  import Tile from './Tile.svelte';
  import OhIcon from './OhIcon.svelte';

  // The common big-number tile: label top, big value+unit, small footer.
  let {
    label = '',
    value = null,
    unit = '',
    accent = '#8b93a1',
    footer = '',
    icon = '',
    iconName = '',
    iconColor = 'currentColor',
    iconSize = '1.35rem',
    dim = false,
    span = 1,
    valueSize = '',
    footerSize = '',
    footerNoWrap = false,
    centerContent = false,
    stackValue = false,
    hideLabel = false,
    accessibleLabel = label,
    fill = false,
    clip = false,
    padding = '',
  } = $props();

  const display = $derived(
    value === null || value === undefined || value === '—' || Number.isNaN(value) ? '—' : `${value}${unit}`
  );
  const styleVars = $derived([
    valueSize ? `--stat-value-size: ${valueSize}` : '',
    footerSize ? `--stat-footer-size: ${footerSize}` : '',
  ].filter(Boolean).join('; '));
</script>

<Tile
  {label} {accent} {span} {dim} {hideLabel} {accessibleLabel} {fill} {clip}
  {padding} {styleVars} statTile={true}
  centerBody={centerContent}
>
  <div
    class="stat-content"
    data-stat-content-centered={centerContent ? '' : undefined}
  >
    <div class="stat" class:stacked={stackValue}>
      {#if iconName}
        <span class="state-icon" style="color: {iconColor}">
          <OhIcon icon={iconName} size={iconSize} />
        </span>
      {:else if icon}
        <span class="icon">{icon}</span>
      {/if}
      <span class="value">{display}</span>
    </div>
    {#if footer}
      <div class="footer" class:nowrap={footerNoWrap}>{footer}</div>
    {/if}
  </div>
</Tile>

<style>
  .stat-content {
    display: contents;
  }
  .stat {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .stat.stacked {
    flex-direction: column;
    justify-content: center;
    gap: 0.2rem;
    min-width: 0;
    text-align: center;
  }
  .icon {
    font-size: 1.1rem;
    line-height: 1;
  }
  .state-icon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    line-height: 1;
  }
  .value {

    font-size: var(--stat-value-size, 2.4rem);
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #e6edf3;
    white-space: nowrap;
  }
  .footer {
    margin-top: 0.35rem;
    font-size: var(--stat-footer-size, 0.8rem);
    color: #8b93a1;
  }
  .footer.nowrap {
    line-height: 1.1;
    letter-spacing: -0.025em;
    white-space: nowrap;
  }
</style>
