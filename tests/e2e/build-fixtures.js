import {execFileSync} from 'node:child_process';
import {mkdtemp,rm,mkdir} from 'node:fs/promises';
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
    for (const mode of ['maintenance','safe-compat']) {
      const output=join(directory,mode);
      await mkdir(output);
      // Keep the same chart/store instances available to geometry assertions.
      const entries=['src/lib/charts/echarts.js','src/lib/charts/loadEcharts.js','src/lib/ui/chartStore.js'];
      const input={app:resolve('index.html'),...Object.fromEntries(entries.map(path=>[path.slice(0,-3),resolve(path)]))};
      const script="import {build} from 'vite';await build("+JSON.stringify({configLoader:'runner',build:{outDir:output,emptyOutDir:true,rollupOptions:{input,preserveEntrySignatures:'strict',output:{entryFileNames:'[name].js'}}}})+");";
      execFileSync(process.execPath,['--input-type=module','-e',script],{cwd:process.cwd(),env:{...environment,RELEASE_MODE:mode},stdio:'pipe',timeout:120000});
    }
  } catch(error) { await rm(directory,{recursive:true,force:true}); throw error; }
  process.env.EARTHSHIP_FIXTURE_BUILD_DIR=directory;
  return async()=>{delete process.env.EARTHSHIP_FIXTURE_BUILD_DIR;await rm(directory,{recursive:true,force:true});};
}
