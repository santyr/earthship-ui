import vm from 'node:vm';

const NULL_STATES = new Set(['NULL', 'UNDEF']);

function stringState(value) {
  return {
    toString() {
      return String(value);
    },
  };
}

function zonedDateTime(epochMs) {
  return {
    epochMs,
    toInstant() {
      return instant(epochMs);
    },
    plusSeconds(seconds) {
      return zonedDateTime(epochMs + (Number(seconds) * 1000));
    },
    toString() {
      return new Date(epochMs).toISOString();
    },
  };
}

function instant(epochMs) {
  return {
    toEpochMilli() {
      return epochMs;
    },
  };
}

export function feederRequest(requestId, requestedAt = '2026-07-18T12:00:00.000Z') {
  return JSON.stringify({ requestId, requestedAt });
}

export function feederLedger(entries = []) {
  return JSON.stringify({
    version: 'feeder-request-ledger/v1',
    entries,
  });
}

export function createRuleHarness({
  source,
  now = Date.parse('2026-07-18T12:00:00.000Z'),
  states = {},
  histories = {},
  javaInterop = false,
} = {}) {
  if (typeof source !== 'string' || !source.trim()) {
    throw new TypeError('exact OpenHAB rule source is required');
  }

  let nowMs = now;
  let timerFailure = null;
  let persistFailure = null;
  let delayedPersistReads = 0;
  let pendingPersist = null;
  let suppressRequestReadback = false;
  const commandFailures = [];
  const heldProviders = new Set();
  const events = [];
  const timers = [];
  const shared = new Map();
  const itemStates = new Map(Object.entries({
    GoatFeeder_ManualRequest: 'NULL',
    GoatFeeder_ManualResult: 'NULL',
    Goat_Plugs_Outlet2_Switch: 'OFF',
    GoatFeedings: '7',
    ...states,
  }).map(([name, value]) => [name, String(value)]));
  const persisted = new Map(Object.entries(histories).map(([name, values]) => [
    name,
    values.map(String),
  ]));

  function item(name) {
    if (!itemStates.has(name)) itemStates.set(name, 'NULL');
    return {
      name,
      get state() {
        return stringState(itemStates.get(name));
      },
      postUpdate(value) {
        const next = String(value);
        events.push({ type: 'update', item: name, value: next });
        if (!(suppressRequestReadback && name === 'GoatFeeder_ManualRequest')) {
          itemStates.set(name, next);
        }
      },
      sendCommand(value) {
        const next = String(value);
        const failureIndex = commandFailures.findIndex((failure) => (
          failure.item === name && failure.value === next
        ));
        if (failureIndex >= 0) {
          const [failure] = commandFailures.splice(failureIndex, 1);
          throw failure.error;
        }
        events.push({ type: 'command', item: name, value: next });
        // A held provider records the command but does not reflect it into
        // state, simulating a device whose physical readback never followed
        // the command (provider-generation mismatch).
        if (!heldProviders.has(name)) itemStates.set(name, next);
      },
      persistence: {
        persist(serviceId) {
          events.push({
            type: 'persist',
            item: name,
            serviceId: serviceId ?? null,
            value: itemStates.get(name),
          });
          if (persistFailure) throw persistFailure;
          if (delayedPersistReads > 0) {
            pendingPersist = { item: name, value: itemStates.get(name), remaining: delayedPersistReads };
            delayedPersistReads = 0;
            return;
          }
          const history = persisted.get(name) ?? [];
          history.push(itemStates.get(name));
          persisted.set(name, history);
        },
        previousState(_skipEqual, serviceId) {
          events.push({ type: 'history', item: name, serviceId: serviceId ?? null });
          if (pendingPersist?.item === name) {
            if (pendingPersist.remaining > 0) pendingPersist.remaining -= 1;
            else {
              const history = persisted.get(name) ?? [];
              history.push(pendingPersist.value);
              persisted.set(name, history);
              pendingPersist = null;
            }
          }
          const history = persisted.get(name) ?? [];
          if (history.length === 0) return null;
          return { state: stringState(history.at(-1)) };
        },
      },
    };
  }

  const openhab = {
    items: {
      getItem: item,
    },
    cache: {
      shared: {
        get(key, supplier) {
          if (shared.has(key)) return shared.get(key);
          if (typeof supplier !== 'function') return null;
          const value = supplier();
          shared.set(key, value);
          return value;
        },
        put(key, value) {
          const previous = shared.has(key) ? shared.get(key) : null;
          shared.set(key, value);
          return previous;
        },
        remove(key) {
          const previous = shared.has(key) ? shared.get(key) : null;
          shared.delete(key);
          return previous;
        },
      },
    },
    actions: {
      ScriptExecution: {
        createTimer(at, callback) {
          if (timerFailure) throw timerFailure;
          const timer = { at: at.epochMs, callback };
          timers.push(timer);
          events.push({ type: 'timer', at: timer.at });
          return timer;
        },
      },
    },
    time: {
      toInstant(value) {
        if (typeof value?.toInstant === 'function') return value.toInstant();
        const parsed = Date.parse(String(value).replace(/\[[^\]]+\]$/, ''));
        if (!Number.isFinite(parsed)) throw new Error(`invalid instant: ${value}`);
        return instant(parsed);
      },
      ZonedDateTime: {
        now() {
          return zonedDateTime(nowMs);
        },
      },
    },
  };

  function execute(event) {
    class JavaString {
      constructor(value) { this.value = String(value); }
      getBytes() { return new TextEncoder().encode(this.value); }
    }
    const context = vm.createContext({
      event,
      require(specifier) {
        if (specifier !== 'openhab') throw new Error(`unexpected module: ${specifier}`);
        return openhab;
      },
      console: {
        debug() {},
        info() {},
        warn() {},
        error() {},
      },
      Date,
      JSON,
      Math,
      Number,
      String,
      Error,
      TypeError,
      TextEncoder,
      Java: javaInterop ? {
        type(name) {
          if (name === 'java.lang.Thread') return {
            sleep(ms) { events.push({ type: 'sleep', value: Number(ms) }); },
          };
          if (name === 'java.lang.String') return JavaString;
          if (name === 'java.nio.charset.StandardCharsets') return { UTF_8: 'UTF_8' };
          throw new Error(`unexpected Java type: ${name}`);
        },
      } : undefined,
    });
    new vm.Script(`(function earthshipFeederRule() {\n${source}\n}());`, {
      filename: 'openhab/rules/feeder-owner.js',
    }).runInContext(context);
  }

  function runNextTimer() {
    const timer = timers.shift();
    if (!timer) throw new Error('no pending timer');
    nowMs = Math.max(nowMs, timer.at);
    timer.callback();
  }

  return {
    events,
    execute,
    runNextTimer,
    pendingTimers: () => timers.length,
    state: (name) => itemStates.get(name),
    history: (name) => [...(persisted.get(name) ?? [])],
    setState(name, value) {
      itemStates.set(name, String(value));
    },
    advance(ms) {
      nowMs += ms;
    },
    clearVolatileCache() {
      shared.clear();
    },
    setTimerFailure(error) {
      timerFailure = error;
    },
    setPersistFailure(error) {
      persistFailure = error;
    },
    delayNextPersistVisibility(reads) {
      delayedPersistReads = Number(reads);
    },
    suppressRequestReadback(value = true) {
      suppressRequestReadback = value;
    },
    failNextCommand(itemName, value, error = new Error('injected command failure')) {
      commandFailures.push({ item: itemName, value: String(value), error });
    },
    holdProvider(itemName) {
      heldProviders.add(itemName);
    },
    releaseProvider(itemName) {
      heldProviders.delete(itemName);
    },
    resultPayloads() {
      return events
        .filter(({ type, item: name }) => type === 'update' && name === 'GoatFeeder_ManualResult')
        .map(({ value }) => JSON.parse(value));
    },
    actuatorCommands() {
      return events.filter(({ type, item: name }) => (
        type === 'command' && name === 'Goat_Plugs_Outlet2_Switch'
      ));
    },
    ledger() {
      const raw = itemStates.get('GoatFeeder_ManualRequest');
      return NULL_STATES.has(raw) ? null : JSON.parse(raw);
    },
  };
}
