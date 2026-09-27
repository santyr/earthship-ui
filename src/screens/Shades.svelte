<script>
  import { onMount } from 'svelte';
  import { items, connection } from '../lib/openhab/index.js';
  import { SHADE_SLOTS, SHADES_PER_PAGE, shadePresentation } from '../lib/shades/catalog.js';

  let page = $state(0);
  let nowMs = $state(Date.now());
  onMount(() => {
    const timer = setInterval(() => nowMs = Date.now(), 60_000);
    return () => clearInterval(timer);
  });
  const cards = $derived(SHADE_SLOTS.slice(page * SHADES_PER_PAGE, (page + 1) * SHADES_PER_PAGE));
  const mapped = $derived(SHADE_SLOTS.filter((slot) => slot.positionItem && slot.availabilityItem && slot.stateItem).length);
  const reporting = $derived(SHADE_SLOTS.filter((slot) => shadePresentation(slot, $items, $connection, nowMs).state === 'reported').length);
</script>

<div class="shades-page" data-shades-page>
  <header class="page-heading">
    <div>
      <h1>Window shades</h1>
      <p>26 planned · {mapped} mapped · {reporting} reporting</p>
    </div>
    <div class="release-state" role="status">Adapter not commissioned · movement disabled</div>
  </header>

  <div class="page-selector" aria-label="Shade groups">
    <span class="selector-title">Individual shades</span>
    <div class="selector-actions">
      <button type="button" class:active={page === 0} aria-pressed={page === 0} onclick={() => page = 0}>01–13</button>
      <button type="button" class:active={page === 1} aria-pressed={page === 1} onclick={() => page = 1}>14–26</button>
    </div>
  </div>

  <div class="shade-grid" aria-label="Shades {page === 0 ? '1 through 13' : '14 through 26'}">
    {#each cards as slot (slot.number)}
      {@const display = shadePresentation(slot, $items, $connection, nowMs)}
      <article class="shade-card" class:reported={display.state === 'reported'} aria-label={`${slot.label}: ${display.label}`}>
        <div class="card-top">
          <span class="shade-number">{String(slot.number).padStart(2, '0')}</span>
          <span class="shade-status" class:online={display.state === 'reported'}>{display.state === 'reported' ? 'MOTOR REPORT' : 'UNAVAILABLE'}</span>
        </div>
        <div class="card-name">{slot.label}</div>
        <div class="position-row">
          <span class="position-value">{display.position === null ? '—' : `${display.position}%`}</span>
          <span class="position-caption">{display.label}</span>
        </div>
        <div class="position-track" aria-hidden="true"><span style:width={display.position === null ? '0%' : `${display.position}%`}></span></div>
      </article>
    {/each}
  </div>
</div>

<style>
  .shades-page { display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: .58rem; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
  .page-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 54px; }
  h1 { margin: 0; font-size: 1.26rem; font-weight: 650; letter-spacing: .01em; }
  .page-heading p { margin: .18rem 0 0; color: #9aa7b8; font-size: .76rem; }
  .release-state { color: #d5b677; border: 1px solid #564529; background: #211b12; border-radius: .38rem; padding: .4rem .62rem; font-size: .7rem; letter-spacing: .02em; text-align: right; }
  .page-selector { display: flex; align-items: center; justify-content: space-between; min-height: 38px; }
  .selector-title { color: #aeb9c8; font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .09em; }
  .selector-actions { display: flex; gap: .35rem; }
  .selector-actions button { min-width: 5rem; min-height: 36px; border: 1px solid #323d4d; border-radius: .35rem; color: #aeb9c8; background: #111823; font: inherit; font-size: .79rem; cursor: pointer; }
  .selector-actions button.active { color: #e6edf3; border-color: #65819a; background: #1a2a38; }
  .selector-actions button:focus-visible { outline: 2px solid #9fc8e5; outline-offset: 2px; }
  .shade-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); grid-template-rows: repeat(4, minmax(0, 1fr)); gap: .5rem; min-width: 0; min-height: 0; overflow: hidden; }
  .shade-card { display: flex; flex-direction: column; justify-content: space-between; min-width: 0; min-height: 0; border: 1px solid #283342; border-radius: .48rem; background: #111821; padding: .72rem .8rem .68rem; box-sizing: border-box; overflow: hidden; }
  .shade-card.reported { border-color: #315a6b; }
  .card-top, .position-row { display: flex; align-items: baseline; justify-content: space-between; gap: .4rem; min-width: 0; }
  .shade-number { color: #6f8397; font-size: .7rem; font-weight: 650; letter-spacing: .08em; }
  .shade-status { color: #8f9cac; font-size: .57rem; font-weight: 650; letter-spacing: .09em; }
  .shade-status.online { color: #79c1cd; }
  .card-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 1rem; font-weight: 600; }
  .position-value { flex: 0 0 auto; color: #edf3f8; font-size: 1.45rem; line-height: 1; font-weight: 600; }
  .position-caption { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: right; color: #9aa7b8; font-size: .7rem; }
  .position-track { height: 3px; width: 100%; background: #2a3745; border-radius: 3px; overflow: hidden; }
  .position-track span { display: block; height: 100%; background: #78b8c8; }
  @media (max-width: 899px) { .shades-page { overflow-y: auto; } .shade-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: auto; overflow: visible; } .shade-card { min-height: 118px; } .page-heading { align-items: flex-start; } }
  @media (max-width: 520px) { .page-heading { flex-direction: column; gap: .4rem; } .release-state { text-align: left; } .shade-grid { grid-template-columns: 1fr; } }
</style>
