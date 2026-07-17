<script>
  // Task 3.2 — Controls screen: the household switch board, moved off Home
  // (Home stays a data-only dashboard) onto its own 5th nav tab. Pure
  // composition of the existing Toggle primitive (press-and-hold confirm +
  // NULL-safe binding already live in Toggle.svelte) grouped into labeled
  // sections via Tile.
  import Toggle from '../lib/ui/Toggle.svelte';
  import Tile from '../lib/ui/Tile.svelte';
  import { colors } from '../lib/ui/tokens.js';
</script>

<div class="controls-grid">
  <div class="cell">
    <Tile label="Lights" accent={colors.temperature}>
      <div class="toggle-stack">
        <Toggle item="living_room_1_Switch" label="Living Room 1" />
        <Toggle item="living_room_2_Switch" label="Living Room 2" />
        <Toggle item="LED_living_room_1_Switch" label="LED Strip" />
        <Toggle item="LivingRoomCircadian_Enable" label="Circadian" />
      </div>
    </Tile>
  </div>

  <div class="cell">
    <Tile label="Appliances &amp; Outlets" accent={colors.solar}>
      <div class="toggle-stack">
        <Toggle item="Dish_Washer_Power" label="Dishwasher" />
        <Toggle item="ShurefloPump_Power" label="Shureflo Pump" />
        <Toggle item="Goat_Plugs_Outlet1_Switch" label="Goat Cam" />
        <Toggle item="Goat_Plugs_Outlet2_Switch" label="Goat Feeder" />
      </div>
    </Tile>
  </div>

  <div class="cell">
    <Tile label="Water &amp; Overrides" accent={colors.water}>
      <div class="toggle-stack">
        <div class="toggle-with-caption">
          <Toggle item="SouthOutlet_Outlet2_Switch" label="Fountain / Greywater Pump" onColor={colors.water} />
          <div class="caption">manual override &middot; auto-managed</div>
        </div>
        <Toggle item="OverrideSwitch" label="Override" onColor={colors.advisory} />
      </div>
    </Tile>
  </div>
</div>

<style>
  .controls-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    align-content: start;
    gap: 0.75rem;
  }
  .cell {
    min-width: 0;
  }
  .cell :global(.tile) {
    height: 100%;
  }
  .toggle-stack {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .toggle-with-caption {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .caption {
    font-size: 0.68rem;
    color: #8b93a1;
    padding: 0 0.1rem;
  }
</style>
