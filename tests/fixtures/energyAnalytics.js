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
