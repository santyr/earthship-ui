import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const REPORT_SCHEMA = 'earthship-red-playwright-report/v1';

function errorMessage(error) {
  if (typeof error === 'string') return error;
  if (typeof error?.message === 'string') return error.message;
  return String(error ?? 'unknown Playwright error');
}

export default class RedPlaywrightReporter {
  constructor(options = {}) {
    const outputFile = options.outputFile || process.env.EARTHSHIP_RED_REPORT_PATH;
    if (!outputFile) throw new Error('RED Playwright reporter output path is required');
    this.outputFile = resolve(outputFile);
    this.declaredTests = 0;
    this.tests = [];
    this.errors = [];
  }

  onBegin(_config, suite) {
    this.declaredTests = typeof suite?.allTests === 'function' ? suite.allTests().length : 0;
  }

  onTestEnd(test, result) {
    this.tests.push({
      title: String(test?.title ?? ''),
      titlePath: typeof test?.titlePath === 'function'
        ? test.titlePath().map((part) => String(part))
        : [String(test?.title ?? '')],
      status: String(result?.status ?? 'unknown'),
      errors: Array.isArray(result?.errors) ? result.errors.map(errorMessage) : [],
    });
  }

  onError(error) {
    this.errors.push(errorMessage(error));
  }

  async onEnd(result) {
    const report = {
      schema: REPORT_SCHEMA,
      status: String(result?.status ?? 'unknown'),
      declaredTests: this.declaredTests,
      tests: this.tests,
      errors: this.errors,
    };
    mkdirSync(dirname(this.outputFile), { recursive: true });
    writeFileSync(this.outputFile, `${JSON.stringify(report)}\n`, { flag: 'wx' });
  }
}
