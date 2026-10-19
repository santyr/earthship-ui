<script>
  import { onMount } from 'svelte';
  import Shell from './lib/ui/Shell.svelte';
  import Home from './screens/Home.svelte';
  import Energy from './screens/Energy.svelte';
  import Weather from './screens/Weather.svelte';
  import Earthship from './screens/Earthship.svelte';
  import Shades from './screens/Shades.svelte';
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

  // Home, Energy, Weather, Earthship, Shades, and Controls are routed here.
  // The Shades page remains read-only until the hardware is commissioned.
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
  {:else if $currentRoute === 'shades'}
    <Shades />
  {:else if $currentRoute === 'controls'}
    <Controls />
  {/if}
</Shell>

<ChartModal />
<WeatherDetailModal />
