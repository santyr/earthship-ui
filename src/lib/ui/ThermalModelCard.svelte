<script>
  import Tile from './Tile.svelte';
  import ThermalModelPlot from './ThermalModelPlot.svelte';

  let { result, nowMs = Date.now() } = $props();

  function temperature(value) {
    return Number.isFinite(value) ? `${Number(value.toFixed(1))}°F` : '—';
  }

  function modeledDelta(value) {
    if (!Number.isFinite(value)) return null;
    const rounded = Number(Math.abs(value).toFixed(1));
    const sign = value < 0 ? '−' : value > 0 ? '+' : '';
    return `${sign}${rounded}°F modeled`;
  }

  function ageText(generatedAtMs, currentMs) {
    if (!Number.isFinite(generatedAtMs) || !Number.isFinite(currentMs) || currentMs < generatedAtMs) {
      return null;
    }
    const minutes = Math.floor((currentMs - generatedAtMs) / 60_000);
    if (minutes < 60) return `${minutes}m old`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h old`;
  }

  const unavailable = $derived(!result || result.state === 'unavailable');
  const outputAge = $derived(unavailable ? null : ageText(result.generatedAtMs, nowMs));
  const modelAge = $derived(unavailable ? null : ageText(result.modelCreatedAtMs, nowMs));
  const trainingAge = $derived(unavailable ? null : ageText(result.trainedThroughMs, nowMs));
  const freshness = $derived(unavailable
    ? 'Output unavailable'
    : `Output ${result.state === 'stale' ? 'stale' : 'current'}${outputAge ? ` · ${outputAge}` : ''}`);
  const confidence = $derived(unavailable
    ? 'Confidence unavailable'
    : `${result.confidence.slice(0, 1).toUpperCase()}${result.confidence.slice(1)} confidence`);
</script>

<div class="thermal-model-card" data-state={result?.state || 'unavailable'}>
  <Tile label="Thermal Model" accent="#a78bfa" fill clip padding="0.65rem 0.75rem">
    <div class="card-body">
      <div class="status-row">
        <span class="shadow-badge">SHADOW</span>
        <span class:stale={result?.state === 'stale'} class="freshness">{freshness}</span>
        <span class="confidence">{confidence}</span>
      </div>

      {#if unavailable}
        <div class="unavailable">Thermal model unavailable</div>
      {:else}
        <div class="model-ages" aria-label="Shadow model evidence ages">
          <span>Model created · {modelAge ?? 'age unavailable'}</span>
          <span>Training data through · {trainingAge ?? 'age unavailable'}</span>
        </div>
        <div class="metrics">
          <div class="metric">
            <span>Next hallway high</span>
            <strong>{temperature(result.hallwayHigh)}</strong>
          </div>
          <div class="metric">
            <span>Next hallway low</span>
            <strong>{temperature(result.hallwayLow)}</strong>
          </div>
          <div class="metric">
            <span>Morning mass</span>
            <strong>{temperature(result.morningMass)}</strong>
          </div>
        </div>

        <div class="model-row">
          {#if result.ventWindow}
            <div class="window">
              <span>Candidate vent window</span>
              <strong>{result.ventWindow}</strong>
            </div>
          {/if}
          <div class="effects">
            {#if modeledDelta(result.effect?.hallwayPeakDeltaF) !== null}
              <span>Peak delta <strong>{modeledDelta(result.effect.hallwayPeakDeltaF)}</strong></span>
            {/if}
            {#if modeledDelta(result.effect?.morningMassDeltaF) !== null}
              <span>Mass delta <strong>{modeledDelta(result.effect.morningMassDeltaF)}</strong></span>
            {/if}
          </div>
        </div>
      {/if}

      {#if Array.isArray(result?.reasons) && result.reasons.length > 0}
        <ul class="reasons" aria-label="Shadow model status details">
          {#each result.reasons as reason}
            <li class:warning={/cadence|stale|unavailable|recovered/i.test(reason)}>{reason}</li>
          {/each}
        </ul>
      {/if}

      <details>
        <summary>Model details</summary>
        <ThermalModelPlot
          trajectory={unavailable ? [] : result.trajectory}
          observed={unavailable ? [] : result.observed}
        />
      </details>
    </div>
  </Tile>
</div>

<style>
  .thermal-model-card {
    height: 100%;
    min-width: 0;
    min-height: 0;
  }
  .card-body {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    min-height: 0;
    gap: 0.2rem;
  }
  .status-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
    color: #8b93a1;
    font-size: 0.65rem;
  }
  .shadow-badge {
    flex: none;
    border: 1px solid #7c3aed;
    border-radius: 999px;
    padding: 0.14rem 0.38rem;
    color: #c4b5fd;
    font-size: 0.61rem;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .freshness.stale {
    color: #f59e0b;
  }
  .confidence {
    margin-left: auto;
    white-space: nowrap;
  }
  .model-ages {
    display: flex;
    flex-wrap: wrap;
    gap: 0.15rem 0.65rem;
    color: #8b93a1;
    font-size: 0.61rem;
    font-variant-numeric: tabular-nums;
  }
  .reasons {
    display: grid;
    gap: 0.1rem;
    margin: 0;
    padding-left: 1rem;
    color: #8b93a1;
    font-size: 0.61rem;
    line-height: 1.25;
  }
  .reasons li.warning {
    color: #f59e0b;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.4rem;
  }
  .metric,
  .window {
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 0.08rem;
  }
  .metric span,
  .window span,
  .effects span {
    color: #6b7280;
    font-size: 0.62rem;
  }
  .metric strong {
    color: #e6edf3;
    font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
  }
  .model-row {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.7rem;
    min-width: 0;
  }
  .window strong {
    overflow: hidden;
    color: #c4b5fd;
    font-size: 0.72rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .effects {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.15rem 0.5rem;
    text-align: right;
  }
  .effects strong {
    color: #e6edf3;
    font-weight: 600;
    white-space: nowrap;
  }
  .unavailable {
    display: flex;
    flex: 1;
    align-items: center;
    color: #8b93a1;
    font-size: 0.82rem;
  }
  details {
    position: relative;
    min-width: 0;
    color: #8b93a1;
    font-size: 0.66rem;
  }
  summary {
    width: max-content;
    cursor: pointer;
    color: #a78bfa;
  }
  details[open] {
    position: absolute;
    z-index: 20;
    inset: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-sizing: border-box;
    border: 1px solid #303846;
    border-radius: 0.55rem;
    background: #11151c;
    padding: 0.45rem;
    box-shadow: 0 0.5rem 1.2rem rgb(0 0 0 / 45%);
  }
  details[open] summary {
    flex: none;
    margin-bottom: 0.15rem;
  }
  details[open] :global(.thermal-model-plot) {
    position: absolute;
    inset: 1.5rem 0.45rem 0.45rem;
    width: calc(100% - 0.9rem);
    height: calc(100% - 1.95rem);
    min-height: 0;
    max-height: none;
  }
</style>
