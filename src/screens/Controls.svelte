<script>
  import Toggle from '../lib/ui/Toggle.svelte';
  import Tile from '../lib/ui/Tile.svelte';
  import { CONTROL_CATALOG } from '../lib/controls/catalog.js';
  import { colors } from '../lib/ui/tokens.js';
  import { items, thingStatuses } from '../lib/openhab/index.js';
  import { VERIFIED_CAPABILITIES } from '../lib/controls/controlState.js';
  import { CURRENT_RELEASE_MODE } from '../lib/releaseMode.js';

  let { releaseMode = CURRENT_RELEASE_MODE, capabilities = VERIFIED_CAPABILITIES } = $props();

  function providerFor(control) {
    return control.providerThingUid ? $thingStatuses[control.providerThingUid] ?? null : null;
  }

  // Owner busy/transition, derived honestly from the NightLoadOverride_Result
  // item: an accepted/running result with no terminal yet means a transition is
  // in flight, so the owned loads and the override policy must not be commanded.
  // If the item can't prove a transition, don't block — the owner rule itself
  // serializes and denies 'busy', which the client surfaces verbatim.
  const ownerTransitioning = $derived.by(() => {
    const raw = $items.NightLoadOverride_Result;
    if (typeof raw !== 'string' || !raw) return false;
    try {
      const status = String(JSON.parse(raw)?.status ?? '').toLowerCase();
      return status === 'accepted' || status === 'running';
    } catch {
      return false;
    }
  });
</script>

<div class="controls-grid" data-controls-layout>
  <section class="cell" aria-label="Lights">
    <Tile label="Lights" accent={colors.temperature}>
      <div class="control-stack four">
        <Toggle control={CONTROL_CATALOG.living1} {releaseMode} providerStatus={providerFor(CONTROL_CATALOG.living1)} />
        <Toggle control={CONTROL_CATALOG.living2} {releaseMode} providerStatus={providerFor(CONTROL_CATALOG.living2)} />
        <Toggle control={CONTROL_CATALOG.living3} {releaseMode} providerStatus={providerFor(CONTROL_CATALOG.living3)} />
        <Toggle control={CONTROL_CATALOG.circadian} {releaseMode} />
      </div>
    </Tile>
  </section>

  <section class="cell" aria-label="Household loads">
    <Tile label="Household Loads" accent={colors.solar}>
      <div class="control-stack four">
        <Toggle control={CONTROL_CATALOG.dishwasher} {releaseMode} {capabilities} {ownerTransitioning} providerStatus={providerFor(CONTROL_CATALOG.dishwasher)} />
        <Toggle control={CONTROL_CATALOG.shureflo} {releaseMode} {capabilities} {ownerTransitioning} providerStatus={providerFor(CONTROL_CATALOG.shureflo)} />
        <Toggle control={CONTROL_CATALOG.goatCam} {releaseMode} {capabilities} {ownerTransitioning} providerStatus={providerFor(CONTROL_CATALOG.goatCam)} />
        <Toggle control={CONTROL_CATALOG.feedOnce} {releaseMode} {capabilities} providerStatus={providerFor(CONTROL_CATALOG.feedOnce)} onColor={colors.advisory} />
      </div>
    </Tile>
  </section>

  <section class="cell" aria-label="Water and policy">
    <Tile label="Water &amp; Policy" accent={colors.water}>
      <div class="control-stack two">
        <Toggle control={CONTROL_CATALOG.circulation} {releaseMode} {capabilities} providerStatus={providerFor(CONTROL_CATALOG.circulation)} onColor={colors.water} />
        <Toggle control={CONTROL_CATALOG.override} {releaseMode} {capabilities} {ownerTransitioning} onColor={colors.advisory} />
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
