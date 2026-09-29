<script>
  import { onMount } from 'svelte';
  import { items, connection } from '../lib/openhab/index.js';
  import { SHADE_COUNT, SHADE_GROUPS, SHADE_SLOTS, SHADE_VIEWS, shadeGroupPresentation, shadePresentation } from '../lib/shades/catalog.js';

  const shadeTints = ['#63889a', '#78876d', '#807591', '#947e68', '#6b8590'];

  let viewIndex = $state(0);
  let nowMs = $state(Date.now());
  const view = $derived(SHADE_VIEWS[viewIndex]);
  const rooms = $derived(SHADE_GROUPS.filter((room) => view.rooms.includes(room.id)));
  const mapped = $derived(SHADE_SLOTS.filter((slot) => slot.positionItem && slot.availabilityItem && slot.stateItem).length);
  const previewMode = $derived(mapped === 0);
  let previewOpen = $state(Object.fromEntries(SHADE_SLOTS.map((slot) => [slot.number, 50])));
  let sharedPreviewConnected = $state(false);
  let previewWrites = Promise.resolve();
  let activeTouch = null;
  let recentTouchCommit = null;
  let pressedAction = $state('');
  let pressedTimer;
  const touchEventGuardMs = 150;

  onMount(() => {
    const timer = setInterval(() => nowMs = Date.now(), 60_000);
    if (!previewMode) return () => clearInterval(timer);
    const stream = new EventSource('/api/shades-preview/events');
    stream.onopen = () => sharedPreviewConnected = true;
    stream.onerror = () => sharedPreviewConnected = false;
    stream.onmessage = (event) => {
      let snapshot;
      try { snapshot = JSON.parse(event.data); } catch { return; }
      if (!Array.isArray(snapshot?.positions) || snapshot.positions.length !== SHADE_COUNT
          || !snapshot.positions.every((position) => Number.isInteger(position) && position >= 0 && position <= 100)) return;
      previewOpen = Object.fromEntries(snapshot.positions.map((position, index) => [index + 1, position]));
    };
    return () => { clearInterval(timer); clearTimeout(pressedTimer); stream.close(); };
  });

  function previewGroupOpen(slots) {
    const first = previewOpen[slots[0]?.number];
    return slots.length && slots.every((slot) => previewOpen[slot.number] === first) ? first : null;
  }

  function setPreviewPercent(slots, percent) {
    if (!previewMode) return;
    if (!Number.isInteger(percent) || percent < 0 || percent > 100) return;
    for (const slot of slots) previewOpen[slot.number] = percent;
  }

  function publishPreview(slots, percent) {
    if (!previewMode || !Number.isInteger(percent)) return;
    const body = JSON.stringify({ slots: slots.map((slot) => slot.number), openPercent: percent });
    previewWrites = previewWrites.catch(() => {}).then(() => fetch('/api/shades-preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
    })).then((response) => { if (!response.ok) sharedPreviewConnected = false; })
      .catch(() => { sharedPreviewConnected = false; });
  }

  function previewButton(slots, percent, key) {
    setPreviewPercent(slots, percent);
    publishPreview(slots, percent);
    pressedAction = key;
    clearTimeout(pressedTimer);
    pressedTimer = setTimeout(() => pressedAction = '', 450);
  }

  function setPreview(slots, event) {
    if (activeTouch?.element === event.currentTarget
        || (recentTouchCommit?.element === event.currentTarget && Date.now() - recentTouchCommit.at < touchEventGuardMs)) return;
    setPreviewPercent(slots, Number(event.currentTarget.value));
  }

  function commitPreview(slots, event) {
    if (activeTouch?.element === event.currentTarget
        || (recentTouchCommit?.element === event.currentTarget && Date.now() - recentTouchCommit.at < touchEventGuardMs)) return;
    publishPreview(slots, Number(event.currentTarget.value));
  }

  function updateTouchPreview(slots, event) {
    const element = event.currentTarget;
    const bounds = element.getBoundingClientRect();
    if (bounds.height <= 0) return;
    const percent = Math.max(0, Math.min(100, Math.round(100 * (bounds.bottom - event.clientY) / bounds.height)));
    element.value = String(percent);
    setPreviewPercent(slots, percent);
    if (activeTouch) {
      activeTouch.percent = percent;
      if (activeTouch.frame) cancelAnimationFrame(activeTouch.frame);
      const touch = activeTouch;
      touch.frame = requestAnimationFrame(() => {
        if (activeTouch === touch) element.value = String(touch.percent);
      });
    }
  }

  function startTouchPreview(slots, event) {
    if (!previewMode || !['touch', 'pen'].includes(event.pointerType) || activeTouch) return;
    activeTouch = { element: event.currentTarget, pointerId: event.pointerId, percent: null, frame: null };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    updateTouchPreview(slots, event);
  }

  function moveTouchPreview(slots, event) {
    if (activeTouch?.element !== event.currentTarget || activeTouch.pointerId !== event.pointerId) return;
    event.preventDefault();
    updateTouchPreview(slots, event);
  }

  function endTouchPreview(slots, event) {
    if (activeTouch?.element !== event.currentTarget || activeTouch.pointerId !== event.pointerId) return;
    event.preventDefault();
    if (event.type === 'pointerup') updateTouchPreview(slots, event);
    const percent = activeTouch.percent;
    const element = event.currentTarget;
    if (activeTouch.frame) cancelAnimationFrame(activeTouch.frame);
    activeTouch = null;
    recentTouchCommit = { element, at: Date.now() };
    if (percent !== null) {
      element.value = String(percent);
      requestAnimationFrame(() => {
        if (activeTouch?.element !== element) element.value = String(percent);
      });
      publishPreview(slots, percent);
    }
  }

  const reporting = $derived(SHADE_SLOTS.filter((slot) => shadePresentation(slot, $items, $connection, nowMs).state === 'reported').length);
  const allDisplay = $derived(shadeGroupPresentation(SHADE_SLOTS, $items, $connection, nowMs));
  const allOpen = $derived(previewMode ? previewGroupOpen(SHADE_SLOTS) : allDisplay.openPercent);
