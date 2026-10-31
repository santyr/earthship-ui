<script>
  // Fixed top strip: Home date / compact clock elsewhere, alert summary, and
  // connection lamp. The alert region never changes the header height.
  import { currentRoute } from '../../routes.js';
  import Clock from './Clock.svelte';
  import { connection } from '../openhab/index.js';
  import HeaderAlerts from './HeaderAlerts.svelte';
  import DecisionRecommendations from './DecisionRecommendations.svelte';

  const badge = $derived.by(() => {
    const c = $connection;
    if (c === 'live') return { color: '#22c55e', text: 'live' };
    if (c === 'offline') return { color: '#ef4444', text: 'offline' };
    return { color: '#eab308', text: c || 'connecting' }; // stale / connecting
  });
</script>

<header class="header" class:home={$currentRoute === 'home'} style="height: 44px; min-height: 44px; max-height: 44px;">
  {#if $currentRoute === 'home'}
    <Clock showTime={false} />
  {:else}
    <Clock />
  {/if}
  <div class="suggestion-slot"><DecisionRecommendations header /></div>
  <HeaderAlerts />
  <div class="badge" role="img" aria-label="openHAB connection: {badge.text}" title="openHAB connection: {badge.text}">
    <span class="dot" style="background: {badge.color}"></span>
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0 0.75rem;
    border-bottom: 1px solid #1c2230;
    background: #0b0e14;
    height: 44px;
    min-height: 44px;
    max-height: 44px;
    box-sizing: border-box;
    flex-shrink: 0;
    overflow: visible;
  }
  .suggestion-slot { flex: 1 1 auto; min-width: 0; align-self: stretch; display: flex; }
  .badge {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    color: #8b93a1;
  }
  .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    flex-shrink: 0;
  }
  @media (max-width: 600px) {
    .header.home :global(.suggestion-slot) { min-width: 4rem; }
    .header.home :global(.header-summary) { overflow: hidden; }
    .header.home :global(.header-label) {
      flex: 0 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .header.home :global(.header-summary .summary-action),
    .header.home :global(.header-summary .provisional-label),
    .header.home :global(.header-summary .expired-label) { display: none; }
    .header.home :global(.header-summary > span:last-child) { flex-shrink: 0; }
  }
</style>
