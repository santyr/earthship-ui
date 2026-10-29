<script>
  import { onMount } from 'svelte';

  let { large = false, showTime = true, showDate = true } = $props();
  let now = $state(new Date());

  onMount(() => {
    const timer = setInterval(() => {
      now = new Date();
    }, 1000);
    return () => clearInterval(timer);
  });

  const timeText = $derived(
    now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
  );
  const dateText = $derived(now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }));
</script>

<div class="clock" class:large class:dateOnly={showDate && !showTime}>
  {#if showTime}<span class="time">{timeText}</span>{/if}
  {#if showDate}<span class="date">{dateText}</span>{/if}
</div>

<style>
  .clock {
    flex: 0 0 auto;
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .time {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1;
  }
  .date {
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-variant-caps: small-caps;
    color: #8b93a1;
  }
  .large {
    gap: 0.5rem;
  }
  .large .time {
    font-size: clamp(1.5rem, 9vw, 2.625rem);
    line-height: 1.05;
    padding-bottom: 0.05em;
    font-weight: 700;
  }
  .large .date {
    font-size: clamp(0.7rem, 3.5vw, 0.875rem);
    line-height: 1.2;
    letter-spacing: 0.025em;
    color: #c7cfd9;
  }
  .dateOnly .date {
    font-size: 0.875rem;
    line-height: 1.2;
    letter-spacing: 0.025em;
    color: #c7cfd9;
  }
  @media (max-width: 700px) {
    .large { gap: 0.25rem; }
  }
</style>
