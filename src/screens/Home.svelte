<script>
  // Task 3.1 — LIVE dense Home console. Binds real openHAB items (Task 0.1-3.0
  // infra), renders real icons via OhIcon, and makes weather/battery/solar/
  // wind/rain/baro tiles clickable -> openChart(). Indoor added alongside
  // Outdoor per operator request. No controls row (Home is data-only; toggles
  // move to a separate Controls screen).
  import { onMount, onDestroy } from 'svelte';
  import Tile from '../lib/ui/Tile.svelte';
  import StatTile from '../lib/ui/StatTile.svelte';
  import Arc from '../lib/ui/Arc.svelte';
  import Sparkline from '../lib/ui/Sparkline.svelte';
  import CompassRose from '../lib/ui/CompassRose.svelte';
  import OhIcon from '../lib/ui/OhIcon.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { items, num, fmt, socBands, runtimeText, getClientOnce } from '../lib/openhab';
  import { openChart } from '../lib/ui/chartStore.js';

  // ---- History fetch helper for hero sparklines ----------------------------
  // getClientOnce() can briefly be null right at boot (initOpenhab() in
  // App.svelte's onMount hasn't resolved yet), so retry a few times instead
  // of giving up on the first miss.
  async function fetchHistorySafe(name, hours = 6) {
    for (let attempt = 0; attempt < 10; attempt++) {
      const client = getClientOnce();
      if (client) {
        const now = Date.now();
        const starttime = new Date(now - hours * 3600 * 1000).toISOString();
        const endtime = new Date(now).toISOString();
        try {
          return await client.getHistory(name, { starttime, endtime });
        } catch {
          return [];
        }
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    return [];
  }

  let outdoorSpark = $state([]);
  let battSpark = $state([]);
  let baroSpark = $state([]);
  let windGustMaxToday = $state(null);
  let loadToday = $state(null);

  // Same retry pattern as fetchHistorySafe, but with explicit start/end
  // (used for the "today so far" load-energy integration, which needs
  // local-midnight-to-now rather than a rolling N-hour window).
  async function fetchHistoryRange(name, starttime, endtime) {
    for (let attempt = 0; attempt < 10; attempt++) {
      const client = getClientOnce();
      if (client) {
        try {
          return await client.getHistory(name, { starttime, endtime });
        } catch {
          return [];
        }
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    return [];
  }

  // Trapezoidal integration of a W-vs-time series -> kWh. No dedicated
  // "load energy today" item exists on ConextGateway, so it's derived
  // client-side from the ACPowerValue history rather than guessing at an
  // unconfirmed item name.
  function integrateKWh(points) {
    if (!Array.isArray(points) || points.length === 0) return null;
    const pts = points
      .map((p) => ({ t: new Date(p.time).getTime(), w: num(p.state) }))
      .filter((p) => Number.isFinite(p.t) && p.w !== null)
      .sort((a, b) => a.t - b.t);
    if (pts.length < 2) return pts.length === 1 ? 0 : null;
    let wh = 0;
    for (let i = 1; i < pts.length; i++) {
      const dtSec = (pts[i].t - pts[i - 1].t) / 1000;
      if (dtSec <= 0) continue;
      wh += ((pts[i].w + pts[i - 1].w) / 2) * (dtSec / 3600);
    }
    return wh / 1000;
  }

  async function refreshLoadToday() {
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
    const data = await fetchHistoryRange('ConextGateway_ACPowerValue', midnight.toISOString(), now.toISOString());
    loadToday = integrateKWh(data);
  }

  // Refetched on mount AND on a 5-minute interval below, so the trend lines
  // on the always-on wall display stay current (tile numeric values already
  // update live via $items — this is only for the sparkline history).
  async function refreshOutdoorSpark() {
    outdoorSpark = await fetchHistorySafe('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', 6);
  }
  async function refreshBattSpark() {
    battSpark = await fetchHistorySafe('BMS_SOC', 6);
  }
  async function refreshBaroSpark() {
    baroSpark = await fetchHistorySafe('AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative', 6);
  }

  const SPARK_REFRESH_MS = 300000; // 5 minutes
  let sparkRefreshTimer;

  onMount(() => {
    refreshOutdoorSpark();
    refreshBattSpark();
    refreshBaroSpark();
    refreshLoadToday();
    // No dedicated "max wind today" item exists, so derive it from a 24h
    // gust history pull rather than inventing an item name.
    fetchHistorySafe('AmbientWeatherWS2902A_WindGust', 24).then((d) => {
      const vals = (d || []).map((p) => num(p.state)).filter((n) => n !== null);
      windGustMaxToday = vals.length ? Math.max(...vals) : null;
    });

    sparkRefreshTimer = setInterval(() => {
      refreshOutdoorSpark();
      refreshBattSpark();
      refreshBaroSpark();
      refreshLoadToday();
    }, SPARK_REFRESH_MS);
  });

  onDestroy(() => {
    if (sparkRefreshTimer) clearInterval(sparkRefreshTimer);
  });

  // ---- Small null-safe formatting helpers ----------------------------------
  function hasItem(name) {
    return Object.prototype.hasOwnProperty.call($items, name);
  }

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

  function formatTime(iso) {
    if (!iso || iso === 'NULL' || iso === 'UNDEF') return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }

  // Compact form for cramped tiles: "5:54 AM" -> "5:54a" (no space, single
  // lowercase letter) so it doesn't wrap in the narrow Sun & Moon tile.
  function formatTimeShort(iso) {
    const t = formatTime(iso);
    if (t === '—') return t;
    return t.replace(/\s?([AP])M$/i, (_, p) => p.toLowerCase());
  }

  function prettifyMoon(name) {
    if (!name || name === 'NULL' || name === 'UNDEF') return '—';
    return String(name)
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function daylightText(riseIso, setIso) {
    if (!riseIso || !setIso || riseIso === 'NULL' || setIso === 'NULL' || riseIso === 'UNDEF' || setIso === 'UNDEF')
      return '—';
    const r = new Date(riseIso);
    const s = new Date(setIso);
    if (Number.isNaN(r.getTime()) || Number.isNaN(s.getTime())) return '—';
    const diffMs = s - r;
    if (diffMs <= 0) return '—';
    const h = Math.floor(diffMs / 3600000);
    const m = Math.round((diffMs % 3600000) / 60000);
    return `${h}h ${m}m`;
  }

  function wmoEmoji(code) {
    const c = Number(code);
    if (Number.isNaN(c)) return '—';
    if (c === 0) return '☀️';
    if (c === 1 || c === 2) return '⛅';
    if (c === 3) return '☁️';
    if (c === 45 || c === 48) return '🌫️';
    if ([51, 53, 55, 56, 57].includes(c)) return '🌦️';
    if ([61, 63, 65, 66, 67, 80, 81, 82].includes(c)) return '🌧️';
    if ([71, 73, 75, 77, 85, 86].includes(c)) return '🌨️';
    if ([95, 96, 99].includes(c)) return '⛈️';
    return '—';
  }

  // Forecast_Daily_JSON already carries the correct label per entry (Today,
  // Sat, Sun, Mon, ...) in the `d` field — use it directly instead of
  // synthesizing "D3"/"D4" placeholders. Index 1 is shown as "Tomorrow" for
  // readability; everything else (including index 0's "Today") comes
  // straight from the feed.
  function dayLabel(i, dStr) {
    if (i === 1) return 'Tomorrow';
    if (!dStr || dStr === 'NULL' || dStr === 'UNDEF') return i === 0 ? 'Today' : `D${i + 1}`;
    return String(dStr);
  }

  function roundOrDash(v) {
    const n = num(v);
    return n === null ? '—' : Math.round(n);
  }

  function pvText(v) {
    const n = num(v);
    return n === null ? '—' : n.toFixed(1);
  }

  function onKeyActivate(e, fn) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  }

  // ---- Derived, per-tile values --------------------------------------------
  const advisoryParts = $derived(String($items.Thermal_Advisory || '').split('|'));
  const advisoryCode = $derived(advisoryParts[0] || 'none');
  const advisoryText = $derived(advisoryParts.slice(1).join('|'));
  const advisoryActive = $derived(
    advisoryCode && advisoryCode !== 'none' && advisoryCode !== 'NULL' && advisoryCode !== 'UNDEF'
  );

  const gwRunning = $derived($items.SouthOutlet_Outlet2_Switch === 'ON');
  const gwLastAgo = $derived(agoText($items.SouthOutlet_LastAutoRun));

  // ---- Power-flow strip (fills the topbar row when no advisory is active) --
  const NET_POS_COLOR = '#22c55e'; // green — producing surplus / net charging
  const NET_NEG_COLOR = '#f59e0b'; // amber — drawing down / net discharging

  function numFmt(n, unit = '', digits = 0) {
    return n === null || n === undefined ? '—' : n.toFixed(digits) + unit;
  }
  function signedFmt(n, unit = '', digits = 0) {
    if (n === null || n === undefined) return '—';
    const r = Number(Math.abs(n).toFixed(digits));
    const sign = n >= 0 ? '+' : '−';
    return `${sign}${r.toFixed(digits)}${unit}`;
  }

  const pvWatts = $derived(num($items.MPPT60_PV_Power));
  const loadWatts = $derived(num($items.ConextGateway_ACPowerValue));
  const battWatts = $derived.by(() => {
    const native = num($items.DCData_Native_Power);
    if (native !== null) return native;
    const c = num($items.DCData_Current);
    const v = num($items.DCData_Voltage);
    return c === null || v === null ? null : c * v;
  });
  const battArrow = $derived(battWatts === null ? '' : battWatts >= 0 ? '▲' : '▼');
  const battColor = $derived(battWatts === null ? colors.label : battWatts >= 0 ? NET_POS_COLOR : NET_NEG_COLOR);
  const netWatts = $derived(pvWatts === null || loadWatts === null ? null : pvWatts - loadWatts);
  const netColor = $derived(netWatts === null ? colors.label : netWatts >= 0 ? NET_POS_COLOR : NET_NEG_COLOR);

  const pvToday = $derived(num($items.MPPT60_EnergyFromPV_Today));
  const netToday = $derived(pvToday === null || loadToday === null ? null : pvToday - loadToday);
  const netTodayColor = $derived(netToday === null ? colors.label : netToday >= 0 ? NET_POS_COLOR : NET_NEG_COLOR);

  const soc = $derived(num($items.BMS_SOC));
  const socColor = $derived(socBands(soc));
  const battIndicator = $derived.by(() => {
    if ($items.BatteryChargingStatus === 'ON') return { glyph: '▲', text: 'charging' };
    const c = num($items.DCData_Current);
    if (c === null) return { glyph: '●', text: 'idle' };
    if (c > 0) return { glyph: '▲', text: 'charging' };
    if (c < 0) return { glyph: '▼', text: 'discharging' };
    return { glyph: '●', text: 'idle' };
  });
  const battRuntime = $derived(runtimeText(num($items.BMS_TimeToDischarge_Smoothed)));
  const battBasis = $derived(
    $items.BMS_Runtime_Basis && $items.BMS_Runtime_Basis !== 'NULL' && $items.BMS_Runtime_Basis !== 'UNDEF'
      ? $items.BMS_Runtime_Basis
      : ''
  );

  const windDeg = $derived(num($items.AmbientWeatherWS2902A_WindDirection));
  const windSpeedR = $derived.by(() => {
    const n = num($items.AmbientWeatherWS2902A_WindSpeed);
    return n === null ? null : Math.round(n);
  });
  const windGustR = $derived.by(() => {
    const n = num($items.AmbientWeatherWS2902A_WindGust);
    return n === null ? null : Math.round(n);
  });

  const rainFooter = $derived.by(() => {
    const parts = [];
    if (hasItem('AmbientWeatherWS2902A_RainFallEvent'))
      parts.push(`evt ${fmt($items.AmbientWeatherWS2902A_RainFallEvent, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallWeek'))
      parts.push(`wk ${fmt($items.AmbientWeatherWS2902A_RainFallWeek, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallMonth'))
      parts.push(`mo ${fmt($items.AmbientWeatherWS2902A_RainFallMonth, '″', 2)}`);
    return parts.join('·');
  });

  const curtailHours = $derived(num($items.Predicted_Curtailment_Hours));
  const curtailActive = $derived(curtailHours !== null && curtailHours > 0);
  const curtailText = $derived(curtailHours === null ? '—' : `${curtailHours.toFixed(1)} h`);

  const baroTrend = $derived.by(() => {
    const t = $items.AmbientWeatherWS2902A_PressureTrend;
    return t && t !== 'NULL' && t !== 'UNDEF' ? String(t).toLowerCase() : '—';
  });

  // Storm/rain alert for the Baro tile: swap the sparkline for a flashing
  // rain-cloud icon when either a falling-pressure trend (storm indicator)
  // or active rain is present. NULL-safe — missing items just fall back to
  // the normal sparkline.
  const baroStormActive = $derived.by(() => {
    const trendFalling = baroTrend === 'falling';
    const rainRate = num($items.AmbientWeatherWS2902A_RainFallHourlyRate);
    const raining = rainRate !== null && rainRate > 0;
    return trendFalling || raining;
  });

  const zonesList = $derived.by(() => {
    const room = num($items.AmbientWeatherWS2902A_IndoorSensor_Temperature);
    const mk = (label, name) => {
      const t = num($items[name]);
      const delta = t === null || room === null ? null : Math.round((t - room) * 10) / 10;
      return { label, temp: t, delta };
    };
    return [
      mk('Hallway', 'AmbientWeatherWS2902A_IndoorSensor_Temperature'),
      mk('N.Wall', 'AmbientWeatherWS2902A_WH31E_193_Temperature'),
      mk('S.Glass', 'Shelly_HT1_Indoor_Temperature'),
    ];
  });

  const forecastDaily = $derived.by(() => {
    try {
      const raw = $items.Forecast_Daily_JSON;
      if (!raw || raw === 'NULL' || raw === 'UNDEF') return [];
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch {
      return [];
    }
  });

  // ---- Bitcoin card (mirrors Indoor's slot under Battery) ------------------
  const BTC_ACCENT = '#f7931a';
  const btcPriceN = $derived(num($items.BTC_USD_Price));
  const btcPriceText = $derived(btcPriceN === null ? '—' : `$${Math.round(btcPriceN).toLocaleString()}`);
  const btcPct = $derived(num($items.BTC_Price_24h_PercentChange));
  const btcPctText = $derived(btcPct === null ? '—' : `${btcPct >= 0 ? '+' : ''}${btcPct.toFixed(2)}%`);
  const btcPctColor = $derived(btcPct === null ? colors.label : btcPct >= 0 ? '#22c55e' : '#ef4444');

  const sunRiseText = $derived(formatTimeShort($items.Sun_Rise_Start));
  const sunSetText = $derived(formatTimeShort($items.Sun_Set_End));
  const moonText = $derived(prettifyMoon($items.Moon_MoonPhaseName));
  const daylight = $derived(daylightText($items.Sun_Rise_Start, $items.Sun_Set_End));

  // ---- Click-to-chart handlers ----------------------------------------------
  function openOutdoorChart() {
    openChart({
      title: 'Outdoor Temp',
      series: [
        { name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', color: colors.temperature, label: 'Outdoor' },
        { name: 'Forecast_Temp', color: colors.forecast, label: 'Forecast' },
      ],
      hours: 24,
    });
  }
  function openIndoorChart() {
    openChart({
      title: 'Indoor Temp',
      series: [{ name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', color: colors.temperature, label: 'Indoor' }],
      hours: 24,
    });
  }
  function openBatteryChart() {
    openChart({ title: 'Battery SoC', series: [{ name: 'BMS_SOC', color: socColor, label: 'SoC' }], hours: 24 });
  }
  function openWindChart() {
    openChart({
      title: 'Wind',
      series: [
        { name: 'AmbientWeatherWS2902A_WindSpeed', color: colors.wind, label: 'Speed' },
        { name: 'AmbientWeatherWS2902A_WindGust', color: colors.forecast, label: 'Gust' },
      ],
      hours: 24,
    });
  }
  function openRainChart() {
    openChart({
      title: 'Rain',
      series: [{ name: 'AmbientWeatherWS2902A_RainFallDay', color: colors.rain, label: 'Rain/day' }],
      hours: 24,
    });
  }
  function openSolarChart() {
    openChart({
      title: 'Solar PV',
      series: [{ name: 'MPPT60_PV_Power', color: colors.solar, label: 'PV Power' }],
      hours: 24,
    });
  }
  function openBaroChart() {
    openChart({
      title: 'Pressure',
      series: [
        {
          name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative',
          color: colors.label,
          label: 'Pressure',
        },
      ],
      hours: 24,
    });
  }
  function openBitcoinChart() {
    openChart({
      title: 'Bitcoin (USD)',
      series: [{ name: 'BTC_USD_Price', color: BTC_ACCENT, label: 'BTC/USD' }],
      hours: 24,
    });
  }
</script>

<div class="home-grid">
  <div class="cell advisory-cell">
    {#if advisoryActive}
      <Tile label="Advisory" accent={colors.advisory}>
        <div class="advisory-body">
          <span class="advisory-dot"></span>
          <span class="advisory-text">{advisoryText || '—'}</span>
        </div>
      </Tile>
    {:else}
      <Tile label="Power Flow" accent={colors.solar}>
        <div class="powerflow-body">
          <div class="pf-line1">
            <span class="pf-seg" style="color: {colors.solar}">&#9728; {numFmt(pvWatts, ' W')}</span>
            <span class="pf-arrow">&rarr;</span>
            <span class="pf-seg" style="color: {battColor}"
              >&#128267; {signedFmt(battWatts, ' W')} {battArrow}</span
            >
            <span class="pf-arrow">&rarr;</span>
            <span class="pf-seg pf-load">&#127968; {numFmt(loadWatts, ' W')}</span>
            <span class="pf-sep">&middot;</span>
            <span class="pf-net" style="color: {netColor}">net {signedFmt(netWatts, ' W')}</span>
          </div>
          <div class="pf-line2">
            Today: {numFmt(pvToday, ' kWh', 1)} in &middot; {loadToday === null
              ? '—'
              : numFmt(loadToday, ' kWh', 1)} used &middot;
            <span style="color: {netTodayColor}">{signedFmt(netToday, ' kWh', 1)} net</span>
          </div>
        </div>
      </Tile>
    {/if}
  </div>

  <div class="cell greywater-cell">
    <Tile label="Greywater" accent={colors.water}>
      <div class="greywater-body">
        <span class="gw-dot" class:active={gwRunning}></span>
        <div class="gw-text">
          <div class="gw-state">{gwRunning ? 'Running' : 'Idle'}</div>
          <div class="gw-last">last {gwLastAgo}</div>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell outdoor-cell clickable"
    role="button"
    tabindex="0"
    onclick={openOutdoorChart}
    onkeydown={(e) => onKeyActivate(e, openOutdoorChart)}
  >
    <Tile label="Outdoor" accent={colors.temperature}>
      <div class="outdoor-body">
        <div class="outdoor-top">
          <div class="outdoor-main">
            <span class="cond-icon"><OhIcon icon={$items.SkyConditionIcon} size="2rem" /></span>
            <span class="big-temp">{fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°')}</span>
            <span class="aqi-chip">AQI {fmt($items.Forecast_AQI)}</span>
          </div>
          <div class="outdoor-sub">
            feels like {fmt($items.AmbientWeatherWS2902A_ApparentTemperature, '°')}
            &middot; {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity, '%')} RH
          </div>
          <div class="outdoor-hilo">
            H {fmt($items.OutdoorTemp_24h_High, '°')} &nbsp;/&nbsp; L {fmt($items.OutdoorTemp_24h_Low, '°')}
          </div>
        </div>
        <div class="outdoor-spark"><Sparkline data={outdoorSpark} color={colors.temperature} lineWidth={2} /></div>
      </div>
    </Tile>
  </div>

  <div
    class="cell indoor-cell clickable"
    role="button"
    tabindex="0"
    onclick={openIndoorChart}
    onkeydown={(e) => onKeyActivate(e, openIndoorChart)}
  >
    <Tile label="Indoor" accent={colors.temperature}>
      <div class="indoor-body">
        <div class="indoor-temp">{fmt($items.AmbientWeatherWS2902A_IndoorSensor_Temperature, '°')}</div>
        <div class="indoor-meta">
          <div class="indoor-hum">{fmt($items.AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity, '%')} RH</div>
          <div class="indoor-hilo">H {fmt($items.IndoorTemp_24h_High, '°')} / L {fmt($items.IndoorTemp_24h_Low, '°')}</div>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell battery-cell clickable"
    role="button"
    tabindex="0"
    onclick={openBatteryChart}
    onkeydown={(e) => onKeyActivate(e, openBatteryChart)}
  >
    <Tile label="Battery" accent={socColor}>
      <div class="battery-body">
        <div class="battery-top">
          <div class="battery-arc">
            <Arc value={soc ?? 0} color={socColor} label="SoC" sublabel={fmt($items.DCData_Current, ' A', 1)} />
          </div>
          <div class="battery-meta">
            <span class="batt-indicator" style="color: {socColor}">{battIndicator.glyph} {battIndicator.text}</span>
            <span class="batt-runtime"
              >{battRuntime}{#if battBasis}<em> ({battBasis})</em>{/if}</span
            >
          </div>
        </div>
        <div class="battery-spark"><Sparkline data={battSpark} color={socColor} lineWidth={2} /></div>
      </div>
    </Tile>
  </div>

  <div
    class="cell bitcoin-cell clickable"
    role="button"
    tabindex="0"
    onclick={openBitcoinChart}
    onkeydown={(e) => onKeyActivate(e, openBitcoinChart)}
  >
    <Tile label="Bitcoin" accent={BTC_ACCENT}>
      <div class="bitcoin-body">
        <div class="btc-top">
          <span class="btc-price">{btcPriceText}</span>
          <span class="btc-pct" style="color: {btcPctColor}">{btcPctText}</span>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell wind-cell clickable"
    role="button"
    tabindex="0"
    onclick={openWindChart}
    onkeydown={(e) => onKeyActivate(e, openWindChart)}
  >
    <Tile label="Wind" accent={colors.wind}>
      <div class="wind-body">
        <div class="compass-cap">
          <CompassRose degrees={windDeg} speed={windSpeedR} gust={windGustR} showGust={false} />
        </div>
        <div class="wind-meta">
          <span class="wind-gust">gust {windGustR === null ? '—' : windGustR} mph</span>
          <span class="wind-max">max {windGustMaxToday === null ? '—' : Math.round(windGustMaxToday)} mph</span>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell baro-cell clickable"
    role="button"
    tabindex="0"
    onclick={openBaroChart}
    onkeydown={(e) => onKeyActivate(e, openBaroChart)}
  >
    <Tile label="Baro" accent={colors.label}>
      <div class="baro-body">
        <div class="baro-value">
          {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative, '', 2)} <span class="unit">inHg</span>
        </div>
        {#if baroStormActive}
          <div class="baro-spark baro-storm">
            <OhIcon icon={'iconify:mdi:weather-pouring'} size="1.7rem" color={colors.rain} />
          </div>
        {:else}
          <div class="baro-spark"><Sparkline data={baroSpark} color={colors.label} lineWidth={2} /></div>
        {/if}
        <div class="baro-trend">{baroTrend}</div>
      </div>
    </Tile>
  </div>

  <div
    class="cell rain-cell clickable"
    role="button"
    tabindex="0"
    onclick={openRainChart}
    onkeydown={(e) => onKeyActivate(e, openRainChart)}
  >
    <StatTile
      label="Rain"
      value={fmt($items.AmbientWeatherWS2902A_RainFallDay, '', 2)}
      unit="&#8243;"
      accent={colors.rain}
      footer={rainFooter}
    />
  </div>

  <div class="cell sunmoon-cell">
    <Tile label="Sun &amp; Moon" accent={colors.label}>
      <div class="sunmoon-body">
        <div class="sm-row">
          <OhIcon icon={$items.SunPhaseIcon} size="1em" />
          <span class="sm-times">&uarr;{sunRiseText} &darr;{sunSetText}</span>
        </div>
        <div class="sm-row"><OhIcon icon={$items.MoonPhaseicon} size="1em" /> {moonText}</div>
        <div class="sm-row sm-daylight">daylight {daylight}</div>
      </div>
    </Tile>
  </div>

  <div
    class="cell solar-cell clickable"
    role="button"
    tabindex="0"
    onclick={openSolarChart}
    onkeydown={(e) => onKeyActivate(e, openSolarChart)}
  >
    <Tile label="Solar" accent={colors.solar}>
      <div class="solar-body">
        <div class="solar-main">{fmt($items.MPPT60_EnergyFromPV_Today, '', 1)}<span class="unit"> kWh</span></div>
        <div class="solar-sub">of {fmt($items.Predicted_PV_Today_kWh, '', 1)} predicted</div>
        <div class="solar-current">{fmt($items.MPPT60_PV_Power, ' W', 0)} now</div>
        <div class="curtail-lamp">
          <span class="lamp-dot" class:active={curtailActive}></span>
          curtail {curtailText}
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell zones-cell">
    <Tile label="Zones" accent={colors.temperature}>
      <div class="zones-body">
        {#each zonesList as z (z.label)}
          <div class="zone-row">
            <span class="zone-label">{z.label}</span>
            <span class="zone-temp">{z.temp === null ? '—' : Math.round(z.temp) + '°'}</span>
            <span class="zone-delta" class:up={z.delta > 0} class:down={z.delta < 0}
              >{z.delta === null ? '—' : z.delta > 0 ? '▲' : z.delta < 0 ? '▼' : '—'}</span
            >
          </div>
        {/each}
      </div>
    </Tile>
  </div>

  <div class="cell forecast-cell">
    <Tile label="Forecast" accent={colors.forecast}>
      <div class="forecast-body">
        {#if forecastDaily.length === 0}
          <div class="fc-empty">—</div>
        {:else}
          {#each forecastDaily.slice(0, 7) as d, i (i)}
            <div class="fc-day" class:fc-emph={i < 2}>
              <div class="fc-label">{dayLabel(i, d.d)}</div>
              <div class="fc-icon">{wmoEmoji(d.w)}</div>
              <div class="fc-hilo">{roundOrDash(d.hi)}&deg;/{roundOrDash(d.lo)}&deg;</div>
              <div class="fc-pv">PV ~{pvText(d.pv)} kWh</div>
            </div>
          {/each}
        {/if}
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
      'indoor indoor bitcoin bitcoin solar zones'
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
    grid-area: topbar;
  }
  .greywater-cell {
    grid-area: greywater;
  }
  .outdoor-cell {
    grid-area: outdoor;
  }
  .indoor-cell {
    grid-area: indoor;
  }
  .battery-cell {
    grid-area: battery;
  }
  .bitcoin-cell {
    grid-area: bitcoin;
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

  /* ---- Power-flow strip (shown instead of the advisory banner when no
     thermal advisory is active — same cell/grid-area, never both, never
     empty) ---- */
  .powerflow-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.2rem;
    min-width: 0;
  }
  .pf-line1 {
    display: flex;
    align-items: baseline;
    flex-wrap: nowrap;
    gap: 0.5rem;
    font-size: 0.82rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    color: #e6edf3;
  }
  .pf-seg {
    white-space: nowrap;
  }
  .pf-load {
    color: #c7cfd9;
  }
  .pf-arrow {
    color: #4b5563;
    font-weight: 400;
  }
  .pf-sep {
    color: #4b5563;
  }
  .pf-net {
    font-weight: 700;
  }
  .pf-line2 {
    font-size: 0.68rem;
    color: #8b93a1;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
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
    opacity: 0.4;
    flex-shrink: 0;
  }
  .gw-dot.active {
    opacity: 1;
    box-shadow: 0 0 0.4rem #3b82f6;
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
    height: 100%;
    gap: 0.4rem;
  }
  .outdoor-top {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    flex: 0 0 auto;
  }
  .outdoor-main {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }
  .cond-icon {
    display: inline-flex;
    align-items: center;
    line-height: 1;
  }
  .big-temp {
    font-size: 4rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #fff;
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
    font-size: 1.05rem;
    color: #8b93a1;
  }
  .outdoor-hilo {
    font-size: 0.95rem;
    color: #c7cfd9;
  }
  .outdoor-spark {
    flex: 1;
    min-height: 2.2rem;
    min-width: 0;
    overflow: hidden;
    position: relative;
  }
  :global(.outdoor-cell .tile) {
    overflow: hidden;
  }

  /* ---- Indoor ---- */
  .indoor-body {
    display: flex;
    align-items: center;
    height: 100%;
    gap: 0.85rem;
  }
  .indoor-temp {
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #fff;
  }
  .indoor-meta {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    font-size: 0.85rem;
  }
  .indoor-hum {
    font-weight: 600;
    color: #c7cfd9;
  }
  .indoor-hilo {
    color: #8b93a1;
  }

  /* ---- Battery hero ---- */
  /* The SoC sparkline's green area-fill was bleeding below the card's
     rounded bottom edge. Clip to the card's own rounded bounds (matching
     how the Outdoor card already stays inside its border) in addition to
     the inner overflow:hidden on .battery-body/.battery-spark below. */
  :global(.battery-cell .tile) {
    overflow: hidden;
  }
  .battery-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0.5rem;
    overflow: hidden;
  }
  .battery-top {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    flex: 0 0 auto;
  }
  .battery-arc {
    width: 36%;
    max-width: 8rem;
  }
  .battery-meta {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.85rem;
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
    font-size: 0.75rem;
  }
  .battery-spark {
    flex: 1;
    min-height: 1.6rem;
    overflow: hidden;
  }

  /* ---- Bitcoin (mirrors Indoor's slot under Battery) ---- */
  :global(.bitcoin-cell .tile) {
    overflow: hidden;
  }
  .bitcoin-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    overflow: hidden;
  }
  .btc-top {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    flex: 0 0 auto;
  }
  .btc-price {
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #f7931a;
  }
  .btc-pct {
    font-size: 0.8rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  /* ---- Wind ---- */
  /* The rose measures the remaining content box. Gust and daily maximum stay
     in a dedicated row so they can never overlap the needle. */
  :global(.wind-cell .tile) {
    overflow: hidden;
    padding: 0.55rem 0.65rem;
  }
  :global(.wind-cell .tile-label) {
    margin-bottom: 0.2rem;
    flex-shrink: 0;
  }
  .wind-body {
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    height: 100%;
    gap: 0.25rem;
    overflow: hidden;
    min-height: 0;
    min-width: 0;
  }
  .compass-cap {
    width: 100%;
    height: 100%;
    min-height: 0;
    min-width: 0;
  }
  .wind-meta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    font-size: 0.68rem;
    line-height: 1;
    white-space: nowrap;
  }
  .wind-gust {
    color: #22c55e;
  }
  .wind-max {
    color: #8b93a1;
  }

  /* ---- Rain ---- */
  .rain-cell :global(.value) {
    font-size: 2.15rem;
  }
  .rain-cell :global(.footer) {
    font-size: 0.72rem;
    line-height: 1.1;
    letter-spacing: -0.025em;
    white-space: nowrap;
  }
  .rain-cell :global(.tile) {
    overflow: hidden;
  }

  /* ---- Baro ---- */
  /* Title/content overlap fix: the tile label (.tile-label, from Tile.svelte)
     defaults to flex-shrink:1, so when this narrow column's row got too
     short it could compress the label box until its text visually collided
     with the value below. Pin the label to its own row and let the body
     lay out top-down beneath it instead of vertically centering into the
     same space. */
  :global(.baro-cell .tile-label) {
    flex-shrink: 0;
  }
  .baro-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: flex-start;
    gap: 0.2rem;
  }
  .baro-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .baro-value .unit {
    font-size: 0.65rem;
    color: #8b93a1;
  }
  .baro-spark {
    flex: 1;
    min-height: 1.4rem;
  }
  /* Storm/rain alert: flashing rain-cloud icon swapped in for the sparkline.
     Gentle opacity-only pulse — no blur/transform — to stay cheap on the
     tablet's modest GPU. */
  .baro-storm {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .baro-storm :global(svg) {
    animation: baro-pulse 1.2s ease-in-out infinite;
  }
  @keyframes baro-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
  .baro-trend {
    font-size: 0.68rem;
    color: #8b93a1;
    text-transform: capitalize;
    line-height: 1;
  }

  /* ---- Sun & Moon ---- */
  :global(.sunmoon-cell .tile-label) {
    flex-shrink: 0;
  }
  .sunmoon-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: flex-start;
    gap: 0.28rem;
  }
  .sm-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.86rem;
    color: #c7cfd9;
    line-height: 1.15;
    white-space: nowrap;
  }
  .sm-times {
    white-space: nowrap;
  }
  .sm-daylight {
    color: #8b93a1;
  }

  /* ---- Solar ---- */
  :global(.solar-cell .tile-label) {
    flex-shrink: 0;
  }
  .solar-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: flex-start;
    gap: 0.18rem;
  }
  .solar-main {
    font-size: 1.4rem;
    font-weight: 700;
    color: #eab308;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .solar-main .unit {
    font-size: 0.8rem;
    font-weight: 500;
    color: #8b93a1;
  }
  .solar-sub {
    font-size: 0.68rem;
    color: #8b93a1;
    line-height: 1.15;
  }
  .solar-current {
    font-size: 0.74rem;
    color: #c7cfd9;
    line-height: 1.15;
  }
  .curtail-lamp {
    margin-top: 0.1rem;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.62rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    white-space: nowrap;
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
  .fc-empty {
    grid-column: span 7;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #8b93a1;
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
