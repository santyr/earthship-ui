import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

const home = read('src/screens/Home.svelte');
const header = read('src/lib/ui/Header.svelte');
const headerAlerts = read('src/lib/ui/HeaderAlerts.svelte');
const compass = read('src/lib/ui/CompassRose.svelte');
const goatFeedingsCard = read('src/lib/ui/GoatFeedingsCard.svelte');
const seasonCountdown = read('src/lib/ui/SeasonCountdown.svelte');
const sparkline = read('src/lib/ui/Sparkline.svelte');
const statTile = read('src/lib/ui/StatTile.svelte');
const tile = read('src/lib/ui/Tile.svelte');

describe('Home tablet presentation contract', () => {
  it('uses the shared additive ten-day forecast controls', () => {
    expect(home).toContain("import DailyForecast from '../lib/ui/DailyForecast.svelte'");
    expect(home).toContain('Forecast_10Day_JSON');
    expect(home).toContain('<DailyForecast');
    expect(home).toContain('variant="home"');
    expect(home).not.toMatch(/forecastDaily\.slice\(0,\s*7\)/);
  });

  it('uses the header ticker slot for a bounded accessible alert summary', () => {
    expect(header).not.toMatch(/BtcTicker|BTC_USD|Bitcoin/i);
    expect(header).toMatch(/<HeaderAlerts\s*\/>/);
    expect(headerAlerts).toContain('data-header-alerts');
    expect(headerAlerts).toMatch(/role="status"/);
    expect(headerAlerts).toContain('No active alerts');
    expect(headerAlerts).toMatch(/white-space:\s*nowrap/);
    expect(headerAlerts).toMatch(/text-overflow:\s*ellipsis/);
  });

  it('keeps the Bitcoin summary and lazy modal activation without inline history', () => {
    expect(home).toContain('btcPriceText');
    expect(home).toContain('btcPctText');
    expect(home).toMatch(/openBitcoinChart/);
    expect(home).not.toMatch(/btcSpark|refreshBtcSpark/);
    expect(home).not.toMatch(/class="btc-spark"/);
    expect(home).toMatch(/class="cell bitcoin-cell clickable"/);
  });

  it('places a read-only Goat summary between Power Flow and Greywater', () => {
    expect(home).toContain('class="cell goat-cell"');
    expect(home).toContain('feedings={$items.GoatFeedingsToday}');
    expect(home).toContain('motorState={$items.Goat_Plugs_Outlet2_Switch}');
    expect(home).toContain("'topbar topbar topbar topbar goat greywater'");
    expect(goatFeedingsCard).not.toMatch(/sendCommand|getClientOnce|onclick|role="button"/);
  });

  it('keeps the seasonal countdown live across local midnight', () => {
    expect(home).toMatch(/<SeasonCountdown\s*\/>/);
    expect(home).not.toContain('nextSeasonEvent(new Date())');
    expect(seasonCountdown).toContain('setInterval');
    expect(seasonCountdown).toContain('clearInterval');
    expect(seasonCountdown).toContain('class="sm-row sm-season"');
  });

  it('keeps time-based Home status live and scoped to the current local day', () => {
    expect(home).toContain('relativeAgeText($items.SouthOutlet_LastAutoRun, wallClock)');
    expect(home).toMatch(/wallClockTimer\s*=\s*setInterval/);
    expect(home).toMatch(/clearInterval\(wallClockTimer\)/);
    expect(home).toContain("fetchHistoryRange('AmbientWeatherWS2902A_WindGust'");
    expect(home).toContain('localDayHistoryRange(new Date())');
    expect(home).toContain('refreshWindGustMaxToday();');
    expect(home).not.toMatch(/fetchHistorySafe\('AmbientWeatherWS2902A_WindGust',\s*24\)/);
  });

  it('renders zero battery flow as a neutral stationary value', () => {
    expect(home).toContain('batteryPowerFlowPresentation(battWatts)');
    expect(home).toContain('{battFlow.text} {battFlow.glyph}');
    expect(home).not.toContain("battWatts >= 0 ? '▲' : '▼'");
  });

  it('pins the requested distance-readable Home typography', () => {
    expect(home).toMatch(/\.big-temp\s*\{[^}]*color:\s*#fff/is);
    expect(home).toMatch(/\.big-temp\s*\{[^}]*font-size:\s*4\.4rem/is);
    expect(home).toMatch(/\.indoor-temp\s*\{[^}]*font-size:\s*4\.4rem/is);
    expect(home).toMatch(/\.indoor-temp\s*\{[^}]*color:\s*#fff/is);
    expect(home).toMatch(/<StatTile[\s\S]*?label="Rain"[\s\S]*?valueSize="1rem"/);
    expect(home).toMatch(/<StatTile[\s\S]*?label="Rain"[\s\S]*?footerSize="0\.72rem"/);
    expect(home).toMatch(/<StatTile[\s\S]*?label="Rain"[\s\S]*?footerNoWrap/);
    expect(home).toMatch(/<StatTile[\s\S]*?label="Rain"[\s\S]*?stackValue/);
    expect(statTile).toContain('--stat-value-size');
    expect(statTile).toContain('--stat-footer-size');
    expect(home).not.toMatch(/\.rain-cell\s+:global/);
    expect(home).toContain('harvestedGallons(rainDayInches)');
    expect(home).toContain('harvestedGallons(rainWeekInches)');
    expect(home).toContain('value={rainValue}');
    expect(home).toContain('footer={rainFooter}');
    expect(home).toMatch(/\.sm-row\s*\{[^}]*font-size:\s*0\.(?:8[2-9]|9)\d*rem/is);
    expect(home).toContain('adaptCurrentAqi($items.Current_US_AQI)');
    expect(home).toContain("currentAqi.value ?? '—'");
    expect(home).toContain('color: {currentAqi.textColor}');
    expect(home).toContain('border-color: {currentAqi.accent}');
  });

  it('opts every Home card into the Tile-owned centered-body policy', () => {
    const centeredTileLabels = [
      'Power Flow',
      'Greywater',
      'Outdoor',
      'Indoor',
      'Battery',
      'Bitcoin',
      'Wind',
      'Baro',
      'Sun &amp; Moon',
      'Solar',
      'Zones',
      'Forecast',
    ];
    const tileTags = [...home.matchAll(/<Tile\b[^>]*>/g)].map(([tag]) => tag);
    expect(tileTags).toHaveLength(centeredTileLabels.length);
    for (const label of centeredTileLabels) {
      const tag = tileTags.find((candidate) => candidate.includes(`label="${label}"`));
      expect(tag, label).toBeTruthy();
      expect(tag, label).toMatch(/\bcenterBody\b/);
    }
    const rainTag = home.match(/<StatTile[\s\S]*?label="Rain"[\s\S]*?>/)?.[0];
    expect(rainTag).toMatch(/\bcenterContent\b/);
  });

  it('lets the compass consume its measured parent instead of a fixed cap', () => {
    expect(home).not.toMatch(/max-width:\s*4\.6rem/);
    expect(compass).toContain('ResizeObserver');
    expect(compass).toMatch(/Math\.min\(width,\s*height\)/);
    expect(compass).toMatch(/class="compass-square"/);
  });

  it('resizes and clips sparkline paint to its settled card box', () => {
    expect(sparkline).toContain('ResizeObserver');
    expect(sparkline).toMatch(/chart\?\.resize\(\{\s*width,\s*height\s*\}\)/);
    expect(sparkline).toMatch(/overflow:\s*hidden/);
    expect(home).toMatch(/\.outdoor-spark\s*\{[^}]*overflow:\s*hidden/is);
    expect(home).toMatch(/<Tile\s+label="Outdoor"[^>]*\bclip\b/);
    expect(tile).toContain('data-tile-clip');
    expect(tile).toMatch(/\.tile\[data-tile-clip\]\s*\{[^}]*overflow:\s*hidden/is);
    expect(home).not.toMatch(/\.outdoor-cell\s+:global/);
  });
});
