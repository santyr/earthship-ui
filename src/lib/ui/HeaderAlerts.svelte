<script>
  import { consoleAlerts } from '../alerts/alertStore.js';
  import { navigate } from '../../routes.js';

  let { alertStore = consoleAlerts } = $props();
  let listOpen = $state(false);
  let assertiveText = $state('');
  let seenTransitions = new Map();
  let initialized = false;

  const alertState = $derived($alertStore);
  const winner = $derived(alertState.winner ?? null);
  const additionalCount = $derived(alertState.additionalCount ?? 0);
  const ordered = $derived(alertState.ordered ?? []);
  const politeText = $derived(
    winner
      ? `${winner.shortText}${additionalCount ? ` +${additionalCount}` : ''}`
      : 'No active alerts'
  );

  $effect(() => {
    const next = new Map(ordered.map((alert) => [alert.dedupeKey, alert.activeSince]));
    if (initialized) {
      const entered = ordered.find((alert) => (
        (alert.id === 'connection-offline' || alert.severity === 'critical')
        && seenTransitions.get(alert.dedupeKey) !== alert.activeSince
      ));
      if (entered) assertiveText = entered.shortText;
    }
    seenTransitions = next;
    initialized = true;
  });

  function activate(alert) {
    if (alert?.route) {
      listOpen = false;
      navigate(alert.route);
    } else {
      listOpen = true;
    }
  }

  function closeList() {
    listOpen = false;
  }

  function onListKeydown(event) {
    if (event.key === 'Escape') closeList();
  }
</script>

<div class="header-alerts" data-header-alerts style="height: 44px; white-space: nowrap;">
  {#if winner}
    <button
      type="button"
      class="winner"
      data-header-alert-winner
      data-severity={winner.severity}
      aria-label={winner.fullText}
      title={winner.fullText}
      onclick={() => activate(winner)}
    >
      <span class="winner-text">{winner.shortText}</span>
    </button>
    {#if additionalCount > 0}
      <button
        type="button"
        class="count"
        aria-label={`Show ${additionalCount} additional alert${additionalCount === 1 ? '' : 's'}`}
        aria-expanded={listOpen}
        onclick={() => (listOpen = true)}
      >+{additionalCount}</button>
    {/if}
  {/if}

  <span class="sr-only" role="status" aria-live="polite">{politeText}</span>
  <span class="sr-only" aria-live="assertive" aria-atomic="true">{assertiveText}</span>

  {#if listOpen}
    <div
      class="alert-list"
      role="dialog"
      aria-label="Active alerts"
      aria-modal="false"
      tabindex="-1"
      onkeydown={onListKeydown}
    >
      <div class="list-heading">
        <span>Active alerts</span>
        <button type="button" class="close" aria-label="Close alerts" onclick={closeList}>×</button>
      </div>
      <div class="list-body">
        {#each ordered as alert (alert.dedupeKey)}
          {#if alert.route}
            <button
              type="button"
              class="list-item"
              data-alert-list-item
              data-severity={alert.severity}
              aria-label={alert.fullText}
              onclick={() => activate(alert)}
            >
              <span class="item-text">{alert.fullText}</span>
              <span class="route-mark" aria-hidden="true">›</span>
            </button>
          {:else}
            <div class="list-item global" data-alert-list-item data-severity={alert.severity}>
              <span class="item-text">{alert.fullText}</span>
            </div>
          {/if}
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .header-alerts {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex: 1 1 auto;
    min-width: 0;
    height: 44px;
    overflow: visible;
    white-space: nowrap;
  }

  .winner,
  .count,
  .close,
  .list-item {
    border: 0;
    font: inherit;
  }

  .winner {
    min-width: 0;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    overflow: hidden;
    background: transparent;
    color: #f59e0b;
    padding: 0 0.35rem;
    cursor: pointer;
  }

  .winner[data-severity='critical'] { color: #ef4444; }
  .winner[data-severity='advisory'] { color: #f97316; }
  .winner[data-severity='info'] { color: #93c5fd; }

  .winner-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.76rem;
    font-weight: 650;
  }

  .count {
    flex: 0 0 auto;
    min-width: 44px;
    height: 44px;
    background: transparent;
    color: #c7cfd9;
    font-size: 0.72rem;
    font-weight: 700;
    cursor: pointer;
  }

  .winner:focus-visible,
  .count:focus-visible,
  .close:focus-visible,
  .list-item:focus-visible {
    outline: 2px solid #60a5fa;
    outline-offset: -2px;
  }

  .alert-list {
    position: absolute;
    z-index: 50;
    top: 42px;
    right: 0;
    width: min(32rem, calc(100vw - 4rem));
    max-height: calc(100dvh - 56px);
    overflow: hidden;
    border: 1px solid #30394a;
    border-radius: 0.65rem;
    background: #11151c;
    box-shadow: 0 0.8rem 2.2rem rgb(0 0 0 / 55%);
    white-space: normal;
  }

  .list-heading {
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-left: 0.8rem;
    border-bottom: 1px solid #252c3a;
    color: #c7cfd9;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }

  .close {
    width: 44px;
    height: 44px;
    background: transparent;
    color: #8b93a1;
    cursor: pointer;
    font-size: 1.25rem;
  }

  .list-body {
    max-height: calc(100dvh - 102px);
    overflow: auto;
  }

  .list-item {
    width: 100%;
    min-height: 44px;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.58rem 0.8rem;
    border-bottom: 1px solid #1c2230;
    background: transparent;
    color: #d8dee9;
    text-align: left;
  }

  button.list-item { cursor: pointer; }
  button.list-item:hover { background: #171d27; }
  .list-item[data-severity='critical'] { border-left: 3px solid #ef4444; }
  .list-item[data-severity='warning'] { border-left: 3px solid #f59e0b; }
  .list-item[data-severity='advisory'] { border-left: 3px solid #f97316; }
  .list-item[data-severity='info'] { border-left: 3px solid #60a5fa; }

  .item-text {
    min-width: 0;
    flex: 1;
    font-size: 0.76rem;
    line-height: 1.35;
  }

  .route-mark {
    color: #8b93a1;
    font-size: 1.1rem;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
</style>
