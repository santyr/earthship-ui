<script>
  import { onMount } from 'svelte';
  import { items, connection } from '../lib/openhab/index.js';
  import { SHADE_COUNT, SHADE_GROUPS, SHADE_SLOTS, SHADE_VIEWS, shadeGroupPresentation, shadePresentation } from '../lib/shades/catalog.js';

  let viewIndex = $state(0);
  let nowMs = $state(Date.now());
  onMount(() => {
    const timer = setInterval(() => nowMs = Date.now(), 60_000);
    return () => clearInterval(timer);
  });
  const view = $derived(SHADE_VIEWS[viewIndex]);
  const rooms = $derived(SHADE_GROUPS.filter((room) => view.rooms.includes(room.id)));
  const mapped = $derived(SHADE_SLOTS.filter((slot) => slot.positionItem && slot.availabilityItem && slot.stateItem).length);
  const reporting = $derived(SHADE_SLOTS.filter((slot) => shadePresentation(slot, $items, $connection, nowMs).state === 'reported').length);
</script>

<div class="shades-page" data-shades-page>
  <header class="page-heading">
    <div>
      <h1>Window shades</h1>
      <p>{SHADE_COUNT} planned · {mapped} mapped · {reporting} reporting</p>
    </div>
    <div class="release-state" role="status">Hardware not commissioned · movement disabled</div>
  </header>

  <div class="page-selector" aria-label="Shade views">
    <div class="selector-actions">
      {#each SHADE_VIEWS as option, index (option.id)}
        <button type="button" class:active={viewIndex === index} aria-pressed={viewIndex === index} onclick={() => viewIndex = index}>{option.label}</button>
      {/each}
    </div>
    <div class="all-actions" aria-label="All shade controls">
      <span>All {SHADE_COUNT} shades</span>
      <button type="button" disabled title="Movement remains disabled until commissioning">Open all</button>
      <button type="button" disabled title="Movement remains disabled until commissioning">Close all</button>
    </div>
  </div>

  <div class="zones" aria-label="{view.label} shade zones">
    {#each rooms as room (room.id)}
      {@const cards = SHADE_SLOTS.filter((slot) => slot.room === room.id)}
      {@const groupDisplay = shadeGroupPresentation(cards, $items, $connection, nowMs)}
      <section class="zone" aria-label="{room.label} shades">
        <div class="zone-heading">
          <div class="zone-title"><h2>{room.label}</h2><span>{cards.length} shades</span><span class="sensor-evidence">{room.temperatureRole === 'unavailable' ? 'Zone temperature pending' : room.temperatureRole === 'hallway_proxy' ? 'Hallway temperature proxy' : 'Hallway temperature reference'}</span></div>
          <div class="zone-actions" aria-label="{room.label} controls">
            <button type="button" disabled title="Movement remains disabled until commissioning">Open {room.label}</button>
            <button type="button" disabled title="Movement remains disabled until commissioning">Close {room.label}</button>
          </div>
        </div>
        <div class="shade-grid" style:--columns={cards.length + 1}>
          <article class="shade-card group-card" aria-label="{room.label} group: {groupDisplay.label}">
            <div class="card-top">
              <span class="shade-number">ZONE</span>
            </div>
            <div class="card-name"><span>{room.label}</span><span>Group</span></div>
            <div class="position-row">
              <span class="position-value">{groupDisplay.openPercent === null ? '—' : `${groupDisplay.openPercent}%`}</span>
              <span class="position-caption">{groupDisplay.state === 'mixed' ? 'mixed' : 'open'}</span>
            </div>
            <div class="window-control" class:unknown={groupDisplay.openPercent === null} style:--closed-percent={`${groupDisplay.openPercent === null ? 0 : 100 - groupDisplay.openPercent}%`}>
              <div class="window-glass" aria-hidden="true"><div class="shade-fabric"></div></div>
              <input type="range" min="0" max="100" value={groupDisplay.openPercent ?? 0} disabled
                aria-label="{room.label} group percent open; movement disabled until commissioning" />
            </div>
          </article>
          {#each cards as slot (slot.number)}
            {@const display = shadePresentation(slot, $items, $connection, nowMs)}
            <article class="shade-card" class:reported={display.state === 'reported'} aria-label={`${slot.label}: ${display.label}`}>
              <div class="card-top">
                <span class="shade-number">{String(slot.number).padStart(2, '0')}</span>
                <span class="shade-status" class:online={display.state === 'reported'}>{display.state === 'reported' ? 'REPORT' : 'PENDING'}</span>
              </div>
              <div class="card-name"><span>{room.label}</span><span>Shade {String(slot.number).padStart(2, '0')}</span></div>
              <div class="position-row">
                <span class="position-value">{display.openPercent === undefined ? '—' : `${display.openPercent}%`}</span>
                <span class="position-caption">open</span>
              </div>
              <div class="window-control" class:unknown={display.openPercent === undefined} style:--closed-percent={`${display.openPercent === undefined ? 0 : 100 - display.openPercent}%`}>
                <div class="window-glass" aria-hidden="true"><div class="shade-fabric"></div></div>
                <input type="range" min="0" max="100" value={display.openPercent ?? 0} disabled
                  aria-label="{slot.label} percent open; movement disabled until commissioning" />
              </div>
            </article>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</div>

<style>
  .shades-page { display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: .48rem; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
  .page-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 54px; }
  h1 { margin: 0; font-size: 1.26rem; font-weight: 650; letter-spacing: .01em; }
  .page-heading p { margin: .18rem 0 0; color: #9aa7b8; font-size: .76rem; }
  .release-state { color: #d5b677; border: 1px solid #564529; background: #211b12; border-radius: .38rem; padding: .4rem .62rem; font-size: .7rem; letter-spacing: .02em; text-align: right; }
  .page-selector { display: flex; align-items: center; justify-content: space-between; gap: .6rem; min-height: 38px; }
  .selector-actions { display: flex; gap: .35rem; }
  .selector-actions button { min-height: 36px; padding: 0 .65rem; border: 1px solid #323d4d; border-radius: .35rem; color: #aeb9c8; background: #111823; font: inherit; font-size: .79rem; cursor: pointer; white-space: nowrap; }
  .selector-actions button.active { color: #e6edf3; border-color: #65819a; background: #1a2a38; }
  .selector-actions button:focus-visible { outline: 2px solid #9fc8e5; outline-offset: 2px; }
  .all-actions, .zone-actions { display: flex; align-items: center; gap: .38rem; }
  .all-actions span { color: #9aa7b8; font-size: .72rem; margin-right: .2rem; white-space: nowrap; }
  .all-actions button, .zone-actions button { min-height: 34px; border: 1px solid #3b4654; border-radius: .35rem; background: #1a222d; color: #aab5c1; font: inherit; font-size: .72rem; padding: 0 .55rem; white-space: nowrap; }
  .all-actions button:disabled, .zone-actions button:disabled { opacity: .58; cursor: not-allowed; }
  .zones { display: grid; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: .55rem; min-width: 0; min-height: 0; overflow: hidden; }
  .zone { display: grid; grid-template-rows: 34px minmax(0, 1fr); gap: .25rem; min-width: 0; min-height: 0; overflow: hidden; }
  .zone-heading { display: flex; align-items: center; justify-content: space-between; gap: .6rem; min-width: 0; }
  .zone-title { display: flex; align-items: baseline; gap: .48rem; }
  h2 { margin: 0; font-size: .96rem; font-weight: 650; }
  .zone-title span { color: #91a1b2; font-size: .7rem; }
  .zone-title .sensor-evidence { color: #75889b; }
  .shade-grid { display: grid; grid-template-columns: repeat(var(--columns), minmax(0, 72px)); grid-template-rows: minmax(0, 1fr); justify-content: space-between; gap: .38rem; min-width: 0; min-height: 0; overflow: hidden; }
  .shade-card { display: flex; flex-direction: column; justify-content: space-between; min-width: 0; min-height: 0; border: 1px solid #283342; border-radius: .48rem; background: #111821; padding: .5rem .3rem; box-sizing: border-box; overflow: hidden; }
  .shade-card.reported { border-color: #315a6b; }
  .group-card { border-color: #41566b; background: #15212c; }
  .card-top, .position-row { display: flex; align-items: baseline; justify-content: space-between; gap: .2rem; min-width: 0; }
  .shade-number { color: #6f8397; font-size: .7rem; font-weight: 650; letter-spacing: .08em; }
  .shade-status { color: #8f9cac; font-size: .52rem; font-weight: 650; letter-spacing: .03em; }
  .shade-status.online { color: #79c1cd; }
  .card-name { display: flex; flex-direction: column; gap: .08rem; min-width: 0; font-size: .65rem; font-weight: 600; line-height: 1.15; }
  .card-name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card-name span:first-child { overflow: visible; text-overflow: clip; white-space: normal; }
  .card-name span + span { color: #b6c4d0; font-size: .65rem; font-weight: 500; }
  .position-value { flex: 0 0 auto; color: #edf3f8; font-size: 1.25rem; line-height: 1; font-weight: 600; }
  .position-caption { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: right; color: #9aa7b8; font-size: .65rem; }
  .window-control { display: flex; align-items: center; justify-content: center; gap: .25rem; min-height: 80px; padding-top: .15rem; }
  .window-glass { position: relative; width: 26px; height: 72px; flex: none; border: 2px solid #7890a4; background: linear-gradient(180deg, #233e4a, #1b313d); box-sizing: border-box; overflow: hidden; }
  .window-glass::after { content: ''; position: absolute; inset: 0; border: 2px solid #23313c; pointer-events: none; }
  .shade-fabric { width: 100%; height: var(--closed-percent); background: repeating-linear-gradient(180deg, #8b9aa3 0, #8b9aa3 7px, #778791 8px); }
  .window-control.unknown .window-glass { border-color: #3c4b59; background: #1b2732; }
  .window-control.unknown .shade-fabric { display: none; }
  .window-control input[type='range'] { width: 22px; height: 72px; margin: 0; padding: 0; writing-mode: vertical-lr; direction: rtl; accent-color: #78b8c8; cursor: not-allowed; }
  .window-control input[type='range']:disabled { opacity: .68; }
  .window-control.unknown input[type='range'] { opacity: .27; }
  .window-control.unknown input[type='range']::-webkit-slider-thumb { opacity: 0; }
  .window-control.unknown input[type='range']::-moz-range-thumb { opacity: 0; }
  @media (max-width: 899px) and (min-width: 700px) {
    .shade-grid { gap: .25rem; }
    .shade-card { padding: .35rem .2rem; }
    .window-control { gap: .15rem; min-height: 64px; }
    .window-glass { width: 22px; height: 61px; }
    .window-control input[type='range'] { width: 17px; height: 61px; }
  }
  @media (max-width: 749px) and (min-width: 700px) { .shade-status { width: 6px; height: 6px; flex: none; border-radius: 50%; background: #8f9cac; font-size: 0; } .shade-status.online { background: #79c1cd; } }
  @media (max-height: 540px) { .shades-page { grid-template-rows: auto auto auto; overflow-y: auto; } .zones { grid-template-rows: repeat(2, auto); min-height: max-content; overflow: visible; } .zone { grid-template-rows: auto auto; min-height: max-content; overflow: visible; } .shade-grid { grid-template-rows: auto; min-height: 155px; overflow: visible; } .shade-card { min-height: 155px; } }
  @media (max-width: 699px) { .shades-page { overflow-y: auto; } .zones { grid-template-rows: auto; overflow: visible; } .zone { min-height: 0; grid-template-rows: auto auto; overflow: visible; } .shade-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); grid-template-rows: auto; overflow: visible; } .shade-card { min-height: 155px; } .page-selector { align-items: flex-start; flex-direction: column; gap: .4rem; } .page-heading { align-items: flex-start; } }
  @media (max-width: 520px) { .page-heading { flex-direction: column; gap: .4rem; } .release-state { text-align: left; } .shade-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
