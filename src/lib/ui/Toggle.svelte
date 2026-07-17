<script>
  // Press-and-hold toggle control. Wall taps are easy to trigger by
  // accident (leaning on the display, wiping dust off, etc) so a plain tap
  // does nothing — only a ~500ms hold fires the command, with a filling
  // progress bar as the visual "confirm" cue.
  import { items } from '../openhab/index.js';
  import { getClientOnce } from '../openhab/index.js';

  let { item, label = '', onColor = '#22c55e' } = $props();

  const HOLD_MS = 500;

  let progress = $state(0); // 0..1
  let holding = $state(false);
  let timer = null;
  let raf = null;
  let startedAt = 0;

  const state = $derived($items?.[item]);
  const isOn = $derived(state === 'ON');

  function tickProgress() {
    if (!holding) return;
    const elapsed = performance.now() - startedAt;
    progress = Math.min(1, elapsed / HOLD_MS);
    if (progress < 1) {
      raf = requestAnimationFrame(tickProgress);
    }
  }

  function startHold() {
    holding = true;
    progress = 0;
    startedAt = performance.now();
    raf = requestAnimationFrame(tickProgress);
    timer = setTimeout(fire, HOLD_MS);
  }

  function cancelHold() {
    holding = false;
    progress = 0;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (raf) {
      cancelAnimationFrame(raf);
      raf = null;
    }
  }

  function fire() {
    const client = getClientOnce();
    holding = false;
    progress = 0;
    if (raf) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    if (!client || !item) return;
    const next = state === 'ON' ? 'OFF' : 'ON';
    client.sendCommand(item, next);
  }
</script>

<button
  type="button"
  class="toggle"
  class:on={isOn}
  onpointerdown={startHold}
  onpointerup={cancelHold}
  onpointerleave={cancelHold}
  onpointercancel={cancelHold}
>
  {#if label}
    <span class="toggle-label">{label}</span>
  {/if}
  <span class="pill" style="background: {isOn ? onColor : '#374151'}">
    {isOn ? 'ON' : 'OFF'}
  </span>
  {#if holding}
    <span class="hold-progress" style="width: {progress * 100}%"></span>
  {/if}
</button>

<style>
  .toggle {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    width: 100%;
    background: transparent;
    border: 1px solid #1c2230;
    border-radius: 0.6rem;
    padding: 0.5rem 0.75rem;
    cursor: pointer;
    overflow: hidden;
    -webkit-user-select: none;
    user-select: none;
    touch-action: none;
  }
  .toggle-label {
    color: #8b93a1;
    font-size: 0.85rem;
  }
  .pill {
    color: #0b0f16;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
  }
  .toggle:not(.on) .pill {
    color: #e5e7eb;
  }
  .hold-progress {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 3px;
    background: currentColor;
    color: #22c55e;
    transition: width 60ms linear;
  }
</style>
