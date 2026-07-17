<script>
  // Temporary primitives gallery for Task 2.1 visual verification.
  // Renders one of each console primitive with representative sample props.
  // Throwaway wiring — Task 2.2 restores the real App shell.
  import Tile from '../lib/ui/Tile.svelte';
  import StatTile from '../lib/ui/StatTile.svelte';
  import Arc from '../lib/ui/Arc.svelte';
  import Sparkline from '../lib/ui/Sparkline.svelte';
  import CompassRose from '../lib/ui/CompassRose.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { socBands } from '../lib/openhab/values.js';

  const sparkData = Array.from({ length: 24 }, (_, i) => ({
    time: `${i}:00`,
    state: String(60 + 15 * Math.sin(i / 3) + (Math.random() * 4 - 2)),
  }));

  const soc = 72;
</script>

<main class="gallery">
  <h1 class="gallery-title">Console Primitives Gallery</h1>

  <section class="grid">
    <Tile label="Plain tile" accent={colors.label}>
      <p style="color:#e6edf3">Bare Tile chrome — arbitrary content via slot.</p>
    </Tile>
    <Tile label="Dimmed tile" accent={colors.advisory} dim={true}>
      <p style="color:#e6edf3">dim=true lowers opacity (~0.5).</p>
    </Tile>
    <Tile label="Wide tile" accent={colors.forecast} span={2}>
      <p style="color:#e6edf3">span=2 spans two grid columns.</p>
    </Tile>

    <StatTile label="Outdoor Temp" value="89.8" unit="°F" accent={colors.temperature} footer="feels like 92°" />
    <StatTile label="Wind" value="12" unit=" mph" accent={colors.wind} footer="gusting 18 mph" />
    <StatTile label="Rainfall" value="0.4" unit=" in" accent={colors.rain} footer="last 24h" />
    <StatTile label="Solar" value="310" unit=" W" accent={colors.solar} footer="PV production" />
    <StatTile label="Forecast" value="Clear" accent={colors.forecast} footer="tonight" />
    <StatTile label="Advisory" value="—" accent={colors.advisory} footer="no active advisories" />
    <StatTile label="No data" value={null} accent={colors.label} footer="renders em-dash" />

    <Tile label="SoC Arc" accent={socBands(soc)}>
      <Arc value={soc} color={socBands(soc)} label="battery" sublabel="24.1 V" />
    </Tile>

    <Tile label="Sparkline" accent={colors.temperature}>
      <Sparkline data={sparkData} color={colors.temperature} />
    </Tile>

    <Tile label="Compass" accent={colors.wind}>
      <CompassRose degrees={135} speed={12} gust={18} />
    </Tile>
  </section>
</main>

<style>
  .gallery {
    padding: 1.5rem;
    max-width: 1340px;
    margin: 0 auto;
  }
  .gallery-title {
    font-size: 1.1rem;
    color: #8b93a1;
    margin-bottom: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
  }
  .grid :global(.tile) {
    min-height: 9rem;
  }
</style>
