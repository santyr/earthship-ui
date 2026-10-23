<script>
  import { itemUpdateEvidence, thingStatuses } from '../lib/openhab/store.js';
  import { nativeCurrentSkyContext } from '../lib/weather/astroPresentation.js';
  import { stationPresentation, rainPeriodText } from '../lib/weather/stationPresentation.js';

  import { onMount } from 'svelte';
  import {
    historyExtremaForDay,
    localDayHistoryRange,
    outdoorConditionIcon,
  } from '../lib/ui/homeCardState.js';
  import { createLatestRefreshCoordinator } from '../lib/ui/latestRefresh.js';
  import { getClientOnce } from '../lib/openhab';
  let wallClock = $state(Date.now());
  let outdoorTodayHistory = $state([]);
  let temperatureHistoryDay = $state(null);
  const temperatureRefresh = createLatestRefreshCoordinator();
  const outdoorToday = $derived(historyExtremaForDay(
    outdoorTodayHistory, temperatureHistoryDay, wallClock,
    stationItems.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature,
  ));

  async function refreshOutdoorToday() {
    const range = localDayHistoryRange(new Date());
    if (!range) return;
    return temperatureRefresh.run(async (signal) => {
      for (let attempt = 0; attempt < 10; attempt++) {
        if (signal.aborted) return [];
        const client = getClientOnce();
        if (client) {
          try {
            return await client.getHistory('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', {
              ...range, includeStartState: true, signal,
            });
          } catch {
            return [];
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 300));
      }
      return [];
    }, (points) => {
      if (range.starttime !== localDayHistoryRange(new Date())?.starttime) return;
      temperatureHistoryDay = range.starttime;
      outdoorTodayHistory = points;
    });
  }

  onMount(() => {
    const update = () => {
      const priorDay = localDayHistoryRange(new Date(wallClock))?.starttime;
      wallClock = Date.now();
      if (localDayHistoryRange(new Date(wallClock))?.starttime !== priorDay) {
        temperatureHistoryDay = null;
        outdoorTodayHistory = [];
        refreshOutdoorToday();
      }
    };
    refreshOutdoorToday();
    const timer = setInterval(update, 5000);
    const historyTimer = setInterval(refreshOutdoorToday, 300000);
    document.addEventListener('visibilitychange', update);
    return () => {
      temperatureRefresh.destroy();
      clearInterval(timer);
      clearInterval(historyTimer);
      document.removeEventListener('visibilitychange', update);
    };
  });
  const astroContext = $derived({ states:$items, evidence:$itemUpdateEvidence, now:Math.max(wallClock, Date.now()),
    connected:$connection === 'live', sunOnline:$thingStatuses['astro:sun:local']?.status === 'ONLINE',
    moonOnline:$thingStatuses['astro:moon:local']?.status === 'ONLINE' });
  const skyIcon = $derived(outdoorConditionIcon($items.SkyConditionIcon, {
    ...nativeCurrentSkyContext(astroContext),
  }));
  // Task 5.1 — Weather console: current conditions, 14h hourly strip, 10-day
  // forecast, and measured wind/rain/pressure tiles. Mirrors Home's
  // dark-console aesthetic (Tile/StatTile chrome, tokens.colors,
  // click-to-chart via openChart) but is forecast/observation-focused
  // rather than power-flow-focused, so it gets its own grid.
  import Tile from '../lib/ui/Tile.svelte';
  import StatTile from '../lib/ui/StatTile.svelte';
  import OhIcon from '../lib/ui/OhIcon.svelte';
  import HourlyStrip from '../lib/ui/HourlyStrip.svelte';
  import DailyForecast from '../lib/ui/DailyForecast.svelte';
  import ForecastComparison from '../lib/ui/ForecastComparison.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { skyIconColor } from '../lib/ui/wmo.js';
  import { items, connection, num, fmt } from '../lib/openhab';
  import { openChart } from '../lib/ui/chartStore.js';
  import { openWeatherDetail } from '../lib/weather/detailStore.js';
  import {
    parseForecast10Day,
    parseLegacyDailyForecast,
    forecastDaysFromToday,
    hourlyForecastFromDetail,
  } from '../lib/weather/forecastDetail.js';

  function hasItem(name) {
    return Object.prototype.hasOwnProperty.call($items, name);
  }

  function onKeyActivate(e, fn) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  }

  // ---- Hourly (14h) ------------------------------------------------------
  const forecastDetail = $derived(parseForecast10Day($items.Forecast_10Day_JSON,
    { nowMs: wallClock }));
  const forecastHourly = $derived.by(() => {
    if (forecastDetail.status === 'ready') {
      return hourlyForecastFromDetail(forecastDetail, { nowMs: wallClock });
    }
    if (!forecastDetail.legacyFallbackAllowed) return [];
    try {
      const raw = $items.Forecast_Hourly_JSON;
      if (!raw || raw === 'NULL' || raw === 'UNDEF') return [];
      const arr = JSON.parse(raw);
      const currentHourMs = Math.floor(wallClock / 3_600_000) * 3_600_000;
      return Array.isArray(arr) ? arr.filter((hour) => {
        if (!hour?.at) return true; // Compatibility with undated legacy payloads.
        const atMs = Date.parse(hour.at);
        return Number.isFinite(atMs) && atMs >= currentHourMs;
      }).slice(0, 14) : [];
    } catch {
      return [];
    }
  });

  // ---- 10-day controls with null-safe legacy fallback ---------------------
  const legacyForecast = $derived(parseLegacyDailyForecast($items.Forecast_Daily_JSON));
  const forecastDays = $derived(
    forecastDetail.status === 'stale' || (forecastDetail.status !== 'ready' && !forecastDetail.legacyFallbackAllowed) ? []
      : forecastDetail.days.length > 0
        ? forecastDaysFromToday(forecastDetail, { nowMs: wallClock }) : legacyForecast
  );

  function selectForecastDay(day) {
    openWeatherDetail({ date: day.date, label: day.label });
  }

  const station = $derived(stationPresentation($items, { nowMs:Math.max(wallClock,Date.now()) }));
  const stationItems = $derived(station.mode === 'legacy' ? $items : {...$items,...station.current});
  const pressureValue = $derived(station.mode === 'legacy'
    ? stationItems.AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative : station.pressure.value);
  const pressureItem = $derived(station.mode === 'legacy'
    ? 'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative' : 'WeatherStation_PressureAbsoluteV2');
  const rainDay = $derived(station.mode === 'legacy' ? stationItems.AmbientWeatherWS2902A_RainFallDay : station.rain.day);

  // ---- Rain footer (mirrors Home's Rain tile) ------------------------------
  const rainFooter = $derived.by(() => {
    if (station.mode === 'v2') {
      const amount = value => value === null ? '—' : `${value.toFixed(2)}″`;
      return `event ${amount(station.rain.event)} · wk ${rainPeriodText(station.rain, 'week')} · mo ${rainPeriodText(station.rain, 'month')}`;
    }
    const parts = [];
    if (hasItem('AmbientWeatherWS2902A_RainFallEvent'))
      parts.push(`event ${fmt(stationItems.AmbientWeatherWS2902A_RainFallEvent, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallWeek'))
      parts.push(`wk ${fmt(stationItems.AmbientWeatherWS2902A_RainFallWeek, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallMonth'))
      parts.push(`mo ${fmt(stationItems.AmbientWeatherWS2902A_RainFallMonth, '″', 2)}`);
    return parts.join(' · ');
  });

  const baroTrend = $derived.by(() => {
    if (station.mode === 'v2') return station.pressure.trendLabel;
    const t = stationItems.AmbientWeatherWS2902A_PressureTrend;
    return t && t !== 'NULL' && t !== 'UNDEF' ? String(t).toLowerCase() : '—';
  });

  // ---- Click-to-chart handlers ---------------------------------------------
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
      series: [{ name: 'AmbientWeatherWS2902A_RainFallDay', color: colors.rain, label: 'Recorded rain/day' }],
      hours: 24,
    });
  }
  function openPressureChart() {
    openChart({
      title: 'Station pressure (absolute)',
      series: [
        {
          name: pressureItem,
          color: colors.label,
          label: 'Station pressure',
        },
      ],
      hours: 24,
    });
  }
