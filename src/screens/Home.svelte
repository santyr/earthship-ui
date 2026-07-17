<script>
  // Task 2.3 — static Home console layout. ALL values below are hardcoded
  // sample data for the aesthetic sign-off; live binding to openHAB items
  // is the next task (Phase 3). Layout/typography/color are the things
  // pending operator sign-off on the M9 tablet at 1340x800.
  import Tile from '../lib/ui/Tile.svelte';
  import StatTile from '../lib/ui/StatTile.svelte';
  import Arc from '../lib/ui/Arc.svelte';
  import Sparkline from '../lib/ui/Sparkline.svelte';
  import CompassRose from '../lib/ui/CompassRose.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { socBands, runtimeText } from '../lib/openhab/values.js';

  // ---- Sample data (design doc "Home" tile list) ----
  const outdoor = {
    temp: 89,
    feels: 86,
    hi: 94,
    hiTime: '3:12p',
    lo: 61,
    loTime: '5:47a',
    condition: '☀', // sun glyph
    aqi: 24,
  };

  const battery = { soc: 55, current: -3.2, runtimeMin: 980, basis: 'bms' };
  const socColor = socBands(battery.soc);
  const battRuntime = runtimeText(battery.runtimeMin); // -> "16 h 20 m"
  const battIndicator =
    battery.current < 0
      ? { glyph: '▼', text: 'discharging' }
      : battery.current > 0
        ? { glyph: '▲', text: 'charging' }
        : { glyph: '●', text: 'idle' };

  const wind = { degrees: 135, speed: 6, gust: 11, maxToday: 18 };

  const rain = { today: 0.61, event: 0.61, week: 0.61, month: 0.61, rate: 0 };
  const rainFooter = `event ${rain.event}″ · wk ${rain.week}″ · mo ${rain.month}″ · rate ${rain.rate.toFixed(2)}″/hr`;

  const solar = { pvToday: 4.2, predicted: 6.8, currentW: 310, curtailed: false };

  const zones = [
    { label: 'Room', temp: 71, delta: 1 },
    { label: 'N.Wall', temp: 70, delta: -1 },
    { label: 'S.Glass', temp: 74, delta: 2 },
  ];

  const baro = { inHg: '30.06', trend: 'steady' };
  const baroSpark = Array.from({ length: 24 }, (_, i) => ({
    time: `${i}`,
    state: String(29.9 + 0.2 * Math.sin(i / 5)),
  }));

  const forecastToday = { label: 'Today', hi: 89, lo: 60, icon: '☀', pv: '6.9' };
  const forecastTomorrow = { label: 'Tomorrow', hi: 90, lo: 62, icon: '⛅', pv: '6.7' };
  const forecastDays = [
    { label: 'Sun', hi: 91, lo: 63, icon: '☀', pv: '6.9' },
    { label: 'Mon', hi: 88, lo: 61, icon: '⛅', pv: '6.2' },
    { label: 'Tue', hi: 85, lo: 59, icon: '\u{1f326}', pv: '5.1' },
    { label: 'Wed', hi: 87, lo: 60, icon: '☀', pv: '6.8' },
    { label: 'Thu', hi: 92, lo: 64, icon: '☀', pv: '7.0' },
  ];

  const sunMoon = { rise: '5:52a', set: '8:25p', moon: 'waxing crescent', daylight: '14h 30m' };

  const advisory = { active: true, text: 'Vent tonight — 90° tomorrow' };

  const greywater = { state: 'Idle', lastAgo: '17 h ago' };
</script>

