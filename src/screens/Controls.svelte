<script>
  import Toggle from '../lib/ui/Toggle.svelte';
  import Tile from '../lib/ui/Tile.svelte';
  import { CONTROL_CATALOG } from '../lib/controls/catalog.js';
  import { colors } from '../lib/ui/tokens.js';
</script>

<div class="controls-grid" data-controls-layout>
  <section class="cell" aria-label="Lights">
    <Tile label="Lights" accent={colors.temperature}>
      <div class="control-stack four">
        <Toggle control={CONTROL_CATALOG.living1} />
        <Toggle control={CONTROL_CATALOG.living2} />
        <Toggle control={CONTROL_CATALOG.living3} />
        <Toggle control={CONTROL_CATALOG.circadian} />
      </div>
    </Tile>
  </section>

  <section class="cell" aria-label="Household loads">
    <Tile label="Household Loads" accent={colors.solar}>
      <div class="control-stack four">
        <Toggle control={CONTROL_CATALOG.dishwasher} />
        <Toggle control={CONTROL_CATALOG.shureflo} />
        <Toggle control={CONTROL_CATALOG.goatCam} />
        <Toggle control={CONTROL_CATALOG.feedOnce} onColor={colors.advisory} />
      </div>
    </Tile>
  </section>

  <section class="cell" aria-label="Water and policy">
    <Tile label="Water &amp; Policy" accent={colors.water}>
      <div class="control-stack two">
        <Toggle control={CONTROL_CATALOG.circulation} onColor={colors.water} />
        <Toggle control={CONTROL_CATALOG.override} onColor={colors.advisory} />
      </div>
    </Tile>
  </section>
</div>

<style>
  .controls-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.72rem;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  .cell {
    min-width: 0;
    min-height: 0;
    height: 100%;
    overflow: hidden;
  }

  .cell :global(.tile) {
    height: 100%;
    overflow: hidden;
  }

  .cell :global(.tile-body) {
    overflow: hidden;
  }

  .control-stack {
    display: grid;
    gap: 0.52rem;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  .control-stack.four {
    grid-template-rows: repeat(4, minmax(0, 1fr));
  }

  .control-stack.two {
    grid-template-rows: repeat(2, minmax(0, 1fr));
  }

  @media (min-width: 1280px) and (max-height: 720px) {
    .controls-grid {
      gap: 0.6rem;
    }

    .control-stack {
      gap: 0.42rem;
    }

    .cell :global(.tile) {
      padding: 0.72rem;
    }
  }
</style>
