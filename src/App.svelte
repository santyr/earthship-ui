<script>
  import { onMount } from 'svelte';
  import Shell from './lib/ui/Shell.svelte';
  import Home from './screens/Home.svelte';
  import Controls from './screens/Controls.svelte';
  import ChartModal from './lib/ui/ChartModal.svelte';
  import { currentRoute } from './routes.js';
  import { initOpenhab } from './lib/openhab/index.js';
  import { loadConfig } from './lib/config.js';

  onMount(async () => {
    initOpenhab(await loadConfig());
  });

  // Home is the static (sample-data) console layout built in Task 2.3; live
  // binding is a later task. Energy/Weather/Earthship are filled in during
  // Phases 3–6 and remain router-driven placeholders for now. Controls
  // (Task 3.2) is the live household switch board, moved off Home so Home
  // stays a data-only dashboard.
</script>

<Shell>
  {#if $currentRoute === 'home'}
    <Home />
  {:else if $currentRoute === 'energy'}
    <div>Energy screen (Task 2.3+)</div>
  {:else if $currentRoute === 'weather'}
    <div>Weather screen (Task 2.3+)</div>
  {:else if $currentRoute === 'earthship'}
    <div>Earthship screen (Task 2.3+)</div>
  {:else if $currentRoute === 'controls'}
    <Controls />
  {/if}
</Shell>

<ChartModal />
