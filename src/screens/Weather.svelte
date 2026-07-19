<script>
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
  import { colors } from '../lib/ui/tokens.js';
  import { items, num, fmt } from '../lib/openhab';
  import { openChart } from '../lib/ui/chartStore.js';
  import { openWeatherDetail } from '../lib/weather/detailStore.js';
  import {
    parseForecast10Day,
    parseLegacyDailyForecast,
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

  // ---- AQI (EPA bands) -------------------------------------------------
  // Forecast_AQI is a categorical refresh/status surface. Current conditions
  // must come only from the separately provisioned numeric Current_US_AQI item.
  function currentAqi(raw) {
    const text = typeof raw === 'number' ? String(raw) : String(raw ?? '').trim();
    const unavailable = {
      value: null,
      color: '#6b7280',
      band: 'Current sensor not configured',
      status: 'unavailable',
    };
    if (!/^(?:\d+\.?\d*|\.\d+)$/.test(text)) return unavailable;
    const value = Math.round(Number(text));
    if (!Number.isFinite(value) || value < 0) return unavailable;
    if (value <= 50) return { value, color: '#22c55e', band: 'Good', status: 'good' };
    if (value <= 100) return { value, color: '#eab308', band: 'Moderate', status: 'moderate' };
    if (value <= 150) {
      return { value, color: '#f97316', band: 'Unhealthy for sensitive groups', status: 'unhealthy' };
    }
    if (value <= 200) return { value, color: '#ef4444', band: 'Unhealthy', status: 'unhealthy' };
    if (value <= 300) return { value, color: '#a855f7', band: 'Very unhealthy', status: 'critical' };
    if (value <= 500) return { value, color: '#991b1b', band: 'Hazardous', status: 'critical' };
    return { value, color: '#ef4444', band: 'Beyond index', status: 'critical' };
  }
  const aqi = $derived(currentAqi($items.Current_US_AQI));

  // ---- Hourly (14h) ------------------------------------------------------
  const forecastHourly = $derived.by(() => {
    try {
      const raw = $items.Forecast_Hourly_JSON;
      if (!raw || raw === 'NULL' || raw === 'UNDEF') return [];
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.slice(0, 14) : [];
    } catch {
      return [];
    }
  });

  // ---- 10-day controls with null-safe legacy fallback ---------------------
  const forecastDetail = $derived(parseForecast10Day($items.Forecast_10Day_JSON));
  const legacyForecast = $derived(parseLegacyDailyForecast($items.Forecast_Daily_JSON));
  const forecastDays = $derived(
    forecastDetail.days.length > 0 ? forecastDetail.days : legacyForecast
  );

  function selectForecastDay(day) {
    openWeatherDetail({ date: day.date, label: day.label });
  }

  // ---- Rain footer (mirrors Home's Rain tile) ------------------------------
  const rainFooter = $derived.by(() => {
    const parts = [];
    if (hasItem('AmbientWeatherWS2902A_RainFallEvent'))
      parts.push(`event ${fmt($items.AmbientWeatherWS2902A_RainFallEvent, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallWeek'))
      parts.push(`wk ${fmt($items.AmbientWeatherWS2902A_RainFallWeek, '″', 2)}`);
    if (hasItem('AmbientWeatherWS2902A_RainFallMonth'))
      parts.push(`mo ${fmt($items.AmbientWeatherWS2902A_RainFallMonth, '″', 2)}`);
    return parts.join(' · ');
  });

  const baroTrend = $derived.by(() => {
    const t = $items.AmbientWeatherWS2902A_PressureTrend;
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
      series: [{ name: 'AmbientWeatherWS2902A_RainFallDay', color: colors.rain, label: 'Rain/day' }],
      hours: 24,
    });
  }
  function openPressureChart() {
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
</script>

<div class="weather-grid">
  <div class="cell current-cell">
    <Tile label="Current Conditions" accent={colors.temperature}>
      <div class="current-body">
        <div class="cur-main">
          <span class="cur-icon"><OhIcon icon={$items.SkyConditionIcon} size="2.4rem" /></span>
          <span class="cur-temp">{fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°')}</span>
          <div class="cur-meta">
            <div class="cur-feels">
              feels like {fmt($items.AmbientWeatherWS2902A_ApparentTemperature, '°')}
            </div>
            <div class="cur-hilo">
              H {fmt($items.OutdoorTemp_24h_High, '°')} &nbsp;/&nbsp; L {fmt($items.OutdoorTemp_24h_Low, '°')}
            </div>
            <div class="cur-hum">
              {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity, '%')} RH
            </div>
          </div>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell aqi-cell">
    <Tile label="Modeled US AQI" accent={aqi.color}>
      <div class="aqi-body" data-source-item="Current_US_AQI" data-aqi-status={aqi.status}>
        {#if aqi.value === null}
          <div class="aqi-unavailable">Unavailable</div>
        {:else}
          <div class="aqi-value" style="color: {aqi.color}">{aqi.value}</div>
        {/if}
        <div class="aqi-band" style="color: {aqi.color}">{aqi.band}</div>
      </div>
    </Tile>
  </div>

  <div class="cell hourly-cell">
    <Tile label="Next 14 Hours" accent={colors.forecast}>
      <div class="hourly-wrap">
        <HourlyStrip hours={forecastHourly} height={96} />
      </div>
    </Tile>
  </div>

  <div class="cell daily-cell">
    <Tile label="10-Day Forecast" accent={colors.forecast}>
      <DailyForecast days={forecastDays} variant="weather" onselect={selectForecastDay} />
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
      value={fmt($items.AmbientWeatherWS2902A_WindSpeed, '', 0)}
      unit=" mph"
      accent={colors.wind}
      footer={`gust ${fmt($items.AmbientWeatherWS2902A_WindGust, ' mph', 0)}`}
    />
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

  <div
    class="cell pressure-cell clickable"
    role="button"
    tabindex="0"
    onclick={openPressureChart}
    onkeydown={(e) => onKeyActivate(e, openPressureChart)}
  >
    <StatTile
      label="Pressure"
      value={fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative, '', 2)}
      unit=" inHg"
      accent={colors.label}
      footer={baroTrend}
    />
  </div>
</div>

<style>
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
      'current current current current aqi aqi'
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
  .aqi-cell {
    grid-area: aqi;
  }
  .hourly-cell {
    grid-area: hourly;
  }
  .daily-cell {
    grid-area: daily;
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

  /* ---- AQI ---- */
  .aqi-body {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 0.15rem;
  }
  .aqi-unavailable {
    color: #8b93a1;
    font-size: 1rem;
    font-weight: 650;
    line-height: 1.1;
  }
  .aqi-value {
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .aqi-band {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    text-align: center;
  }

  /* ---- Hourly strip ---- */
  .hourly-wrap {
    height: 100%;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

</style>
