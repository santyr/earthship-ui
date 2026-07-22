<script>
  import { onMount } from 'svelte';
  import Shell from './lib/ui/Shell.svelte';
  import Home from './screens/Home.svelte';
  import Energy from './screens/Energy.svelte';
  import Weather from './screens/Weather.svelte';
  import Earthship from './screens/Earthship.svelte';
  import Controls from './screens/Controls.svelte';
  import ChartModal from './lib/ui/ChartModal.svelte';
  import WeatherDetailModal from './lib/ui/WeatherDetailModal.svelte';
  import { currentRoute } from './routes.js';
  import { initOpenhab } from './lib/openhab/index.js';
  import { startStalenessMonitor } from './lib/alerts/alertStore.js';
  import { loadConfig } from './lib/config.js';

  onMount(() => {
    loadConfig().then((config) => initOpenhab(config));
    // Item-staleness alerts: periodic check that essential telemetry is
    // still flowing; the returned stop() is onMount's cleanup.
    return startStalenessMonitor();
  });

  // Home (Task 3.1), Energy (Task 4.1), Weather (Task 5.1), and Earthship
  // (Task 6.1) are live. Controls (Task 3.2) is the live household switch
  // board, moved off Home so Home stays a data-only dashboard.
</script>

<Shell>
  {#if $currentRoute === 'home'}
    <Home />
  {:else if $currentRoute === 'energy'}
    <Energy />
  {:else if $currentRoute === 'weather'}
    <Weather />
  {:else if $currentRoute === 'earthship'}
    <Earthship />
  {:else if $currentRoute === 'controls'}
    <Controls />
  {/if}
</Shell>

<ChartModal />
<WeatherDetailModal />
