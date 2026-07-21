<script>
  import OhIcon from './OhIcon.svelte';
  import { colors } from './tokens.js';
  import { rainAmountText } from '../openhab/values.js';
  import { wmoIcon, wmoLabel, wmoColor } from './wmo.js';

  let { days = [], variant = 'home', onselect = () => {} } = $props();

  const value = (raw, suffix = '') => (
    typeof raw === 'number' && Number.isFinite(raw) ? `${Math.round(raw)}${suffix}` : '—'
  );

  const accessibleName = (day) => [
    day.label,
    wmoLabel(day.summary.weatherCode),
    `high ${value(day.summary.highF, ' degrees')}`,
    `low ${value(day.summary.lowF, ' degrees')}`,
    `precipitation ${value(day.summary.precipPct, ' percent')}`,
  ].join(', ');
</script>

<div class="daily-forecast" data-forecast-variant={variant}>
  {#each days as day, index (`${day.date ?? 'legacy'}-${day.label}-${index}`)}
    <button
      type="button"
      class="forecast-day"
      class:emphasized={index < 2}
      data-forecast-day={day.date ?? ''}
      aria-label={accessibleName(day)}
      onclick={() => onselect(day)}
    >
      <span class="day-label">{day.label}</span>
      <span class="day-icon"><OhIcon icon={wmoIcon(day.summary.weatherCode)} size="1.2rem" color={wmoColor(day.summary.weatherCode) ?? 'currentColor'} /></span>
      <span class="day-hilo">
        {value(day.summary.highF, '°')} / {value(day.summary.lowF, '°')}
      </span>
      <span class="day-meta">
        <span>{value(day.summary.precipPct, '%')}</span>
        {#if rainAmountText(day.summary.precipSumIn)}
          <span data-testid="day-rain-amount" style="color: {colors.rain}">{rainAmountText(day.summary.precipSumIn)}</span>
        {/if}
        <span aria-hidden="true"> · </span>
        <span>PV {value(day.summary.pvKwh, ' kWh')}</span>
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

  .day-meta {
    color: #94a3b8;
    font-size: 0.58rem;
    white-space: nowrap;
  }

  .daily-forecast[data-forecast-variant='weather'] .day-meta {
    font-size: 0.66rem;
  }
</style>
