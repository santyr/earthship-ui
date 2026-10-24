import { it, expect } from 'vitest';
import { createServer } from 'vite';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { shadeExecutionPlugin } from '../src/lib/shades/executionServer.js';

const disabled={enabled:false,owner:null,installation:()=>({})};
const profile=dir=>{writeFileSync(join(dir,'profile.json'),JSON.stringify({schema:'earthship-shade-owner-installation/v1',commandsEnabled:false,ownerKeyFile:'secret.bin',slots:[]}),{mode:0o600});writeFileSync(join(dir,'secret.bin'),'synthetic-key-only',{mode:0o600});return join(dir,'profile.json');};
function options(root,path,extra={}){return {configFile:false,root,logLevel:'silent',plugins:[shadeExecutionPlugin({runtime:disabled,profilePath:path})],server:{host:'127.0.0.1',port:0,fs:{strict:true,allow:[root]},...extra}};}
it('refuses owner directories in normal/public/additional served roots before listening, even when runtime is disabled',async()=>{
 const base=mkdtempSync(join(tmpdir(),'shade-private-serving-'));try{
  const root=join(base,'www');mkdirSync(root,{mode:0o700});mkdirSync(join(root,'public'),{mode:0o700});
  for(const dir of [root,join(root,'public')])await expect(createServer(options(root,profile(dir)))).rejects.toThrow(/outside every served root/);
  const privateDir=join(base,'private');mkdirSync(privateDir,{mode:0o700});const path=profile(privateDir);
  await expect(createServer(options(root,path,{fs:{strict:false,allow:[root]}}))).rejects.toThrow(/strict served-file boundaries/);
  await expect(createServer(options(root,path,{fs:{strict:true,allow:[base]}}))).rejects.toThrow(/outside every served root/);
 }finally{rmSync(base,{recursive:true,force:true});}
});
it('actual HTTP cannot read a permitted private profile or key through normal or @fs paths',async()=>{
 const base=mkdtempSync(join(tmpdir(),'shade-private-http-'));let server;try{
  const root=join(base,'www'),privateDir=join(base,'private');mkdirSync(root);mkdirSync(privateDir,{mode:0o700});
  const path=profile(privateDir);mkdirSync(join(root,'public'));
  symlinkSync(path,join(root,'public','linked-profile.json'));
  symlinkSync(privateDir,join(root,'public','linked-dir'));
  symlinkSync(privateDir,join(root,'linked-root-dir'));
  server=await createServer(options(root,path));await server.listen();const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  for(const route of ['/linked-profile.json','/linked-dir/profile.json','/linked-dir/secret.bin','/linked-root-dir/secret.bin','/linked-dir/secret.bin?raw'])expect((await fetch(origin+route)).status).toBe(403);
  for(const file of ['profile.json','secret.bin']){
   const direct=await fetch(origin+'/'+file);expect(direct.status).toBe(404);
   const absolute=await fetch(origin+'/@fs/'+join(privateDir,file));expect(absolute.status).toBe(403);expect(await absolute.text()).not.toContain('synthetic-key-only');
  }
 }finally{await server?.close();rmSync(base,{recursive:true,force:true});}
});
