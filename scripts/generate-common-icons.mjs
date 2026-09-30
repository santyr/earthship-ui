import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Normal wall-display icons stay local and small. Unknown OpenHAB icon names
// still load the complete offline collection on demand in OhIcon.svelte.
const names = {
  mdi: [
    'battery', 'battery-alert', 'battery-charging', 'battery-charging-outline',
    'bitcoin', 'cloud-alert', 'fountain',
    'gauge', 'help-circle', 'help-circle-outline', 'home-thermometer', 'solar-power-variant',
    'weather-cloudy', 'weather-fog', 'weather-lightning', 'weather-night',
    'weather-night-partly-cloudy', 'weather-partly-cloudy', 'weather-pouring',
    'weather-rainy', 'weather-snowy', 'weather-snowy-heavy', 'weather-sunny',
    'weather-sunset', 'weather-sunset-down', 'weather-sunset-up', 'white-balance-sunny',
    ...['new', 'waxing-crescent', 'first-quarter', 'waxing-gibbous', 'full',
      'waning-gibbous', 'last-quarter', 'waning-crescent'].map(phase => `moon-${phase}`),
    ...Array.from({ length: 9 }, (_, step) => `battery-${(step + 1) * 10}`),
    ...Array.from({ length: 10 }, (_, step) => `battery-charging-${(step + 1) * 10}`),
  ],
  bi: ['cloud-sun-fill', 'clouds-fill'],
};

mkdirSync(fileURLToPath(new URL('../src/lib/ui/icons/', import.meta.url)), { recursive: true });

for (const [prefix, selected] of Object.entries(names)) {
  const source = JSON.parse(readFileSync(fileURLToPath(
    new URL(`../node_modules/@iconify-json/${prefix}/icons.json`, import.meta.url)), 'utf8'));
  const icons = {};
  for (const name of selected) {
    const icon = source.icons[name];
    if (!icon) throw new Error(`missing ${prefix}:${name} in installed Iconify package`);
    icons[name] = icon;
  }
  const collection = { prefix, icons,
    ...(source.width ? { width: source.width } : {}),
    ...(source.height ? { height: source.height } : {}) };
  writeFileSync(fileURLToPath(new URL(`../src/lib/ui/icons/${prefix}-common.json`, import.meta.url)),
    `${JSON.stringify(collection)}\n`);
}
