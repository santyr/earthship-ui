<script module>
  // Offline icon collections — bundled at build time so the wall display
  // never depends on network access to render an icon. openHAB icon
  // strings look like 'iconify:mdi:moon-waxing-crescent' or
  // 'iconify:bi:cloud-sun-fill'; we strip the 'iconify:' prefix and hand
  // the rest ('mdi:name' / 'bi:name') straight to the offline Icon.
  import { addCollection } from '@iconify/svelte/offline';
  import mdiIcons from '@iconify-json/mdi/icons.json';
  import biIcons from '@iconify-json/bi/icons.json';

  addCollection(mdiIcons);
  addCollection(biIcons);
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

{#if name}
  <Icon icon={name} width={size} height={size} {color} />
{/if}
