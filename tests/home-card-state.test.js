import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  HOME_AQI_COLORS,
  HOME_AQI_TEXT_COLOR,
  HOME_STATE_COLORS,
  HOME_UV_COLORS,
  HOME_WIND_COLORS,
  adaptCurrentAqi,
  advanceGoatFeederTracker,
  batteryDirectionState,
  batteryPowerFlowPresentation,
  batteryIcon,
  bitcoinStateColor,
  aqiChipColor,
  createGoatFeederTracker,
  curtailmentColor,
  formatGoatFeedings,
  greywaterState,
  harvestedGallons,
  indoorTemperatureIconColor,
  localDayHistoryRange,
  maxHistoryValue,
  netStateColor,
  nextSeasonEvent,
  outdoorConditionIcon,
  outdoorTemperatureIconColor,
  pressurePresentation,
  relativeAgeText,
  rainRateChip,
  rainStateColor,
  solarPvColor,
  uvIndexColor,
  windSpeedColor,
} from '../src/lib/ui/homeCardState.js';

const home = readFileSync(new URL('../src/screens/Home.svelte', import.meta.url), 'utf8');

function relativeLuminance(hex) {
  const channels = hex.match(/[0-9a-f]{2}/gi).map((channel) => {
    const value = Number.parseInt(channel, 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground, background) {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
    / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
}

describe('Home signed card state colors', () => {
  it.each([
    ['0', '0 feedings today'],
    ['1', '1 feeding today'],
    ['2.4', '2 feedings today'],
    ['UNDEF', 'Feedings unavailable'],
    [-1, 'Feedings unavailable'],
  ])('formats Goat feedings %s truthfully', (raw, expected) => {
    expect(formatGoatFeedings(raw)).toBe(expected);
  });

  it('activates only after a known OFF to ON transition', () => {
    let state = createGoatFeederTracker();
    let result = advanceGoatFeederTracker(state, 'ON');
    expect(result.activated).toBe(false);
    state = result.tracker;

    result = advanceGoatFeederTracker(state, 'ON');
    expect(result.activated).toBe(false);
    state = advanceGoatFeederTracker(result.tracker, 'OFF').tracker;

    expect(advanceGoatFeederTracker(state, 'ON').activated).toBe(true);
  });

  it('breaks the OFF to ON chain when an unknown state intervenes', () => {
    let state = advanceGoatFeederTracker(createGoatFeederTracker(), 'OFF').tracker;
    state = advanceGoatFeederTracker(state, 'UNDEF').tracker;

    expect(advanceGoatFeederTracker(state, 'ON').activated).toBe(false);
  });

  it('counts browser-local calendar days to the 2026 autumn equinox', () => {
    expect(nextSeasonEvent(new Date(2026, 6, 18, 23, 30))).toMatchObject({
      name: 'autumn equinox',
      days: 66,
      label: '66 days to autumn equinox',
    });
  });

  it('uses singular and event-day seasonal wording', () => {
    expect(nextSeasonEvent(new Date(2026, 8, 21, 12))).toMatchObject({
      days: 1,
      label: '1 day to autumn equinox',
    });
    expect(nextSeasonEvent(new Date(2026, 8, 22, 23))).toMatchObject({
      days: 0,
      label: 'autumn equinox today',
    });
  });

  it('counts local calendar days across daylight-saving changes', () => {
    expect(nextSeasonEvent(new Date(2026, 2, 7, 23))).toMatchObject({
      name: 'spring equinox',
      days: 13,
    });
  });

  it('rolls from the December solstice to the next spring equinox', () => {
    expect(nextSeasonEvent(new Date(2026, 11, 22, 12))).toMatchObject({
      name: 'spring equinox',
    });
  });

  it('declines dates outside the supported astronomical approximation', () => {
    expect(nextSeasonEvent(new Date(1999, 0, 1))).toBeNull();
    expect(nextSeasonEvent(new Date('invalid'))).toBeNull();
  });

  it.each([
    [null, { text: '—', glyph: '', color: HOME_STATE_COLORS.neutral }],
    ['UNDEF', { text: '—', glyph: '', color: HOME_STATE_COLORS.neutral }],
    [0, { text: '0 W', glyph: '', color: HOME_STATE_COLORS.neutral }],
    [-0, { text: '0 W', glyph: '', color: HOME_STATE_COLORS.neutral }],
    [12.6, { text: '+13 W', glyph: '▲', color: HOME_STATE_COLORS.positive }],
    [-12.6, { text: '−13 W', glyph: '▼', color: '#f59e0b' }],
  ])('presents battery power flow %s without implying motion at zero', (value, expected) => {
    expect(batteryPowerFlowPresentation(value)).toEqual(expected);
  });

  it('formats relative age against an injected live clock', () => {
    const event = new Date(2026, 6, 18, 12, 0).getTime();
    expect(relativeAgeText(new Date(event).toISOString(), event + 29 * 60_000)).toBe('29 m ago');
    expect(relativeAgeText(new Date(event).toISOString(), event + 61 * 60_000)).toBe('1 h ago');
    expect(relativeAgeText(new Date(event).toISOString(), event + 26 * 3_600_000)).toBe('1 d ago');
  });

  it.each([null, 'NULL', 'UNDEF', 'not-a-date'])('keeps invalid relative age %s honest', (value) => {
    expect(relativeAgeText(value, Date.now())).toBe('—');
  });

  it('builds a local-midnight-to-now history range', () => {
    const now = new Date(2026, 6, 18, 15, 42, 17, 123);
    const range = localDayHistoryRange(now);
    const start = new Date(range.starttime);
    const end = new Date(range.endtime);

    expect([start.getFullYear(), start.getMonth(), start.getDate()]).toEqual([2026, 6, 18]);
    expect([start.getHours(), start.getMinutes(), start.getSeconds(), start.getMilliseconds()]).toEqual([0, 0, 0, 0]);
    expect(end.getTime()).toBe(now.getTime());
  });

  it('finds the maximum finite history value without inventing unavailable data', () => {
    expect(maxHistoryValue([
      { state: '8.5' },
      { state: 'UNDEF' },
      { state: 17 },
      { state: 'NaN' },
    ])).toBe(17);
    expect(maxHistoryValue([])).toBeNull();
    expect(maxHistoryValue(null)).toBeNull();
  });

  it.each([
    [1, HOME_STATE_COLORS.positive],
    [-1, HOME_STATE_COLORS.negative],
    [0, HOME_STATE_COLORS.neutral],
    [null, HOME_STATE_COLORS.neutral],
  ])('maps power-flow net %s to %s', (value, expected) => {
    expect(netStateColor(value)).toBe(expected);
  });

  it.each([
    [1, HOME_STATE_COLORS.positive],
    [-1, HOME_STATE_COLORS.negative],
    [0, HOME_STATE_COLORS.bitcoin],
    [null, HOME_STATE_COLORS.bitcoin],
  ])('maps Bitcoin change %s to %s', (value, expected) => {
    expect(bitcoinStateColor(value)).toBe(expected);
  });

  it.each([
    [null, HOME_WIND_COLORS.neutral],
    [0, HOME_WIND_COLORS.neutral],
    [4.99, HOME_WIND_COLORS.neutral],
    [5, HOME_WIND_COLORS.green],
    [14.99, HOME_WIND_COLORS.green],
    [15, HOME_WIND_COLORS.orange],
    [24.99, HOME_WIND_COLORS.orange],
    [25, HOME_WIND_COLORS.red],
  ])('maps wind speed %s to %s', (value, expected) => {
    expect(windSpeedColor(value)).toBe(expected);
  });

  it.each([
    [null, HOME_UV_COLORS.neutral],
    [-1, HOME_UV_COLORS.neutral],
    [0, HOME_UV_COLORS.green],
    [2, HOME_UV_COLORS.green],
    [3, HOME_UV_COLORS.yellow],
    [5, HOME_UV_COLORS.yellow],
    [6, HOME_UV_COLORS.orange],
    [7, HOME_UV_COLORS.orange],
    [8, HOME_UV_COLORS.red],
    [10, HOME_UV_COLORS.red],
    [11, HOME_UV_COLORS.purple],
  ])('maps UV index %s to %s', (value, expected) => {
    expect(uvIndexColor(value)).toBe(expected);
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    ['UNDEF', HOME_STATE_COLORS.neutral],
    [50, '#22c55e'],
    [51, '#eab308'],
    [100, '#eab308'],
    [101, '#f97316'],
    [150, '#f97316'],
    [151, '#ef4444'],
    [200, '#ef4444'],
    [201, '#a855f7'],
    [300, '#a855f7'],
    [301, '#991b1b'],
    [500, '#991b1b'],
    [501, '#991b1b'],
  ])('maps AQI %s to EPA color %s', (value, expected) => {
    expect(aqiChipColor(value)).toBe(expected);
  });

  it.each([
    [null],
    [''],
    ['NULL'],
    ['UNDEF'],
    ['REFRESH'],
    ['42 AQI'],
    ['1e'],
    [-0.1],
    ['-1'],
  ])('treats invalid or negative current AQI %s as unavailable', (raw) => {
    expect(adaptCurrentAqi(raw)).toEqual({
      value: null,
      band: 'Unavailable',
      status: 'unavailable',
      accent: HOME_AQI_COLORS.unavailable,
      textColor: HOME_AQI_TEXT_COLOR,
    });
  });

  it.each([
    ['0', 0, 'Good', 'good', HOME_AQI_COLORS.good],
    ['50.4', 50, 'Good', 'good', HOME_AQI_COLORS.good],
    ['50.5', 51, 'Moderate', 'moderate', HOME_AQI_COLORS.moderate],
    ['100.4', 100, 'Moderate', 'moderate', HOME_AQI_COLORS.moderate],
    ['100.5', 101, 'Unhealthy for sensitive groups', 'unhealthy', HOME_AQI_COLORS.sensitive],
    ['150.4', 150, 'Unhealthy for sensitive groups', 'unhealthy', HOME_AQI_COLORS.sensitive],
    ['150.5', 151, 'Unhealthy', 'unhealthy', HOME_AQI_COLORS.unhealthy],
    ['200.5', 201, 'Very unhealthy', 'critical', HOME_AQI_COLORS.veryUnhealthy],
    ['300.5', 301, 'Hazardous', 'critical', HOME_AQI_COLORS.hazardous],
    ['500.4', 500, 'Hazardous', 'critical', HOME_AQI_COLORS.hazardous],
    ['500.5', 501, 'Beyond AQI / hazardous', 'critical', HOME_AQI_COLORS.beyond],
  ])(
    'rounds current AQI %s to %s before classifying it as %s',
    (raw, value, band, status, accent) => {
      expect(adaptCurrentAqi(raw)).toEqual({
        value,
        band,
        status,
        accent,
        textColor: HOME_AQI_TEXT_COLOR,
      });
    },
  );

  it('keeps small AQI text readable while the separate accent carries the EPA band', () => {
    const states = [0, 51, 101, 151, 201, 301, 501].map(adaptCurrentAqi);

    expect(contrastRatio(HOME_AQI_TEXT_COLOR, '#202631')).toBeGreaterThanOrEqual(4.5);
    expect(new Set(states.map((state) => state.textColor))).toEqual(new Set([HOME_AQI_TEXT_COLOR]));
    expect(new Set(states.map((state) => state.accent)).size).toBeGreaterThan(1);
    expect(states.at(-1)).toMatchObject({
      accent: HOME_AQI_COLORS.beyond,
      status: 'critical',
    });
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    [59.9, '#3498db'],
    [60, '#00bcd4'],
    [67.9, '#00bcd4'],
    [68, '#4caf50'],
    [73.9, '#4caf50'],
    [74, '#ff9800'],
    [79.9, '#ff9800'],
    [80, '#f44336'],
  ])('maps Indoor temperature %s to icon color %s', (value, expected) => {
    expect(indoorTemperatureIconColor(value)).toBe(expected);
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    [31.9, '#ab47bc'],
    [32, '#3498db'],
    [49.9, '#3498db'],
    [50, '#00bcd4'],
    [64.9, '#00bcd4'],
    [65, '#4caf50'],
    [74.9, '#4caf50'],
    [75, '#ff9800'],
    [84.9, '#ff9800'],
    [85, '#f44336'],
  ])('maps Outdoor temperature %s to icon color %s', (value, expected) => {
    expect(outdoorTemperatureIconColor(value)).toBe(expected);
  });

  it('keeps every Outdoor icon and sparkline band above 3:1 card contrast', () => {
    const bandColors = [null, 31.9, 32, 50, 65, 75, 85]
      .map((temperature) => outdoorTemperatureIconColor(temperature));

    for (const color of bandColors) {
      expect(contrastRatio(color, '#11151c'), color).toBeGreaterThanOrEqual(3);
    }
  });

  it.each([
    ['iconify:bi:sun-fill', 'iconify:bi:sun-fill'],
    ['iconify:mdi:weather-rainy', 'iconify:mdi:weather-rainy'],
    [null, 'iconify:mdi:weather-partly-cloudy'],
    ['', 'iconify:mdi:weather-partly-cloudy'],
    ['NULL', 'iconify:mdi:weather-partly-cloudy'],
    ['UNDEF', 'iconify:mdi:weather-partly-cloudy'],
    ['  ', 'iconify:mdi:weather-partly-cloudy'],
  ])('selects item-driven Outdoor icon %s as %s', (value, expected) => {
    expect(outdoorConditionIcon(value)).toBe(expected);
  });

  it.each([
    [0.42, 733],
    [1.72, 3000],
    [0, 0],
    [null, null],
    ['UNDEF', null],
    [-0.1, null],
  ])('converts harvested rain %s inches to %s gallons', (value, expected) => {
    expect(harvestedGallons(value)).toBe(expected);
  });

  it.each([
    ['ON', -4, 'charging', '▲', '#22c55e'],
    ['OFF', 4, 'charging', '▲', '#22c55e'],
    ['OFF', -4, 'discharging', '▼', '#f59e0b'],
    ['OFF', 0, 'idle', '●', HOME_STATE_COLORS.neutral],
    ['OFF', null, 'idle', '●', HOME_STATE_COLORS.neutral],
    [null, null, 'unavailable', '—', HOME_STATE_COLORS.neutral],
  ])('maps Battery status %s and current %s to %s', (status, current, text, glyph, color) => {
    expect(batteryDirectionState(status, current)).toEqual({ text, glyph, color });
  });

  it.each([
    ['iconify:mdi:battery-60', 'iconify:mdi:battery-60'],
    [null, 'iconify:mdi:battery'],
    ['NULL', 'iconify:mdi:battery'],
    ['UNDEF', 'iconify:mdi:battery'],
  ])('selects Battery icon %s as %s', (value, expected) => {
    expect(batteryIcon(value)).toBe(expected);
  });

  it.each([
    ['ON', 'Running', '#3b82f6'],
    ['OFF', 'Idle', HOME_STATE_COLORS.neutral],
    ['NULL', 'Unavailable', HOME_STATE_COLORS.neutral],
    ['UNDEF', 'Unavailable', HOME_STATE_COLORS.neutral],
    [null, 'Unavailable', HOME_STATE_COLORS.neutral],
  ])('maps Greywater %s to truthful state %s', (value, label, color) => {
    expect(greywaterState(value)).toEqual({ label, color });
  });

  it.each([
    ['falling', 'iconify:mdi:weather-lightning', '#ff5722', 'falling'],
    ['RISING', 'iconify:mdi:gauge', '#2196f3', 'rising'],
    ['steady', 'iconify:mdi:gauge', HOME_STATE_COLORS.neutral, 'steady'],
    ['UNDEF', 'iconify:mdi:gauge', HOME_STATE_COLORS.neutral, '—'],
    [null, 'iconify:mdi:gauge', HOME_STATE_COLORS.neutral, '—'],
  ])('maps pressure trend %s to its status presentation', (value, icon, color, label) => {
    expect(pressurePresentation(value)).toEqual({ icon, color, label });
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    [-0.1, HOME_STATE_COLORS.neutral],
    [0, HOME_STATE_COLORS.neutral],
    [0.01, '#3b82f6'],
  ])('maps daily rain %s to icon color %s', (value, expected) => {
    expect(rainStateColor(value)).toBe(expected);
  });

  it.each([
    [null, null],
    ['NULL', null],
    ['UNDEF', null],
    [-0.1, null],
    [0, null],
    [0.01, 'RAIN 0.01 in/h'],
    [0.126, 'RAIN 0.13 in/h'],
    [1.2, 'RAIN 1.2 in/h'],
  ])('formats rain rate %s as %s', (value, expected) => {
    expect(rainRateChip(value)).toBe(expected);
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    [0, HOME_STATE_COLORS.neutral],
    [49.9, HOME_STATE_COLORS.neutral],
    [50, '#ffc107'],
    [499.9, '#ffc107'],
    [500, '#ff9800'],
  ])('maps current PV %s to icon and current-line color %s', (value, expected) => {
    expect(solarPvColor(value)).toBe(expected);
  });

  it.each([
    [null, HOME_STATE_COLORS.neutral],
    [0, HOME_STATE_COLORS.neutral],
    [0.1, '#eab308'],
  ])('maps curtailment %s hours to indicator color %s', (value, expected) => {
    expect(curtailmentColor(value)).toBe(expected);
  });

  it('uses independent Wind colors plus current UV and Indoor icon UI', () => {
    expect(home).toContain('AmbientWeatherWS2902A_UVIndex');
    expect(home).toContain('class="outdoor-chips"');
    expect(home).toMatch(/class="aqi-chip"\s+class:unavailable=\{currentAqi\.value === null\}/);
    expect(home).toMatch(/class="wind-gust"\s+style="color: \{windGustColor\}"/);
    expect(home).toMatch(/class="wind-max"\s+style="color: \{windMaxColor\}"/);
    expect(home).toContain('icon="iconify:mdi:home-thermometer"');
    expect(home).toMatch(/class="indoor-icon"\s+style="color: \{indoorIconColor\}"/);
    expect(home).toContain('selectOutdoorConditionIcon($items.SkyConditionIcon)');
    expect(home).toMatch(/<OhIcon icon=\{outdoorConditionIcon\} size="2rem" color=\{outdoorIconColor\}/);
  });

  it('uses the Overview Bitcoin icon and couples its state color to the percentage', () => {
    expect(home).toContain('icon="iconify:mdi:bitcoin"');
    expect(home).toMatch(/class="btc-icon"\s+style="color:\s*\{btcPctColor\}"/);
    expect(home).toMatch(/class="btc-pct"\s+style="color:\s*\{btcPctColor\}"/);
  });

  it('keeps card sizes while enlarging the two primary temperature readings', () => {
    expect(home).toMatch(/\.big-temp\s*\{[^}]*font-size:\s*4\.4rem/is);
    expect(home).toMatch(/\.indoor-temp\s*\{[^}]*font-size:\s*4\.4rem/is);
  });

  it('removes the visible SoC label while retaining truthful battery accessibility', () => {
    expect(home).toMatch(/<Arc[^>]*label=""/);
    expect(home).not.toMatch(/<Arc[^>]*label="SoC"/);
    expect(home).toMatch(/<Arc\s+value=\{soc\}/);
    expect(home).not.toContain('value={soc ?? 0}');
    expect(home).toContain('current SoC unavailable');
    expect(home).toMatch(/current SoC \$\{Math\.round\(soc\)\}%/);
  });

  it('wires Battery direction separately from SoC and shows both truthful estimates', () => {
    expect(home).toContain('selectBatteryIcon($items.BatteryIcon)');
    expect(home).toMatch(/class="batt-indicator"\s+style="color: \{battIndicator\.color\}"/);
    expect(home).toContain('BMS_TimeToDischarge_Smoothed');
    expect(home).toContain('BMS_TimeToFull_Smoothed');
    expect(home).toContain('<strong>Empty</strong> {battRuntimeEmpty}');
    expect(home).toContain('<strong>Full</strong> {battRuntimeFull}');
    expect(home).not.toContain('BMS_Runtime_Basis');
    expect(home).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  it('wires the remaining Overview state icons without implying unavailable states', () => {
    expect(home).toContain('accessibleLabel={gwAccessibleLabel}');
    expect(home).toContain('icon="iconify:mdi:fountain"');
    expect(home).toContain('accent={windAccent}');
    expect(home).toContain('icon={pressureStatus.icon}');
    expect(home).toContain('style="color: {pressureStatus.color}"');
    expect(home).toContain('iconName="iconify:mdi:weather-rainy"');
    expect(home).toContain('iconColor={rainIconColor}');
    expect(home).toContain('icon="iconify:mdi:solar-power-variant"');
    expect(home).toContain('style="color: {solarColor}"');
  });

  it('centers Rain through StatTile and centers Sun and Moon without parent reach-through', () => {
    expect(home).toMatch(/<StatTile[\s\S]*?label="Rain"[\s\S]*?centerContent/);
    expect(home).not.toMatch(/\.rain-cell\s+:global/);
    expect(home).toMatch(/\{#if rainRateLabel\}[\s\S]*class="rain-rate-chip"/);
    expect(home).toMatch(/\.sunmoon-body\s*\{[^}]*justify-content:\s*center/is);
  });

  it('uses stronger smoothing only for the compact Baro sparkline', () => {
    expect(home).toMatch(
      /<Sparkline\s+data=\{baroSpark\}\s+color=\{colors\.label\}\s+lineWidth=\{2\}\s+smoothingAlpha=\{0\.12\}/
    );
    expect(home).toMatch(/<Sparkline\s+data=\{outdoorSpark\}\s+color=\{outdoorIconColor\}\s+lineWidth=\{2\}\s*\/>/);
    expect(home).toMatch(/<Sparkline\s+data=\{battSpark\}\s+color=\{socColor\}\s+lineWidth=\{2\}\s*\/>/);
  });
});
