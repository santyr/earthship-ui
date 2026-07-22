import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { relative, resolve, sep } from 'node:path';

// Mirrors the REAL current suite (stale entries for long-deleted test files
// were dropped 2026-07; e2e owners point at the specs that superseded the
// originals). Must stay identical to EXPECTED_OWNERS in
// tests/expect-failure.test.js.
export const RED_SENTINEL_OWNERS = Object.freeze({
  'RED:T2A-1': 'tests/safe-controls.test.js',
  'RED:T4A-1': 'tests/openhab/night-load-override-rule.test.js',
  'RED:T5A-1': 'tests/history-periods.test.js',
  'RED:T6A-1': 'tests/history-request.test.js',
  'RED:T7A-1': 'tests/chart-options.test.js',
  'RED:T7A-2': 'tests/e2e/weather-detail-modal.spec.js',
  'RED:T8A-1': 'tests/console-alerts.test.js',
  'RED:T9A-1': 'tests/e2e/home-runtime.spec.js',
  'RED:T10A-2': 'tests/e2e/energy-layout.spec.js',
  'RED:T11A-2': 'tests/e2e/weather-earthship-layout.spec.js',
  'RED:T12A-2': 'tests/e2e/controls-layout.spec.js',
  'RED:T13A-1': 'tests/openhab/rest-safety.test.js',
  'RED:T14A-1': 'tests/openhab/feeder-rule.test.js',
  'RED:T15A-1': 'tests/openhab/greywater-rule.test.js',
  'RED:T16A-1': 'tests/openhab/night-load-override-rule.test.js',
});

const TEST_SOURCE_RE = /\.(?:test|spec)\.(?:[cm]?[jt]sx?)$/;
const SKIP_DIRECTORIES = new Set(['.git', '.superpowers', 'dist', 'node_modules', 'test-results']);
const SENTINEL_PREFIX_RE = /^\[(RED:[^\]\r\n]*)\]/;

function posixPath(path) {
  return path.split(sep).join('/').replace(/^\.\//, '');
}

function selectedPath(rootDir, path) {
  const absolute = resolve(rootDir, path);
  return posixPath(relative(rootDir, absolute));
}

function collectTestSources(rootDir) {
  const files = [];

  function visit(directory) {
    if (!existsSync(directory)) return;
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRECTORIES.has(entry.name)) visit(resolve(directory, entry.name));
        continue;
      }
      if (entry.isFile() && TEST_SOURCE_RE.test(entry.name)) files.push(resolve(directory, entry.name));
    }
  }

  visit(resolve(rootDir, 'tests'));
  return files.sort();
}

