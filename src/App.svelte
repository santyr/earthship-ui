<script>
  import { onMount } from 'svelte';
  import { initOpenhab, items, connection, fmt } from './lib/openhab';
  import { loadConfig } from './lib/config.js';
  onMount(async () => { initOpenhab(await loadConfig()); });
</script>
<main class="p-8">
  <p class="text-sm text-neutral-500">connection: {$connection}</p>
  <h1 class="text-6xl font-bold" style="color:#f59e0b">
    {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°', 0)}
  </h1>
  <p class="text-2xl">SoC {fmt($items.BMS_SOC, '%', 0)} · PV {fmt($items.MPPT60_PV_Power, ' W', 0)}</p>
</main>
