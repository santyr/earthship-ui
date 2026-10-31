import { describe, expect, it, vi } from 'vitest';
import { EventEmitter } from 'node:events';
import { mkdtempSync, writeFileSync, chmodSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { shadeExecutionPlugin, loadShadeOwnerProfile, publicShadeInstallation } from '../src/lib/shades/executionServer.js';

async function request(method,body,{headers={},remoteAddress='127.0.0.1',encrypted=false}={}){
 let handler;const calls=[];const authority={};const owner={authenticateManual:value=>value==='Basic fixture'?authority:null,requestManual:async(value,token)=>{expect(token).toBe(authority);calls.push(value);return {status:'published_awaiting_adapter_result'};},requestManualBatch:async()=>({status:'not_published',results:[]})};
 shadeExecutionPlugin({runtime:{enabled:false,installation:()=>({schemaVersion:1,manualOwnerAvailable:true,slots:[]}),owner}}).configureServer({middlewares:{use:(path,fn)=>{if(path==='/api/shades/manual')handler=fn;}}});
 const req=new EventEmitter();Object.assign(req,{method,url:'/',headers:{host:'console',origin:'http://console','content-type':'application/json',authorization:'Basic fixture',...headers},socket:{remoteAddress,encrypted}});
 let code,result;const res={writeHead:(status)=>{code=status;return res;},end:raw=>result=JSON.parse(raw)};
 const done=handler(req,res);if(method==='POST'){req.emit('data',typeof body==='string'?body:JSON.stringify(body));req.emit('end');}await done;return {code,result,calls};
}
const command={request_id:'00000000-0000-4000-8000-000000000001',requested_at_ms:1792854000000,slot:1,command:'UP'};
describe('private shade execution server',()=>{
 it('requires authenticated explicit manual requests and safe origin/transport',async()=>{
  expect((await request('POST',command,{headers:{authorization:''}})).code).toBe(401);
  expect((await request('POST',command,{headers:{origin:'http://foreign'}})).code).toBe(403);
  expect((await request('POST',command,{remoteAddress:'192.0.2.5'})).code).toBe(403);
  expect((await request('POST',command,{remoteAddress:'192.0.2.5',encrypted:true,headers:{origin:'https://console'}})).code).toBe(200);
  expect((await request('POST',command,{remoteAddress:'192.0.2.5',encrypted:true,headers:{origin:'http://console'}})).code).toBe(403);
 });
 it('does not permit arbitrary origins, Item names, body growth or lifecycle writes',async()=>{
  expect((await request('POST',{...command,source:'manual'})).calls).toEqual([]);
  expect((await request('POST','x'.repeat(4096))).code).toBe(413);
  expect((await request('GET')).calls).toEqual([]);
 });
 it('publishes only an authenticated explicit operator request and preserves honest outcomes',async()=>{
  const result=await request('POST',command);expect(result.code).toBe(200);expect(result.calls).toEqual([command]);expect(result.result.status).toBe('published_awaiting_adapter_result');
 });
 it('loads private configuration without following symlinks or accepting writable files',()=>{
  const root=mkdtempSync(join(tmpdir(),'dd7066-owner-'));
  try{
   const path=join(root,'profile.json');writeFileSync(path,JSON.stringify({schema:'earthship-shade-owner-installation/v1',commandsEnabled:false,slots:[]}),{mode:0o600});
   expect(loadShadeOwnerProfile(path).slots).toEqual([]);chmodSync(path,0o644);expect(()=>loadShadeOwnerProfile(path)).toThrow();chmodSync(path,0o600);symlinkSync(path,join(root,'link'));expect(()=>loadShadeOwnerProfile(join(root,'link'))).toThrow();
  }finally{rmSync(root,{recursive:true,force:true});}
 });
 it('exposes only logical Item mappings and defaults all uncommissioned slots disabled',()=>{
  const value=publicShadeInstallation({slots:[]});expect(value.slots).toHaveLength(26);expect(value.manualOwnerAvailable).toBe(false);expect(value.slots.every(slot=>slot.manualReleased===false&&slot.positionItem===null)).toBe(true);
  expect(JSON.stringify(value)).not.toContain('ownerKey');
 });
});