</script>

<div class="shades-page" data-shades-page>
  <header class="page-heading">
    <div>
      <h1>Window shades</h1>
      <p>{SHADE_COUNT} planned · {mapped} mapped · {reporting} reporting</p>
    </div>
    <div class="release-state" role="status">{previewMode ? sharedPreviewConnected ? 'Shared preview only · no shade commands' : 'Local preview only · no shade commands' : 'Hardware not commissioned · movement disabled'}</div>
  </header>

  <div class="page-selector" aria-label="Shade views">
    <div class="selector-actions">
      {#each SHADE_VIEWS as option, index (option.id)}
        <button type="button" class:active={viewIndex === index} aria-pressed={viewIndex === index} onclick={() => viewIndex = index}>{option.label}</button>
      {/each}
    </div>
    <div class="all-actions" aria-label="All shade controls">
      <span>All {SHADE_COUNT} shades</span>
      <button type="button" class:pressed={pressedAction === 'all-open'} disabled={!previewMode} title={previewMode ? 'Preview only; no shade command' : 'Movement remains disabled until commissioning'} onclick={() => previewButton(SHADE_SLOTS, 100, 'all-open')}>Open all</button>
      <button type="button" class:pressed={pressedAction === 'all-close'} disabled={!previewMode} title={previewMode ? 'Preview only; no shade command' : 'Movement remains disabled until commissioning'} onclick={() => previewButton(SHADE_SLOTS, 0, 'all-close')}>Close all</button>
    </div>
  </div>

  <div class="shades-layout">
    <article class="shade-card master-card group-card" aria-label={`All ${SHADE_COUNT} shades: ${previewMode ? 'Local preview' : allDisplay.label}`}>
      <div class="card-top"><span class="shade-number">ALL</span></div>
      <div class="card-name">{SHADE_COUNT} shades</div>
      <div class="position-row">
        <span class="position-value">{allOpen === null ? '—' : `${allOpen}%`}</span>
        <span class="position-caption">{previewMode ? allOpen === null ? 'mixed' : 'preview' : allDisplay.state === 'mixed' ? 'mixed' : 'open'}</span>
      </div>
      <div class="window-control" class:unknown={!previewMode && allOpen === null} class:mixed={previewMode && allOpen === null} style:--closed-percent={`${allOpen === null ? 0 : 100 - allOpen}%`}>
        <div class="window-glass" aria-hidden="true"><div class="shade-fabric"></div></div>
        <input type="range" min="0" max="100" step="1" value={allOpen ?? 50} disabled={!previewMode}
          oninput={(event) => setPreview(SHADE_SLOTS, event)}
          onchange={(event) => commitPreview(SHADE_SLOTS, event)}
          onpointerdown={(event) => startTouchPreview(SHADE_SLOTS, event)}
          onpointermove={(event) => moveTouchPreview(SHADE_SLOTS, event)}
          onpointerup={(event) => endTouchPreview(SHADE_SLOTS, event)}
          onpointercancel={(event) => endTouchPreview(SHADE_SLOTS, event)}
          aria-label={`All ${SHADE_COUNT} shades ${previewMode ? 'local preview percent open' : 'percent open; movement disabled until commissioning'}`}
          aria-valuetext={previewMode && allOpen === null ? 'Mixed preview positions; adjust to set all' : `${allOpen ?? 0}% open${previewMode ? ' in local preview' : ''}`} />
      </div>
    </article>
    <div class="zones" aria-label="{view.label} shade zones">
      {#each rooms as room (room.id)}
      {@const cards = SHADE_SLOTS.filter((slot) => slot.room === room.id)}
      {@const groupDisplay = shadeGroupPresentation(cards, $items, $connection, nowMs)}
      {@const groupOpen = previewMode ? previewGroupOpen(cards) : groupDisplay.openPercent}
      <section class="zone" aria-label="{room.label} shades">
        <div class="zone-heading">
          <div class="zone-title"><h2>{room.label}</h2><span>{cards.length} shades</span><span class="sensor-evidence">{room.temperatureRole === 'unavailable' ? 'Zone temperature pending' : room.temperatureRole === 'hallway_proxy' ? 'Hallway temperature proxy' : 'Hallway temperature reference'}</span></div>
          <div class="zone-actions" aria-label="{room.label} controls">
            <button type="button" class:pressed={pressedAction === `${room.id}-open`} disabled={!previewMode} title={previewMode ? 'Preview only; no shade command' : 'Movement remains disabled until commissioning'} onclick={() => previewButton(cards, 100, `${room.id}-open`)}>Open {room.label}</button>
            <button type="button" class:pressed={pressedAction === `${room.id}-close`} disabled={!previewMode} title={previewMode ? 'Preview only; no shade command' : 'Movement remains disabled until commissioning'} onclick={() => previewButton(cards, 0, `${room.id}-close`)}>Close {room.label}</button>
          </div>
        </div>
        <div class="shade-grid" style:--columns={cards.length + 1}>
          <article class="shade-card group-card" aria-label="{room.label} group: {previewMode ? 'Local preview' : groupDisplay.label}">
            <div class="card-top">
              <span class="shade-number">ZONE</span>
            </div>
            <div class="card-name">All {cards.length}</div>
            <div class="position-row">
              <span class="position-value">{groupOpen === null ? '—' : `${groupOpen}%`}</span>
              <span class="position-caption">{previewMode ? groupOpen === null ? 'mixed' : 'preview' : groupDisplay.state === 'mixed' ? 'mixed' : 'open'}</span>
            </div>
            <div class="window-control" class:unknown={!previewMode && groupOpen === null} class:mixed={previewMode && groupOpen === null} style:--closed-percent={`${groupOpen === null ? 0 : 100 - groupOpen}%`}>
              <div class="window-glass" aria-hidden="true"><div class="shade-fabric"></div></div>
              <input type="range" min="0" max="100" step="1" value={groupOpen ?? 50} disabled={!previewMode}
                oninput={(event) => setPreview(cards, event)}
                onchange={(event) => commitPreview(cards, event)}
                onpointerdown={(event) => startTouchPreview(cards, event)}
                onpointermove={(event) => moveTouchPreview(cards, event)}
                onpointerup={(event) => endTouchPreview(cards, event)}
                onpointercancel={(event) => endTouchPreview(cards, event)}
                aria-label="{room.label} group {previewMode ? 'local preview percent open' : 'percent open; movement disabled until commissioning'}"
                aria-valuetext={previewMode && groupOpen === null ? 'Mixed preview positions; adjust to set group' : `${groupOpen ?? 0}% open${previewMode ? ' in local preview' : ''}`} />
            </div>
          </article>
          {#each cards as slot (slot.number)}
            {@const display = shadePresentation(slot, $items, $connection, nowMs)}
            {@const openPercent = previewMode ? previewOpen[slot.number] : display.openPercent}
            <article class="shade-card" class:reported={!previewMode && display.state === 'reported'} style:--shade-tint={shadeTints[(slot.number - 1) % shadeTints.length]} aria-label={`${slot.label}: ${previewMode ? 'Local preview' : display.label}`}>
              <div class="card-top">
                <span class="shade-number">{String(slot.number).padStart(2, '0')}</span>
                <span class="shade-status" class:online={!previewMode && display.state === 'reported'}>{previewMode ? 'PREVIEW' : display.state === 'reported' ? 'REPORT' : 'PENDING'}</span>
              </div>
              <div class="position-row">
                <span class="position-value">{openPercent === undefined ? '—' : `${openPercent}%`}</span>
                <span class="position-caption">{previewMode ? 'preview' : 'open'}</span>
              </div>
              <div class="window-control" class:unknown={openPercent === undefined} style:--closed-percent={`${openPercent === undefined ? 0 : 100 - openPercent}%`}>
                <div class="window-glass" aria-hidden="true"><div class="shade-fabric"></div></div>
                <input type="range" min="0" max="100" step="1" value={openPercent ?? 0} disabled={!previewMode}
                  oninput={(event) => setPreview([slot], event)}
                  onchange={(event) => commitPreview([slot], event)}
                  onpointerdown={(event) => startTouchPreview([slot], event)}
                  onpointermove={(event) => moveTouchPreview([slot], event)}
                  onpointerup={(event) => endTouchPreview([slot], event)}
                  onpointercancel={(event) => endTouchPreview([slot], event)}
                  aria-label="{slot.label} {previewMode ? 'local preview percent open' : 'percent open; movement disabled until commissioning'}"
                  aria-valuetext={`${openPercent ?? 0}% open${previewMode ? ' in local preview' : ''}`} />
              </div>
            </article>
          {/each}
        </div>
      </section>
      {/each}
    </div>
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
  .selector-actions button { min-height: 36px; padding: 0 .65rem; border: 1px solid #647e91; border-radius: .35rem; color: #d8e6ed; background: #263b4a; font: inherit; font-size: .79rem; cursor: pointer; white-space: nowrap; }
  .selector-actions button.active { color: #f5fbfd; border-color: #9fc8d6; background: #375568; }
  .selector-actions button:focus-visible { outline: 2px solid #9fc8e5; outline-offset: 2px; }
  .all-actions, .zone-actions { display: flex; align-items: center; gap: .38rem; }
  .all-actions span { color: #9aa7b8; font-size: .72rem; margin-right: .2rem; white-space: nowrap; }
  .all-actions button, .zone-actions button { min-height: 34px; border: 1px solid #7891a1; border-radius: .35rem; background: #2d4554; color: #f0f7fa; font: inherit; font-size: .72rem; font-weight: 600; padding: 0 .55rem; white-space: nowrap; }
  .all-actions button:not(:disabled):hover, .zone-actions button:not(:disabled):hover { background: #38576a; }
  .all-actions button:disabled, .zone-actions button:disabled { opacity: .58; cursor: not-allowed; }
  .shades-layout { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: .5rem; min-width: 0; min-height: 0; overflow: hidden; }
  .zones { display: grid; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: .55rem; min-width: 0; min-height: 0; overflow: hidden; }
  .zone { display: grid; grid-template-rows: 34px minmax(0, 1fr); gap: .25rem; min-width: 0; min-height: 0; overflow: hidden; }
  .zone-heading { display: flex; align-items: center; justify-content: space-between; gap: .6rem; min-width: 0; }
  .zone-title { display: flex; align-items: baseline; gap: .48rem; }
  h2 { margin: 0; font-size: .96rem; font-weight: 650; }
  .zone-title span { color: #91a1b2; font-size: .7rem; }
  .zone-title .sensor-evidence { color: #75889b; }
  .shade-grid { display: grid; grid-template-columns: repeat(var(--columns), minmax(0, 56px)); grid-template-rows: minmax(0, 1fr); justify-content: space-evenly; align-items: center; gap: .3rem; min-width: 0; min-height: 0; overflow: hidden; }
  .shade-card { display: flex; flex-direction: column; height: 100%; min-width: 0; min-height: 0; border: 1px solid #283342; border-radius: .48rem; background: #111821; padding: .5rem .2rem; box-sizing: border-box; overflow: hidden; }
  .shade-card:not(.group-card) { border-color: color-mix(in srgb, var(--shade-tint) 44%, #283342); background: linear-gradient(180deg, color-mix(in srgb, var(--shade-tint) 12%, #111821), #111821); }
  .shade-card.reported { border-color: #5296a8; }
  .shade-card:focus-within { border-color: #8cc8d8; box-shadow: inset 0 0 0 1px #4b8290; }
  .shade-card:has(input:active) { border-color: #a9e3ed; background: #1b2e38; }
  .shade-card:has(input:active) .position-value { color: #b6f0f7; }
  .group-card { border-color: #58748a; background: #1c2d39; }
  .master-card { background: #223643; }
  .card-top, .position-row { display: flex; align-items: baseline; justify-content: space-between; gap: .2rem; min-width: 0; }
  .shade-number { color: #6f8397; font-size: .7rem; font-weight: 650; letter-spacing: .08em; }
  .shade-status { width: 6px; height: 6px; flex: none; border-radius: 50%; background: #8f9cac; font-size: 0; }
  .shade-status.online { background: #79c1cd; }
  .card-name { min-width: 0; font-size: .64rem; font-weight: 600; line-height: 1.15; white-space: nowrap; }
  .position-row { flex-direction: column; align-items: flex-start; gap: .1rem; }
  .position-value { color: #edf3f8; font-size: 1rem; line-height: 1; font-weight: 600; white-space: nowrap; }
  .position-caption { color: #9aa7b8; font-size: .62rem; }
  .window-control { position: relative; display: flex; flex: 1 1 auto; align-items: center; justify-content: flex-start; min-height: 72px; padding-top: .35rem; }
  .window-glass { position: relative; width: 18px; height: 100%; margin-left: 3px; flex: none; border: 2px solid #7890a4; background: linear-gradient(180deg, #233e4a, #1b313d); box-sizing: border-box; overflow: hidden; }
  .window-glass::after { content: ''; position: absolute; inset: 0; border: 2px solid #23313c; pointer-events: none; }
  .shade-fabric { width: 100%; height: var(--closed-percent); background: repeating-linear-gradient(180deg, #8b9aa3 0, #8b9aa3 7px, #778791 8px); }
  .window-control.unknown .window-glass { border-color: #3c4b59; background: #1b2732; }
  .window-control.unknown .shade-fabric { display: none; }
  .window-control.mixed .window-glass { background: repeating-linear-gradient(135deg, #20313f 0, #20313f 8px, #304355 8px, #304355 16px); }
  .window-control.mixed .shade-fabric { display: none; }
  .window-control input[type='range'] { position: absolute; top: .35rem; left: 0; width: 100%; height: calc(100% - .35rem); margin: 0; padding: 0; box-sizing: border-box; writing-mode: vertical-lr; direction: rtl; accent-color: #78b8c8; cursor: not-allowed; touch-action: none; }
  .master-card { padding: .5rem .3rem; }
  .master-card .position-value { font-size: 1.12rem; }
  .window-control input[type='range']:disabled { opacity: .68; }
  .window-control input[type='range']:not(:disabled) { cursor: ns-resize; }
  .window-control input[type='range']:active { accent-color: #b6f0f7; }
  .all-actions button:not(:disabled):active, .zone-actions button:not(:disabled):active,
  .all-actions button.pressed, .zone-actions button.pressed { border-color: #c1edf5; background: #527b8b; color: #fff; box-shadow: inset 0 0 0 1px #a9e3ed; }
  .window-control.unknown input[type='range'] { opacity: .27; }
  .window-control.unknown input[type='range']::-webkit-slider-thumb { opacity: 0; }
  .window-control.unknown input[type='range']::-moz-range-thumb { opacity: 0; }
  @media (max-width: 899px) and (min-width: 700px) {
    .shades-page { gap: .3rem; }
    .page-heading { min-height: 44px; }
    .page-selector { min-height: 34px; }
    .selector-actions button { min-height: 32px; }
    .all-actions button { min-height: 32px; }
    .zones { gap: .35rem; }
    .shade-grid { grid-template-columns: repeat(var(--columns), minmax(0, 48px)); gap: .2rem; }
    .shade-card { padding: .2rem .15rem; }
    .shade-grid .position-value { font-size: .8rem; letter-spacing: -.02em; }
    .window-control { min-height: 72px; }
    .window-glass { width: 16px; }
  }
  @media (max-width: 899px) and (min-width: 700px) and (min-height: 541px) and (max-height: 700px) {
    .shades-page { grid-template-rows: auto auto auto; overflow-y: auto; }
    .shades-layout, .zones, .zone, .shade-grid { overflow: visible; }
    .shades-layout, .zones { min-height: max-content; }
    .shades-layout { height: calc(496px + .35rem); }
    .zones { grid-template-rows: repeat(2, 248px); }
    .zone { min-height: 248px; }
  }
  @media (max-height: 540px) { .shades-page { grid-template-rows: auto auto auto; overflow-y: auto; } .shades-layout { min-height: max-content; overflow: visible; } .zones { grid-template-rows: repeat(2, auto); min-height: max-content; overflow: visible; } .zone { grid-template-rows: auto auto; min-height: max-content; overflow: visible; } .shade-grid { grid-template-rows: auto; min-height: 190px; overflow: visible; } .shade-card { min-height: 190px; } }
  @media (max-width: 699px) { .shades-page { overflow-y: auto; } .shades-layout { grid-template-columns: minmax(0, 1fr); overflow: visible; } .master-card { min-height: 155px; } .master-card .window-control { min-height: 95px; } .zones { grid-template-rows: auto; overflow: visible; } .zone { min-height: 0; grid-template-rows: auto auto; overflow: visible; } .shade-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); grid-template-rows: auto; overflow: visible; } .shade-card { min-height: 190px; } .page-selector { align-items: flex-start; flex-direction: column; gap: .4rem; } .page-heading { align-items: flex-start; } }
  @media (max-width: 520px) { .page-heading { flex-direction: column; gap: .4rem; } .release-state { text-align: left; } .shade-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
