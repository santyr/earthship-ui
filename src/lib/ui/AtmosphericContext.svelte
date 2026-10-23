<script>
  import { atmosphericCapabilityAt } from '../weather/atmosphericForecast.js';
  let { product, hours = [], nowMs = Date.now(), timezone = 'America/Denver' } = $props();
  let selectedAt = $state('');
  const available = $derived(hours.map(h => atmosphericCapabilityAt(product, h.at)).filter(Boolean));
  const selected = $derived(available.find(h => h.at === selectedAt) ?? available[0] ?? null);
  const moisture = $derived(product?.atmosphere?.moisture);
  const labels = {temperature:'temperature',dewpoint:'dew point',pressure:'sea-level pressure',speed:'scalar wind',u:'wind u',v:'wind v',total:'total cloud',high:'high cloud',medium:'mid cloud',low:'low cloud'};
  const sources = $derived.by(() => {
    const unique = new Map();
    for (const [name, source] of Object.entries(selected?.fieldSources ?? {})) {
      if (!source) continue;
      if (!unique.has(source.ref_sha256)) unique.set(source.ref_sha256, {source, labels:[]});
      unique.get(source.ref_sha256).labels.push(labels[name]);
    }
    return [...unique.values()];
  });
  const comparison = $derived(({forecast_air_drier:'Forecast outdoor air is drier than current qualified indoor air.',forecast_air_wetter:'Forecast outdoor air is wetter than current qualified indoor air.',similar_vapor_pressure:'Forecast outdoor and current qualified indoor air have similar vapor pressure.'})[moisture?.comparison]);
  const missing = $derived((moisture?.missingDependencies ?? []).map(reason => ({
    qualified_indoor_temperature_and_relative_humidity:'Qualified indoor temperature and humidity required.',
    compatible_same_zone_indoor_temperature_and_humidity:'Compatible indoor temperature and humidity from the same zone required.',
    forecast_dewpoint:'Forecast dew point unavailable.',
    outdoor_target_within_two_hours:'Indoor comparison requires an outdoor target within two hours.',
    indoor_temperature_outside_diagnostic_domain:'Indoor temperature is outside the moisture diagnostic domain.',
    indoor_evidence_expired:'Indoor evidence expired; qualified current temperature and humidity required.',
  })[reason]).filter(Boolean).join(' '));
  const number = (v, unit = '', digits = 1) => typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(digits)}${unit}` : 'unavailable';
  const age = at => {const minutes = Math.max(0, Math.floor((nowMs - Date.parse(at))/60000));return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes/60)}h`;};
  const hourLabel = at => new Date(at).toLocaleTimeString('en-US', {timeZone:timezone,hour:'numeric',minute:'2-digit'});
</script>

{#if selected}
  <details class="atmosphere-context">
    <summary>Forecast atmosphere · raw diagnostic</summary>
    <div class="atmosphere-body">
      <label class="hour-picker">Forecast hour
        <select aria-label="Atmospheric forecast hour" value={selected.at} onchange={event => selectedAt = event.currentTarget.value}>
          {#each available as hour (hour.at)}<option value={hour.at}>{hourLabel(hour.at)}</option>{/each}
        </select>
      </label>
      <div class="quantities">
        <span>Dew point: {number(selected.dewpointF, '°F')}</span>
        <span>Diagnostic RH: {number(selected.relativeHumidityPct, '%')}</span>
        <span>Sea-level pressure: {number(selected.pressureHpa, ' hPa')}</span>
        <span>Scalar mean wind: {number(selected.scalarSpeedMph, ' mph')}</span>
        <span>Mean vector: {number(selected.vectorMagnitudeMph, ' mph')} from {number(selected.windFromDegrees, '°', 0)}</span>
        <span>Cloud total {number(selected.clouds.total, '%', 0)} · high {number(selected.clouds.high, '%', 0)} · mid {number(selected.clouds.medium, '%', 0)} · low {number(selected.clouds.low, '%', 0)}</span>
      </div>
      <p>Diagnostic RH from forecast mean temperature and dew point, not ensemble mean RH. Scalar speed and mean vector are distinct; neither is a gust. Cloud layers overlap.</p>
      {#if moisture?.targetAt === selected.at}
        {#if moisture.mode === 'qualified_comparison'}
          <p class="moisture-comparison">{comparison} Indoor {number(moisture.indoorTemperatureF, '°F')} / {number(moisture.indoorRelativeHumidityPct, '% RH')}; vapor pressure outside {number(moisture.outdoorVaporPressureHpa, ' hPa', 2)}, inside {number(moisture.indoorVaporPressureHpa, ' hPa', 2)}.</p>
        {:else}
          <p>{missing} Outdoor vapor pressure: {number(moisture.outdoorVaporPressureHpa, ' hPa', 2)}.</p>
        {/if}
      {:else}
        <p>Indoor moisture comparison unavailable for this forecast hour.</p>
      {/if}
      <p>Current temperature model does not use these added fields. Surface condensation not assessed.</p>
      {#each sources as entry (entry.source.ref_sha256)}
        <p class="source" title={`Run ${entry.source.run_id}; available ${entry.source.available_at}`}>
          {entry.labels.join(', ')}: initialized {age(entry.source.initialized_at)} ago; available {age(entry.source.available_at)} ago
        </p>
      {/each}
      {#if product.atmosphere.selectionTruncated}<p>Source scan reached its limit; some fields may be unavailable.</p>{/if}
      {#if product.atmosphere.withheldSources}<p>{product.atmosphere.withheldSources} unavailable original sources withheld.</p>{/if}
    </div>
  </details>
{/if}

<style>
  .atmosphere-context { text-align:left; color:#cbd5e1; margin:.15rem 0; border-top:1px solid #273244; font-size:.73rem; }
  summary { cursor:pointer; min-height:2.25rem; align-content:center; color:#93c5fd; }
  summary:focus-visible, select:focus-visible { outline:2px solid #a78bfa; outline-offset:1px; }
  .atmosphere-body { max-height:10rem; overflow:auto; padding:0 .25rem .3rem; }
  .hour-picker { display:flex; align-items:center; gap:.6rem; margin-bottom:.3rem; }
  select { background:#17202c; color:#e5e7eb; border:1px solid #475569; border-radius:.25rem; min-height:2rem; }
  .quantities { display:flex; flex-wrap:wrap; gap:.25rem 1rem; font-variant-numeric:tabular-nums; }
  p { margin:.25rem 0; line-height:1.35; }
  .source { color:#94a3b8; font-size:.69rem; }
  .moisture-comparison { color:#bfdbfe; }
</style>
