<script>
  // App shell: one fixed header row plus a bounded screen and target nav.
  import Header from './Header.svelte';
  import { currentRoute, navigate } from '../../routes.js';

  let { children } = $props();

  const navItems = [
    { name: 'home', label: 'Home', icon: '⌂' },
    { name: 'energy', label: 'Energy', icon: '⚡' },
    { name: 'weather', label: 'Weather', icon: '☁' },
    { name: 'earthship', label: 'Earthship', icon: '◆' },
    { name: 'controls', label: 'Controls', icon: '⏻' },
  ];
</script>

<div class="shell" data-bounded-shell>
  <nav class="rail" aria-label="Primary">
    {#each navItems as item (item.name)}
      <button
        type="button"
        class="rail-item"
        class:active={$currentRoute === item.name}
        aria-current={$currentRoute === item.name ? 'page' : undefined}
        onclick={() => navigate(item.name)}
      >
        <span class="icon">{item.icon}</span>
        <span class="label">{item.label}</span>
      </button>
    {/each}
  </nav>
  <div class="header-slot"><Header /></div>
  <main class="screen">
    {@render children?.()}
  </main>
  <nav class="tabs" aria-label="Primary">
    {#each navItems as item (item.name)}
      <button
        type="button"
        class="tab-item"
        class:active={$currentRoute === item.name}
        aria-current={$currentRoute === item.name ? 'page' : undefined}
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
    --rail-size: 52px;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 44px minmax(0, 1fr) 52px;
    width: 100%;
    height: 100vh;
    height: 100dvh;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    background: #06080c;
    color: #e6edf3;
  }

  .header-slot {
    grid-row: 1;
    min-width: 0;
    min-height: 0;
    z-index: 20;
  }

  .screen {
    grid-row: 2;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    padding: 0.65rem;
    box-sizing: border-box;
  }

  .rail {
    display: none;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.6rem 0.4rem;
    box-sizing: border-box;
    border-right: 1px solid #1c2230;
    background: #0b0e14;
    overflow: hidden;
  }
  .rail-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
    background: transparent;
    border: none;
    color: #8b93a1;
    min-height: 44px;
    padding: 0.35rem 0.1rem;
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

  .tabs {
    grid-row: 3;
    display: flex;
    border-top: 1px solid #1c2230;
    background: #0b0e14;
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
    .shell {
      grid-template-columns: var(--rail-size) minmax(0, 1fr);
      grid-template-rows: 44px minmax(0, 1fr);
    }
    .rail {
      display: flex;
      grid-column: 1;
      grid-row: 1 / span 2;
      width: var(--rail-size);
      height: 100dvh;
    }
    .header-slot {
      grid-column: 2;
      grid-row: 1;
    }
    .screen {
      grid-column: 2;
      grid-row: 2;
    }
    .tabs {
      display: none;
    }
  }

  @media (min-width: 1440px) {
    .shell { --rail-size: 60px; }
  }

  @media (min-width: 1280px) and (max-height: 720px) {
    .screen { padding: 0.55rem; }
  }
</style>
