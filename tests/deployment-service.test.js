import fs from 'node:fs';
import { describe, expect, it } from 'vitest';

const SERVICE_PATH = 'deploy/earthship-ui.service';

describe('household UI user service', () => {
  it('runs the explicit safe-compat Vite server on the one production port', () => {
    expect(fs.existsSync(SERVICE_PATH)).toBe(true);
    if (!fs.existsSync(SERVICE_PATH)) return;

    const source = fs.readFileSync(SERVICE_PATH, 'utf8');
    expect(source).toMatch(/^WorkingDirectory=\/home\/sat\/earthship-ui$/m);
    expect(source).toMatch(/^Environment=RELEASE_MODE=safe-compat$/m);
    expect(source).toMatch(
      /^ExecStart=\/home\/sat\/\.npm-global\/bin\/npm run dev -- --host 0\.0\.0\.0 --port 5190 --strictPort$/m,
    );
    expect(source).toMatch(/^Restart=(?:on-failure|always)$/m);
    expect(source).toMatch(/^WantedBy=default\.target$/m);
    expect(source).not.toMatch(/nginx/i);
    expect(source).not.toMatch(/vite\s+preview/i);
  });
});
