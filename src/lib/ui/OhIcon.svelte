<script module>
  // Common wall-display icons render immediately from small local subsets.
  // Unanticipated OpenHAB icons still load the complete offline collection
  // on demand; no icon requires an external network request.
  import { addCollection } from '@iconify/svelte/offline';
  import mdiCommon from './icons/mdi-common.json';
  import biCommon from './icons/bi-common.json';

  addCollection(mdiCommon);
  addCollection(biCommon);
  const common = new Set([
    ...Object.keys(mdiCommon.icons).map(name => `mdi:${name}`),
    ...Object.keys(biCommon.icons).map(name => `bi:${name}`),
  ]);
  let fullLoaded = $state({ mdi: false, bi: false });
  const loading = {};

  export const iconCollectionsReady = Promise.resolve();

  function ensureFull(prefix) {
    if (loading[prefix]) return;
    loading[prefix] = (prefix === 'mdi'
      ? import('@iconify-json/mdi/icons.json')
      : import('@iconify-json/bi/icons.json'))
      .then(module => {
        addCollection(module.default ?? module);
        fullLoaded[prefix] = true;
      }).catch(() => {
        // Same-origin chunk failure leaves only this unrecognized icon blank.
        loading[prefix] = null;
      });
  }
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
  const prefix = $derived(name?.split(':', 1)[0]);
  $effect(() => {
    if (name && !common.has(name) && (prefix === 'mdi' || prefix === 'bi')) {
      ensureFull(prefix);
    }
  });
</script>

{#if name && (common.has(name) || fullLoaded[prefix])}
  <Icon icon={name} width={size} height={size} {color} />
{/if}
