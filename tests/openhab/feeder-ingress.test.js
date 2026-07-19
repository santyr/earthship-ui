import { describe, expect, it, vi } from 'vitest';
import {
  bindOpenhabReceipt,
  buildIngressReceipt,
  quiesceServices,
  restoreServices,
  topologicalOrder,
  withReceiptChecksum,
} from '../../scripts/feeder-ingress.mjs';
import * as ingressModule from '../../scripts/feeder-ingress.mjs';

const capturedUnits = [
  {
    id: 'lnbits.service',
    scope: 'system',
    exists: true,
    enabled: 'enabled',
    activeState: 'active',
    subState: 'running',
    mainPid: 101,
    commandHash: 'a'.repeat(64),
    listeners: [3002],
    openhabConnections: 1,
    dependsOn: [],
  },
  {
    id: 'lightning_goats.service',
    scope: 'system',
    exists: true,
    enabled: 'enabled',
    activeState: 'active',
    subState: 'running',
    mainPid: 202,
    commandHash: 'b'.repeat(64),
    listeners: [8090],
    openhabConnections: 1,
    dependsOn: ['lnbits.service'],
  },
];

function receipt(units = capturedUnits) {
  return buildIngressReceipt({
    generation: 'ingress-20260718T160000Z',
    units,
    unknownProcesses: [],
    createdAt: '2026-07-18T16:00:00.000Z',
  });
}

