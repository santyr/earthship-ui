<script>
  import { onDestroy, onMount } from 'svelte';
  import OhIcon from './OhIcon.svelte';
  import Tile from './Tile.svelte';
  import {
    advanceGoatFeederTracker,
    createGoatFeederTracker,
    formatGoatFeedings,
  } from './homeCardState.js';

  let { feedings, motorState, feedbackMs = 1800 } = $props();

  let active = $state(false);
  let tracker = createGoatFeederTracker();
  let feedbackTimer;
  let audioContext;
  let audioArmed = false;

  const feedingText = $derived(formatGoatFeedings(feedings));

  function removeAudioArmListeners() {
    if (typeof window === 'undefined') return;
    window.removeEventListener('pointerdown', armAudio);
    window.removeEventListener('keydown', armAudio);
  }

  function armAudio() {
    if (audioArmed || typeof window === 'undefined') return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    try {
      audioContext = new AudioContext();
      const resume = audioContext.resume?.();
      resume?.catch?.(() => {});
      audioArmed = true;
      removeAudioArmListeners();
    } catch {
      audioContext = undefined;
    }
  }

  function scheduleChime() {
    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(659.25, now);
    oscillator.frequency.exponentialRampToValueAtTime(880, now + 0.12);
    gain.gain.setValueAtTime(0.025, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.25);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.25);
  }

  function playChime() {
    if (!audioArmed || !audioContext) return;
    try {
      if (audioContext.state === 'suspended' && audioContext.resume) {
        Promise.resolve(audioContext.resume()).then(scheduleChime).catch(() => {});
        return;
      }
      scheduleChime();
    } catch {
      // The visual state remains authoritative; audio is only best-effort.
    }
  }

  function activateFeedback() {
    active = true;
    clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => {
      active = false;
    }, feedbackMs);
    playChime();
  }

  $effect(() => {
    const result = advanceGoatFeederTracker(tracker, motorState);
    tracker = result.tracker;
    if (result.activated) activateFeedback();
  });

  onMount(() => {
    window.addEventListener('pointerdown', armAudio, { passive: true });
    window.addEventListener('keydown', armAudio);
  });

  onDestroy(() => {
    clearTimeout(feedbackTimer);
    removeAudioArmListeners();
    try {
      const close = audioContext?.close?.();
      close?.catch?.(() => {});
    } catch {
      // Teardown remains safe when a browser rejects closing the context.
    }
  });
</script>

<Tile
  label="Goat Feedings"
  accessibleLabel={`Goat feedings: ${feedingText}`}
  accent="#8b5cf6"
  hideLabel
  fill
  clip
  centerBody
  padding="0.55rem 0.65rem"
>
  <div class="goat-feeding-body">
    {#if active}
      <span class="goat-activation-icon" role="img" aria-label="Goat feeder activated">🐐</span>
    {:else}
      <span class="goat-feed-icon" aria-hidden="true">
        <OhIcon icon="iconify:mdi:food-apple-outline" size="1.35rem" />
      </span>
    {/if}
    <span class="goat-feeding-text" title={feedingText}>{feedingText}</span>
  </div>
</Tile>

<style>
  .goat-feeding-body {
    width: 100%;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    overflow: hidden;
    color: #c7cfd9;
  }
  .goat-feed-icon,
  .goat-activation-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    color: #8b5cf6;
    line-height: 1;
  }
  .goat-activation-icon {
    color: #f59e0b;
    font-family: "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif;
    font-size: 1.35rem;
    animation: goat-pulse 600ms ease-in-out infinite alternate;
  }
  .goat-feeding-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.78rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  @keyframes goat-pulse {
    from { transform: scale(1); opacity: 0.75; }
    to { transform: scale(1.12); opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .goat-activation-icon {
      animation: none;
    }
  }
</style>
