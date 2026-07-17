<script>
  // Task 4.1 — Energy console: battery + solar + forecast story with
  // history charts. Reuses Home's dark instrument-panel aesthetic (Tile /
  // StatTile chrome, tokens.colors) but favors inline HistoryChart panels
  // over Home's click-to-modal pattern, since this screen IS the charts.
  import Tile from '../lib/ui/Tile.svelte';
  import StatTile from '../lib/ui/StatTile.svelte';
  import HistoryChart from '../lib/ui/HistoryChart.svelte';
  import { colors } from '../lib/ui/tokens.js';
  import { items, num, fmt, socBands, runtimeText } from '../lib/openhab';

  // ---- Battery / SoC -------------------------------------------------------
  const soc = $derived(num($items.BMS_SOC));
  const socColor = $derived(socBands(soc));
  const trough = $derived(num($items.Predicted_SoC_Trough_Tomorrow));
  const troughText = $derived(trough === null ? '—' : `${Math.round(trough)}%`);

  const socSeries = $derived([
    { name: 'BMS_SOC', color: socColor, label: 'SoC' },
    {
      name: 'Predicted_SoC_Trough_Tomorrow',
      color: colors.forecast,
      label: 'Predicted trough',
      dashedFromNow: true,
    },
  ]);

  // ---- Runtime + basis ------------------------------------------------------
  const basisRaw = $derived(
    $items.BMS_Runtime_Basis && $items.BMS_Runtime_Basis !== 'NULL' && $items.BMS_Runtime_Basis !== 'UNDEF'
      ? String($items.BMS_Runtime_Basis).toLowerCase()
      : ''
  );
  const basisLabel = $derived.by(() => {
    if (basisRaw === 'bms') return 'live';
    if (basisRaw === 'now') return 'projected';
    if (basisRaw === 'evening') return 'overnight';
    return basisRaw || '—';
  });

  // ---- PV production --------------------------------------------------------
  const pvToday = $derived(num($items.MPPT60_EnergyFromPV_Today));
  const pvPredicted = $derived(num($items.Predicted_PV_Today_kWh));
  const pvError = $derived(num($items.Forecast_PV_Error_7d));
  const pvAccuracyBadge = $derived(pvError === null ? 'calibrating' : `±${Math.round(Math.abs(pvError))}% (7d)`);

  // ---- Curtailment ------------------------------------------------------
  const curtailHours = $derived(num($items.Predicted_Curtailment_Hours));
  const curtailPct = $derived(curtailHours === null ? 0 : Math.max(0, Math.min(100, (curtailHours / 24) * 100)));
  const curtailText = $derived(curtailHours === null ? '—' : `${curtailHours.toFixed(1)} h`);

  // ---- 7-day PV outlook -------------------------------------------------
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

  function dayLabel(i, dStr) {
    if (i === 1) return 'Tomorrow';
    if (!dStr || dStr === 'NULL' || dStr === 'UNDEF') return i === 0 ? 'Today' : `D${i + 1}`;
    return String(dStr);
  }

  const pvOutlook = $derived.by(() => {
    const days = forecastDaily.slice(0, 7).map((d, i) => ({ label: dayLabel(i, d.d), pv: num(d.pv) }));
    const maxPv = Math.max(1, ...days.map((d) => d.pv ?? 0));
    return days.map((d) => ({ ...d, pct: d.pv === null ? 0 : Math.max(2, (d.pv / maxPv) * 100) }));
  });

  // ---- Battery vitals ------------------------------------------------------
  const battTemp = $derived(fmt($items.BMS_Temperature, '°'));
  const battCycles = $derived(fmt($items.BMS_Charge_Cycles));
  const battCapacity = $derived(fmt($items.BMS_Capacity_Remaining_Ah, ' Ah', 1));
  const commsOk = $derived($items.BMS_Comms_Status === 'OK' || $items.BMS_Comms_Status === 'ON');
  const devicePresent = $derived($items.BMS_DevicePresent === 'ON' || $items.BMS_DevicePresent === 'OK');
  const bmsHealthy = $derived(commsOk && devicePresent);
</script>

