<script>
  // Compact top strip: live clock/date, deterministic alert summary, and
  // connection lamp. The alert region never changes the header height.
  import { onMount, onDestroy } from 'svelte';
  import { connection, items, num } from '../openhab/index.js';

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

  const activeAlerts = $derived.by(() => {
    const alerts = [];
    const state = $connection || 'connecting';

    if (state === 'offline') alerts.push('openHAB offline');

    const soc = num($items.BMS_SOC);
    if (soc !== null && soc <= 12) alerts.push(`Battery critical · ${Math.round(soc)}%`);

    if (state !== 'live' && state !== 'offline') {
      alerts.push(`Connection ${state}`);
    }

    const thermal = String($items.Thermal_Advisory || 'none').split('|');
    const thermalCode = thermal[0];
    const thermalText = thermal.slice(1).join('|').trim();
    if (thermalCode === 'close_up_tomorrow') {
      alerts.push(thermalText || 'Close up tomorrow');
    }

    const aqi = num($items.Current_US_AQI);
    if (aqi !== null && aqi >= 101) alerts.push(`Air quality unhealthy · AQI ${Math.round(aqi)}`);

    if (thermalCode === 'vent_tonight') {
      alerts.push(thermalText || 'Vent tonight');
    } else if (thermalCode && !['none', 'NULL', 'UNDEF', 'close_up_tomorrow'].includes(thermalCode)) {
      alerts.push(thermalText || `Thermal advisory · ${thermalCode}`);
    }

    return alerts;
  });

  const alertSummary = $derived(
    activeAlerts.length === 0
      ? 'No active alerts'
      : `${activeAlerts[0]}${activeAlerts.length > 1 ? ` +${activeAlerts.length - 1}` : ''}`
  );
</script>

<header class="header">
  <div class="clock">
    <span class="time">{timeText}</span>
    <span class="date">{dateText}</span>
  </div>
  <div class="alerts" role="status" aria-live="polite" aria-label={alertSummary}>
    {#if activeAlerts.length > 0}
      <span class="alert-text">{activeAlerts[0]}</span>
      {#if activeAlerts.length > 1}
        <span class="alert-count">+{activeAlerts.length - 1}</span>
      {/if}
    {:else}
      <span class="sr-only">No active alerts</span>
    {/if}
  </div>
  <div class="badge" role="img" aria-label="openHAB connection: {badge.text}" title="openHAB connection: {badge.text}">
    <span class="dot" style="background: {badge.color}"></span>
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 0.9rem;
    border-bottom: 1px solid #1c2230;
    background: #0b0e14;
    height: 2.75rem;
    min-height: 2.75rem;
    box-sizing: border-box;
    flex-shrink: 0;
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
  .alerts {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.35rem;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: 0.72rem;
    font-weight: 600;
    color: #f59e0b;
  }
  .alert-text {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .alert-count {
    flex: 0 0 auto;
    color: #c7cfd9;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
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
