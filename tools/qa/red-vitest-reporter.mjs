import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const REPORT_SCHEMA = 'earthship-red-vitest-report/v1';

function errorMessage(error) {
  if (typeof error === 'string') return error;
  if (typeof error?.message === 'string') return error.message;
  return String(error ?? 'unknown Vitest error');
}

function isTimeoutError(error) {
  return /timeout|timed out/i.test(`${error?.name ?? ''} ${errorMessage(error)}`);
}

function entityErrors(entity) {
  if (typeof entity?.result === 'function') {
    const errors = entity.result()?.errors;
    return Array.isArray(errors) ? errors.map(errorMessage) : [];
  }
  if (typeof entity?.errors === 'function') {
    const errors = entity.errors();
    return Array.isArray(errors) ? errors.map(errorMessage) : [];
  }
  return [];
}

export default class RedVitestReporter {
  constructor(options = {}) {
    const outputFile = options.outputFile || process.env.EARTHSHIP_RED_REPORT_PATH;
    if (!outputFile) throw new Error('RED Vitest reporter output path is required');
    this.outputFile = resolve(outputFile);
    this.declaredTests = 0;
    this.tests = [];
    this.errors = [];
    this.hookSnapshots = new WeakMap();
  }

  onTestModuleCollected() {
    // Executed tests are counted from results so name-filtered skips do not count.
  }

  onHookStart(hook) {
    if (hook?.entity && typeof hook.entity === 'object') {
      this.hookSnapshots.set(hook.entity, entityErrors(hook.entity));
    }
  }

  onHookEnd(hook) {
    if (!hook?.entity || typeof hook.entity !== 'object') return;
    const before = this.hookSnapshots.get(hook.entity) ?? [];
    const after = entityErrors(hook.entity);
    for (const message of after.slice(before.length)) {
      this.errors.push({ phase: 'hook', message });
    }
    this.hookSnapshots.delete(hook.entity);
  }

  onTestCaseResult(testCase) {
    const result = typeof testCase?.result === 'function' ? testCase.result() : {};
    if (['pending', 'skipped'].includes(result?.state)) return;
    this.declaredTests += 1;
    const errors = Array.isArray(result?.errors) ? result.errors : [];
    for (const error of errors.filter(isTimeoutError)) {
      this.errors.push({ phase: 'timeout', message: errorMessage(error) });
    }
    this.tests.push({
      title: String(testCase?.name ?? testCase?.fullName ?? ''),
      status: String(result?.state ?? 'unknown'),
      errors: errors.map(errorMessage),
    });
  }

  async onTestRunEnd(testModules, unhandledErrors, reason) {
    for (const testModule of testModules ?? []) {
      for (const message of entityErrors(testModule)) {
        this.errors.push({ phase: 'suite', message });
      }
    }
    for (const error of unhandledErrors ?? []) {
      this.errors.push({ phase: 'runner', message: errorMessage(error) });
    }
    const report = {
      schema: REPORT_SCHEMA,
      status: String(reason ?? 'unknown'),
      declaredTests: this.declaredTests,
      tests: this.tests,
      errors: this.errors,
    };
    mkdirSync(dirname(this.outputFile), { recursive: true });
    writeFileSync(this.outputFile, `${JSON.stringify(report)}\n`, { flag: 'wx' });
  }
}
