<script>
  // Compact top strip: live clock/date, deterministic alert summary, and
  // connection lamp. The alert region never changes the header height.
  import { onMount, onDestroy } from 'svelte';
  import { connection } from '../openhab/index.js';
  import HeaderAlerts from './HeaderAlerts.svelte';

  let now = $state(new Date());
  let timer;

  onMount(() => {
    timer = setInterval(() => {
      now = new Date();
    }, 1000);
  });
  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  const timeText = $derived(
    now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
  );
  const dateText = $derived(now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }));

  const badge = $derived.by(() => {
    const c = $connection;
    if (c === 'live') return { color: '#22c55e', text: 'live' };
    if (c === 'offline') return { color: '#ef4444', text: 'offline' };
    return { color: '#eab308', text: c || 'connecting' }; // stale / connecting
  });
</script>

<header class="header" style="height: 44px; min-height: 44px; max-height: 44px;">
  <div class="clock">
    <span class="time">{timeText}</span>
    <span class="date">{dateText}</span>
  </div>
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
  .clock {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    font-variant-numeric: tabular-nums;
  }
  .time {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1;
  }
  .date {
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    color: #8b93a1;
  }
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
</style>