</script>

<div class="weather-grid">
  <div class="cell current-cell">
    <Tile label="Current Conditions" accent={colors.temperature}>
      <div class="current-body">
        <div class="cur-main">
          <span class="cur-icon">
            <OhIcon
              icon={skyIcon}
              size="2.4rem"
              color={skyIconColor(skyIcon) ?? 'currentColor'}
            />
          </span>
          <span class="cur-temp">{fmt(stationItems.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°')}</span>
          <div class="cur-meta">
            <div class="cur-feels">
              feels like {fmt(stationItems.AmbientWeatherWS2902A_ApparentTemperature, '°')}
            </div>
            <div class="cur-hilo">
              H {fmt(outdoorToday.high, '°')} &nbsp;/&nbsp; L {fmt(outdoorToday.low, '°')}
            </div>
            <div class="cur-hum">
              {fmt(stationItems.AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity, '%')} RH
            </div>
          </div>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell hourly-cell">
    <Tile label="Next 14 Hours" accent={colors.forecast}>
      <div class="hourly-wrap">
        {#if forecastDetail.status === 'stale'}
          <div class="forecast-unavailable" role="status">Forecast stale</div>
        {:else if forecastDetail.status !== 'ready' && !forecastDetail.legacyFallbackAllowed}
          <div class="forecast-unavailable" role="status">Forecast unavailable</div>
        {:else}
          <HourlyStrip hours={forecastHourly} height={96} />
        {/if}
      </div>
    </Tile>
  </div>

  <div class="cell daily-cell">
    <Tile label={forecastDetail.provider === 'weathernext3' ? '10-Day Forecast · WeatherNext 3' : '10-Day Forecast'} accent={colors.forecast}>
      <DailyForecast days={forecastDays} variant="weather" onselect={selectForecastDay} />
      {#if hasItem('Forecast_Provider_Status_JSON') || hasItem('Forecast_Comparison_JSON') || hasItem('Forecast_Local_Shadow_JSON')}
        <ForecastComparison statusRaw={$items.Forecast_Provider_Status_JSON} comparisonRaw={$items.Forecast_Comparison_JSON} localRaw={$items.Forecast_Local_Shadow_JSON} nowMs={wallClock} connected={$connection === 'live'} />
      {/if}
    </Tile>
  </div>

  <div
    class="cell wind-cell clickable"
    role="button"
    tabindex="0"
    onclick={openWindChart}
    onkeydown={(e) => onKeyActivate(e, openWindChart)}
  >
    <StatTile
      label="Wind"
      value={fmt(stationItems.AmbientWeatherWS2902A_WindSpeed, '', 0)}
      unit=" mph"
      accent={colors.wind}
      footer={`gust ${fmt(stationItems.AmbientWeatherWS2902A_WindGust, ' mph', 0)}`}
    />
  </div>

  <div
    class="cell rain-cell clickable"
    title="Recorded rainfall: accepted continuous counter increments; unknown gaps are excluded. Complete interval coverage remains separately qualified."
    role="button"
    tabindex="0"
    onclick={openRainChart}
    onkeydown={(e) => onKeyActivate(e, openRainChart)}
  >
    <StatTile
      label="Rain"
      value={station.mode === 'v2' ? rainPeriodText(station.rain, 'day') : fmt(rainDay, '', 2)}
      unit={station.mode === 'v2' ? '' : '″'}
      accent={colors.rain}
      footer={rainFooter}
    />
  </div>

  <div
    class="cell pressure-cell clickable"
    role="button"
    tabindex="0"
    onclick={openPressureChart}
    onkeydown={(e) => onKeyActivate(e, openPressureChart)}
  >
    <StatTile
      label="Station pressure"
      value={fmt(pressureValue, '', 2)}
      unit=" inHg"
      accent={colors.label}
      footer={baroTrend}
    />
  </div>
</div>

<style>
  .daily-cell { position: relative; }
  .weather-grid {
    block-size: 100%;
    min-width: 0;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows:
      minmax(0, 0.75fr) minmax(0, 1.05fr)
      minmax(0, 1.2fr) minmax(0, 0.6fr);
    grid-template-areas:
      'current current current current current current'
      'hourly hourly hourly hourly hourly hourly'
      'daily daily daily daily daily daily'
      'wind wind rain rain pressure pressure';
    gap: 0.75rem;
    overflow: hidden;
  }
  .cell {
    min-width: 0;
    min-height: 0;
    overflow: hidden;
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

  .current-cell {
    grid-area: current;
  }
  .hourly-cell {
    grid-area: hourly;
  }
  .daily-cell {
    grid-area: daily;
    position: relative;
  }
  .wind-cell {
    grid-area: wind;
  }
  .rain-cell {
    grid-area: rain;
  }
  .pressure-cell {
    grid-area: pressure;
  }

  /* ---- Current conditions ---- */
  .current-body {
    display: flex;
    align-items: center;
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
  .cur-main {
    display: flex;
    align-items: center;
    min-width: 0;
    min-height: 0;
    gap: 0.9rem;
  }
  .cur-icon {
    display: inline-flex;
    align-items: center;
    line-height: 1;
  }
  .cur-temp {
    font-size: 3.4rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #f59e0b;
  }
  .cur-meta {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.9rem;
    color: #c7cfd9;
  }
  .cur-feels {
    color: #8b93a1;
  }
  .cur-hum {
    color: #8b93a1;
  }

  /* ---- Hourly strip ---- */
  .hourly-wrap {
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
  .forecast-unavailable {
    display: grid;
    place-items: center;
    height: 100%;
    color: #94a3b8;
    font-size: 0.75rem;
  }

</style>
