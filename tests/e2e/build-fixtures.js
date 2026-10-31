import {execFileSync} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';

// Compiler and browser run sequentially inside the SAME original job budget.
// Build the complete application; fixtures retain all route/assertion coverage.
export default async function buildFixtures(config) {
  if (process.argv.includes('--project=sensors') || config.projects.every(p=>p.name==='sensors')) return;
  const directory=await mkdtemp(join(tmpdir(),'earthship-fixture-build-'));
  const environment={...process.env,OPENHAB_PROXY_TARGET:'http://127.0.0.1:9',RAYON_NUM_THREADS:'1',ROLLDOWN_WORKER_THREADS:'1',TOKIO_WORKER_THREADS:'1',UV_THREADPOOL_SIZE:'1'};
  delete environment.OPENHAB_TOKEN;
  try {
    execFileSync(process.execPath,[resolve('node_modules/vite/bin/vite.js'),'build','--outDir',directory,'--emptyOutDir'],{cwd:process.cwd(),env:environment,stdio:'pipe',timeout:120000});
  } catch(error) { await rm(directory,{recursive:true,force:true}); throw error; }
  process.env.EARTHSHIP_FIXTURE_BUILD_DIR=directory;
  return async()=>{delete process.env.EARTHSHIP_FIXTURE_BUILD_DIR;await rm(directory,{recursive:true,force:true});};
}
