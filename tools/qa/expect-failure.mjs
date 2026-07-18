import { spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import {
  RED_SENTINEL_OWNERS,
  validateSentinelInventory,
} from './red-sentinel-inventory.mjs';

const RUNNERS = new Set(['vitest', 'playwright']);
const ALTERNATE_FILTER_FLAGS = Object.freeze({
  vitest: Object.freeze(['--testNamePattern', '--test-name-pattern']),
  playwright: Object.freeze(['-g', '--grep-invert']),
});
const TEST_SOURCE_RE = /(?:^|\/)tests\/.+\.(?:test|spec)\.(?:[cm]?[jt]sx?)$/;
const VITEST_REPORTER_PATH = fileURLToPath(new URL('./red-vitest-reporter.mjs', import.meta.url));
const REPORTER_PATH = fileURLToPath(new URL('./red-playwright-reporter.mjs', import.meta.url));
const MAX_DIAGNOSTIC_CHARS = 2_000;

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function expectedFilter(sentinel) {
  return `^\\[${escapeRegex(sentinel)}\\]`;
}

function bounded(value) {
  const text = String(value ?? '').replace(/\u001b\[[0-9;]*m/g, '');
  return text.length <= MAX_DIAGNOSTIC_CHARS
    ? text
    : `${text.slice(0, MAX_DIAGNOSTIC_CHARS)}…[truncated]`;
}

function selectedTestFiles(command) {
  return command
    .filter((value) => TEST_SOURCE_RE.test(String(value).replaceAll('\\', '/').replace(/^\.\//, '')))
    .map((value) => String(value).replaceAll('\\', '/').replace(/^\.\//, ''));
}

function flagValue(command, flag) {
  const values = [];
  for (let index = 0; index < command.length; index += 1) {
    if (command[index] === flag) values.push(command[index + 1]);
    if (String(command[index]).startsWith(`${flag}=`)) {
      values.push(String(command[index]).slice(flag.length + 1));
    }
  }
  return values;
}

function hasFlag(command, flag) {
  return command.some((value) => value === flag || String(value).startsWith(`${flag}=`));
}

export function parseExpectedFailureArgs(argv) {
  if (!Array.isArray(argv)) throw new TypeError('expected-failure argv must be an array');
  const separator = argv.indexOf('--');
  if (separator < 0 || separator === argv.length - 1) {
    throw new Error('expected-failure invocation requires a -- command separator and command');
  }

  const options = argv.slice(0, separator);
  const command = argv.slice(separator + 1);
  let runner;
  let sentinel;
  for (let index = 0; index < options.length; index += 2) {
    const flag = options[index];
    const value = options[index + 1];
    if (value === undefined) throw new Error(`missing value for ${flag}`);
    if (flag === '--runner' && runner === undefined) runner = value;
    else if (flag === '--sentinel' && sentinel === undefined) sentinel = value;
    else throw new Error(`unknown or duplicate wrapper option: ${flag}`);
  }

  if (!RUNNERS.has(runner)) throw new Error(`unknown runner: ${runner ?? 'missing'}`);
  if (!RED_SENTINEL_OWNERS[sentinel]) throw new Error(`unknown sentinel: ${sentinel ?? 'missing'}`);

  const selectedFiles = selectedTestFiles(command);
  if (selectedFiles.length !== 1) {
    throw new Error(`expected exactly one producer test file; found ${selectedFiles.length}`);
  }
  if (selectedFiles[0] !== RED_SENTINEL_OWNERS[sentinel]) {
    throw new Error(`selected file ${selectedFiles[0]} is not sentinel owner ${RED_SENTINEL_OWNERS[sentinel]}`);
  }

  const filterFlag = runner === 'vitest' ? '-t' : '--grep';
  const filters = flagValue(command, filterFlag);
  if (filters.length !== 1 || filters[0] !== expectedFilter(sentinel)) {
    throw new Error(`runner requires one exact anchored ${filterFlag} filter for [${sentinel}]`);
  }
  if (ALTERNATE_FILTER_FLAGS[runner].some((flag) => hasFlag(command, flag))) {
    throw new Error(`alternate or conflicting ${runner} name filter is not allowed`);
  }
  if (command.some((value) => String(value).startsWith('--reporter')
    || String(value).startsWith('--outputFile'))) {
    throw new Error('caller-supplied reporter output is not allowed');
  }

  return { runner, sentinel, command, selectedFiles, filter: filters[0] };
}

function firstErrorLine(value) {
  const line = bounded(value).split(/\r?\n/, 1)[0].trim();
  return line.replace(/^(?:AssertionError|Error|TypeError|RangeError):\s*/, '');
}

function normalizeVitestReport(report) {
  if (!report || report.schema !== 'earthship-red-vitest-report/v1'
    || !Array.isArray(report.tests) || !Array.isArray(report.errors)) {
    throw new Error('malformed Vitest report structure');
  }
  if (report.errors.length > 0) {
    const error = report.errors[0];
    const phase = String(error?.phase ?? 'runner');
    throw new Error(`Vitest ${phase} error: ${bounded(error?.message ?? error)}`);
  }
  if (report.status !== 'failed'
    || Number(report.declaredTests) !== 1
    || report.tests.length !== 1) {
    throw new Error('expected exactly one executed and failed test');
  }
  const test = report.tests[0];
  if (test?.status !== 'failed') {
    throw new Error(`expected exactly one failed Vitest test; received ${test?.status ?? 'unknown'}`);
  }
  if (!Array.isArray(test.errors) || test.errors.length !== 1) {
    throw new Error('expected exactly one Vitest test error');
  }
  return {
    title: String(test.title ?? ''),
    error: firstErrorLine(test.errors[0]),
  };
}

function normalizePlaywrightReport(report) {
  if (!report || report.schema !== 'earthship-red-playwright-report/v1'
    || !Array.isArray(report.tests) || !Array.isArray(report.errors)) {
    throw new Error('malformed Playwright report structure');
  }
  if (report.errors.length > 0) {
    throw new Error(`Playwright runner error or collection error: ${bounded(report.errors[0])}`);
  }
  if (report.status !== 'failed' || Number(report.declaredTests) !== 1 || report.tests.length !== 1) {
    throw new Error('expected exactly one executed and failed test');
  }
  const test = report.tests[0];
  if (test?.status !== 'failed' || !Array.isArray(test.errors) || test.errors.length !== 1) {
    throw new Error('expected exactly one failed Playwright test and error');
  }
  return { title: String(test.title ?? ''), error: firstErrorLine(test.errors[0]) };
}

export function validateExpectedFailureReport({
  runner,
  report,
  sentinel,
  exitCode,
  signal,
}) {
  if (signal) throw new Error(`runner crashed or received signal ${signal}`);
  if (exitCode !== 1) throw new Error(`runner exit must be 1; received ${exitCode}`);
  const normalized = runner === 'vitest'
    ? normalizeVitestReport(report)
    : runner === 'playwright'
      ? normalizePlaywrightReport(report)
      : (() => { throw new Error(`unknown runner: ${runner}`); })();
  const prefix = `[${sentinel}]`;
  if (!normalized.title.startsWith(prefix)) {
    throw new Error(`test title does not begin with sentinel ${prefix}`);
  }
  if (!normalized.error.startsWith(prefix)) {
    throw new Error(`test error does not begin with sentinel ${prefix}`);
  }
  return { valid: true, ...normalized, runner, sentinel };
}

function runnerCommand(parsed, reportPath) {
  if (parsed.runner === 'vitest') {
    return [...parsed.command, `--reporter=${VITEST_REPORTER_PATH}`];
  }
  return [...parsed.command, `--reporter=${REPORTER_PATH}`];
}

export function executeExpectedFailure({
  argv,
  cwd = process.cwd(),
  spawn = spawnSync,
  timeoutMs = 120_000,
} = {}) {
  const parsed = parseExpectedFailureArgs(argv);
  validateSentinelInventory({
    rootDir: cwd,
    requestedSentinel: parsed.sentinel,
    selectedFiles: parsed.selectedFiles,
  });

  const reportRoot = mkdtempSync(join(tmpdir(), 'earthship-red-report-'));
  const reportPath = join(reportRoot, `${parsed.runner}.json`);
  let child;
  try {
    const command = runnerCommand(parsed, reportPath);
    child = spawn(command[0], command.slice(1), {
      cwd,
      encoding: 'utf8',
      env: { ...process.env, EARTHSHIP_RED_REPORT_PATH: reportPath },
      maxBuffer: 256 * 1024,
      timeout: timeoutMs,
    });
    if (child?.error) throw new Error(`runner process error: ${bounded(child.error.message)}`);
    if (!existsSync(reportPath)) throw new Error('missing report output');
    const artifacts = readdirSync(reportRoot);
    if (artifacts.length !== 1 || artifacts[0] !== basename(reportPath)) {
      throw new Error(`duplicate or unexpected report artifact: ${artifacts.join(', ')}`);
    }

    let report;
    try {
      report = JSON.parse(readFileSync(reportPath, 'utf8'));
    } catch (error) {
      throw new Error(`malformed report output: ${bounded(error.message)}`);
    }
    return validateExpectedFailureReport({
      runner: parsed.runner,
      report,
      sentinel: parsed.sentinel,
      exitCode: child?.status,
      signal: child?.signal,
    });
  } catch (error) {
    const stdout = bounded(child?.stdout);
    const stderr = bounded(child?.stderr);
    const diagnostics = [stdout && `stdout: ${stdout}`, stderr && `stderr: ${stderr}`]
      .filter(Boolean)
      .join('\n');
    throw new Error(diagnostics ? `${error.message}\n${diagnostics}` : error.message);
  } finally {
    rmSync(reportRoot, { recursive: true, force: true });
  }
}

export function main(argv = process.argv.slice(2)) {
  try {
    const result = executeExpectedFailure({ argv });
    process.stdout.write(`verified expected RED ${result.sentinel}: ${bounded(result.title)}\n`);
  } catch (error) {
    process.stderr.write(`expected RED validation failed: ${bounded(error.message)}\n`);
    process.exitCode = 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
