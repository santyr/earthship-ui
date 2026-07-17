// Tiny hash router — no dependency. Four screens: home, energy, weather, earthship.
import { writable } from 'svelte/store';

export const ROUTES = ['home', 'energy', 'weather', 'earthship'];
const DEFAULT_ROUTE = 'home';

// Pure: hash string -> route name. Unknown/empty hash falls back to default.
// Accepts '#/energy', '#energy', or 'energy'.
export function parseHash(hash) {
  const name = String(hash ?? '')
    .trim()
    .replace(/^#\/?/, '');
  return ROUTES.includes(name) ? name : DEFAULT_ROUTE;
}

const initialHash = typeof location !== 'undefined' ? location.hash : '';
export const currentRoute = writable(parseHash(initialHash));

// Sets location.hash; the hashchange listener below updates the store.
// Falls back to setting the store directly when no browser location exists
// (e.g. under test).
export function navigate(name) {
  const route = ROUTES.includes(name) ? name : DEFAULT_ROUTE;
  if (typeof location !== 'undefined') {
    location.hash = `/${route}`;
  } else {
    currentRoute.set(route);
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => {
    currentRoute.set(parseHash(location.hash));
  });
}