function scanStringTokens(source) {
  const mask = [...source];
  const strings = [];
  let index = 0;

  function blank(start, end) {
    for (let cursor = start; cursor < end; cursor += 1) {
      if (mask[cursor] !== '\n' && mask[cursor] !== '\r') mask[cursor] = ' ';
    }
  }

  while (index < source.length) {
    const char = source[index];
    const next = source[index + 1];

    if (char === '/' && next === '/') {
      const start = index;
      index += 2;
      while (index < source.length && source[index] !== '\n') index += 1;
      blank(start, index);
      continue;
    }

    if (char === '/' && next === '*') {
      const start = index;
      index += 2;
      while (index < source.length && !(source[index] === '*' && source[index + 1] === '/')) {
        index += 1;
      }
      index = Math.min(source.length, index + 2);
      blank(start, index);
      continue;
    }

    if (char === "'" || char === '"' || char === '`') {
      const quote = char;
      const start = index;
      index += 1;
      let value = '';
      while (index < source.length) {
        const current = source[index];
        if (current === '\\') {
          if (index + 1 < source.length) value += source[index + 1];
          index += 2;
          continue;
        }
        if (current === quote) {
          index += 1;
          break;
        }
        value += current;
        index += 1;
      }
      strings.push({ start, value });
      blank(start, index);
      continue;
    }

    index += 1;
  }

  const code = mask.join('');
  return strings.map((token) => {
    const prefix = code.slice(Math.max(0, token.start - 160), token.start).trimEnd();
    let kind = null;
    if (/(?:^|[^\w$.])(?:it|test)(?:\.(?:only|skip|todo))?\s*\(\s*$/.test(prefix)) {
      kind = 'title';
    } else if (/(?<![\w$.])(?:new\s+)?(?:Error|TypeError|RangeError)\s*\(\s*$/.test(prefix)
      || /expect\.fail\s*\(\s*$/.test(prefix)) {
      kind = 'error';
    }
    return { ...token, kind };
  });
}

function scanMarkers(source) {
  return scanStringTokens(source).flatMap(({ kind, value }) => {
    if (!kind) return [];
    const match = SENTINEL_PREFIX_RE.exec(value);
    return match ? [{ kind, sentinel: match[1] }] : [];
  });
}

function countsFor(markersByFile, owner, sentinel) {
  const markers = markersByFile.get(owner) || [];
  return {
    title: markers.filter((marker) => marker.sentinel === sentinel && marker.kind === 'title').length,
    error: markers.filter((marker) => marker.sentinel === sentinel && marker.kind === 'error').length,
  };
}

function requireExactPair(markersByFile, owner, sentinel, context) {
  const counts = countsFor(markersByFile, owner, sentinel);
  if (counts.title !== 1) {
    throw new Error(`${context} requires exactly one title marker for ${sentinel}; found ${counts.title}`);
  }
  if (counts.error !== 1) {
    throw new Error(`${context} requires exactly one error marker for ${sentinel}; found ${counts.error}`);
  }
}

export function validateSentinelInventory({
  rootDir = process.cwd(),
  requestedSentinel,
  selectedFiles = [],
  mode = 'incomplete',
} = {}) {
  if (!['incomplete', 'complete'].includes(mode)) {
    throw new Error(`unknown sentinel inventory mode: ${mode}`);
  }
  if (!Array.isArray(selectedFiles)) throw new TypeError('selectedFiles must be an array');
  if (mode === 'incomplete' && requestedSentinel === undefined) {
    throw new Error('incomplete mode requires a requested sentinel');
  }

  const normalizedRoot = resolve(rootDir);
  let ownerFile = null;
  if (requestedSentinel !== undefined) {
    ownerFile = RED_SENTINEL_OWNERS[requestedSentinel];
    if (!ownerFile) throw new Error(`unknown sentinel: ${requestedSentinel}`);
    if (selectedFiles.length !== 1) {
      throw new Error('requested RED validation requires exactly one selected file');
    }
    const normalizedSelection = selectedPath(normalizedRoot, selectedFiles[0]);
    if (normalizedSelection !== ownerFile) {
      throw new Error(`selected file ${normalizedSelection} is not owner ${ownerFile}`);
    }
  } else if (selectedFiles.length !== 0) {
    throw new Error('selected files require a requested sentinel');
  }

  const markersByFile = new Map();
  for (const absolutePath of collectTestSources(normalizedRoot)) {
    const file = posixPath(relative(normalizedRoot, absolutePath));
    const markers = scanMarkers(readFileSync(absolutePath, 'utf8'));
    markersByFile.set(file, markers);
    for (const marker of markers) {
      const expectedOwner = RED_SENTINEL_OWNERS[marker.sentinel];
      if (!expectedOwner) throw new Error(`unregistered sentinel ${marker.sentinel} in ${file}`);
      if (expectedOwner !== file) {
        throw new Error(`${marker.sentinel} belongs to ${expectedOwner}, found in non-owner ${file}`);
      }
    }
  }

  for (const [file, markers] of markersByFile) {
    const present = new Set(markers.map((marker) => marker.sentinel));
    for (const sentinel of present) {
      const counts = countsFor(markersByFile, file, sentinel);
      if (counts.title > 1 || counts.error > 1) {
        throw new Error(`duplicate marker for ${sentinel} in ${file}`);
      }
    }
  }

  if (mode === 'complete') {
    for (const [sentinel, owner] of Object.entries(RED_SENTINEL_OWNERS)) {
      if (!markersByFile.has(owner)) {
        throw new Error(`complete inventory missing owner ${owner} for ${sentinel}`);
      }
      requireExactPair(markersByFile, owner, sentinel, 'complete inventory');
    }
  }

  if (requestedSentinel !== undefined) {
    if (!markersByFile.has(ownerFile)) {
      throw new Error(`missing requested owner ${ownerFile} for ${requestedSentinel}`);
    }
    requireExactPair(markersByFile, ownerFile, requestedSentinel, 'requested inventory');
  }

  return {
    valid: true,
    mode,
    requestedSentinel: requestedSentinel ?? null,
    ownerFile,
    scannedFiles: markersByFile.size,
  };
}
