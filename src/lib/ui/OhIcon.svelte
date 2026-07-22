<script module>
  // Offline icon collections — still bundled at build time so the wall
  // display never depends on network access to render an icon, but loaded
  // via dynamic import() so the ~4.1MB of icon JSON becomes split async
  // chunks instead of bloating the main chunk. Icons appear momentarily
  // after first paint once the chunks resolve (same-origin, no network).
  //
  // openHAB icon strings look like 'iconify:mdi:moon-waxing-crescent' or
  // 'iconify:bi:cloud-sun-fill'; we strip the 'iconify:' prefix and hand
  // the rest ('mdi:name' / 'bi:name') straight to the offline Icon.
  import { addCollection } from '@iconify/svelte/offline';

  // The offline Icon looks a collection up only when it (re)renders, so
  // rendering is gated on this module-level state flipping true.
  let collectionsLoaded = $state(false);

  // Exported so tests (or any caller needing determinism) can await the
  // exact point after which icons render synchronously.
  export const iconCollectionsReady = Promise.all([
    import('@iconify-json/mdi/icons.json'),
    import('@iconify-json/bi/icons.json'),
  ]).then((modules) => {
    for (const module of modules) addCollection(module.default ?? module);
    collectionsLoaded = true;
  }).catch(() => {
    // Bundled chunks should never fail to load; if they somehow do, keep
    // the display alive — icons stay blank, everything else renders.
  });
</script>

<script>
  import Icon from '@iconify/svelte/offline';

  // icon: raw openHAB icon string, e.g. 'iconify:mdi:moon-waxing-crescent'.
  // NULL-safe: empty/NULL/UNDEF/missing -> render nothing.
  let { icon, size = '1.4em', color = 'currentColor' } = $props();

  const name = $derived.by(() => {
    if (!icon || icon === 'NULL' || icon === 'UNDEF') return null;
    return String(icon).replace(/^iconify:/, '');
  });
</script>

{#if name && collectionsLoaded}
  <Icon icon={name} width={size} height={size} {color} />
{/if}
