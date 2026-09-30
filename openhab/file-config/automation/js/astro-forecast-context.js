'use strict';

const SOURCE = 'astro:sun:local';
const OUTPUT = 'Astro_Forecast_Context_JSON';
const SCHEMA = 'astro-future-solar-context/v1';

function quantity(raw, unit, low, high) {
  const text = String(raw);
  if (!text.endsWith(' ' + unit)) throw new Error('Astro quantity unit mismatch');
  const number = text.slice(0, -unit.length - 1);
  if (!/^-?\d+(?:\.\d+)?$/.test(number)) throw new Error('Astro numeric quantity required');
  const value = Number(number);
  if (!Number.isFinite(value) || value < low || value > high) {
    throw new Error('Astro quantity range mismatch');
  }
  return value;
}

function buildContext(adapter) {
  const days = [];
  const sunrise = new Map();
  const rise = index => {
    if (!sunrise.has(index)) sunrise.set(index, adapter.event(index, 'SUN_RISE', 'START'));
    return sunrise.get(index);
  };
  for (let i = 0; i < 10; i++) {
    const day = adapter.day(i);
    const daylightStartAt = adapter.event(i, 'DAYLIGHT', 'START');
    const sunsetAt = adapter.event(i, 'SUN_SET', 'START');
    const nextSunriseAt = rise(i + 1);
    const daylightSeconds = (Date.parse(sunsetAt) - Date.parse(daylightStartAt)) / 1000;
    const sunsetToNextSunriseSeconds = (Date.parse(nextSunriseAt) - Date.parse(sunsetAt)) / 1000;
    if (!(daylightSeconds > 0 && daylightSeconds < 86400
          && sunsetToNextSunriseSeconds > 0 && sunsetToNextSunriseSeconds < 86400)) {
      throw new Error('Astro daily event ordering mismatch');
    }
    days.push({day, sunriseAt: rise(i), daylightStartAt, sunsetAt, nextSunriseAt,
      daylightSeconds, sunsetToNextSunriseSeconds,
      noonElevationDegrees: quantity(adapter.elevation(i), '°', -90, 90),
      noonAzimuthDegrees: quantity(adapter.azimuth(i), '°', 0, 360),
      noonReferenceRadiationWm2: quantity(adapter.radiation(i), 'W/m²', 0, 1500)});
  }
  const result = {version: 1, schema: SCHEMA, sourceThing: SOURCE,
    calculationVersion: 'openhab-astro-5.2.1', timezone: adapter.timezone,
    geolocation: adapter.geolocation, recordedAt: adapter.recordedAt,
    validUntil: adapter.validUntil, days};
  const body = JSON.stringify(result);
  if (body.length > 16384) throw new Error('Astro context exceeds bound');
  return body;
}

function publish() {
  try {
    const {actions, things, items, osgi} = require('openhab');
    const thing = things.getThing(SOURCE);
    if (String(thing.status) !== 'ONLINE') return;
    const sun = actions.get('astro', SOURCE);
    if (!sun) return;
    const FrameworkUtil = Java.type('org.osgi.framework.FrameworkUtil');
    const bundles = FrameworkUtil.getBundle(Java.type('org.openhab.core.OpenHAB')).getBundleContext().getBundles();
    const binding = Array.from(bundles).find(bundle => String(bundle.getSymbolicName()) === 'org.openhab.binding.astro');
    if (!binding || String(binding.getVersion()) !== '5.2.1') return;
    const zone = osgi.getService('org.openhab.core.i18n.TimeZoneProvider').getTimeZone();
    const ZonedDateTime = Java.type('java.time.ZonedDateTime');
    const now = ZonedDateTime.now(zone);
    const first = now.toLocalDate();
    const configuration = thing.rawThing.getConfiguration();
    const atNoon = index => first.plusDays(index).atTime(12, 0).atZone(zone);
    const body = buildContext({
      timezone: String(zone.getId()), geolocation: String(configuration.get('geolocation')),
      recordedAt: String(now.toInstant()),
      validUntil: String(first.plusDays(1).atStartOfDay(zone).toInstant()),
      day: index => String(first.plusDays(index)),
      event: (index, phase, moment) => String(sun.getEventTime(phase, atNoon(index), moment).toInstant()),
      elevation: index => sun.getElevation(atNoon(index)),
      azimuth: index => sun.getAzimuth(atNoon(index)),
      radiation: index => sun.getTotalRadiation(atNoon(index)),
    });
    items.getItem(OUTPUT).postUpdate(body);
  } catch (_) {
    console.warn('Astro forecast context unavailable; no calculated receipt published');
  }
}

if (typeof Java !== 'undefined') {
  const {rules, triggers} = require('openhab');
  rules.JSRule({id: 'hex_astro_forecast_context', name: 'Astro Future Solar Context',
    description: 'Daily calculated geometry only; no weather observation or hardware commands',
    triggers: [triggers.GenericCronTrigger('0 10 0 * * ?'), triggers.SystemStartlevelTrigger(100)],
    execute: publish});
  // File hot-load initializes a new observational Item without forcing an
  // unrelated rule. Cold-start source unavailability simply withholds context.
  publish();
}
if (typeof module !== 'undefined') module.exports = {buildContext, quantity};