<div class="home-grid">
  <div class="cell advisory-cell">
    <Tile label="Advisory" accent={colors.advisory}>
      <div class="advisory-body">
        <span class="advisory-dot"></span>
        <span class="advisory-text">{advisory.text}</span>
      </div>
    </Tile>
  </div>

  <div class="cell greywater-cell">
    <Tile label="Greywater" accent={colors.water}>
      <div class="greywater-body">
        <span class="gw-dot"></span>
        <div class="gw-text">
          <div class="gw-state">{greywater.state}</div>
          <div class="gw-last">last {greywater.lastAgo}</div>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell outdoor-cell">
    <Tile label="Outdoor" accent={colors.temperature}>
      <div class="outdoor-body">
        <div class="outdoor-main">
          <span class="cond-icon">{outdoor.condition}</span>
          <span class="big-temp">{outdoor.temp}&deg;</span>
          <span class="aqi-chip">AQI {outdoor.aqi}</span>
        </div>
        <div class="outdoor-sub">feels like {outdoor.feels}&deg;</div>
        <div class="outdoor-hilo">
          H {outdoor.hi}&deg; <span class="time">{outdoor.hiTime}</span>
          &nbsp;/&nbsp; L {outdoor.lo}&deg; <span class="time">{outdoor.loTime}</span>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell battery-cell">
    <Tile label="Battery" accent={socColor}>
      <div class="battery-body">
        <div class="battery-arc">
          <Arc value={battery.soc} color={socColor} label="SoC" sublabel="{battery.current} A" />
        </div>
        <div class="battery-meta">
          <span class="batt-indicator" style="color: {socColor}">{battIndicator.glyph} {battIndicator.text}</span>
          <span class="batt-runtime">{battRuntime} <em>({battery.basis})</em></span>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell wind-cell">
    <Tile label="Wind" accent={colors.wind}>
      <div class="wind-body">
        <div class="compass-cap">
          <CompassRose degrees={wind.degrees} speed={wind.speed} gust={wind.gust} />
        </div>
        <div class="wind-max">max today {wind.maxToday} mph</div>
      </div>
    </Tile>
  </div>

  <div class="cell baro-cell">
    <Tile label="Baro" accent={colors.label}>
      <div class="baro-body">
        <div class="baro-value">{baro.inHg} <span class="unit">inHg</span></div>
        <div class="baro-spark"><Sparkline data={baroSpark} color={colors.label} /></div>
        <div class="baro-trend">{baro.trend}</div>
      </div>
    </Tile>
  </div>

  <div class="cell rain-cell">
    <StatTile label="Rain" value={rain.today} unit="&#8243;" accent={colors.rain} footer={rainFooter} />
  </div>

  <div class="cell sunmoon-cell">
    <Tile label="Sun &amp; Moon" accent={colors.label}>
      <div class="sunmoon-body">
        <div class="sm-row">&uarr; {sunMoon.rise} &middot; &darr; {sunMoon.set}</div>
        <div class="sm-row">{sunMoon.moon}</div>
        <div class="sm-row">daylight {sunMoon.daylight}</div>
      </div>
    </Tile>
  </div>

  <div class="cell solar-cell">
    <Tile label="Solar" accent={colors.solar}>
      <div class="solar-body">
        <div class="solar-main">
          <span class="solar-value">{solar.pvToday}</span><span class="unit"> kWh</span>
        </div>
        <div class="solar-sub">of {solar.predicted} predicted</div>
        <div class="solar-current">{solar.currentW} W now</div>
        <div class="curtail-lamp">
          <span class="lamp-dot" class:active={solar.curtailed}></span>
          curtailment {solar.curtailed ? 'active' : 'idle'}
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell zones-cell">
    <Tile label="Zones" accent={colors.temperature}>
      <div class="zones-body">
        {#each zones as z (z.label)}
          <div class="zone-row">
            <span class="zone-label">{z.label}</span>
            <span class="zone-temp">{z.temp}&deg;</span>
            <span class="zone-delta" class:up={z.delta > 0} class:down={z.delta < 0}
              >{z.delta > 0 ? '▲' : z.delta < 0 ? '▼' : '—'}</span
            >
          </div>
        {/each}
      </div>
    </Tile>
  </div>

  <div class="cell forecast-cell">
    <Tile label="Forecast" accent={colors.forecast}>
      <div class="forecast-body">
        <div class="fc-day fc-emph">
          <div class="fc-label">{forecastToday.label}</div>
          <div class="fc-icon">{forecastToday.icon}</div>
          <div class="fc-hilo">{forecastToday.hi}/{forecastToday.lo}</div>
          <div class="fc-pv">PV ~{forecastToday.pv} kWh</div>
        </div>
        <div class="fc-day fc-emph">
          <div class="fc-label">{forecastTomorrow.label}</div>
          <div class="fc-icon">{forecastTomorrow.icon}</div>
          <div class="fc-hilo">{forecastTomorrow.hi}/{forecastTomorrow.lo}</div>
          <div class="fc-pv">PV ~{forecastTomorrow.pv} kWh</div>
        </div>
        {#each forecastDays as d (d.label)}
          <div class="fc-day">
            <div class="fc-label">{d.label}</div>
            <div class="fc-icon">{d.icon}</div>
            <div class="fc-hilo">{d.hi}/{d.lo}</div>
            <div class="fc-pv">~{d.pv}</div>
          </div>
        {/each}
      </div>
    </Tile>
  </div>
</div>

<style>
  .home-grid {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows: auto repeat(3, minmax(0, 1fr)) auto;
    grid-template-areas:
      'topbar topbar topbar topbar topbar greywater'
      'outdoor outdoor battery battery wind baro'
      'outdoor outdoor battery battery rain sunmoon'
      'outdoor outdoor battery battery solar zones'
      'forecast forecast forecast forecast forecast forecast';
    gap: 0.75rem;
  }
  .cell {
    min-width: 0;
    min-height: 0;
  }
  .cell :global(.tile) {
    height: 100%;
  }

  .advisory-cell {
    grid-area: topbar;
  }
  .greywater-cell {
    grid-area: greywater;
  }
  .outdoor-cell {
    grid-area: outdoor;
  }
  .battery-cell {
    grid-area: battery;
  }
  .wind-cell {
    grid-area: wind;
  }
  .baro-cell {
    grid-area: baro;
  }
  .rain-cell {
    grid-area: rain;
  }
  .sunmoon-cell {
    grid-area: sunmoon;
  }
  .solar-cell {
    grid-area: solar;
  }
  .zones-cell {
    grid-area: zones;
  }
  .forecast-cell {
    grid-area: forecast;
  }

  /* ---- Advisory ---- */
  .advisory-body {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: 100%;
  }
  .advisory-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: #f97316;
    flex-shrink: 0;
  }
  .advisory-text {
    font-size: 0.95rem;
    font-weight: 600;
    color: #f97316;
  }

  /* ---- Greywater ---- */
  .greywater-body {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: 100%;
  }
  .gw-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #3b82f6;
    opacity: 0.5;
    flex-shrink: 0;
  }
  .gw-state {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1.1;
  }
  .gw-last {
    font-size: 0.68rem;
    color: #8b93a1;
  }

  /* ---- Outdoor hero ---- */
  .outdoor-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.5rem;
  }
  .outdoor-main {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }
  .cond-icon {
    font-size: 2rem;
    line-height: 1;
  }
  .big-temp {
    font-size: 4.2rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #f59e0b;
  }
  .aqi-chip {
    margin-left: auto;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    background: #14351f;
    color: #22c55e;
    border-radius: 999px;
    padding: 0.2rem 0.6rem;
    align-self: flex-start;
  }
  .outdoor-sub {
    font-size: 1.1rem;
    color: #8b93a1;
  }
  .outdoor-hilo {
    font-size: 1rem;
    color: #c7cfd9;
  }
  .outdoor-hilo .time {
    color: #6b7280;
    font-size: 0.8rem;
  }

  /* ---- Battery hero ---- */
  .battery-body {
    display: flex;
    align-items: center;
    height: 100%;
    gap: 1rem;
  }
  .battery-arc {
    width: 60%;
    max-width: 14rem;
  }
  .battery-meta {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    font-size: 0.95rem;
  }
  .batt-indicator {
    font-weight: 600;
  }
  .batt-runtime {
    color: #c7cfd9;
  }
  .batt-runtime em {
    font-style: normal;
    color: #6b7280;
    font-size: 0.8rem;
  }

  /* ---- Wind ---- */
  .wind-body {
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 100%;
    justify-content: center;
    gap: 0.35rem;
  }
  .compass-cap {
    width: 100%;
    max-width: 7.5rem;
  }
  .wind-max {
    font-size: 0.72rem;
    color: #8b93a1;
  }

  /* ---- Baro ---- */
  .baro-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.25rem;
  }
  .baro-value {
    font-size: 1.3rem;
    font-weight: 600;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
  }
  .baro-value .unit {
    font-size: 0.7rem;
    color: #8b93a1;
  }
  .baro-spark {
    height: 2.2rem;
  }
  .baro-trend {
    font-size: 0.72rem;
    color: #8b93a1;
    text-transform: capitalize;
  }

  /* ---- Sun & Moon ---- */
  .sunmoon-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.3rem;
  }
  .sm-row {
    font-size: 0.82rem;
    color: #c7cfd9;
  }

  /* ---- Solar ---- */
  .solar-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.25rem;
  }
  .solar-main {
    font-size: 1.7rem;
    font-weight: 700;
    color: #eab308;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .solar-main .unit {
    font-size: 0.9rem;
    font-weight: 500;
    color: #8b93a1;
  }
  .solar-sub {
    font-size: 0.72rem;
    color: #8b93a1;
  }
  .solar-current {
    font-size: 0.82rem;
    color: #c7cfd9;
  }
  .curtail-lamp {
    margin-top: 0.15rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.68rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .lamp-dot {
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 50%;
    background: #374151;
  }
  .lamp-dot.active {
    background: #eab308;
  }

  /* ---- Zones ---- */
  .zones-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.3rem;
  }
  .zone-row {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    font-size: 0.82rem;
  }
  .zone-label {
    color: #8b93a1;
    flex: 1;
  }
  .zone-temp {
    color: #e6edf3;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .zone-delta.up {
    color: #f59e0b;
  }
  .zone-delta.down {
    color: #3b82f6;
  }

  /* ---- Forecast strip ---- */
  .forecast-body {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 0.5rem;
    height: 100%;
    align-items: center;
  }
  .fc-day {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.15rem;
  }
  .fc-label {
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    color: #8b93a1;
  }
  .fc-icon {
    font-size: 1.2rem;
    line-height: 1;
  }
  .fc-hilo {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
  }
  .fc-emph .fc-hilo {
    font-size: 1rem;
    color: #c4b5fd;
  }
  .fc-pv {
    font-size: 0.65rem;
    color: #6b7280;
  }
</style>
