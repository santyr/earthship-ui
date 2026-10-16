<script>
  import { onMount } from 'svelte';
  import Tile from './Tile.svelte';
  import {QUALIFICATION_GATES,QUALIFICATION_FAMILIES} from '../household/qualification.js';
  import { parseHouseholdObservation } from '../household/observation.js';
  import { loadHouseholdObservation, loadBatteryPerformance, loadCapturedPvPerformance } from '../household/observationClient.js';

  import { parseCapturedPvPerformance } from '../household/capturedPvPerformance.js';
  import { parseBatteryPerformance } from '../household/batteryPerformance.js';

  let capturedPvRaw = $state(null);
  const capturedPv = $derived(parseCapturedPvPerformance(capturedPvRaw, { nowMs }));
  let batteryRaw = $state(null);
  const battery = $derived(parseBatteryPerformance(batteryRaw, { nowMs }));
  let raw = $state(null), nowMs = $state(Date.now());
  const view = $derived(parseHouseholdObservation(raw, { nowMs }));
  const selected = $derived(view?.proposals.filter(item => item.selected) ?? []);
  const words = value => value == null ? 'unknown' : value.replaceAll('_', ' ');
  const date = value => new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit',
  }).format(Date.parse(value));

  onMount(() => {
    let stopped = false, controller = null, deadline = null;
    async function refresh() {
      nowMs = Date.now(); controller?.abort(); clearTimeout(deadline);
      const current = new AbortController(); controller = current;
      deadline = setTimeout(() => current.abort(), 10_000);
      const results = await Promise.allSettled([
        loadHouseholdObservation(current.signal), loadBatteryPerformance(current.signal), loadCapturedPvPerformance(current.signal),
      ]);
      if (!stopped && controller === current) {
        raw = results[0].status === 'fulfilled' ? results[0].value : null;
        batteryRaw = results[1].status === 'fulfilled' ? results[1].value : null;
        capturedPvRaw = results[2].status === 'fulfilled' ? results[2].value : null;
        nowMs = Date.now(); clearTimeout(deadline);
      }
    }
    refresh();
    const timer = setInterval(refresh, 30_000);
    const clock = setInterval(() => { nowMs = Date.now(); }, 1_000);
    return () => { stopped = true; clearInterval(timer); clearInterval(clock); clearTimeout(deadline); controller?.abort(); };
  });
</script>

