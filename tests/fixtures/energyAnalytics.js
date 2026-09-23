export const GENERATED_AT = '2026-08-20T18:00:00+00:00';
export const GENERATED_AT_MS = Date.parse(GENERATED_AT);

export function energyAnalyticsFixture(overrides = {}) {
  return {
    schema: 'earthship-energy-ui/v1',
    generatedAt: GENERATED_AT,
    timezone: 'America/Denver',
    epochId: 'discover_4_module_2026',
    throughDate: '2026-08-19',
    status: 'degraded',
    battery: {
      status: 'ok', latestMinSocPct: 67, latestReached99: true,
      endingCumulativeEfc: 4.36, currentNoFullDays: 0, daysSinceFull: 0,
    },
    energy: {
      status: 'ok',
      latest: { date: '2026-08-19', pvKwh: 8, loadKwh: 5, chargeKwh: 4, dischargeKwh: 3 },
      activeLoads: { status: 'unavailable', measurement: 'state_only', reason: 'no_power_meter_contract' },
      observedCurtailmentKwh: null,
      observedCurtailmentStatus: 'unavailable',
    },
    winter: {
      status: 'unavailable', observationDays: 0, lowestSocPct: null,
      medianMinSocPct: null, longestNoFullDays: null, worstDeficitPeriod: null,
    },
    lifecycle: {
      status: 'ok', chargeKwh: 7, dischargeKwh: 7, periodEfc: 0.33,
      endingCumulativeEfc: 4.36, highSocHoursAbove90: 6,
      highSocHoursAbove95: 1.5, stateOfHealthPct: null,
      moduleHealth: {
        status: 'unavailable', reason: 'no_module_samples', moduleCount: null,
        latestCurrentSharingRangeA: null, maximumCellSpreadMv: null,
      },
    },
    forecast: {
      status: 'current', issuedAt: '2026-08-20T17:00:00+00:00',
      validFor: '2026-08-21T06:00:00-06:00', pv24hKwh: 7.2,
      nextMorningSocPct: null, fullToday: null, fullTomorrow: null, reason: null,
    },
    health: {
      status: 'degraded', analytics: 'ok', forecast: 'ok', bms: 'ok',
      schneider: 'ok', weather: 'ok', collector: 'ok', publisher: 'ok', reasons: [],
    },
    ...overrides,
  };
}

export function energyAnalyticsV2Fixture() {
  const value = energyAnalyticsFixture();
  value.schema = 'earthship-energy-ui/v2';
  Object.assign(value.battery, { latestDepthOfDischargePct: 16, latestEfc: 0.16 });
  return value;
}

export function energyAnalyticsV3Fixture() {
  const value = energyAnalyticsV2Fixture();
  value.schema = 'earthship-energy-ui/v3';
  value.battery.status = 'degraded';
  value.battery.endingCumulativeEfc = null;
  value.lifecycle.endingCumulativeEfc = null;
  value.energy.latest.loadKwh = null;
  value.accounting = {
    policy: 'qualified_power_evidence_v1',
    basis: 'observed_qualified_throughput_in_requested_window',
    cutover: '2026-08-18T12:00:00Z', windowStart: '2026-08-18',
    windowEndExclusive: '2026-08-20', daysPresent: 1, missingDays: 1,
    latestBatteryCoverage: 0.8, latestPvCoverage: 0.9,
    latestRevision: { id: 12, sha256: 'a'.repeat(64), computedAt: GENERATED_AT },
    loadStatus: 'ac_load_evidence_unqualified',
  };
  return value;
}

export function energyAnalyticsV4Fixture() {
  const value = energyAnalyticsV3Fixture();
  value.schema = 'earthship-energy-ui/v4';
  value.acLoad = {
    policy: 'qualified_inverter_ac_output_v1',
    cutover: '2026-08-18T12:00:00Z',
    topologyFrom: '2026-08-18T12:00:00Z', topologyUntil: null,
    status: 'observed',
    latest: { date: '2026-08-19', observedKwh: 12.5, coverage: 0.95,
      windowStart: '2026-08-19T06:00:00Z', windowEnd: '2026-08-20T06:00:00Z',
      revision: { id: 7, sha256: 'b'.repeat(64), computedAt: GENERATED_AT } },
  };
  return value;
}
