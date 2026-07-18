<script>
  import { items, connection, getClientOnce } from '../openhab/index.js';
  import { holdAction } from '../actions/holdAction.js';
  import {
    activationModeFor,
    commandTargetFor,
  } from '../controls/catalog.js';
  import {
    deriveControlState,
    outcomePresentation,
  } from '../controls/controlState.js';
  import { CURRENT_RELEASE_MODE } from '../releaseMode.js';

  let {
    control,
    onColor = '#22c55e',
    releaseMode = CURRENT_RELEASE_MODE,
    providerStatus = null,
    capabilities = {},
    ownerTransitioning = false,
    ownerBusy = false,
  } = $props();

  let submissionPhase = $state('confirmed');

  const providerHealth = $derived(
    providerStatus && control?.stateItem
      ? { [control.stateItem]: providerStatus }
      : {},
  );

  const view = $derived.by(() => deriveControlState(control, {
    items: $items,
    connection: $connection,
    releaseMode,
    providerOnline: providerHealth,
    capabilities,
    ownerTransitioning,
    ownerBusy,
  }));

  const buttonDisabled = $derived(!view.enabled || submissionPhase === 'pending');
  const activePhase = $derived(view.enabled ? submissionPhase : 'unavailable');
  const phaseView = $derived(outcomePresentation(activePhase));
  const isOn = $derived(view.value === 'ON');
  const activationMode = $derived(activationModeFor(control));
  const commandContract = $derived([
    control?.kind || '',
    commandTargetFor(control) || '',
    view.value || '',
    view.enabled ? 'enabled' : 'disabled',
    releaseMode,
  ].join('|'));
  const statusText = $derived.by(() => {
    if (view.valueLabel === 'Unavailable') return 'Unavailable';
    if (control.kind === 'action') return `Actuator ${view.valueLabel}`;
    if (control.kind === 'safety-request') return `Pump ${view.valueLabel}`;
    if (control.kind === 'policy-status') return `Policy ${view.valueLabel}`;
    return view.valueLabel;
  });
  const descriptionId = $derived(
    `control-${control?.stateItem || 'unknown'}-description`,
  );

  $effect(() => {
    if (!view.enabled) {
      submissionPhase = 'unavailable';
    } else if (submissionPhase === 'unavailable') {
      submissionPhase = 'confirmed';
    }
  });

  function onPhaseChange(phase) {
    submissionPhase = phase;
  }

  async function submit() {
    const target = commandTargetFor(control);
    const client = getClientOnce();
    if (!target || !client) return { status: 'unknown' };

    const next = view.value === 'ON' ? 'OFF' : 'ON';
    try {
      await client.sendCommand(target, next);
      return { status: 'accepted' };
    } catch (error) {
      // An explicit non-2xx response is a rejection. A transport break after
      // POST may still have reached openHAB, so it is deliberately uncertain
      // and is never retried.
      if (/sendCommand\s+\S+\s+\d{3}/.test(String(error?.message || ''))) {
        throw error;
      }
      const unknown = new Error('Command outcome unknown');
      unknown.outcomeUnknown = true;
      throw unknown;
    }
  }
</script>

<button
  type="button"
  class="control"
  class:on={isOn}
  class:holding={activePhase === 'holding'}
  class:pending={activePhase === 'pending'}
  class:error={activePhase === 'error'}
  class:unknown={activePhase === 'unknown'}
  disabled={buttonDisabled}
  aria-pressed={view.value ? isOn : undefined}
  aria-describedby={descriptionId}
  title={[view.reason, view.detail].filter(Boolean).join(' · ')}
  use:holdAction={{
    mode: activationMode,
    disabled: buttonDisabled,
    contractKey: commandContract,
    onSubmit: submit,
    onPhaseChange,
  }}
