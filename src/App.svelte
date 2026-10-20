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
  import { initOpenhab, stopOpenhab } from './lib/openhab/index.js';
  import { startStalenessMonitor } from './lib/alerts/alertStore.js';
  import { loadConfig } from './lib/config.js';

  onMount(() => {
    const lifetime = new AbortController();
    async function boot() {
      let delay = 2_000;
      while (!lifetime.signal.aborted) {
        try {
          const config = await loadConfig({ signal: lifetime.signal });
          if (lifetime.signal.aborted) return;
          await initOpenhab(config, { signal: lifetime.signal });
          return;
        } catch {
          if (lifetime.signal.aborted) return;
          await new Promise(resolve => {
            const done = () => {
              clearTimeout(timer);
              lifetime.signal.removeEventListener('abort', done);
              resolve();
            };
            const timer = setTimeout(done, delay);
            lifetime.signal.addEventListener('abort', done, { once: true });
          });
          delay = Math.min(delay * 2, 30_000);
        }
      }
    }
    void boot();
    const stopAlerts = startStalenessMonitor();
    return () => {
      lifetime.abort();
      stopOpenhab();
      stopAlerts();
    };
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