<div class="energy-grid">
  <div class="cell hero-cell">
    <Tile label="Battery — 24h + tonight's forecast" accent={socColor}>
      <div class="hero-body">
        <div class="hero-chart"><HistoryChart series={socSeries} hours={24} height="100%" /></div>
        <div class="hero-footer">
          <span class="hero-soc" style="color: {socColor}">SoC {soc === null ? '—' : Math.round(soc) + '%'}</span>
          <span class="hero-trough" style="color: {colors.forecast}">predicted trough tonight: {troughText}</span>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell pv-cell">
    <Tile label="Solar PV" accent={colors.solar}>
      <div class="pv-body">
        <div class="pv-top">
          <div class="pv-numbers">
            <span class="pv-today">{pvToday === null ? '—' : pvToday.toFixed(1)}</span>
            <span class="pv-unit">kWh today</span>
          </div>
          <div class="pv-sub">of {pvPredicted === null ? '—' : pvPredicted.toFixed(1)} kWh predicted</div>
          <span class="pv-badge">{pvAccuracyBadge}</span>
        </div>
        <div class="pv-chart">
          <HistoryChart
            series={[{ name: 'MPPT60_PV_Power', color: colors.solar, label: 'PV Power' }]}
            hours={24}
            height="100%"
          />
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell runtime-cell">
    <Tile label="Runtime" accent={colors.label}>
      <div class="runtime-body">
        <div class="runtime-value">{runtimeText(num($items.BMS_TimeToDischarge_Smoothed))}</div>
        <div class="runtime-basis">{basisLabel}</div>
      </div>
    </Tile>
  </div>

  <div class="cell curtail-cell">
    <Tile label="Curtailment (today)" accent={colors.advisory}>
      <div class="curtail-body">
        <div class="curtail-value">{curtailText}</div>
        <div class="curtail-bar-track">
          <div class="curtail-bar-fill" style="width: {curtailPct}%; background: {colors.advisory}"></div>
        </div>
      </div>
    </Tile>
  </div>

  <div class="cell outlook-cell">
    <Tile label="7-Day PV Outlook" accent={colors.solar}>
      <div class="outlook-body">
        {#if pvOutlook.length === 0}
          <div class="outlook-empty">—</div>
        {:else}
          {#each pvOutlook as d, i (i)}
            <div class="outlook-day">
              <div class="outlook-bar-track">
                <div class="outlook-bar-fill" style="height: {d.pct}%"></div>
              </div>
              <div class="outlook-label">{d.label}</div>
              <div class="outlook-value">{d.pv === null ? '—' : d.pv.toFixed(1)}</div>
            </div>
          {/each}
        {/if}
      </div>
    </Tile>
  </div>

  <div class="cell vitals-cell">
    <Tile label="Battery Vitals" accent={colors.label}>
      <div class="vitals-body">
        <div class="vital">
          <div class="vital-label">Temp</div>
          <div class="vital-value">{battTemp}</div>
        </div>
        <div class="vital">
          <div class="vital-label">Cycles</div>
          <div class="vital-value">{battCycles}</div>
        </div>
        <div class="vital">
          <div class="vital-label">Capacity</div>
          <div class="vital-value">{battCapacity}</div>
        </div>
        <div class="vital">
          <div class="vital-label">BMS Health</div>
          <div class="vital-value vital-lamp">
            <span class="lamp-dot" class:ok={bmsHealthy}></span>
            {bmsHealthy ? 'OK' : 'Fault'}
          </div>
        </div>
      </div>
    </Tile>
  </div>
</div>

<style>
  .energy-grid {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-template-rows: minmax(15rem, 1.3fr) minmax(9rem, 1fr) auto auto;
    grid-template-areas:
      'hero hero hero hero hero hero'
      'pv pv pv runtime curtail curtail'
      'outlook outlook outlook outlook outlook outlook'
      'vitals vitals vitals vitals vitals vitals';
    gap: 0.75rem;
  }
  .cell {
    min-width: 0;
    min-height: 0;
  }
  .cell :global(.tile) {
    height: 100%;
  }
  .hero-cell {
    grid-area: hero;
  }
  .pv-cell {
    grid-area: pv;
  }
  .runtime-cell {
    grid-area: runtime;
  }
  .curtail-cell {
    grid-area: curtail;
  }
  .outlook-cell {
    grid-area: outlook;
  }
  .vitals-cell {
    grid-area: vitals;
  }

  /* ---- Hero SoC chart ---- */
  .hero-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0.4rem;
  }
  .hero-chart {
    flex: 1;
    min-height: 0;
  }
  .hero-footer {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 0.8rem;
    font-weight: 600;
    flex: 0 0 auto;
  }

  /* ---- PV production ---- */
  .pv-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0.4rem;
  }
  .pv-top {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.5rem;
    flex: 0 0 auto;
  }
  .pv-numbers {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
  }
  .pv-today {
    font-size: 1.6rem;
    font-weight: 700;
    color: #eab308;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .pv-unit {
    font-size: 0.75rem;
    color: #8b93a1;
  }
  .pv-sub {
    font-size: 0.75rem;
    color: #8b93a1;
  }
  .pv-badge {
    margin-left: auto;
    font-size: 0.68rem;
    letter-spacing: 0.02em;
    background: #2a2410;
    color: #eab308;
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
  }
  .pv-chart {
    flex: 1;
    min-height: 0;
  }

  /* ---- Runtime ---- */
  .runtime-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    height: 100%;
    gap: 0.3rem;
  }
  .runtime-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .runtime-basis {
    font-size: 0.72rem;
    color: #8b93a1;
    text-transform: capitalize;
  }

  /* ---- Curtailment ---- */
  .curtail-body {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 100%;
    gap: 0.5rem;
  }
  .curtail-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .curtail-bar-track {
    height: 0.5rem;
    border-radius: 999px;
    background: #1c2230;
    overflow: hidden;
  }
  .curtail-bar-fill {
    height: 100%;
    border-radius: 999px;
  }

  /* ---- 7-day PV outlook ---- */
  .outlook-body {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 0.5rem;
    height: 100%;
    align-items: end;
  }
  .outlook-empty {
    grid-column: span 7;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #8b93a1;
    height: 100%;
  }
  .outlook-day {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    height: 100%;
  }
  .outlook-bar-track {
    flex: 1;
    width: 60%;
    display: flex;
    align-items: flex-end;
    min-height: 2.5rem;
  }
  .outlook-bar-fill {
    width: 100%;
    background: #eab308;
    border-radius: 0.2rem 0.2rem 0 0;
    min-height: 2px;
  }
  .outlook-label {
    font-size: 0.65rem;
    color: #8b93a1;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-variant-caps: small-caps;
  }
  .outlook-value {
    font-size: 0.72rem;
    font-weight: 600;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
  }

  /* ---- Battery vitals ---- */
  .vitals-body {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    height: 100%;
    align-items: center;
    gap: 0.5rem;
  }
  .vital {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .vital-label {
    font-size: 0.68rem;
    color: #8b93a1;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-variant-caps: small-caps;
  }
  .vital-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
  }
  .vital-lamp {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.95rem;
  }
  .lamp-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #ef4444;
    flex-shrink: 0;
  }
  .lamp-dot.ok {
    background: #22c55e;
  }
</style>
