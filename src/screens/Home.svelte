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
  import GoatFeedingsCard from '../lib/ui/GoatFeedingsCard.svelte';
  import SeasonCountdown from '../lib/ui/SeasonCountdown.svelte';
  import OhIcon from '../lib/ui/OhIcon.svelte';
  import DailyForecast from '../lib/ui/DailyForecast.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import {
    adaptCurrentAqi,
    batteryPowerFlowPresentation,
    batteryDirectionState,
    batteryIcon as selectBatteryIcon,
    bitcoinStateColor,
    curtailmentColor,
    greywaterState,
    harvestedGallons,
    indoorTemperatureIconColor,
    localDayHistoryRange,
    maxHistoryValue,
    netStateColor,
    outdoorConditionIcon as selectOutdoorConditionIcon,
    outdoorTemperatureIconColor,
    pressurePresentation,
    rainRateChip,
    relativeAgeText,
    rainStateColor,
    solarPvColor,
    uvIndexColor,
    windSpeedColor,
  } from '../lib/ui/homeCardState.js';
  import { items, num, fmt, socBands, runtimeText, getClientOnce } from '../lib/openhab';
  import { openChart } from '../lib/ui/chartStore.js';
  import { openWeatherDetail } from '../lib/weather/detailStore.js';
  import {
    parseForecast10Day,
    parseLegacyDailyForecast,
  } from '../lib/weather/forecastDetail.js';

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

  let wallClock = $state(Date.now());
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
    const range = localDayHistoryRange(new Date());
    if (!range) return;
    const data = await fetchHistoryRange('ConextGateway_ACPowerValue', range.starttime, range.endtime);
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

  async function refreshWindGustMaxToday() {
    const range = localDayHistoryRange(new Date());
    const data = await fetchHistoryRange('AmbientWeatherWS2902A_WindGust', range.starttime, range.endtime);
    windGustMaxToday = maxHistoryValue(data);
  }

  const SPARK_REFRESH_MS = 300000; // 5 minutes
  const WALL_CLOCK_REFRESH_MS = 60000; // one minute
  let sparkRefreshTimer;
  let wallClockTimer;

  onMount(() => {
    wallClock = Date.now();
    refreshOutdoorSpark();
    refreshBattSpark();
    refreshBaroSpark();
    refreshLoadToday();
    refreshWindGustMaxToday();

    wallClockTimer = setInterval(() => {
      wallClock = Date.now();
    }, WALL_CLOCK_REFRESH_MS);

    sparkRefreshTimer = setInterval(() => {
      refreshOutdoorSpark();
      refreshBattSpark();
      refreshBaroSpark();
      refreshLoadToday();
      refreshWindGustMaxToday();
    }, SPARK_REFRESH_MS);
  });

  onDestroy(() => {
    if (sparkRefreshTimer) clearInterval(sparkRefreshTimer);
    if (wallClockTimer) clearInterval(wallClockTimer);
  });

  // ---- Small null-safe formatting helpers ----------------------------------


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

  function onKeyActivate(e, fn) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  }

  const gwStatus = $derived(greywaterState($items.SouthOutlet_Outlet2_Switch));
  const gwAccessibleLabel = $derived(`Greywater status ${gwStatus.label.toLowerCase()}`);
  const gwLastAgo = $derived(relativeAgeText($items.SouthOutlet_LastAutoRun, wallClock));


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
  const battFlow = $derived(batteryPowerFlowPresentation(battWatts));
  const netWatts = $derived(pvWatts === null || loadWatts === null ? null : pvWatts - loadWatts);
  const netColor = $derived(netStateColor(netWatts));

  const pvToday = $derived(num($items.MPPT60_EnergyFromPV_Today));
  const netToday = $derived(pvToday === null || loadToday === null ? null : pvToday - loadToday);
  const netTodayColor = $derived(netStateColor(netToday));

  const outdoorTemp = $derived(num($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature));
  const outdoorConditionIcon = $derived(selectOutdoorConditionIcon($items.SkyConditionIcon));
  const outdoorIconColor = $derived(outdoorTemperatureIconColor(outdoorTemp));
  const currentAqi = $derived(adaptCurrentAqi($items.Current_US_AQI));
  const uvIndex = $derived(num($items.AmbientWeatherWS2902A_UVIndex));
  const uvColor = $derived(uvIndexColor(uvIndex));
  const indoorTemp = $derived(num($items.AmbientWeatherWS2902A_IndoorSensor_Temperature));
  const indoorIconColor = $derived(indoorTemperatureIconColor(indoorTemp));

  const soc = $derived(num($items.BMS_SOC));
  const socColor = $derived(socBands(soc));
  const batteryStatusIcon = $derived(selectBatteryIcon($items.BatteryIcon));
  const batteryChartLabel = $derived(
    soc === null ? 'Open Battery chart; current SoC unavailable' : `Open Battery chart; current SoC ${Math.round(soc)}%`
  );
  const battIndicator = $derived(
    batteryDirectionState($items.BatteryChargingStatus, $items.DCData_Current)
  );
  const battRuntimeEmpty = $derived(runtimeText(num($items.BMS_TimeToDischarge_Smoothed)));
  const battRuntimeFull = $derived(runtimeText(num($items.BMS_TimeToFull_Smoothed)));

  const windDeg = $derived(num($items.AmbientWeatherWS2902A_WindDirection));
  const windSpeedR = $derived.by(() => {
    const n = num($items.AmbientWeatherWS2902A_WindSpeed);
    return n === null ? null : Math.round(n);
  });
  const windGustR = $derived.by(() => {
    const n = num($items.AmbientWeatherWS2902A_WindGust);
    return n === null ? null : Math.round(n);
  });
  const windGustColor = $derived(windSpeedColor(windGustR));
  const windMaxColor = $derived(windSpeedColor(windGustMaxToday));
  const windAccent = $derived(windSpeedColor(windSpeedR));

  const rainDayInches = $derived(num($items.AmbientWeatherWS2902A_RainFallDay));
  const rainWeekInches = $derived(num($items.AmbientWeatherWS2902A_RainFallWeek));
  const rainDayGallons = $derived(harvestedGallons(rainDayInches));
  const rainWeekGallons = $derived(harvestedGallons(rainWeekInches));
  const rainIconColor = $derived(rainStateColor(rainDayInches));
  const rainRateLabel = $derived(rainRateChip($items.AmbientWeatherWS2902A_RainFallHourlyRate));
  const rainValue = $derived(
    rainDayInches === null || rainDayGallons === null
      ? '—'
      : `${rainDayInches.toFixed(2)}″ / ${rainDayGallons.toLocaleString('en-US')} gal`
  );
  const rainFooter = $derived(
    rainWeekInches === null || rainWeekGallons === null
      ? 'Week —'
      : `Week ${rainWeekInches.toFixed(2)}″ / ${rainWeekGallons.toLocaleString('en-US')} gal`
  );

  const curtailHours = $derived(num($items.Predicted_Curtailment_Hours));
  const curtailActive = $derived(curtailHours !== null && curtailHours > 0);
  const curtailText = $derived(curtailHours === null ? '—' : `${curtailHours.toFixed(1)} h`);
  const curtailColor = $derived(curtailmentColor(curtailHours));
  const solarColor = $derived(solarPvColor(pvWatts));

  const pressureStatus = $derived(pressurePresentation($items.AmbientWeatherWS2902A_PressureTrend));

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

  const forecastDetail = $derived(parseForecast10Day($items.Forecast_10Day_JSON));
  const legacyForecast = $derived(parseLegacyDailyForecast($items.Forecast_Daily_JSON));
  const forecastDays = $derived(
    forecastDetail.days.length > 0 ? forecastDetail.days : legacyForecast
  );

  function selectForecastDay(day) {
    openWeatherDetail({ date: day.date, label: day.label });
  }

  // ---- Bitcoin card (mirrors Indoor's slot under Battery) ------------------
  const BTC_ACCENT = '#f7931a';
  const btcPriceN = $derived(num($items.BTC_USD_Price));
  const btcPriceText = $derived(btcPriceN === null ? '—' : `$${Math.round(btcPriceN).toLocaleString()}`);
  const btcPct = $derived(num($items.BTC_Price_24h_PercentChange));
  const btcPctText = $derived(btcPct === null ? '—' : `${btcPct >= 0 ? '+' : ''}${btcPct.toFixed(2)}%`);
  const btcPctColor = $derived(bitcoinStateColor(btcPct));

  const sunRiseText = $derived(formatTimeShort($items.Sun_Rise_Start));
  const sunSetText = $derived(formatTimeShort($items.Sun_Set_End));
  const moonText = $derived(prettifyMoon($items.Moon_MoonPhaseName));
  const daylight = $derived(daylightText($items.Sun_Rise_Start, $items.Sun_Set_End));

  // ---- Click-to-chart handlers ----------------------------------------------
  function openOutdoorChart() {
    openChart({
      title: 'Outdoor Temp',
      series: [
        {
          name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
          color: colors.temperature,
          label: 'Outdoor',
          markers: ['min', 'max'],
          markerUnit: '°',
        },
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
    openChart({
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        color: socColor,
        label: 'SoC',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    });
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
  <div class="cell powerflow-cell">
      <Tile label="Power Flow" accent={colors.solar} hideLabel fill clip centerBody padding="0.55rem 0.65rem">
        <div class="powerflow-body">
          <div class="pf-line1">
            <span class="pf-seg" style="color: {colors.solar}">&#9728; {numFmt(pvWatts, ' W')}</span>
            <span class="pf-arrow">&rarr;</span>
            <span class="pf-seg" style="color: {battFlow.color}"
              >&#128267; {battFlow.text} {battFlow.glyph}</span
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
  </div>

  <div class="cell goat-cell">
    <GoatFeedingsCard
      feedings={$items.GoatFeedingsToday}
      motorState={$items.Goat_Plugs_Outlet2_Switch}
    />
  </div>

  <div class="cell greywater-cell">
    <Tile label="Greywater" accessibleLabel={gwAccessibleLabel} accent={colors.water} hideLabel fill clip centerBody padding="0.55rem 0.65rem">
      <div class="greywater-body">
        <span class="gw-icon" style="color: {gwStatus.color}">
          <OhIcon icon="iconify:mdi:fountain" size="1.35rem" />
        </span>
        <div class="gw-text">
          <div class="gw-state" style="color: {gwStatus.color}">{gwStatus.label}</div>
          <div class="gw-last">last {gwLastAgo}</div>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell outdoor-cell clickable"
    role="button"
    tabindex="0"
    aria-label="Open Outdoor temperature chart"
    onclick={openOutdoorChart}
    onkeydown={(e) => onKeyActivate(e, openOutdoorChart)}
  >
    <Tile label="Outdoor" accent={colors.temperature} hideLabel fill clip centerBody padding="0.7rem">
      <div class="outdoor-body">
        <div class="outdoor-top">
          <div class="outdoor-main">
            <span class="cond-icon"><OhIcon icon={outdoorConditionIcon} size="2rem" color={outdoorIconColor} /></span>
            <span class="big-temp">{fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°')}</span>
            <div class="outdoor-chips">
              <span
                class="aqi-chip"
                class:unavailable={currentAqi.value === null}
                style="color: {currentAqi.textColor}; border-color: {currentAqi.accent}"
                >AQI {currentAqi.value ?? '—'}</span
              >
              <span class="uv-chip" style="color: {uvColor}">UV {fmt($items.AmbientWeatherWS2902A_UVIndex)}</span>
              {#if rainRateLabel}
                <span class="rain-rate-chip" style="color: {colors.rain}; border-color: {colors.rain}">{rainRateLabel}</span>
              {/if}
            </div>
          </div>
          <div class="outdoor-sub">
            feels like {fmt($items.AmbientWeatherWS2902A_ApparentTemperature, '°')}
            &middot; {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity, '%')} RH
          </div>
          <div class="outdoor-hilo">
            H {fmt($items.OutdoorTemp_24h_High, '°')} &nbsp;/&nbsp; L {fmt($items.OutdoorTemp_24h_Low, '°')}
          </div>
        </div>
        <div class="outdoor-spark"><Sparkline data={outdoorSpark} color={outdoorIconColor} lineWidth={2} /></div>
      </div>
    </Tile>
  </div>

  <div
    class="cell indoor-cell clickable"
    role="button"
    tabindex="0"
    aria-label="Open Indoor temperature chart"
    onclick={openIndoorChart}
    onkeydown={(e) => onKeyActivate(e, openIndoorChart)}
  >
    <Tile label="Indoor" accent={colors.temperature} hideLabel fill clip centerBody padding="0.65rem">
      <div class="indoor-body">
        <div class="indoor-reading">
          <span class="indoor-icon" style="color: {indoorIconColor}">
            <OhIcon icon="iconify:mdi:home-thermometer" size="2rem" />
          </span>
          <div class="indoor-temp">{fmt($items.AmbientWeatherWS2902A_IndoorSensor_Temperature, '°')}</div>
        </div>
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
    aria-label={batteryChartLabel}
    onclick={openBatteryChart}
    onkeydown={(e) => onKeyActivate(e, openBatteryChart)}
  >
    <Tile label="Battery" accent={socColor} hideLabel fill clip centerBody padding="0.65rem">
      <div class="battery-body">
        <div class="battery-top">
          <div class="battery-arc">
            <Arc value={soc} color={socColor} label="" sublabel={fmt($items.DCData_Current, ' A', 1)} />
          </div>
          <div class="battery-meta">
            <div class="batt-status">
              <span class="batt-icon" class:charging={battIndicator.text === 'charging'} style="color: {socColor}">
                <OhIcon icon={batteryStatusIcon} size="1.35rem" />
              </span>
              <span class="batt-indicator" style="color: {battIndicator.color}">{battIndicator.glyph} {battIndicator.text}</span>
            </div>
            <span class="batt-runtime batt-runtime-empty"><strong>Empty</strong> {battRuntimeEmpty}</span>
            <span class="batt-runtime batt-runtime-full"><strong>Full</strong> {battRuntimeFull}</span>
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
    aria-label="Open Bitcoin history chart"
    onclick={openBitcoinChart}
    onkeydown={(e) => onKeyActivate(e, openBitcoinChart)}
  >
    <Tile label="Bitcoin" accent={BTC_ACCENT} hideLabel fill clip centerBody padding="0.65rem">
      <div class="bitcoin-body">
        <div class="btc-top">
          <span class="btc-icon" style="color: {btcPctColor}">
            <OhIcon icon="iconify:mdi:bitcoin" size="1.5rem" />
          </span>
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
    aria-label="Open Wind chart"
    onclick={openWindChart}
    onkeydown={(e) => onKeyActivate(e, openWindChart)}
  >
    <Tile label="Wind" accent={colors.wind} hideLabel fill clip centerBody padding="0.5rem 0.6rem">
      <div class="wind-body">
        <div class="compass-cap">
          <CompassRose degrees={windDeg} speed={windSpeedR} gust={windGustR} showGust={false} accent={windAccent} />
        </div>
        <div class="wind-meta">
          <span class="wind-gust" style="color: {windGustColor}">gust {windGustR === null ? '—' : windGustR} mph</span>
          <span class="wind-max" style="color: {windMaxColor}">max {windGustMaxToday === null ? '—' : Math.round(windGustMaxToday)} mph</span>
        </div>
      </div>
    </Tile>
  </div>

  <div
    class="cell baro-cell clickable"
    role="button"
    tabindex="0"
    aria-label="Open Barometric pressure chart"
    onclick={openBaroChart}
    onkeydown={(e) => onKeyActivate(e, openBaroChart)}
  >
    <Tile label="Baro" accent={pressureStatus.color} hideLabel fill clip centerBody padding="0.65rem">
      <div class="baro-body">
        <div class="baro-head">
          <span class="baro-status-icon" style="color: {pressureStatus.color}"><OhIcon icon={pressureStatus.icon} size="1.15rem" /></span>
          <div class="baro-value">
            {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative, '', 2)} <span class="unit">inHg</span>
          </div>
        </div>
        <div class="baro-spark"><Sparkline data={baroSpark} color={colors.label} lineWidth={2} smoothingAlpha={0.12} /></div>
        <div class="baro-trend" style="color: {pressureStatus.color}">{pressureStatus.label}</div>
      </div>
    </Tile>
  </div>

  <div
    class="cell rain-cell clickable"
    role="button"
    tabindex="0"
    aria-label="Open Rain chart"
    onclick={openRainChart}
    onkeydown={(e) => onKeyActivate(e, openRainChart)}
  >
    <StatTile
      label="Rain"
      value={rainValue}
      unit=""
      accent={colors.rain}
      iconName="iconify:mdi:weather-rainy"
      iconColor={rainIconColor}
      footer={rainFooter}
      valueSize="1rem"
      footerSize="0.72rem"
      footerNoWrap
      stackValue
      centerContent
      hideLabel fill clip
      padding="0.65rem"
    />
  </div>

  <div class="cell sunmoon-cell">
    <Tile label="Sun &amp; Moon" accent={colors.label} hideLabel fill clip centerBody padding="0.65rem">
      <div class="sunmoon-body">
        <div class="sm-row">
          <span class="sm-icon"><OhIcon icon={$items.SunPhaseIcon} size="1em" /></span>
          <span class="sm-times">&uarr;{sunRiseText} &darr;{sunSetText}</span>
        </div>
        <div class="sm-row">
          <span class="sm-icon"><OhIcon icon={$items.MoonPhaseicon} size="1em" /></span>
          <span class="sm-moon" title={moonText}>{moonText}</span>
        </div>
        <div class="sm-row sm-daylight">daylight {daylight}</div>
        <SeasonCountdown />
      </div>
    </Tile>
  </div>

  <div
    class="cell solar-cell clickable"
    role="button"
    tabindex="0"
    aria-label="Open Solar chart"
    onclick={openSolarChart}
    onkeydown={(e) => onKeyActivate(e, openSolarChart)}
  >
    <Tile label="Solar" accent={colors.solar} hideLabel fill clip centerBody padding="0.65rem">
      <div class="solar-body">
        <div class="solar-head">
          <span class="solar-icon" style="color: {solarColor}"><OhIcon icon="iconify:mdi:solar-power-variant" size="1.25rem" /></span>
          <div class="solar-main">{fmt($items.MPPT60_EnergyFromPV_Today, '', 1)}<span class="unit"> kWh</span></div>
        </div>
        <div class="solar-sub">of {fmt($items.Predicted_PV_Today_kWh, '', 1)} predicted</div>
        <div class="solar-current" style="color: {solarColor}">{fmt($items.MPPT60_PV_Power, ' W', 0)} now</div>
        <div class="curtail-lamp" style="color: {curtailColor}">
          <span class="lamp-dot" class:active={curtailActive}></span>
          curtail {curtailText}
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell zones-cell">
    <Tile label="Zones" accent={colors.temperature} hideLabel fill clip centerBody padding="0.65rem">
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
    <Tile label="Forecast" accent={colors.forecast} hideLabel fill clip centerBody padding="0.55rem 0.65rem">
      <DailyForecast days={forecastDays} variant="home" onselect={selectForecastDay} />
    </Tile>
  </div>
</div>

<style>
  .home-grid {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows:
      minmax(0, 0.38fr)
      minmax(0, 1.2fr)
      minmax(0, 1fr)
      minmax(0, 0.9fr)
      minmax(0, 0.72fr);
    grid-template-areas:
      'topbar topbar topbar topbar goat greywater'
      'outdoor outdoor battery battery wind baro'
      'outdoor outdoor battery battery rain sunmoon'
      'indoor indoor bitcoin bitcoin solar zones'
      'forecast forecast forecast forecast forecast forecast';
    gap: 0.55rem;
    overflow: hidden;
  }
  .cell {
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
  .clickable {
    cursor: pointer;
    border-radius: 0.75rem;
  }
  .clickable:hover { filter: brightness(1.07); }
  .clickable:focus-visible {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }

  .powerflow-cell {
    grid-area: topbar;
  }
  .goat-cell {
    grid-area: goat;
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

  /* ---- Power-flow strip; advisories live only in the fixed header. ---- */
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
    color: #94a3b8;
    font-weight: 400;
  }
  .pf-sep {
    color: #94a3b8;
  }
  .pf-net {
    font-weight: 700;
  }
  .pf-line2 {
    font-size: 0.68rem;
    color: #aab4c2;
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
  .gw-icon {
    display: inline-flex;
    align-items: center;
    flex-shrink: 0;
    line-height: 1;
  }
  .gw-state {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1.1;
  }
  .gw-last {
    font-size: 0.68rem;
    color: #aab4c2;
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
    align-items: flex-start;
    gap: 0.6rem;
  }
  .cond-icon {
    display: inline-flex;
    align-items: center;
    line-height: 1;
  }
  .big-temp {
    font-size: 4.4rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #fff;
  }
  .outdoor-chips {
    margin-left: auto;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.25rem;
    flex: 0 0 auto;
  }
  .aqi-chip,
  .uv-chip,
  .rain-rate-chip {
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    border-radius: 999px;
    border: 1px solid currentColor;
    padding: 0.2rem 0.6rem;
    text-align: center;
    white-space: nowrap;
  }
  .aqi-chip {
    background: #202631;
  }
  .aqi-chip.unavailable {
    color: #aab4c2;
  }
  .uv-chip,
  .rain-rate-chip {
    background: #202631;
  }
  .outdoor-sub {
    font-size: 1.05rem;
    color: #aab4c2;
  }
  .outdoor-hilo {
    font-size: 1.05rem;
    color: #d7dee6;
  }
  .outdoor-spark {
    flex: 1;
    min-height: 2.2rem;
    min-width: 0;
    overflow: hidden;
    position: relative;
  }

  /* ---- Indoor ---- */
  .indoor-body {
    display: flex;
    align-items: center;
    height: 100%;
    gap: 0.85rem;
  }
  .indoor-reading {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 0 0 auto;
    min-width: 0;
  }
  .indoor-icon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    line-height: 1;
  }
  .indoor-temp {
    font-size: 4.4rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #fff;
  }
  .indoor-meta {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }
  .indoor-hum {
    font-size: 1.05rem;
    font-weight: 600;
    color: #c7cfd9;
  }
  .indoor-hilo {
    font-size: 1.05rem;
    color: #d7dee6;
  }

  /* ---- Battery hero ---- */
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
  .batt-status {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .batt-icon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    line-height: 1;
  }
  .batt-icon.charging :global(svg) {
    animation: batt-pulse 1.4s ease-in-out infinite;
  }
  @keyframes batt-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.45;
    }
  }
  .batt-indicator {
    font-weight: 600;
  }
  .batt-runtime {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    color: #c7cfd9;
    font-size: 0.76rem;
    line-height: 1;
    white-space: nowrap;
  }
  .batt-runtime strong {
    color: #aab4c2;
    font-size: 0.68rem;
    font-weight: 500;
    min-width: 2.5rem;
  }
  .battery-spark {
    flex: 1;
    min-height: 1.6rem;
    overflow: hidden;
  }

  /* ---- Bitcoin (mirrors Indoor's slot under Battery) ---- */
  .bitcoin-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    overflow: hidden;
  }
  .btc-top {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex: 0 0 auto;
  }
  .btc-icon {
    display: inline-flex;
    flex: 0 0 auto;
    line-height: 1;
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

  /* ---- Baro ---- */
  .baro-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.2rem;
  }
  .baro-head {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .baro-status-icon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    line-height: 1;
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
    color: #aab4c2;
  }
  .baro-spark {
    flex: 1;
    min-height: 1.4rem;
    overflow: hidden;
  }
  .baro-trend {
    font-size: 0.68rem;
    color: #aab4c2;
    text-transform: capitalize;
    line-height: 1;
  }

  /* ---- Sun & Moon ---- */
  .sunmoon-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.28rem;
    min-width: 0;
    overflow: hidden;
  }
  .sm-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.86rem;
    color: #c7cfd9;
    line-height: 1.15;
    white-space: nowrap;
    min-width: 0;
    max-width: 100%;
    overflow: hidden;
  }
  .sm-icon {
    display: inline-flex;
    flex: 0 0 auto;
    line-height: 1;
  }

  .sm-times,
  .sm-moon {
    white-space: nowrap;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sm-daylight {
    color: #aab4c2;
  }

  /* ---- Solar ---- */
  .solar-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    gap: 0.18rem;
  }
  .solar-head {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .solar-icon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    line-height: 1;
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
    color: #aab4c2;
  }
  .solar-sub {
    font-size: 0.68rem;
    color: #aab4c2;
    line-height: 1.15;
  }
  .solar-current {
    font-size: 0.74rem;
    line-height: 1.15;
  }
  .curtail-lamp {
    margin-top: 0.1rem;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    white-space: nowrap;
  }
  .lamp-dot {
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 50%;
    background: currentColor;
  }
  .lamp-dot.active {
    box-shadow: 0 0 0.25rem currentColor;
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
    color: #aab4c2;
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

  @media (prefers-reduced-motion: reduce) {
    .batt-icon.charging :global(svg) {
      animation: none;
    }
  }
</style>
