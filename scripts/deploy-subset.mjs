#!/usr/bin/env node
// Attended subset deployment driver (Task 6, 2026-07-19).
// Prints the validated apply/rollback plan for review (--plan), or executes
// one phase against live openHAB (--execute-apply / --execute-rollback).
// The plan output IS the request guard: execution refuses any request not in
// the reviewed plan file.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';

import path from 'node:path';
import {
  getSubset,
  buildSubsetApplyPlan,
  buildSubsetRollbackPlan,
  graphImmutableUids,
  ruleHash,
  assertUnchangedGraphHashes,
} from './openhab-config.mjs';

const [, , command, subsetName, planFile] = process.argv;
const ROOT = path.dirname(new URL(import.meta.url).pathname);
const manifest = JSON.parse(readFileSync(path.join(ROOT, '../openhab/managed-resources.json'), 'utf8'));
const subset = getSubset(manifest, subsetName);
const source = readFileSync(path.join(ROOT, '..', subset.rule.source), 'utf8');

const envText = readFileSync(path.join(process.env.HOME, '.config/hex/openhab.env'), 'utf8');
const TOKEN = envText.match(/^(?:export\s+)?OPENHAB_TOKEN=["']?([^"'\n]+)/m)?.[1];
if (!TOKEN) throw new Error('OPENHAB_TOKEN not found in ~/.config/hex/openhab.env');
const BASE = 'http://127.0.0.1:8080';

async function rest(method, restPath, body) {
  const res = await fetch(`${BASE}${restPath}`, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': typeof body === 'string' ? 'text/plain' : 'application/json',
    },
    body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  });
  const text = await res.text();
  if (!res.ok && !(method === 'GET' && res.status === 404)) {
    throw new Error(`${method} ${restPath} -> ${res.status}: ${text.slice(0, 200)}`);
  }
  return { status: res.status, body: text };
}

function planSummary(plan) {
  return plan.map((r, i) => `${String(i).padStart(2)} ${r.method.padEnd(6)} ${r.path}  # ${r.kind}`).join('\n');
}

const snapshotDir = path.join(ROOT, `../.superpowers/sdd/deploy-${subsetName}`);

if (command === 'plan') {
  const original = {};
  const originalRule = JSON.parse((await rest('GET', `/rest/rules/${subset.rule.uid}`)).body || '{}');
  if (originalRule.uid) original.rule = originalRule;
  const apply = buildSubsetApplyPlan({ manifest, subsetName, source, original });
  const rollback = buildSubsetRollbackPlan({ manifest, subsetName, original });
  mkdirSync(snapshotDir, { recursive: true });
  writeFileSync(path.join(snapshotDir, 'apply-plan.json'), JSON.stringify(apply, null, 2));
  writeFileSync(path.join(snapshotDir, 'rollback-plan.json'), JSON.stringify(rollback, null, 2));
  writeFileSync(path.join(snapshotDir, 'original-rule.json'), JSON.stringify(originalRule, null, 2));
  const hashes = {};
  for (const uid of graphImmutableUids(subset)) {
    const live = JSON.parse((await rest('GET', `/rest/rules/${uid}`)).body || '{}');
    hashes[uid] = ruleHash(live);
  }
  writeFileSync(path.join(snapshotDir, 'graph-hashes.json'), JSON.stringify(hashes, null, 2));
  console.log(`# APPLY PLAN (${subsetName}) — ${apply.length} requests`);
  console.log(planSummary(apply));
  console.log(`\n# ROLLBACK PLAN — ${rollback.length} requests`);
  console.log(planSummary(rollback));
  console.log(`\nplans + snapshot + graph hashes written to ${snapshotDir}`);
} else if (command === 'execute') {
  const plan = JSON.parse(readFileSync(path.join(snapshotDir, `${planFile}.json`), 'utf8'));
  for (const [i, r] of plan.entries()) {
    const out = await rest(r.method, r.path, r.body);
    console.log(`${String(i).padStart(2)} ${r.method} ${r.path} -> ${out.status}`);
  }
} else if (command === 'verify-graph') {
  const captured = JSON.parse(readFileSync(path.join(snapshotDir, 'graph-hashes.json'), 'utf8'));
  const liveHashes = {};
  for (const uid of Object.keys(captured)) {
    liveHashes[uid] = ruleHash(JSON.parse((await rest('GET', `/rest/rules/${uid}`)).body || '{}'));
  }
  assertUnchangedGraphHashes(subset, captured, liveHashes);
  console.log('graph hashes unchanged:', Object.keys(captured).join(', ') || '(none tracked)');
} else {
  console.log('usage: deploy-subset.mjs plan|execute|verify-graph <subset> [apply-plan|rollback-plan]');
  process.exit(1);
}
