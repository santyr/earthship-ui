<script>
  // Passive thermal loop diagram — four zones (North Mass -> Room Air ->
  // South Wall -> Outdoor) with live temps and delta-driven flow arrows. Pure
  // SVG, no
  // chart library (same pattern as Arc/CompassRose). NULL-safe throughout:
  // any zone temp may be missing and the arrows/labels degrade to neutral
  // gray rather than throwing.
  //
  // Sign convention (shared with the Thermal Mass card in Earthship.svelte):
  // the first two deltas are computed as "into room" positive —
  //   mass-room arrow: delta = mass - room (>0 => mass discharges into room)
  //   wall-room arrow: delta = wall - room (>0 => solar wall warms room)
  // Amber means inward gain and blue means heat leaving the room. The envelope
  // arrow uses delta = wall - outdoor: positive points outward (blue loss),
  // negative points inward (amber gain). Every arrow therefore points from the
  // warmer live temperature toward the cooler one.
  let {
    mass = null,
    room = null,
    wall = null,
    outdoor = null,
    onZoneClick = null,
  } = $props();

  const FLAT_EPS = 0.3; // °F — below this, treat as no net flow
  const MAX_SWING = 12; // °F — delta magnitude that maxes out arrow size

  const deltaMR = $derived(mass === null || room === null ? null : mass - room);
  const deltaWR = $derived(wall === null || room === null ? null : wall - room);
  const deltaWO = $derived(wall === null || outdoor === null ? null : wall - outdoor);

  function arrowInfo(delta, positiveColor = '#f59e0b', negativeColor = '#3b82f6') {
    if (delta === null || Math.abs(delta) < FLAT_EPS) {
      return { dir: 0, mag: 0, color: '#374151', marker: null };
    }
    const dir = delta > 0 ? 1 : -1;
    const mag = Math.max(0.15, Math.min(1, Math.abs(delta) / MAX_SWING));
    const color = dir === 1 ? positiveColor : negativeColor;
    const marker = color === '#f59e0b' ? 'url(#tl-head-amber)' : 'url(#tl-head-blue)';
    return { dir, mag, color, marker };
  }

  // Mass is left of the room, so positive into-room flow points right.
  const arrow1 = $derived(arrowInfo(deltaMR));
  // The south wall is right of the room, so positive into-room flow points left.
  const arrow2 = $derived(arrowInfo(deltaWR));
  // Wall warmer than outdoors means outward loss: rightward and blue. Outdoor
  // warmer than wall means inward gain: leftward and amber.
  const arrow3 = $derived(arrowInfo(deltaWO, '#3b82f6', '#f59e0b'));

  function fmtDeg(v) {
    return v === null || v === undefined ? '—' : `${Math.round(v)}°`;
  }

  function handleZoneKey(e) {
    if (!onZoneClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onZoneClick();
    }
  }

  // Precomputed arrow geometry (viewBox is a fixed 0 0 796 190). Rightward
  // arrows draw left->right with the arrowhead at the right end; leftward
  // arrows draw right->left with the arrowhead at the left end (a straight
  // swap of endpoints, not a CSS flip, so the marker orientation stays
  // correct without extra transforms).
  const ARROW1_LEFT = 158;
  const ARROW1_RIGHT = 218;
  const ARROW2_LEFT = 368;
  const ARROW2_RIGHT = 428;
  const ARROW3_LEFT = 578;
  const ARROW3_RIGHT = 638;
  const ARROW_Y = 95;

  function arrowPath(left, right, dirRightwardWhenPositive, dir) {
    if (dir === 0) return { x1: left, x2: right, hasHead: false };
    const rightward = dirRightwardWhenPositive ? dir === 1 : dir === -1;
    return rightward ? { x1: left, x2: right, hasHead: true } : { x1: right, x2: left, hasHead: true };
  }

  const a1 = $derived(arrowPath(ARROW1_LEFT, ARROW1_RIGHT, true, arrow1.dir));
  const a2 = $derived(arrowPath(ARROW2_LEFT, ARROW2_RIGHT, false, arrow2.dir));
  const a3 = $derived(arrowPath(ARROW3_LEFT, ARROW3_RIGHT, true, arrow3.dir));
</script>

