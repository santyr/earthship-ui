<script>
  import { dailyPvRaw, dailyPvClock } from '../energy/dailyPvState.js';
  import { parseDailyPvPotential, dailyPvForDate } from '../energy/dailyPvPotential.js';
  const dailyPv = $derived(parseDailyPvPotential($dailyPvRaw, { nowMs: $dailyPvClock }));
  import OhIcon from './OhIcon.svelte';
  import { colors } from './tokens.js';
  import { rainAmountText } from '../openhab/values.js';
  import { forecastCondition } from '../weather/presentation.js';

  let { days = [], variant = 'home', onselect = () => {} } = $props();

  const value = (raw, suffix = '') => (
    typeof raw === 'number' && Number.isFinite(raw) ? `${Math.round(raw)}${suffix}` : '—'
  );

  const pvTitle = (pv) => `${pv.calibrationScope && pv.calibrationScope !== 'none' ? 'Provisional, empirically adjusted over the next 24 hours; ' : 'Provisional ' }array DC potential before battery acceptance and demand limits; ${pv.fromAt} through ${pv.throughAt}.`;

  const accessibleName = (day) => [
    day.label,
    ...(dailyPvForDate(dailyPv, day.date) ? [`PV potential ${dailyPvForDate(dailyPv, day.date).potentialKwh.toFixed(1)} kilowatt hours`] : []),
    forecastCondition({ ...day.summary, isDay: true }).label,
    day.summary.temperatureScope === 'remaining' ? 'remaining hours' : 'full day',
    `high ${value(day.summary.highF, ' degrees')}`,
    `low ${value(day.summary.lowF, ' degrees')}`,
    day.summary.precipPct !== null ? `precipitation ${value(day.summary.precipPct, ' percent')}` : `precipitation ${rainAmountText(day.summary.precipSumIn) ?? (day.summary.precipSumIn === 0 ? '0.00 inches' : 'unavailable')}`,
    ...(day.summary.precipitationScope === 'remaining' ? ['precipitation covers remaining complete hours'] : []),
  ].join(', ');
</script>

<div class="daily-forecast" data-forecast-variant={variant}>
  {#if days.length === 0}
    <div class="forecast-empty" role="status">Forecast unavailable</div>
  {/if}
  {#each days as day, index (`${day.date ?? 'legacy'}-${day.label}-${index}`)}
    {@const condition = forecastCondition({ ...day.summary, isDay: true })}
    {@const pv = dailyPvForDate(dailyPv, day.date)}
    <button
      type="button"
      class="forecast-day"
      class:emphasized={index < 2}
      data-forecast-day={day.date ?? ''}
      aria-label={accessibleName(day)}
      onclick={() => onselect(day)}
    >
      <span class="day-label">{day.label}</span>
      <span class="day-icon" title={condition.label} data-condition-basis={condition.basis}><OhIcon icon={condition.icon} size="1.2rem" color={condition.color ?? 'currentColor'} /></span>
      <span class="day-hilo">
        {value(day.summary.highF, '°')} / {value(day.summary.lowF, '°')}
        {#if variant !== 'home' && day.summary.temperatureScope === 'remaining'}<small class="range-note">remaining</small>{/if}
      </span>
      <span class="day-meta">
        {#if day.summary.precipPct !== null}<span>{value(day.summary.precipPct, '%')}</span>{/if}
        {#if rainAmountText(day.summary.precipSumIn)}
          <span data-testid="day-rain-amount" style="color: {colors.rain}">{rainAmountText(day.summary.precipSumIn)}</span>
        {/if}
        {#if day.summary.precipPct === null && !rainAmountText(day.summary.precipSumIn)}<span>{day.summary.precipSumIn === 0 ? '0.00″' : 'Rain unavailable'}</span>{/if}
        {#if variant !== 'home' && day.summary.precipitationScope === 'remaining'}<small class="range-note" title={`Rain forecast from ${day.summary.precipitationFromAt} through ${day.summary.precipitationThroughAt}`}>remaining</small>{/if}
        {#if pv}<span aria-hidden="true"> · </span><span data-testid="daily-pv-potential" title={pvTitle(pv)}>PV {pv.potentialKwh.toFixed(1)} kWh</span>
        {:else if day.summary.pvKwh !== null}<span aria-hidden="true"> · </span><span>PV {value(day.summary.pvKwh, ' kWh')}</span>{/if}
      </span>
    </button>
  {/each}
</div>

<style>
  .daily-forecast {
    display: grid;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
  }

  .forecast-empty {
    grid-column: 1 / -1;
    align-self: center;
    justify-self: center;
    color: #94a3b8;
    font-size: 0.75rem;
  }

  .daily-forecast[data-forecast-variant='home'] {
    grid-template-columns: repeat(10, minmax(0, 1fr));
    gap: 0.3rem;
  }

  .daily-forecast[data-forecast-variant='weather'] {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: repeat(5, minmax(0, 1fr));
    grid-auto-flow: column;
    gap: 0.14rem 0.55rem;
  }

  .forecast-day {
    min-width: 0;
    min-height: 0;
    border: 1px solid transparent;
    border-radius: 0.45rem;
    background: transparent;
    color: #e6edf3;
    padding: 0.1rem;
    font: inherit;
    cursor: pointer;
  }

  .daily-forecast[data-forecast-variant='home'] .forecast-day {
    display: grid;
    grid-template-rows: repeat(4, minmax(0, auto));
    place-items: center;
    text-align: center;
  }

  /* Slightly larger forecast text on the home console for readability. */
  .daily-forecast[data-forecast-variant='home'] .day-label { font-size: 0.74rem; }
  .daily-forecast[data-forecast-variant='home'] .day-hilo { font-size: 0.9rem; }
  .daily-forecast[data-forecast-variant='home'] .day-meta { font-size: 0.64rem; }

  .daily-forecast[data-forecast-variant='weather'] .forecast-day {
    display: grid;
    grid-template-columns:
      minmax(3.5rem, 0.8fr)
      1.2rem
      minmax(4.8rem, 1fr)
      minmax(6.8rem, 1.25fr);
    column-gap: 0.25rem;
    align-items: center;
    text-align: left;
  }

  .forecast-day:hover,
  .forecast-day:focus-visible {
    border-color: #8b5cf6;
    background: rgba(139, 92, 246, 0.1);
    outline: none;
  }

  .day-label {
    min-width: 0;
    overflow: hidden;
    color: #aab4c2;
    font-size: 0.68rem;
    font-variant-caps: small-caps;
    letter-spacing: 0.04em;
    text-overflow: ellipsis;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .day-icon {
    display: grid;
    place-items: center;
    color: #c7cfd9;
  }

  .day-hilo {
    color: #e6edf3;
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    white-space: nowrap;
  }

  .emphasized .day-hilo {
    color: #c4b5fd;
  }

  .range-note { display: block; color: #94a3b8; font-size: .55rem; font-weight: 400; }

  .day-meta {
    color: #94a3b8;
    font-size: 0.58rem;
    white-space: nowrap;
  }

  .daily-forecast[data-forecast-variant='weather'] .day-meta {
    font-size: 0.66rem;
  }
</style>
