<script>
  // App shell: left nav rail (>=900px) / bottom tab bar (<900px), header,
  // stale banner, and a slot for the active screen.
  import Header from './Header.svelte';
  import { currentRoute, navigate } from '../../routes.js';
  import { connection } from '../openhab/index.js';

  let { children } = $props();

  const navItems = [
    { name: 'home', label: 'Home', icon: '⌂' },
    { name: 'energy', label: 'Energy', icon: '⚡' },
    { name: 'weather', label: 'Weather', icon: '☁' },
    { name: 'earthship', label: 'Earthship', icon: '◆' },
    { name: 'controls', label: 'Controls', icon: '⏻' },
  ];
</script>

<div class="shell">
  <Header />
  {#if $connection !== 'live'}
    <div class="stale-banner">
      connection: {$connection} — data may be out of date
    </div>
  {/if}
  <div class="body">
    <nav class="rail" aria-label="Primary">
      {#each navItems as item (item.name)}
        <button
          type="button"
          class="rail-item"
          class:active={$currentRoute === item.name}
          onclick={() => navigate(item.name)}
        >
          <span class="icon">{item.icon}</span>
          <span class="label">{item.label}</span>
        </button>
      {/each}
    </nav>
    <main class="screen">
      {@render children?.()}
    </main>
  </div>
  <nav class="tabs" aria-label="Primary">
    {#each navItems as item (item.name)}
      <button
        type="button"
        class="tab-item"
        class:active={$currentRoute === item.name}
        onclick={() => navigate(item.name)}
      >
        <span class="icon">{item.icon}</span>
        <span class="label">{item.label}</span>
      </button>
    {/each}
  </nav>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #06080c;
    color: #e6edf3;
  }
  .stale-banner {
    background: #3a2a0a;
    color: #f59e0b;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    text-align: center;
    padding: 0.25rem 0.5rem;
    border-bottom: 1px solid #5a3d0f;
  }
  .body {
    flex: 1;
    display: flex;
    min-height: 0;
  }
  .screen {
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    padding: 0.9rem;
  }

  /* Left rail — wide screens only */
  .rail {
    display: none;
    flex-direction: column;
    gap: 0.25rem;
    width: 4.75rem;
    flex-shrink: 0;
    padding: 0.6rem 0.4rem;
    border-right: 1px solid #1c2230;
    background: #0b0e14;
  }
  .rail-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
    background: transparent;
    border: none;
    color: #8b93a1;
    padding: 0.5rem 0.2rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font: inherit;
  }
  .rail-item .icon {
    font-size: 1.1rem;
    line-height: 1;
  }
  .rail-item .label {
    font-size: 0.62rem;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
  }
  .rail-item.active {
    background: #151b26;
    color: #e6edf3;
  }

  /* Bottom tab bar — narrow screens only */
  .tabs {
    display: flex;
    border-top: 1px solid #1c2230;
    background: #0b0e14;
    flex-shrink: 0;
  }
  .tab-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    background: transparent;
    border: none;
    color: #8b93a1;
    padding: 0.4rem 0.2rem 0.5rem;
    cursor: pointer;
    font: inherit;
  }
  .tab-item .icon {
    font-size: 1rem;
    line-height: 1;
  }
  .tab-item .label {
    font-size: 0.6rem;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
  }
  .tab-item.active {
    color: #e6edf3;
  }

  @media (min-width: 900px) {
    .rail {
      display: flex;
    }
    .tabs {
      display: none;
    }
  }
</style>
