<script>
  import { onDestroy, onMount } from 'svelte';
  import { items, itemUpdateEvidence, thingStatuses, connection } from '../openhab/store.js';
  import { nativeSeasonLabel } from '../weather/astroPresentation.js';

  let now = $state(Date.now());
  let refreshTimer;
  const label = $derived(nativeSeasonLabel({ states:$items, evidence:$itemUpdateEvidence,
    now:Math.max(now, Date.now()), connected:$connection === 'live', sunOnline:$thingStatuses['astro:sun:local']?.status === 'ONLINE' }));
  onMount(() => { refreshTimer = setInterval(() => { now = Date.now(); }, 30_000); });
  onDestroy(() => { clearInterval(refreshTimer); });
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
