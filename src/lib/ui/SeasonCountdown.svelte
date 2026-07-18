<script>
  import { onDestroy, onMount } from 'svelte';
  import { nextSeasonEvent } from './homeCardState.js';

  const REFRESH_MS = 60 * 60 * 1000;
  let now = $state(new Date());
  let refreshTimer;

  const label = $derived(nextSeasonEvent(now)?.label ?? 'Season unavailable');

  onMount(() => {
    refreshTimer = setInterval(() => {
      now = new Date();
    }, REFRESH_MS);
  });

  onDestroy(() => {
    clearInterval(refreshTimer);
  });
</script>

<div class="sm-row sm-season" role="status" aria-live="polite" title={label}>{label}</div>

<style>
  .sm-row {
    display: block;
    width: 100%;
    min-width: 0;
    max-width: 100%;
    overflow: hidden;
    color: #8b93a1;
    font-size: 0.86rem;
    line-height: 1.15;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
