// Managed rule hex_living_room_circadian. Canonical Git source; deploy via REST.
// Use Astro's existing elevation and the TP-Link binding's synchronous action.
// Do NOT use colorTemperatureAbs.sendCommand for automation: it sets on_off=1.
// A CT-only raw request preserves power/brightness on the installed KL125s,
// including OFF between query and write (qualified on hardware 2026-10-12).
const { actions, items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const AtomicBoolean = Java.type('java.util.concurrent.atomic.AtomicBoolean');
const SERVICE = 'smartlife.iot.smartbulb.lightingservice';
const BULBS = [
  {name:'living room 1', uid:'tplinksmarthome:kl125:E7FA31', switchItem:'living_room_1_Switch', actualItem:'LivingRoomCircadian_LivingRoom1_ActualK'},
  {name:'living room 2', uid:'tplinksmarthome:kl125:E62B6D', switchItem:'living_room_2_Switch', actualItem:'LivingRoomCircadian_LivingRoom2_ActualK'},
  {name:'living room 3', uid:'tplinksmarthome:kl125:E7CAD9', switchItem:'LED_living_room_1_Switch', actualItem:'LivingRoomCircadian_LivingRoom3_ActualK'},
];
const MIN_DELTA_K = 100;
const MIN_QUERY_INTERVAL_MS = 240000;
const SOLAR_MAX_AGE_MS = 120000; // existing Astro thing updates every 16 seconds
const FAILURE_BACKOFF_MS = 15 * 60 * 1000;
const lock = cache.private.get('lrCircadianBindingLock', () => new AtomicBoolean(false));
function nowMs() { return Instant.now().toEpochMilli(); }
function post(name, value) {
  const item = items.getItem(name);
  if (String(item.state) !== String(value)) item.postUpdate(String(value));
}
function enabled() { return String(items.getItem('LivingRoomCircadian_Enable').state) === 'ON'; }
function solar() {
  if (String(things.getThing('astro:sun:local').status) !== 'ONLINE') throw Error('astro-offline');
  const item = items.getItem('Sun_Position_Elevation');
  const raw = String(item.state).trim();
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:\s*°)?$/.test(raw)) throw Error('astro-invalid');
  const elev = parseFloat(raw);
  if (!Number.isFinite(elev) || elev < -90 || elev > 90) throw Error('astro-invalid');
  const stamp = item.lastStateUpdateTimestamp;
  if (stamp === null || stamp === undefined) throw Error('astro-no-timestamp');
  const age = nowMs() - stamp.toInstant().toEpochMilli();
  if (!Number.isFinite(age) || age < 0 || age > SOLAR_MAX_AGE_MS) throw Error('astro-stale');
  return {elev, targetK:2500 + Math.round(Math.max(0, Math.min(50, elev)) * 80)};
}
function resetFailure(b) {
  cache.private.remove('lrFailure:' + b.uid);
  cache.private.remove('lrBackoff:' + b.uid);
}
function recordFailure(b) {
  const key = 'lrFailure:' + b.uid;
  const count = Number(cache.private.get(key) || 0) + 1;
  cache.private.put(key, count);
  if (count >= 2) cache.private.put('lrBackoff:' + b.uid, nowMs() + FAILURE_BACKOFF_MS);
}
function send(action, method, params) {
  const raw = action.send(JSON.stringify({[SERVICE]:{[method]:params}}));
  const result = JSON.parse(String(raw))[SERVICE];
  const body = result && result[method];
  if (!body || body.err_code !== 0) throw Error('device-response-error');
  return body;
}
function read(action) {
  const body = send(action, 'get_light_state', {});
  if (body.on_off !== 0 && body.on_off !== 1) throw Error('state-unknown');
  const k = body.color_temp;
  if (body.on_off === 1 && (!Number.isInteger(k) || (k !== 0 && (k < 2500 || k > 6500)))) throw Error('temperature-invalid');
  // RGB mode has no measured white temperature; OFF's dft_on_state is a preset.
  return {on:body.on_off === 1, k:body.on_off === 1 && k !== 0 ? k : null};
}
function publishActual(b, state) { post(b.actualItem, state.on && state.k !== null ? state.k : 'UNDEF'); }
function disabled() {
  cache.private.remove('lrBindingLastK');
  cache.private.remove('lrBindingLastRunMs');
  post('LivingRoomCircadian_LastResult', 'disabled');
}
function unavailable(reason) {
  cache.private.remove('lrBindingLastK');
  cache.private.remove('lrBindingLastRunMs');
  post('LivingRoomCircadian_TargetK', 'UNDEF');
  post('LivingRoomCircadian_LastResult', 'unavailable: ' + reason);
}
const evt = typeof event === 'undefined' || event === null ? {} : event;
const triggerItem = String(evt.itemName || '');
const recovery = BULBS.filter(b => {
  const state = String(evt.newState || evt.receivedState || evt.itemState || (triggerItem === b.switchItem ? items.getItem(b.switchItem).state : ''));
  return (triggerItem === b.switchItem && state === 'ON' && (evt.eventType !== 'update' || cache.private.get('lrAwaitingOn:' + b.uid) === true)) ||
    (String(evt.thingUID || '') === b.uid && String(evt.newStatus || evt.status || things.getThing(b.uid).status) === 'ONLINE');
});
// A blocking request must not lose ON/ONLINE recovery notifications. The next
// Astro/cron evaluation consumes this marker if a run is already in progress.
recovery.forEach(b => cache.private.put('lrRecoveryPending:' + b.uid, true));
if (!lock.compareAndSet(false, true)) return;
try {
  if (!enabled()) { disabled(); return; }
  let calc;
  try { calc = solar(); } catch (e) { unavailable(String(e.message || e)); return; }
  const policyChange = triggerItem === 'LivingRoomCircadian_Enable';
  if (policyChange) BULBS.forEach(resetFailure);
  const pending = BULBS.filter(b => cache.private.get('lrRecoveryPending:' + b.uid) === true);
  pending.forEach(b => { resetFailure(b); cache.private.remove('lrRecoveryPending:' + b.uid); });
  const force = policyChange || pending.length > 0;
  const lastRun = cache.private.get('lrBindingLastRunMs');
  const lastK = cache.private.get('lrBindingLastK');
  if (!force && lastRun !== null && lastK !== null && nowMs() - Number(lastRun) < MIN_QUERY_INTERVAL_MS && Math.abs(calc.targetK - Number(lastK)) < MIN_DELTA_K) return;
  cache.private.put('lrBindingLastRunMs', nowMs());
  cache.private.put('lrBindingLastK', calc.targetK);
  post('LivingRoomCircadian_TargetK', calc.targetK);
  const results = [];
  let degraded = false;
  for (const b of BULBS) {
    if (!enabled()) { disabled(); return; }
    if (String(items.getItem(b.switchItem).state) === 'OFF') {
      cache.private.remove('lrAwaitingOn:' + b.uid);
      post(b.actualItem, 'UNDEF');
      resetFailure(b);
      results.push(b.name + '=skip-off');
      continue;
    }
    if (String(things.getThing(b.uid).status) !== 'ONLINE') {
      cache.private.remove('lrAwaitingOn:' + b.uid);
      post(b.actualItem, 'UNDEF');
      degraded = true;
      results.push(b.name + '=offline');
      continue;
    }
    if (nowMs() < Number(cache.private.get('lrBackoff:' + b.uid) || 0)) {
      post(b.actualItem, 'UNDEF');
      degraded = true;
      results.push(b.name + '=backoff');
      continue;
    }
    let measured = null;
    try {
      const action = actions.get('tplinksmarthome', b.uid);
      if (!action) throw Error('action-unavailable');
      measured = read(action);
      if (!measured.on && String(items.getItem(b.switchItem).state) === 'ON') cache.private.put('lrAwaitingOn:' + b.uid, true);
      else cache.private.remove('lrAwaitingOn:' + b.uid);
      publishActual(b, measured);
      if (!enabled()) { disabled(); return; }
      if (!measured.on || String(items.getItem(b.switchItem).state) === 'OFF') {
        post(b.actualItem, 'UNDEF');
        resetFailure(b);
        results.push(b.name + '=skip-off');
        continue;
      }
      if (measured.k !== null && Math.abs(measured.k - calc.targetK) < MIN_DELTA_K) {
        resetFailure(b);
        results.push(b.name + '=ok-current(' + measured.k + 'K)');
        continue;
      }
      // Recheck the existing solar source and policy after the blocking query.
      try { solar(); } catch (e) { unavailable(String(e.message || e)); return; }
      if (!enabled()) { disabled(); return; }
      // Omit on_off and brightness. Even a late manual OFF stays OFF.
      measured = null; // attempted writes can time out after changing the bulb
      send(action, 'transition_light_state', {ignore_default:1,color_temp:calc.targetK,transition_period:0});
      measured = read(action);
      publishActual(b, measured);
      if (!measured.on) {
        resetFailure(b);
        results.push(b.name + '=skip-off');
      } else if (measured.k === null || Math.abs(measured.k - calc.targetK) >= MIN_DELTA_K) {
        throw Error('verify-mismatch');
      } else {
        resetFailure(b);
        results.push(b.name + '=verified(' + measured.k + 'K)');
      }
    } catch (e) {
      cache.private.remove('lrAwaitingOn:' + b.uid);
      if (measured === null) post(b.actualItem, 'UNDEF');
      recordFailure(b); // include failed writes; don't reset on successful query
      degraded = true;
      results.push(b.name + '=error(' + String(e.message || e).substring(0, 80) + ')');
    }
  }
  if (!enabled()) { disabled(); return; }
  const summary = (degraded ? 'degraded' : 'healthy') + ' checkedAt=' + String(Instant.now()) + ' elev=' + calc.elev.toFixed(1) + ' target=' + calc.targetK + 'K ' + results.join(' | ');
  post('LivingRoomCircadian_LastResult', summary);
  console.info('LR circadian (TP-Link binding): ' + summary);
} catch (e) {
  unavailable('rule-error: ' + String(e.message || e).substring(0, 120));
  console.error('LR circadian: ' + String(e));
} finally {
  lock.set(false);
}
