// One-shot: executes the reviewed night-load APPLY plan (same driver, fixed target).
import { spawnSync } from 'node:child_process';
const r = spawnSync('node', ['scripts/deploy-subset.mjs', 'execute', 'night-load', 'apply-plan'], { stdio: 'inherit', cwd: new URL('..', import.meta.url).pathname });
process.exit(r.status ?? 1);
