<script>
  import { onMount } from 'svelte';
  import Shell from './lib/ui/Shell.svelte';
  import { currentRoute } from './routes.js';
  import { initOpenhab } from './lib/openhab/index.js';
  import { loadConfig } from './lib/config.js';

  onMount(async () => {
    initOpenhab(await loadConfig());
  });

  // Real screens (Home/Energy/Weather/Earthship) are filled in during
  // Phases 2.3–6. These are router-driven placeholders only.
</script>

<Shell>
  {#if $currentRoute === 'home'}
    <div>Home screen (Task 2.3)</div>
  {:else if $currentRoute === 'energy'}
    <div>Energy screen (Task 2.3+)</div>
  {:else if $currentRoute === 'weather'}
    <div>Weather screen (Task 2.3+)</div>
  {:else if $currentRoute === 'earthship'}
    <div>Earthship screen (Task 2.3+)</div>
  {/if}
</Shell>
