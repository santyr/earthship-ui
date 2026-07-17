<script>
  // Task 6.1 — Earthship console: the passive-thermal loop and greywater
  // circulation, last of the five screens. South Glazing (Shelly_HT1, the
  // solar-gain wall) -> Room Air (WS2902A indoor console) -> North Mass
  // (WH31E ch-193, earth-bermed wall, the house's heat "state of charge").
  // Mirrors the dark-console aesthetic (Tile chrome, tokens.colors,
  // click-to-chart via openChart) established on Home/Energy/Weather.
  import Tile from '../lib/ui/Tile.svelte';
  import ThermalLoop from '../lib/ui/ThermalLoop.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { items, num, fmt } from '../lib/openhab';
  import { openChart } from '../lib/ui/chartStore.js';

  function onKeyActivate(e, fn) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  }

  // ---- Zone temps (South Glazing -> Room Air -> North Mass) ----------------
  const glazingTemp = $derived(num($items.Shelly_HT1_Indoor_Temperature));
  const roomTemp = $derived(num($items.AmbientWeatherWS2902A_IndoorSensor_Temperature));
  const massTemp = $derived(num($items.AmbientWeatherWS2902A_WH31E_193_Temperature));

  function openZonesChart() {
    openChart({
      title: 'Thermal Loop — Zone Temps (24h)',
      series: [
        { name: 'Shelly_HT1_Indoor_Temperature', color: '#f59e0b', label: 'South Glazing' },
        { name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', color: '#e6edf3', label: 'Room Air' },
        { name: 'AmbientWeatherWS2902A_WH31E_193_Temperature', color: '#c2703d', label: 'North Mass' },
      ],
      hours: 24,
    });
  }

  // ---- Thermal Mass — the house's heat "state of charge" -------------------
  // Sign convention: delta = mass - room. Positive => mass is warmer than the
  // room, i.e. it is discharging stored heat INTO the room (typically
  // overnight). Negative => mass is cooler, absorbing heat FROM the room
  // (typically daytime charging). Same convention ThermalLoop.svelte uses
  // for its room<->mass arrow.
  const massDelta = $derived(massTemp === null || roomTemp === null ? null : massTemp - roomTemp);
  const EQUILIBRIUM_EPS = 0.3;
  function massDeltaText(d) {
    if (d === null) return '—';
    const r = Math.round(d * 10) / 10;
    if (Math.abs(r) < EQUILIBRIUM_EPS) return 'equilibrium';
    const sign = r > 0 ? '+' : '−';
    const abs = Math.abs(r).toFixed(1);
    return r > 0 ? `${sign}${abs}°F, discharging into room` : `${sign}${abs}°F, absorbing`;
  }
  const massDeltaColor = $derived(
    massDelta === null
      ? colors.label
      : massDelta > EQUILIBRIUM_EPS
        ? '#f59e0b'
        : massDelta < -EQUILIBRIUM_EPS
          ? '#3b82f6'
          : colors.label
  );
  function openMassChart() {
    openChart({
      title: 'Thermal Mass vs Room Air (24h)',
      series: [
        { name: 'AmbientWeatherWS2902A_WH31E_193_Temperature', color: '#c2703d', label: 'North Mass' },
        { name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', color: '#e6edf3', label: 'Room Air' },
      ],
      hours: 24,
    });
  }

  // ---- Thermal Buffering — passive-envelope quality metric ------------------
  // outdoor 24h swing ÷ indoor 24h swing. Guarded against divide-by-near-zero:
  // an indoor swing under 0.5°F (a very well-buffered/stable day) reports a
  // flat "≥20×" floor instead of an exploding or NaN ratio.
  const MIN_INDOOR_SWING = 0.5;
  const bufferInfo = $derived.by(() => {
    const oHi = num($items.OutdoorTemp_24h_High);
    const oLo = num($items.OutdoorTemp_24h_Low);
    const iHi = num($items.IndoorTemp_24h_High);
    const iLo = num($items.IndoorTemp_24h_Low);
    if (oHi === null || oLo === null || iHi === null || iLo === null) {
      return { text: '—', color: colors.label };
    }
    const outdoorSwing = oHi - oLo;
    const indoorSwing = iHi - iLo;
    if (indoorSwing < MIN_INDOOR_SWING) {
      return { text: '≥20×', color: '#22c55e' }; // ≥20×
    }
    const ratio = outdoorSwing / indoorSwing;
    const color = ratio >= 8 ? '#22c55e' : ratio >= 4 ? '#eab308' : '#f97316';
    return { text: `${ratio.toFixed(1)}×`, color };
  });

  // ---- Thermal Advisory ------------------------------------------------------
  const advisoryParts = $derived(String($items.Thermal_Advisory || '').split('|'));
  const advisoryCode = $derived(advisoryParts[0] || 'none');
  const advisoryText = $derived(advisoryParts.slice(1).join('|'));
  const advisoryActive = $derived(
    advisoryCode && advisoryCode !== 'none' && advisoryCode !== 'NULL' && advisoryCode !== 'UNDEF'
  );
  const tomorrowHiLo = $derived(
    `H ${fmt($items.Forecast_Tomorrow_High, '°')} / L ${fmt($items.Forecast_Tomorrow_Low, '°')}`
  );

  // ---- Greywater — South planter aerobic circulation -------------------------
  const gwRunning = $derived($items.SouthOutlet_Outlet2_Switch === 'ON');

  function parseKV(raw) {
    if (!raw || raw === 'NULL' || raw === 'UNDEF') return {};
    const map = {};
    String(raw)
      .split(',')
      .forEach((part) => {
        const eq = part.indexOf('=');
        if (eq === -1) return;
        map[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
      });
    return map;
  }
  function prettify(s) {
    if (!s) return '';
    return String(s).replace(/_/g, ' ');
  }
  function minsToText(v) {
    const n = num(v);
    if (n === null || n < 0) return null;
    if (n < 60) return `${Math.round(n)}m`;
    const h = Math.floor(n / 60);
    const m = Math.round(n % 60);
    return `${h}h ${m}m`;
  }
  const gwStatusText = $derived.by(() => {
    const kv = parseKV($items.SouthOutlet_AutoStatus);
    if (!kv.reason) return '—';
    let text = prettify(kv.reason);
    const fb = minsToText(kv.fallbackInMin);
    if (fb) text += ` · fallback in ${fb}`;
    return text;
  });

  function agoText(iso) {
    if (!iso || iso === 'NULL' || iso === 'UNDEF') return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    const diffMs = Date.now() - d.getTime();
    if (diffMs < 0) return '—';
    const min = diffMs / 60000;
    if (min < 60) return `${Math.round(min)} m ago`;
    const hr = min / 60;
    if (hr < 24) return `${Math.round(hr)} h ago`;
    return `${Math.round(hr / 24)} d ago`;
  }
  const gwLastAgo = $derived(agoText($items.SouthOutlet_LastAutoRun));

  // ---- Zone humidity ---------------------------------------------------------
  const humidityZones = $derived([
    { label: 'South Glazing', value: $items.Shelly_HT1_Atmospheric_Humidity },
    { label: 'Room Air', value: $items.AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity },
    { label: 'North Mass', value: $items.AmbientWeatherWS2902A_WH31E_193_RelativeHumidity },
  ]);
</script>

<div class="earthship-grid">
  <div class="cell advisory-cell">
    <Tile label="Thermal Advisory" accent={advisoryActive ? colors.advisory : colors.label}>
      <div class="advisory-body">
        <div class="advisory-main">
          <span class="advisory-dot" class:active={advisoryActive}></span>
          <span class="advisory-text" class:active={advisoryActive}>
            {advisoryActive ? advisoryText || '—' : 'All good'}
          </span>
        </div>
        <div class="advisory-footer">Tomorrow {tomorrowHiLo}</div>
      </div>
    </Tile>
  </div>

  <div class="cell loop-cell">
    <Tile label="Passive Thermal Loop" accent={colors.temperature}>
      <ThermalLoop glazing={glazingTemp} room={roomTemp} mass={massTemp} onZoneClick={openZonesChart} />
    </Tile>
  </div>

  <div
    class="cell mass-cell clickable"
    role="button"
    tabindex="0"
    onclick={openMassChart}
    onkeydown={(e) => onKeyActivate(e, openMassChart)}
  >
    <Tile label="Thermal Mass" accent="#c2703d">
      <div class="mass-body">
        <div class="mass-temp">{fmt($items.AmbientWeatherWS2902A_WH31E_193_Temperature, '°')}</div>
        <div class="mass-caption">heat state-of-charge</div>
        <div class="mass-delta" style="color: {massDeltaColor}">{massDeltaText(massDelta)}</div>
      </div>
    </Tile>
  </div>

  <div class="cell buffering-cell">
    <Tile label="Thermal Buffering" accent={bufferInfo.color}>
      <div class="buffering-body">
        <div class="buffering-value" style="color: {bufferInfo.color}">{bufferInfo.text}</div>
        <div class="buffering-caption">outdoor swing &divide; indoor swing</div>
      </div>
    </Tile>
  </div>

  <div class="cell greywater-cell">
    <Tile label="Greywater Circulation" accent={colors.water}>
      <div class="greywater-body">
        <div class="gw-top">
          <span class="gw-dot" class:active={gwRunning}></span>
          <div class="gw-text">
            <div class="gw-state">{gwRunning ? 'Running' : 'Idle'}</div>
            <div class="gw-status">{gwStatusText}</div>
          </div>
        </div>
        <div class="gw-footer">
          <span>last run {gwLastAgo}</span>
          <span class="gw-caption">South planter &middot; aerobic circulation</span>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell humidity-cell">
    <Tile label="Zone Humidity" accent={colors.water}>
      <div class="humidity-body">
        {#each humidityZones as z (z.label)}
          <div class="humidity-row">
            <span class="humidity-label">{z.label}</span>
            <span class="humidity-value">{fmt(z.value, '%')}</span>
          </div>
        {/each}
      </div>
    </Tile>
  </div>
</div>

<style>
  .earthship-grid {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows: auto minmax(14rem, 1fr) minmax(9rem, auto);
    grid-template-areas:
      'advisory advisory advisory advisory advisory advisory'
      'loop loop loop loop mass buffering'
      'greywater greywater greywater humidity humidity humidity';
    gap: 0.75rem;
    overflow-y: auto;
  }
  .cell {
    min-width: 0;
    min-height: 0;
  }
  .cell :global(.tile) {
    height: 100%;
  }
  .clickable {
    cursor: pointer;
  }
  .clickable:hover :global(.tile) {
    border-color: #333d4f;
  }
  .clickable:focus-visible :global(.tile) {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }

  .advisory-cell {
    grid-area: advisory;
  }
  .loop-cell {
    grid-area: loop;
  }
  .mass-cell {
    grid-area: mass;
  }
  .buffering-cell {
    grid-area: buffering;
  }
  .greywater-cell {
    grid-area: greywater;
  }
  .humidity-cell {
    grid-area: humidity;
  }

  /* ---- Advisory ---- */
  .advisory-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.3rem;
  }
  .advisory-main {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .advisory-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: #374151;
    flex-shrink: 0;
  }
  .advisory-dot.active {
    background: #f97316;
    box-shadow: 0 0 0.4rem #f97316;
  }
  .advisory-text {
    font-size: 0.95rem;
    font-weight: 600;
    color: #8b93a1;
  }
  .advisory-text.active {
    color: #f97316;
  }
  .advisory-footer {
    font-size: 0.72rem;
    color: #6b7280;
  }

  /* ---- Thermal loop ---- */
  .loop-cell :global(.tile-body) {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 0;
  }

  /* ---- Thermal Mass ---- */
  .mass-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.15rem;
  }
  .mass-temp {
    font-size: 2.2rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #c2703d;
  }
  .mass-caption {
    font-size: 0.68rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .mass-delta {
    margin-top: 0.3rem;
    font-size: 0.82rem;
    font-weight: 600;
  }

  /* ---- Thermal Buffering ---- */
  .buffering-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    height: 100%;
    gap: 0.25rem;
  }
  .buffering-value {
    font-size: 2.2rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .buffering-caption {
    font-size: 0.66rem;
    color: #6b7280;
  }

  /* ---- Greywater ---- */
  .greywater-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.5rem;
  }
  .gw-top {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .gw-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: #3b82f6;
    opacity: 0.4;
    flex-shrink: 0;
  }
  .gw-dot.active {
    opacity: 1;
    box-shadow: 0 0 0.4rem #3b82f6;
  }
  .gw-state {
    font-size: 0.95rem;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1.2;
  }
  .gw-status {
    font-size: 0.72rem;
    color: #8b93a1;
  }
  .gw-footer {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    font-size: 0.7rem;
    color: #6b7280;
  }
  .gw-caption {
    color: #4b5563;
  }

  /* ---- Zone humidity ---- */
  .humidity-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.35rem;
  }
  .humidity-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    font-size: 0.85rem;
  }
  .humidity-label {
    color: #8b93a1;
  }
  .humidity-value {
    color: #e6edf3;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
</style>
