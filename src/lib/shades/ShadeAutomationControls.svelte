<script>
  import { onMount } from 'svelte';
  import Toggle from '../ui/Toggle.svelte';
  import { SHADE_GROUPS } from './catalog.js';
  import { SHADE_POLICY_ITEMS } from './policyModel.js';
  import { createShadePolicyRequests, shadePolicyPresentation, validateShadePolicySnapshot } from './policy.js';

  let policySnapshot = $state(null);
  let policySaving = $state('');
  let policyErrors = $state({});
  let policyRequest = 0;
  let policyMounted = false;
  let policyReading = false;
  const policyRequests = createShadePolicyRequests();

  async function readPolicy() {
    if (!policyMounted || policySaving || policyReading) return;
    policyReading = true;
    const request = ++policyRequest;
    try {
      const { response, snapshot } = await policyRequests.request();
      if (!response.ok || !validateShadePolicySnapshot(snapshot)) throw new Error('Policy unavailable');
      if (policyMounted && request === policyRequest) policySnapshot = snapshot;
    } catch {
      if (policyMounted && request === policyRequest) policySnapshot = null;
    } finally { if (policyMounted) policyReading = false; }
  }

  async function savePolicy(zone) {
    const presentation = shadePolicyPresentation(policySnapshot, zone);
    if (!policyMounted || policySaving || !presentation.canSave) return { phase: 'unknown' };
    const enabled = presentation.checked !== true;
    const request = ++policyRequest;
    policySaving = zone;
    policyErrors = { ...policyErrors, [zone]: '' };
    try {
      const { response, snapshot } = await policyRequests.request({
        method: 'POST', headers: { 'Content-Type': 'application/json' }, cache: 'no-store',
        body: JSON.stringify({ zone, enabled, expectedGeneration: policySnapshot.generation, expectedSessionId: policySnapshot.sessionId }),
      });
      if (!response.ok || !validateShadePolicySnapshot(snapshot) || !snapshot.connected
          || !snapshot.zones[zone].authoritative || snapshot.zones[zone].saved !== (enabled ? 'ON' : 'OFF')) {
        throw new Error('Save not confirmed');
      }
      if (policyMounted && request === policyRequest) policySnapshot = snapshot;
      return { phase: 'confirmed' };
    } catch {
      if (policyMounted && request === policyRequest) {
        policySnapshot = null;
        policyErrors = { ...policyErrors, [zone]: 'Save not confirmed — checking policy again' };
      }
      return { phase: 'unknown' };
    } finally { if (policyMounted && request === policyRequest) policySaving = ''; }
  }

  onMount(() => {
    policyMounted = true;
    readPolicy();
    const timer = setInterval(readPolicy, 5000);
    const reconcile = () => { if (document.visibilityState !== 'hidden') readPolicy(); };
    window.addEventListener('online', reconcile);
    window.addEventListener('focus', reconcile);
    document.addEventListener('visibilitychange', reconcile);
    return () => {
      policyMounted = false;
      ++policyRequest;
      policyRequests.dispose();
      clearInterval(timer);
      window.removeEventListener('online', reconcile);
      window.removeEventListener('focus', reconcile);
      document.removeEventListener('visibilitychange', reconcile);
    };
  });

</script>

{#each SHADE_GROUPS as room (room.id)}
  {@const presentation = shadePolicyPresentation(policySnapshot, room.id)}
  <div class="policy-control" data-shade-automation-zone={room.id}>
    <Toggle
      control={{label: room.label, kind: 'shade-policy', stateItem: SHADE_POLICY_ITEMS[room.id],
        contextKey: `${policySnapshot?.sessionId ?? ''}:${policySnapshot?.generation ?? 0}`}}
      viewOverride={{
        enabled: !policySaving && presentation.canSave,
        value: presentation.checked === 'mixed' ? null : presentation.checked ? 'ON' : 'OFF',
        valueLabel: presentation.checked === 'mixed' ? 'Unavailable' : presentation.checked ? 'ON' : 'OFF',
        reason: policySaving === room.id ? 'Saving…' : presentation.label,
      }}
      submitOverride={() => savePolicy(room.id)}
    />
    {#if policyErrors[room.id]}<span class="policy-error" role="alert">{policyErrors[room.id]}</span>{/if}
  </div>
{/each}

<style>
  .policy-control { display: grid; grid-template-rows: minmax(0, 1fr) auto; min-width: 0; min-height: 0; }
  .policy-error { color: #efb4a3; font-size: .65rem; line-height: 1.2; }
</style>
