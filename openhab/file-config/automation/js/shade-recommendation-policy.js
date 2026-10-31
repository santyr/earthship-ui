'use strict';

// PREPARED ONLY: policy persistence, never shade/load commands or OverrideSwitch
// writes. Night-load ownership, schedules and greywater remain unchanged.
// The future commissioned owner must share this lock for final automatic
// admission AND policy inhibition; no physical owner exists in this repository.
const { rules, triggers, items, cache } = require('openhab');
const UUID = Java.type('java.util.UUID');
const ReentrantLock = Java.type('java.util.concurrent.locks.ReentrantLock');
const Thread = Java.type('java.lang.Thread');
const System = Java.type('java.lang.System');
const LOCK_KEY = 'earthship/shade-recommendation-policy/serialized-owner-v1';
const lock = cache.shared.get(LOCK_KEY, () => new ReentrantLock());
const POLICY = {
  kitchen: 'Shade_Kitchen_RecommendationAutomation',
  living: 'Shade_LivingRoom_RecommendationAutomation',
  bathroom: 'Shade_Bathroom_RecommendationAutomation',
  bedroom: 'Shade_Bedroom_RecommendationAutomation',
};
const REVISION = 'Shade_RecommendationAutomationRevision';
const SESSION = 'Shade_RecommendationAutomationSession';
const ownerSession = String(UUID.randomUUID());
// A reload/restart cannot borrow a restored receipt from the previous owner.
items.getItem(SESSION).postUpdate('UNDEF');
let initialized = false;
const valid = (value) => value === 'ON' || value === 'OFF';
const state = (name) => String(items.getItem(name).state);
const persisted = (item) => {
  const previous = item.persistence.previousState(false, 'jdbc');
  return previous === null ? null : { state: String(previous.state),
    at: Number(previous.timestamp.toInstant().toEpochMilli()) };
};

function restoreDefaults() {
  for (const name of Object.values(POLICY)) {
    const target = items.getItem(name);
    if (valid(String(target.state))) continue;
    // A failed JDBC read is NOT evidence of a fresh installation.
    const saved = persisted(target);
    if (saved !== null && !valid(saved.state)) throw new Error('saved_policy_invalid');
    target.postUpdate(saved === null ? 'OFF' : saved.state);
  }
  Thread.sleep(50); // registry settlement, never a motor wait
}

function commitReceipt() {
  const receipt = { schemaVersion: 1, generation: String(UUID.randomUUID()), ownerSession, at: Date.now(),
    preferences: {}, persistedAt: {}, override: null, durable: false };
  try {
    const barrier = Date.now();
    Thread.sleep(2); // an older equal Boolean must not satisfy a new commit
    const pending = new Map();
    for (const [zone, name] of Object.entries(POLICY)) {
      const target = items.getItem(name), value = String(target.state);
      receipt.preferences[zone] = valid(value) ? value : null;
      if (!valid(value)) throw new Error('policy_unrestored');
      target.persistence.persist('jdbc');
      pending.set(zone, { target, value });
    }
    // JDBC writes are asynchronous. Submit the four independent observations
    // together, then confirm actual rows against this commit's original barrier.
    // A matching older Boolean never acknowledges the new generation.
    const deadline = Number(System.nanoTime()) + 2_000_000_000;
    for (let attempt = 0; attempt < 80 && pending.size && Number(System.nanoTime()) < deadline; attempt += 1) {
      Thread.sleep(25);
      for (const [zone, { target, value }] of pending) {
        const proof = persisted(target);
        if (proof?.state === value && proof.at > barrier) {
          receipt.persistedAt[zone] = proof.at;
          pending.delete(zone);
        }
      }
    }
    if (pending.size) throw new Error('policy_persistence_unconfirmed');
    // Read the existing policy as a stable state, without a last-change TTL.
    const override = state('OverrideSwitch');
    receipt.override = valid(override) ? override : null;
    receipt.durable = true;
  } catch (_) { /* publish a new invalid generation; no cached authority */ }
  receipt.at = Date.now();
  const target = items.getItem(REVISION);
  target.postUpdate(JSON.stringify(receipt));
  Thread.sleep(25);
  target.persistence.persist('jdbc');
  items.getItem(SESSION).postUpdate(receipt.durable ? ownerSession : 'UNDEF');
  // The Node owner separately requires exact JDBC receipt readback before
  // confirming any choice. This registry write alone confers no authority.
}

rules.JSRule({
  id: 'hex_shade_recommendation_policy',
  name: 'Shade recommendation permissions — policy only',
  triggers: [triggers.SystemStartlevelTrigger(100),
    ...Object.values(POLICY).map((name) => triggers.ItemStateChangeTrigger(name)),
    triggers.ItemStateChangeTrigger('OverrideSwitch')],
  execute: (event) => {
    lock.lock();
    try {
      // Of the declared triggers only the completed-startup event lacks an
      // itemName. Restoration updates before startlevel 100 cannot authorize.
      if (!event?.itemName) {
        try { restoreDefaults(); initialized = true; }
        catch (_) { initialized = false; items.getItem(SESSION).postUpdate('UNDEF'); }
      }
      if (initialized) commitReceipt();
    } finally { lock.unlock(); }
  },
});