<div class="thermal-loop">
  <svg viewBox="0 0 796 190" class="loop-svg" preserveAspectRatio="xMidYMid meet">
    <defs>
      <marker id="tl-head-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#f59e0b" />
      </marker>
      <marker id="tl-head-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#3b82f6" />
      </marker>
    </defs>

    <!-- Arrow: mass <-> room -->
    {#if a1.hasHead}
      <line
        x1={a1.x1}
        y1={ARROW_Y}
        x2={a1.x2}
        y2={ARROW_Y}
        stroke={arrow1.color}
        stroke-width={2 + arrow1.mag * 6}
        stroke-linecap="round"
        opacity={0.4 + arrow1.mag * 0.6}
        marker-end={arrow1.marker}
      />
    {:else}
      <line x1={ARROW1_LEFT} y1={ARROW_Y} x2={ARROW1_RIGHT} y2={ARROW_Y} stroke="#374151" stroke-width="2" stroke-linecap="round" />
    {/if}

    <!-- Arrow: room <-> wall -->
    {#if a2.hasHead}
      <line
        x1={a2.x1}
        y1={ARROW_Y}
        x2={a2.x2}
        y2={ARROW_Y}
        stroke={arrow2.color}
        stroke-width={2 + arrow2.mag * 6}
        stroke-linecap="round"
        opacity={0.4 + arrow2.mag * 0.6}
        marker-end={arrow2.marker}
      />
    {:else}
      <line x1={ARROW2_LEFT} y1={ARROW_Y} x2={ARROW2_RIGHT} y2={ARROW_Y} stroke="#374151" stroke-width="2" stroke-linecap="round" />
    {/if}

    <!-- Arrow: wall <-> outdoor -->
    {#if a3.hasHead}
      <line
        x1={a3.x1}
        y1={ARROW_Y}
        x2={a3.x2}
        y2={ARROW_Y}
        stroke={arrow3.color}
        stroke-width={2 + arrow3.mag * 6}
        stroke-linecap="round"
        opacity={0.4 + arrow3.mag * 0.6}
        marker-end={arrow3.marker}
      />
    {:else}
      <line x1={ARROW3_LEFT} y1={ARROW_Y} x2={ARROW3_RIGHT} y2={ARROW_Y} stroke="#374151" stroke-width="2" stroke-linecap="round" />
    {/if}

    <!-- Zone: North Mass -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <g
      class="zone-group"
      class:clickable={!!onZoneClick}
      role={onZoneClick ? 'button' : undefined}
      tabindex={onZoneClick ? 0 : undefined}
      onclick={onZoneClick}
      onkeydown={handleZoneKey}
    >
      <rect x="8" y="30" width="150" height="130" rx="14" fill="#161b24" stroke="#1c2230" stroke-width="1.5" />
      <text x="83" y="52" text-anchor="middle" class="zone-label">North Mass</text>
      <text x="83" y="98" text-anchor="middle" class="zone-temp" style="fill: #c2703d">{fmtDeg(mass)}</text>
      <text x="83" y="120" text-anchor="middle" class="zone-sub">thermal storage</text>
    </g>

    <!-- Zone: Room Air -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <g
      class="zone-group"
      class:clickable={!!onZoneClick}
      role={onZoneClick ? 'button' : undefined}
      tabindex={onZoneClick ? 0 : undefined}
      onclick={onZoneClick}
      onkeydown={handleZoneKey}
    >
      <rect x="218" y="30" width="150" height="130" rx="14" fill="#161b24" stroke="#1c2230" stroke-width="1.5" />
      <text x="293" y="52" text-anchor="middle" class="zone-label">Room Air</text>
      <text x="293" y="98" text-anchor="middle" class="zone-temp" style="fill: #e6edf3">{fmtDeg(room)}</text>
      <text x="293" y="120" text-anchor="middle" class="zone-sub">living space</text>
    </g>

    <!-- Zone: South Wall -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <g
      class="zone-group"
      class:clickable={!!onZoneClick}
      role={onZoneClick ? 'button' : undefined}
      tabindex={onZoneClick ? 0 : undefined}
      onclick={onZoneClick}
      onkeydown={handleZoneKey}
    >
      <rect x="428" y="30" width="150" height="130" rx="14" fill="#161b24" stroke="#1c2230" stroke-width="1.5" />
      <text x="503" y="52" text-anchor="middle" class="zone-label">South Wall</text>
      <text x="503" y="98" text-anchor="middle" class="zone-temp" style="fill: #f59e0b">{fmtDeg(wall)}</text>
      <text x="503" y="120" text-anchor="middle" class="zone-sub">solar wall</text>
    </g>

    <!-- Zone: Outdoor -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <g
      class="zone-group"
      class:clickable={!!onZoneClick}
      role={onZoneClick ? 'button' : undefined}
      tabindex={onZoneClick ? 0 : undefined}
      onclick={onZoneClick}
      onkeydown={handleZoneKey}
    >
      <rect x="638" y="30" width="150" height="130" rx="14" fill="#161b24" stroke="#1c2230" stroke-width="1.5" />
      <text x="713" y="52" text-anchor="middle" class="zone-label">Outdoor</text>
      <text x="713" y="98" text-anchor="middle" class="zone-temp" style="fill: #38bdf8">{fmtDeg(outdoor)}</text>
      <text x="713" y="120" text-anchor="middle" class="zone-sub">ambient air</text>
    </g>
  </svg>
</div>

<style>
  .thermal-loop {
    width: 100%;
    height: 100%;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .loop-svg {
    width: 100%;
    height: 100%;
  }
  .zone-group.clickable {
    cursor: pointer;
  }
  .zone-group.clickable:focus-visible rect {
    stroke: #3b82f6;
    stroke-width: 2;
  }
  .zone-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    fill: #8b93a1;
  }
  .zone-temp {
    font-size: 30px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .zone-sub {
    font-size: 11px;
    fill: #6b7280;
  }
</style>
