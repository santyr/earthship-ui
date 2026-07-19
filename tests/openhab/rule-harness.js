import vm from 'node:vm';

const NULL_STATES = new Set(['NULL', 'UNDEF']);

function stringState(value) {
  return {
    toString() {
      return String(value);
    },
  };
}

// Emulates a real openHAB local zone so ZonedDateTime.toString() renders the
// bracketed zone id form that production produces. The exact offset is
// arbitrary; the point is a non-'Z' rendering that strict Instant.parse rejects.
const HARNESS_ZONE_OFFSET_MINUTES = -360; // -06:00, America/Denver-like
const HARNESS_ZONE_ID = 'America/Denver';

function offsetLabel(offsetMinutes, { colon = true } = {}) {
  const sign = offsetMinutes < 0 ? '-' : '+';
  const abs = Math.abs(offsetMinutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, '0');
  const mm = String(abs % 60).padStart(2, '0');
  return `${sign}${hh}${colon ? ':' : ''}${mm}`;
}

function localWallClock(epochMs) {
  return new Date(epochMs + (HARNESS_ZONE_OFFSET_MINUTES * 60_000))
    .toISOString()
    .replace('Z', '');
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
    plusNanos(nanos) {
      return zonedDateTime(epochMs + Math.round(Number(nanos) / 1e6));
    },
    // Production ZonedDateTime.now().toString() ends in a bracketed zone id
    // (e.g. 2026-07-18T06:00:00.000-06:00[America/Denver]). Strict
    // Instant.parse() cannot parse this; the rules must normalize first.
    toString() {
      return `${localWallClock(epochMs)}${offsetLabel(HARNESS_ZONE_OFFSET_MINUTES)}[${HARNESS_ZONE_ID}]`;
    },
  };
}

function instant(epochMs) {
  return {
    toEpochMilli() {
      return epochMs;
    },
    // Instant.toString() renders a UTC instant ending in 'Z'.
    toString() {
      return new Date(epochMs).toISOString();
    },
  };
}

// Renders a string exactly as an openHAB DateTime item state does: a colon-less
// numeric offset (confirmed live: 2026-07-19T07:09:25.359-0600). Tests use this
// to simulate an item-state round-trip through persistence/readback.
export function openhabDateTimeState(input, { offsetMinutes = HARNESS_ZONE_OFFSET_MINUTES } = {}) {
  const epochMs = typeof input === 'number' ? input : Date.parse(String(input));
  const local = new Date(epochMs + (offsetMinutes * 60_000)).toISOString().replace('Z', '');
  return `${local}${offsetLabel(offsetMinutes, { colon: false })}`;
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
  filename = 'openhab/rules/feeder-owner.js',
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
      // Emulates real time.toInstant / Instant.parse strictness: a
      // ZonedDateTime object resolves via its own toInstant(); a STRING is
      // accepted only when it is an ISO-8601 UTC instant ending in 'Z'.
      // Offset, colon-less-offset, and bracketed-zone forms throw exactly as
      // production does, so the rules' tolerant timestamp parser is exercised.
      toInstant(value) {
        if (typeof value?.toInstant === 'function') return value.toInstant();
        const text = String(value);
        if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(text)) {
          throw new Error(`invalid instant: ${value}`);
        }
        const parsed = Date.parse(text);
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
    new vm.Script(`(function earthshipRule() {\n${source}\n}());`, {
      filename,
    }).runInContext(context);
  }

  function runNextTimer() {
    const timer = timers.shift();
    if (!timer) throw new Error('no pending timer');
    nowMs = Math.max(nowMs, timer.at);
    timer.callback();
  }

  // Drains timers to quiescence, including timers that reschedule themselves
  // (the bounded provider/coupling verification re-poll). Bounded to avoid
  // spinning forever on a genuine bug.
  function runTimersUntilIdle(max = 64) {
    let ran = 0;
    while (timers.length > 0 && ran < max) {
      runNextTimer();
      ran += 1;
    }
    return ran;
  }

  return {
    events,
    execute,
    runNextTimer,
    runTimersUntilIdle,
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