>
  <span class="control-main">
    <span class="control-label">{control.label}</span>
    <span
      class="pill"
      class:unavailable={view.valueLabel === 'Unavailable'}
      style="--active-color: {onColor}"
    >
      {statusText}
    </span>
  </span>

  <span class="control-meta" id={descriptionId}>
    {#if view.healthLabel}
      <span class:degraded={view.healthLabel === 'Degraded'}>
        {view.healthLabel}
      </span>
    {/if}
    {#if view.reason}
      <span>{view.reason}</span>
    {/if}
    {#if view.detail}
      <span class="detail">{view.detail}</span>
    {/if}
    {#if view.enabled && activePhase !== 'confirmed'}
      <span class="submission" data-tone={phaseView.tone}>{phaseView.label}</span>
    {:else if view.enabled}
      <span class="hint">
        {activationMode === 'tap' ? 'Tap to toggle' : 'Hold 600 ms'}
      </span>
    {/if}
  </span>

  {#if activePhase === 'holding'}
    <span class="hold-progress" aria-hidden="true"></span>
  {/if}
</button>

<style>
  .control {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.28rem;
    width: 100%;
    min-width: 0;
    min-height: 0;
    height: 100%;
    box-sizing: border-box;
    overflow: hidden;
    border: 1px solid #252c3a;
    border-radius: 0.62rem;
    background: #0d1118;
    color: #e6edf3;
    padding: 0.52rem 0.68rem;
    font: inherit;
    text-align: left;
    cursor: pointer;
    touch-action: none;
    -webkit-user-select: none;
    user-select: none;
  }

  .control:not(:disabled):focus-visible {
    outline: 2px solid #60a5fa;
    outline-offset: 2px;
  }

  .control:disabled {
    cursor: not-allowed;
    background: #0b0e14;
    border-color: #1c2230;
  }

  .control-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.45rem;
    min-width: 0;
  }

  .control-label {
    min-width: 0;
    overflow: hidden;
    color: #d8dee9;
    font-size: clamp(0.8rem, 1vw, 0.92rem);
    font-weight: 650;
    line-height: 1.1;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .pill {
    flex: 0 0 auto;
    border: 1px solid #374151;
    border-radius: 999px;
    background: #252b36;
    color: #d9e0e8;
    padding: 0.16rem 0.52rem;
    font-size: 0.64rem;
    font-weight: 750;
    line-height: 1.2;
    letter-spacing: 0.035em;
    white-space: nowrap;
  }

  .control.on .pill {
    border-color: var(--active-color);
    background: var(--active-color);
    color: #07100a;
  }

  .control.on:disabled .pill {
    border-color: color-mix(in srgb, var(--active-color) 65%, #4b5563);
    filter: saturate(0.72);
  }

  .pill.unavailable {
    border-color: #303744;
    background: #171c25;
    color: #7f8999;
  }

  .control-meta {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    min-width: 0;
    overflow: hidden;
    color: #8791a1;
    font-size: clamp(0.62rem, 0.75vw, 0.7rem);
    line-height: 1.15;
    white-space: nowrap;
  }

  .control-meta > span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .control-meta > span + span::before {
    content: '·';
    margin-right: 0.3rem;
    color: #4b5563;
  }

  .degraded {
    flex: 0 0 auto;
    flex-shrink: 0;
  }

  .degraded,
  .submission[data-tone='warning'] {
    color: #f59e0b;
  }

  .submission[data-tone='error'] {
    color: #ef4444;
  }

  .submission[data-tone='success'] {
    color: #22c55e;
  }

  .hint {
    color: #6f7a8a;
  }

  .hold-progress {
    position: absolute;
    left: 0;
    bottom: 0;
    width: 100%;
    height: 3px;
    background: #22c55e;
    transform-origin: left;
    animation: fill-hold 600ms linear forwards;
  }

  .control.error {
    border-color: #7f1d1d;
  }

  .control.unknown {
    border-color: #92400e;
  }

  @keyframes fill-hold {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }

  @media (prefers-reduced-motion: reduce) {
    .hold-progress {
      animation-timing-function: steps(2, end);
    }
  }
</style>