describe('feeder ingress transaction', () => {
  it('orders dependencies forward and stops dependents first', () => {
    expect(topologicalOrder(capturedUnits)).toEqual([
      'lnbits.service',
      'lightning_goats.service',
    ]);
  });

  it('refuses dependency cycles, duplicate IDs, and unmapped feeder callers', () => {
    expect(() => buildIngressReceipt({
      generation: 'duplicate',
      units: [capturedUnits[0], capturedUnits[0]],
      unknownProcesses: [],
    })).toThrow(/duplicate/i);
    expect(() => buildIngressReceipt({
      generation: 'cycle',
      units: [
        { ...capturedUnits[0], dependsOn: ['lightning_goats.service'] },
        capturedUnits[1],
      ],
      unknownProcesses: [],
    })).toThrow(/cycle/i);
    expect(() => buildIngressReceipt({
      generation: 'unknown',
      units: capturedUnits,
      unknownProcesses: [{ pid: 303, reason: 'port 3002' }],
    })).toThrow(/unmapped/i);
  });

  it('binds an exempt connection to a PID, process start, command, and allowlisted reason', () => {
    const exemptProcess = {
      pid: 404,
      startTicks: 12345,
      commandHash: 'c'.repeat(64),
      reason: 'earthship-ui-vite-proxy',
    };
    const captured = buildIngressReceipt({
      generation: 'exempt',
      units: capturedUnits,
      exemptProcesses: [exemptProcess],
    });
    expect(captured.exemptProcesses).toEqual([exemptProcess]);

    expect(() => buildIngressReceipt({
      generation: 'reused-pid',
      units: capturedUnits,
      exemptProcesses: [{ ...exemptProcess, startTicks: null }],
    })).toThrow(/start time/i);
    expect(() => buildIngressReceipt({
      generation: 'wrong-reason',
      units: capturedUnits,
      exemptProcesses: [{ ...exemptProcess, reason: 'arbitrary-process' }],
    })).toThrow(/reason/i);
  });

  it('retains ownerless relevant sockets and rejects idle unmapped feeder processes', () => {
    expect(typeof ingressModule.socketInventoryFromText).toBe('function');
    expect(typeof ingressModule.classifyIngressObservation).toBe('function');
    if (
      typeof ingressModule.socketInventoryFromText !== 'function'
      || typeof ingressModule.classifyIngressObservation !== 'function'
    ) return;

    const sockets = ingressModule.socketInventoryFromText(
      'LISTEN 0 128 0.0.0.0:3002 0.0.0.0:*',
      'ESTAB 0 0 10.0.0.3:5190 10.0.0.2:8080',
    );
    expect(sockets.listeners).toEqual([
      expect.objectContaining({ pid: null, port: 3002 }),
    ]);
    expect(sockets.connections).toEqual([
      expect.objectContaining({ pid: null, remotePort: 8080 }),
    ]);

    const classified = ingressModule.classifyIngressObservation({
      units: capturedUnits.map((unit) => ({ ...unit, pids: [unit.mainPid] })),
      sockets,
      processes: [{
        pid: 505,
        startTicks: 9876,
        commandHash: 'd'.repeat(64),
        isKnownFeederCaller: true,
        exemptReason: null,
      }],
    });
    expect(classified.exemptProcesses).toEqual([]);
    expect(classified.unknownProcesses).toEqual(expect.arrayContaining([
      expect.objectContaining({ pid: null, reason: expect.stringMatching(/ownerless.*3002/i) }),
      expect.objectContaining({ pid: null, reason: expect.stringMatching(/ownerless.*8080/i) }),
      expect.objectContaining({ pid: 505, reason: 'unmapped known feeder caller' }),
    ]));
  });

  it('recognizes relative feeder scripts from their canonical working directories', () => {
    expect(typeof ingressModule.isKnownFeederCaller).toBe('function');
    const middlewareCaller = ingressModule.isKnownFeederCaller(
      ['python', 'main.py'],
      '/home/sat/bin/middleware',
    );
    const apiCaller = ingressModule.isKnownFeederCaller(
      ['python3', 'fastapi_ap.py'],
      '/home/sat/bin',
    );
    expect(middlewareCaller).toBe(true);
    expect(apiCaller).toBe(true);
    expect(ingressModule.isKnownFeederCaller(
      ['python', 'main.py'],
      '/tmp',
    )).toBe(false);
    expect(ingressModule.isKnownFeederCaller(
      ['python', 'main.py'],
      null,
    )).toBe(true);

    const classified = ingressModule.classifyIngressObservation({
      units: capturedUnits.map((unit) => ({ ...unit, pids: [unit.mainPid] })),
      sockets: { listeners: [], connections: [] },
      processes: [
        {
          pid: 606,
          startTicks: 111,
          commandHash: 'e'.repeat(64),
          isKnownFeederCaller: middlewareCaller,
          exemptReason: null,
        },
        {
          pid: 707,
          startTicks: 222,
          commandHash: 'f'.repeat(64),
          isKnownFeederCaller: apiCaller,
          exemptReason: null,
        },
      ],
    });
    expect(classified.unknownProcesses).toEqual([
      { pid: 606, reason: 'unmapped known feeder caller' },
      { pid: 707, reason: 'unmapped known feeder caller' },
    ]);
  });

  it('quiesces captured-active services in reverse topological order', async () => {
    const calls = [];
    const adapter = {
      stop: vi.fn(async (unit) => calls.push(`stop:${unit.id}`)),
      verifyQuiescent: vi.fn(async (unit) => calls.push(`quiet:${unit.id}`)),
      start: vi.fn(),
      verifyReady: vi.fn(),
    };
    const result = await quiesceServices(receipt(), adapter, { allowStopKnownServices: true });

    expect(calls).toEqual([
      'stop:lightning_goats.service',
      'quiet:lightning_goats.service',
      'stop:lnbits.service',
      'quiet:lnbits.service',
    ]);
    expect(result.phase).toBe('quiescent');
  });

  it('passes the complete receipt to the global quiescence verifier', async () => {
    const verifyAllQuiescent = vi.fn();
    const adapter = {
      stop: vi.fn(),
      verifyQuiescent: vi.fn(),
      verifyAllQuiescent,
      start: vi.fn(),
      verifyReady: vi.fn(),
    };
    const captured = receipt(capturedUnits.map((unit) => ({
      ...unit,
      activeState: 'inactive',
      subState: 'dead',
      mainPid: 0,
      listeners: [],
      openhabConnections: 0,
    })));

    await quiesceServices(captured, adapter, { allowStopKnownServices: true });

    expect(verifyAllQuiescent).toHaveBeenCalledOnce();
    expect(verifyAllQuiescent.mock.calls[0][0]).toMatchObject({
      generation: captured.generation,
      units: captured.units,
      exemptProcesses: [],
    });
  });

  it('compensates in forward order after a partial stop failure', async () => {
    const calls = [];
    const adapter = {
      async stop(unit) {
        calls.push(`stop:${unit.id}`);
        if (unit.id === 'lnbits.service') throw new Error('injected stop failure');
      },
      async verifyQuiescent(unit) {
        calls.push(`quiet:${unit.id}`);
      },
      async start(unit) {
        calls.push(`start:${unit.id}`);
      },
      async verifyReady(unit) {
        calls.push(`ready:${unit.id}`);
      },
    };

    await expect(quiesceServices(
      receipt(),
      adapter,
      { allowStopKnownServices: true },
    )).rejects.toThrow(/compensating restore completed/i);
    expect(calls).toEqual([
      'stop:lightning_goats.service',
      'quiet:lightning_goats.service',
      'stop:lnbits.service',
      'start:lnbits.service',
      'ready:lnbits.service',
      'start:lightning_goats.service',
      'ready:lightning_goats.service',
    ]);
  });

  it('restores dependencies before dependents and preserves captured-inactive units', async () => {
    const inactive = {
      ...capturedUnits[1],
      activeState: 'inactive',
      subState: 'dead',
      mainPid: 0,
      listeners: [],
      openhabConnections: 0,
    };
    const calls = [];
    const adapter = {
      async start(unit) { calls.push(`start:${unit.id}`); },
      async verifyReady(unit) { calls.push(`ready:${unit.id}`); },
      async verifyInactive(unit) { calls.push(`inactive:${unit.id}`); },
    };

    await restoreServices(receipt([capturedUnits[0], inactive]), adapter);
    expect(calls).toEqual([
      'start:lnbits.service',
      'ready:lnbits.service',
      'inactive:lightning_goats.service',
    ]);
  });

  it('binds only an exact checksum-valid open OpenHAB feeder receipt', () => {
    const ingress = withReceiptChecksum({ ...receipt(), phase: 'quiescent' });
    expect(ingress.captureChecksum).toMatch(/^[a-f0-9]{64}$/);
    const openhab = withReceiptChecksum({
      schema: 'earthship-ui-openhab-feeder-receipt/v1',
      subset: 'feeder',
      state: 'open',
      generation: 'feeder-20260718T160000Z',
      ingressGeneration: ingress.generation,
      ingressBinding: {
        generation: ingress.generation,
        checksum: ingress.captureChecksum,
      },
    });
    const bound = bindOpenhabReceipt(ingress, openhab);
    expect(bound.openhabBinding).toEqual({
      generation: openhab.generation,
      checksum: openhab.checksum,
    });
    expect(bindOpenhabReceipt(bound, openhab)).toEqual(bound);

    expect(() => bindOpenhabReceipt(ingress, { ...openhab, subset: 'other' }))
      .toThrow(/checksum|feeder/i);
    expect(() => bindOpenhabReceipt(ingress, withReceiptChecksum({
      ...openhab,
      ingressBinding: { ...openhab.ingressBinding, checksum: 'f'.repeat(64) },
    }))).toThrow(/binding/i);
  });

  it('authorizes caller restoration only from a closed allowed OpenHAB terminal', () => {
    expect(typeof ingressModule.assertRestoreReceiptPair).toBe('function');
    if (typeof ingressModule.assertRestoreReceiptPair !== 'function') return;

    const ingress = withReceiptChecksum({ ...receipt(), phase: 'quiescent' });
    const openhab = withReceiptChecksum({
      schema: 'earthship-ui-openhab-feeder-receipt/v1',
      subset: 'feeder',
      state: 'open',
      phase: 'snapshot',
      generation: 'feeder-20260718T160000Z',
      ingressGeneration: ingress.generation,
      snapshotChecksum: 'e'.repeat(64),
      ingressBinding: {
        generation: ingress.generation,
        checksum: ingress.captureChecksum,
      },
    });
    const bound = bindOpenhabReceipt(ingress, openhab);

    expect(() => ingressModule.assertRestoreReceiptPair(bound, openhab)).toThrow(/closed/i);
    const closed = withReceiptChecksum({
      ...openhab,
      state: 'closed',
      phase: 'closed',
      terminal: 'desired',
    });
    expect(() => ingressModule.assertRestoreReceiptPair(bound, closed)).not.toThrow();
    expect(() => ingressModule.assertRestoreReceiptPair(bound, withReceiptChecksum({
      ...closed,
      terminal: 'unexpected',
    }))).toThrow(/terminal/i);
  });

  it('fsyncs the receipt file and parent directory around atomic rename', async () => {
    expect(typeof ingressModule.durableAtomicWriteJson).toBe('function');
    if (typeof ingressModule.durableAtomicWriteJson !== 'function') return;
    const calls = [];
    const fileHandle = {
      async writeFile(value) { calls.push(['write', value]); },
      async sync() { calls.push(['file-sync']); },
      async close() { calls.push(['file-close']); },
    };
    const directoryHandle = {
      async sync() { calls.push(['directory-sync']); },
      async close() { calls.push(['directory-close']); },
    };
    const openFile = async (path, flags, mode) => {
      calls.push(['open', path, flags, mode]);
      return flags === 'r' ? directoryHandle : fileHandle;
    };

    await ingressModule.durableAtomicWriteJson('/tmp/receipts/feeder.json', { safe: true }, {
      makeDirectory: async (...args) => calls.push(['mkdir', ...args]),
      openFile,
      renameFile: async (...args) => calls.push(['rename', ...args]),
    });

    expect(calls.map(([action]) => action)).toEqual([
      'mkdir',
      'open',
      'write',
      'file-sync',
      'file-close',
      'rename',
      'open',
      'directory-sync',
      'directory-close',
    ]);
  });

  it('matches restored enabled state and per-process command identities across new PIDs', () => {
    expect(typeof ingressModule.restoredUnitMatchesCapture).toBe('function');
    if (typeof ingressModule.restoredUnitMatchesCapture !== 'function') return;
    const captured = {
      ...capturedUnits[0],
      pids: [101, 102],
      processes: [
        { pid: 101, startTicks: 1001, commandHash: '1'.repeat(64) },
        { pid: 102, startTicks: 1002, commandHash: '2'.repeat(64) },
      ],
    };
    const restarted = {
      ...captured,
      pids: [901, 902],
      processes: [
        { pid: 901, startTicks: 9001, commandHash: '2'.repeat(64) },
        { pid: 902, startTicks: 9002, commandHash: '1'.repeat(64) },
      ],
    };
    expect(ingressModule.restoredUnitMatchesCapture(captured, restarted)).toBe(true);
    expect(ingressModule.restoredUnitMatchesCapture(captured, {
      ...restarted,
      enabled: 'disabled',
    })).toBe(false);
    expect(ingressModule.restoredUnitMatchesCapture(captured, {
      ...restarted,
      processes: restarted.processes.slice(0, 1),
    })).toBe(false);
  });

  it('closes ingress only with the terminal corresponding to its authorized restore', () => {
    expect(typeof ingressModule.assertIngressCloseTerminal).toBe('function');
    if (typeof ingressModule.assertIngressCloseTerminal !== 'function') return;

    expect(() => ingressModule.assertIngressCloseTerminal({
      state: 'open',
      phase: 'restored',
      openhabTerminal: 'desired',
    }, 'restored')).not.toThrow();
    expect(() => ingressModule.assertIngressCloseTerminal({
      state: 'open',
      phase: 'restored',
      openhabTerminal: 'unmutated',
    }, 'restored-unmutated')).not.toThrow();
    expect(() => ingressModule.assertIngressCloseTerminal({
      state: 'open',
      phase: 'restored',
      openhabTerminal: 'absent',
    }, 'restored-no-openhab')).not.toThrow();
    expect(() => ingressModule.assertIngressCloseTerminal({
      state: 'open',
      phase: 'restored',
      openhabTerminal: 'rolled-back',
    }, 'restored-unmutated')).toThrow(/terminal/i);
    expect(() => ingressModule.assertIngressCloseTerminal({
      state: 'open',
      phase: 'quiescent',
      openhabTerminal: 'desired',
    }, 'restored')).toThrow(/phase/i);
  });
});

describe('transaction self-connection exemption', () => {
  it('ignores the CLI process own OpenHAB monitor connection', async () => {
    const { classifyIngressObservation } = await import('../../scripts/feeder-ingress.mjs');
    const observed = classifyIngressObservation({
      units: [],
      sockets: {
        listeners: [],
        connections: [{ pid: process.pid, remotePort: 8080 }],
      },
      processes: [],
    });
    expect(observed.unknownProcesses).toEqual([]);
    expect(observed.exemptProcesses).toEqual([]);
  });
});