<div class="household" aria-label="Household model inspection">
  <Tile label="Household intelligence">
    <h1>{view?.effectiveMode === 'shadow' ? 'Shadow' : 'Unavailable'}</h1>
    <p>Read-only planning evidence · automatic actuation disabled</p>
    {#if view}
      <dl class="summary">
        <div><dt>Snapshot age</dt><dd>{view.snapshotAgeSeconds} seconds</dd></div>
        <div><dt>Original snapshot</dt><dd>{date(view.snapshot_as_of)}</dd></div>
        <div><dt>Original decision</dt><dd>{date(view.decision_at)}</dd></div>
        <div><dt>Original expiry</dt><dd>{date(view.valid_until)}</dd></div>
        <div><dt>Plan status</dt><dd>{words(view.plan_status)}</dd></div>
        <div><dt>Candidate generation</dt><dd>{words(view.candidate_generation.status)} · {words(view.candidate_generation.reason)}</dd></div>
      </dl>
      {#if view.expired}<p class="notice">Original plan expired</p>{/if}
      <p>Confidence: {view.confidence} · <span>Effects unqualified</span></p>
      {#if view.policyComparison}
        <h2>Observed greywater policy</h2>
        {@const policy = view.policyComparison}
        {#if policy.expired}<p class="notice">Owner policy observation is stale</p>{/if}
        {#if policy.owner_reason}<p>At original issue: {words(policy.owner_reason)} · {words(policy.owner_scheduling)}.</p>{/if}
        {#if policy.status === 'observed_block'}<p>Observed block: {words(policy.gate)}.</p>
        {:else}<p>Policy gate comparison unavailable · {words(policy.reason)}.</p>{/if}
        {#each policy.comparisons as comparison (comparison.intent_id)}
          <p>Greywater proposal: {words(comparison.status)}.</p>
        {/each}
        {#if !policy.comparisons.length}<p>No greywater proposal to compare at this issue.</p>{/if}
        {#if policy.evaluated_at}<p>Owner evaluated {date(policy.evaluated_at)} · expires {date(policy.valid_until)}.</p>{/if}
        <p>Action eligibility and performance benefits remain unknown.</p>
      {:else}
        <p>Current OpenHAB policy comparison: unavailable · {words(view.policy_comparison.reason)}</p>
      {/if}
      <h2>Suggested action</h2>
      {#if selected.length === 0}<p>No action selected</p>
      {:else}<p>Selected shadow proposals: {selected.map(item => item.type).join(', ')}. Effects remain unqualified.</p>{/if}
      <p>Expected effects are model estimates; unknown values remain unknown.</p>
    {:else}
      <p>Verified observation unavailable</p>
      <p>Suggested action, model identities, effects and policy comparison are unavailable.</p>
    {/if}
  </Tile>
  <Tile label="Battery forecast accuracy">
    {#if battery}
      {#if battery.expired}<p class="notice">Battery accuracy report is stale</p>{/if}
      <p>Mean absolute error in battery SoC percentage points; lower is better.</p>
      <div class="source-table">
        <table><thead><tr><th>Horizon</th><th>Constant power</th><th>Hold SoC</th><th>Samples</th><th>Origin days</th></tr></thead>
          <tbody>{#each ['1', '6', '12', '24'] as hours}
            {@const row = battery.by_horizon[hours]}
            <tr><td>{hours}h</td><td>{row.count ? row.mae_soc_pct.constant_power.toFixed(2) : 'Collecting'}</td>
              <td>{row.count ? row.mae_soc_pct.hold_soc.toFixed(2) : 'Collecting'}</td><td>{row.count} / {row.attempted_count} attempts</td><td>{row.unique_origin_days}</td></tr>
          {/each}</tbody>
        </table>
      </div>
      <p>Assumes current battery power continues; capacity is configured. One original forecast per hour over the last seven days.</p>
      <p>Last measured endpoint: {battery.last_target_at ? date(battery.last_target_at) : 'Collecting'}.</p>
      {#if battery.next_mature_at}<p>Next pending assessment: {date(battery.next_mature_at)}.</p>{/if}
      <p>Report updated {date(battery.generated_at)}. These comparisons do not establish action benefits.</p>
    {:else}<p>Battery accuracy report unavailable</p>{/if}
  </Tile>
  <Tile label="Captured-PV forecast accuracy">
    {#if capturedPv}
      {#if capturedPv.expired}<p class="notice">Captured-PV accuracy report is stale</p>{/if}
      <p>Controller DC output after charging acceptance. Errors in kWh for the hour ending at each lead; lower is better.</p>
      <div class="source-table">
        <table><thead><tr><th>Lead</th><th>Scenario</th><th>Model MAE</th><th>Persistence MAE</th><th>RMSE skill</th><th>Pairs / mature</th><th>Origin days</th></tr></thead>
          <tbody>{#each ['1', '6', '12', '24'] as hours}
            {#each [['constant_load_pv', 'Constant AC load'], ['profiled_load_pv', 'Learned AC load']] as [key, label]}
              {@const row = capturedPv.by_horizon[hours].models[key]}
              <tr><td>{hours}h</td><td>{label}</td><td>{row.count ? row.mae_kwh.toFixed(3) : 'Collecting'}</td>
                <td>{row.count ? row.persistence_mae_kwh.toFixed(3) : 'Collecting'}</td>
                <td>{row.count && row.rmse_skill !== null ? `${(row.rmse_skill * 100).toFixed(1)}%` : 'Unavailable'}</td>
                <td>{row.count} / {row.attempted_count}</td><td>{row.unique_origin_days}</td></tr>
            {/each}
          {/each}</tbody>
        </table>
      </div>
      <p>Only hours with at least 99% qualified coverage are scored. Each model and its current-PV persistence reference use the same observed intervals and paired samples.</p>
      <p>Positive RMSE skill beats persistence; negative skill is worse. Skill is unavailable when the reference error is zero.</p>
      <p>First qualified original per UTC hour over seven days; {capturedPv.unique_origin_days} independent origin days. Dense readings are not independent experiments.</p>
      <p>Last measured hour ends: {capturedPv.last_target_at ? date(capturedPv.last_target_at) : 'Collecting'}.</p>
      {#if capturedPv.next_mature_at}<p>Next pending assessment: {date(capturedPv.next_mature_at)}.</p>{/if}
      <p>Report updated {date(capturedPv.generated_at)}. Potential array yield remains unscored. These provisional comparisons do not establish calibration or action benefits.</p>
    {:else}<p>Captured-PV accuracy report unavailable</p>{/if}
  </Tile>
  {#if view?.qualification_report}
    <Tile label="Intent qualification">
      <section aria-label="Intent qualification">
        <p>Every intent family remains unqualified. Request translation stays disabled.</p>
        <p>Original-plan evidence informs a separate release review. Action eligibility remains unknown.</p>
        {#if view.expired}<p class="notice">Original plan expired; its evidence is historical.</p>{/if}
        {#each view.qualification_report.families as family, i (family.intent_type)}
          <details>
            <summary>{QUALIFICATION_FAMILIES[i][2]} · not qualified</summary>
            <p>{family.proposal_count} original proposals · owner {family.owner ?? 'unavailable'}.</p>
            <div class="source-table"><table>
              <thead><tr><th>Release gate</th><th>Evidence</th><th>Reason</th></tr></thead>
              <tbody>{#each family.gates as gate, j (gate.id)}
                <tr><td>{QUALIFICATION_GATES[j][1]}</td><td>{gate.evidence_status === 'observed' ? 'Observed in original' : 'Unavailable'}</td><td>{words(gate.reason)}</td></tr>
              {/each}</tbody>
            </table></div>
          </details>
        {/each}
      </section>
    </Tile>
  {/if}
  {#if view}
    <Tile label="Models and original identities">
      {#each view.model_identities as model (model.domain)}
        <h2>{words(model.domain)} model</h2>
        <p>Confidence: {model.confidence} · {words(model.qualification)}</p>
        <dl class="identities">
          <dt>Artifact</dt><dd>{model.artifact_sha256 ?? 'unavailable'}</dd>
          <dt>Runtime</dt><dd>{model.runtime_sha256 ?? 'unavailable'}</dd>
          <dt>Projection</dt><dd>{model.projection_sha256}</dd>
        </dl>
      {/each}
      <dl class="identities"><dt>Snapshot</dt><dd>{view.snapshot_id}</dd><dt>Receipt</dt><dd>{view.receipt_sha256}</dd></dl>
      <p>Verified {date(view.verified_at)} · original source and intent expiry retained</p>
    </Tile>
    <Tile label="Shadow proposals and hard constraints">
      {#if !view.proposals.length}<p>No optional proposals generated. No qualified action effects available.</p>{/if}
      {#each view.proposals as proposal (proposal.intent_id)}
        <article>
          <h2>{proposal.type}</h2>
          <p>Shadow proposal · {proposal.selected ? 'selected' : 'not selected'} · Confidence: {proposal.confidence}</p>
          <p>Decision: {proposal.decision_status} · {words(proposal.decision_reason)}</p>
          <p>Reasons: {proposal.reasons.map(words).join(', ')}</p>
          <dl class="summary">
            {#each Object.entries(proposal.expected_effects) as [key, value]}
              <div><dt>{key}: {value === null ? 'unknown' : `${value} ${proposal.effect_units[key]} modeled`}</dt></div>
            {/each}
          </dl>
          <h3>Hard constraints</h3>
          <ul>{#each proposal.hard_checks as check}<li>{words(check.rule)}: {check.status} · {words(check.reason)}</li>{/each}</ul>
        </article>
      {/each}
    </Tile>
    <Tile label="Evidence quality and source blockers">
      <p>Original issue quality and current expiry are shown separately.</p>
      <div class="source-table">
        <table><thead><tr><th>Source</th><th>At issue</th><th>Now</th><th>Reason</th></tr></thead>
          <tbody>{#each view.source_quality as source (`${source.domain}:${source.role}`)}
            <tr><td>{source.domain} · {words(source.role)}</td><td>{source.quality_at_issue}</td><td>{source.current_quality}</td><td>{words(source.reason)}</td></tr>
          {/each}</tbody>
        </table>
      </div>
    </Tile>
  {/if}
</div>

<style>
  .household { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.7rem; align-content: start; }
  h1 { margin: 0.3rem 0; font-size: 1.4rem; }
  h2 { font-size: 1rem; margin: 0.8rem 0 0.35rem; }
  h3 { font-size: 0.9rem; }
  p, li, dl, table { font-size: 0.85rem; line-height: 1.45; }
  p { margin: 0.45rem 0; }
  .notice { color: #fbbf24; }
  .summary { display: flex; flex-wrap: wrap; gap: 0.6rem 1.5rem; }
  dt, th { color: #8b93a1; text-align: left; }
  dd { margin: 0; }
  .identities dd { font-family: monospace; overflow-wrap: anywhere; margin-bottom: 0.35rem; }
  .source-table { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 0.35rem 0.5rem; vertical-align: top; border-bottom: 1px solid #1c2230; }
  article + article { margin-top: 1rem; border-top: 1px solid #1c2230; }
  @media (min-width: 1050px) { .household { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
