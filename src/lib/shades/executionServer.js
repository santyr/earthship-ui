// Prepared server-only installation/owner path. Missing private profile means
// all 26 slots stay unmapped and no publisher process or device transport starts.
import { constants, openSync, fstatSync, readFileSync, closeSync, realpathSync, statSync, readdirSync } from 'node:fs';
import { resolve, dirname, relative, isAbsolute } from 'node:path';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { SHADE_SLOTS } from './catalog.js';
import { createShadeExecutionOwner } from './executionOwner.js';
import { createOwnerLedger } from './ownerLedger.js';
import { createShadePolicyOwner } from './policyServer.js';
const mappings=['positionItem','availabilityItem','stateItem','serviceAvailabilityItem','bridgeAvailabilityItem','serviceStateItem','bridgeStateItem','serviceThingUID'];
const item=value=>typeof value==='string'&&/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(value);
const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
function privateBytes(path,maximum=65536) {
  const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);
  try{const info=fstatSync(fd);if(!info.isFile()||(info.mode&0o777)!==0o600||info.nlink!==1||info.size>maximum||info.uid!==process.getuid())throw new Error('Private owner configuration required');return readFileSync(fd);}
  finally{closeSync(fd);}
}
function uniqueJson(raw,maximum=65536) {
  if(typeof raw!=='string'||raw.length>maximum)throw new Error('Invalid owner JSON');
  const value=JSON.parse(raw),tokens=raw.match(/"(?:\\.|[^"\\])*"|[{}\[\]:]/g)??[],stack=[];
  if(tokens.length>8192)throw new Error('Invalid owner JSON');
  for(let i=0;i<tokens.length;i++){
    const token=tokens[i];
    if(token==='{'||token==='['){stack.push(token==='{'?new Set():null);if(stack.length>16)throw new Error('Invalid owner JSON');}
    else if(token==='}'||token===']')stack.pop();
    else if(token[0]==='"'&&tokens[i+1]===':'){
      const key=JSON.parse(token),keys=stack.at(-1);if(!keys||keys.has(key))throw new Error('Duplicate owner JSON key');keys.add(key);
    }
  }
  return value;
}
export function loadShadeOwnerProfile(path) {
  const base=realpathSync(dirname(resolve(path))),info=statSync(base);
  if((info.mode&0o777)!==0o700||info.uid!==process.getuid())throw new Error('Private owner directory required');
  const profile=uniqueJson(privateBytes(path).toString('utf8'));
  for(const value of [profile?.ownerKeyFile,profile?.ownerJournalFile,profile?.publisher?.config]){
    if(value===undefined)continue;
    if(typeof value!=='string'||!value||dirname(resolve(base,value))!==base)throw new Error('Owner files must share the private directory');
  }
  if(profile?.schema!=='earthship-shade-owner-installation/v1'||!Array.isArray(profile.slots)||profile.slots.length>26
    ||typeof profile.commandsEnabled!=='boolean')throw new Error('Invalid shade installation');
  const numbers=new Set(),ids=new Set(),positionItems=new Set(),devices=new Set();
  if(profile.slots.length&&(!/^[0-9A-F]{12,32}$/.test(profile.bridgeId??'')))throw new Error('Pinned bridge identity required');
  for(const record of profile.slots){
    const base=SHADE_SLOTS.find(slot=>slot.number===record.slot);
    if(!base||numbers.has(record.slot)||ids.has(record.id)||record.zone!==base.room
      ||typeof record.id!=='string'||!/^[a-z][a-z0-9_-]{0,47}$/.test(record.id))throw new Error('Invalid shade mapping');
    numbers.add(record.slot);ids.add(record.id);
    if(record.deviceId!=null){if(!/^[0-9A-F]{12,32}$/.test(record.deviceId)||devices.has(record.deviceId))throw new Error('Duplicate or invalid shade identity');devices.add(record.deviceId);}
    for(const key of [...mappings,'resultItem']){const value=record[key];if(value!=null&&(key==='serviceThingUID'?!/^mqtt:[A-Za-z0-9:_-]{1,180}$/.test(value):!item(value)))throw new Error('Invalid shade Item mapping');}
    if(record.positionItem){if(positionItems.has(record.positionItem))throw new Error('Duplicate shade Item mapping');positionItems.add(record.positionItem);}
  }
  return profile;
}
export function publicShadeInstallation(profile={slots:[]},{manualOwnerAvailable=false}={}) {
  return {schemaVersion:1,automaticReleased:false,manualOwnerAvailable,
    contextId:createHash('sha256').update(JSON.stringify(profile.slots)).digest('hex'),
    slots:SHADE_SLOTS.map(base=>{
      const source=profile.slots.find(record=>record.slot===base.number),mapped=Object.fromEntries(mappings.map(key=>[key,source?.[key]??null]));
      const sourceIdentity=source&&uuid(source.commissionedEpoch)&&/^[0-9A-F]{12,32}$/.test(source.deviceId??'')&&/^[0-9A-F]{12,32}$/.test(profile.bridgeId??'')
        ?createHash('sha256').update(JSON.stringify({bridge_id:profile.bridgeId,commissioned_epoch:source.commissionedEpoch,device_id:source.deviceId}),'ascii').digest('hex'):null;
      const commissioned=Boolean(sourceIdentity&&mappings.every(key=>mapped[key]));
      return {...base,...mapped,resultItem:source?.resultItem??null,adapterShadeId:source?.id??null,sourceIdentity,commissionedEpoch:source?.commissionedEpoch??null,commissioned,manualReleased:Boolean(manualOwnerAvailable&&commissioned&&source.manualReleased===true),
        operations:commissioned&&Array.isArray(source.operations)?source.operations.filter(op=>['UP','DOWN','STOP'].includes(op)):[],percentage:Boolean(commissioned&&source.percentage===true)};
    })};
}
function publishProcess(profile,base,kind,message,{spawnImpl=spawn}={}) {
  return new Promise((accept,reject)=>{
    const publisher=profile.publisher;
    if(publisher?.enabled!==true||typeof publisher.python!=='string'||typeof publisher.config!=='string')return reject(new Error('Owner publisher unavailable'));
    const child=spawnImpl(resolve(base,publisher.python),['-m','dooya_openhab.owner_publish','--config',resolve(base,publisher.config),'--publish'],{stdio:['pipe','pipe','ignore']});
    let output='',finished=false,killTimer;
    const terminate=()=>{child.kill('SIGTERM');killTimer=setTimeout(()=>child.kill('SIGKILL'),1000);killTimer.unref?.();};
    const finish=(error,result)=>{if(finished)return;finished=true;clearTimeout(timer);error?reject(error):accept(result);};
    const timer=setTimeout(()=>{terminate();finish(new Error('Owner publication uncertain'));},5000);
    child.on('error',()=>finish(new Error('Owner publisher unavailable')));
    child.stdout.on('data',chunk=>{output+=chunk;if(output.length>4096){terminate();finish(new Error('Owner publication uncertain'));}});
    child.on('close',code=>{clearTimeout(killTimer);try{const value=uniqueJson(output,4096);if(code!==0||value.published!==true||value.broker_acknowledged!==true||value.movement_confirmed!==false)throw new Error();finish(null,{published:true});}catch{finish(new Error('Owner publication uncertain'));}});
    child.stdin.on('error',()=>finish(new Error('Owner publication uncertain')));
    child.stdin.end(JSON.stringify({kind,message}));
  });
}
export function createShadeExecutionRuntime({profilePath,upstream,authorization,fetchImpl=fetch,spawnImpl=spawn}={}) {
  if(!profilePath)return {enabled:false,owner:null,installation:()=>publicShadeInstallation()};
  const profile=loadShadeOwnerProfile(profilePath),base=dirname(resolve(profilePath));
  if(!upstream||!authorization)return {enabled:false,owner:null,installation:()=>publicShadeInstallation(profile)};
  async function read(path) {
    const response=await fetchImpl(upstream.replace(/\/$/,'')+path,{headers:{Authorization:authorization},cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw new Error('Shade source unavailable');return response.json();
  }
  async function readAdapter() {
    const record=profile.slots.find(row=>mappings.every(key=>row[key]));if(!record)throw new Error('Shade source unavailable');
    const first=await read('/rest/items/'+record.serviceStateItem);
    const [bridge,provider,serviceAvailability,last]=await Promise.all([read('/rest/items/'+record.bridgeStateItem),read('/rest/things/'+encodeURIComponent(record.serviceThingUID)),read('/rest/items/'+record.serviceAvailabilityItem),read('/rest/items/'+record.serviceStateItem)]);
    if(first.state!==last.state||provider.statusInfo?.status!=='ONLINE'||serviceAvailability.state!=='ON')throw new Error('Current adapter session unavailable');
    const service=uniqueJson(first.state,8192),state=uniqueJson(bridge.state,8192);
    if(state.bridge_id!==profile.bridgeId)throw new Error('Pinned bridge source mismatch');
    if(service.schema_version!==2||state.schema_version!==2||service.adapter_session_id!==state.adapter_session_id
      ||service.source_generation!==state.source_generation||!Number.isFinite(state.emitted_at)
      ||Date.now()-state.emitted_at*1000>90000||state.emitted_at*1000-Date.now()>5000)throw new Error('Current bridge session unavailable');
    return {...service,ready:service.ready===true&&state.reachable===true,bridge_id:state.bridge_id};
  }
  let owner=null;
  if(profile.publisher?.enabled===true&&typeof profile.ownerKeyFile==='string') {
    const key=privateBytes(resolve(base,profile.ownerKeyFile),4096);
    if(key.length<32)throw new Error('Owner authentication unavailable');
    const policyOwner=createShadePolicyOwner({upstream,authorization,fetchImpl});
    if(profile.commandsEnabled===true&&typeof profile.ownerJournalFile!=='string')throw new Error('Durable owner journal required');
    const journal=typeof profile.ownerJournalFile==='string'?createOwnerLedger(resolve(base,profile.ownerJournalFile)):null;
    owner=createShadeExecutionOwner({loadLedger:journal?.load,saveLedger:journal?.save,inventory:profile.slots.map(record=>({...record,manualReleased:profile.commandsEnabled===true&&record.manualReleased===true})),key,
      manualAuthorizationHash:profile.manualAuthorizationHash,readAdapter,readPolicy:()=>policyOwner.read(),
      publishCommand:message=>publishProcess(profile,base,'command',message,{spawnImpl}),
      publishPolicy:message=>publishProcess(profile,base,'policy',message,{spawnImpl}),
      readPolicyAck:async()=>{if(!item(profile.policyAckItem))throw new Error('Policy synchronization unavailable');const value=await read('/rest/items/'+profile.policyAckItem);return uniqueJson(value.state,8192);}});
  }
  return {enabled:Boolean(owner),owner,installation:()=>publicShadeInstallation(profile,{manualOwnerAvailable:Boolean(owner&&profile.commandsEnabled===true)})};
}
export function shadeExecutionPlugin(options={}) {
  let runtime=options.runtime,serving=null;
  if(!runtime)try{runtime=createShadeExecutionRuntime(options);}catch{runtime={enabled:false,owner:null,installation:()=>publicShadeInstallation()};}
  return {name:'shade-authenticated-execution-owner',configResolved(config){
    // File permissions do not stop this same-UID HTTP process reading secrets.
    // Refuse startup independently of runtime readiness, even for invalid profiles.
    if(!options.profilePath)return;
    if(config.server.fs.strict===false)throw new Error('Private owner requires strict served-file boundaries');
    loadShadeOwnerProfile(options.profilePath);
    const privateRoot=realpathSync(dirname(resolve(options.profilePath)));
    if(readdirSync(privateRoot).length>256)throw new Error('Private owner directory exceeds bounds');
    serving={privateRoot,root:config.root,publicDir:config.publicDir,base:config.base};
    const roots=[config.root,config.publicDir,...config.server.fs.allow].filter(value=>typeof value==='string'&&value);
    for(const root of roots){
      let canonical;try{canonical=realpathSync(root);}catch{canonical=resolve(root);}
      const part=relative(canonical,privateRoot);
      if(!part||(!part.startsWith('../')&&part!=='..'&&!isAbsolute(part)))throw new Error('Owner directory must be outside every served root');
    }
  },configureServer(server){
    if(serving)server.middlewares.use((req,res,next)=>{
      // Vite public delivery skips fs.allow checks. Resolve aliases before its
      // public/static/transform handlers so nested symlinks cannot expose secrets.
      let path;try{path=decodeURIComponent(new URL(req.url,'http://private-boundary.invalid').pathname);}catch{res.statusCode=400;res.end();return;}
      if(serving.base&&serving.base!=='/'&&path.startsWith(serving.base))path='/'+path.slice(serving.base.length);
      const candidates=[resolve(serving.root,'.'+path),...(serving.publicDir?[resolve(serving.publicDir,'.'+path)]:[])];
      if(path.startsWith('/@fs/'))candidates.push(resolve('/'+path.slice(5)));
      for(const candidate of candidates){
        let target;try{target=realpathSync(candidate);}catch{continue;}
        let protectedInode=false;
        try{
          const candidateInfo=statSync(target),names=readdirSync(serving.privateRoot);
          if(names.length>256)throw new Error();
          protectedInode=names.some(name=>{const info=statSync(resolve(serving.privateRoot,name),{throwIfNoEntry:false});return info?.isFile()&&info.dev===candidateInfo.dev&&info.ino===candidateInfo.ino;});
        }catch{res.statusCode=503;res.end();return;}
        const part=relative(serving.privateRoot,target);
        if(protectedInode||!part||(!part.startsWith('../')&&part!=='..'&&!isAbsolute(part))){res.statusCode=403;res.end();return;}
      }
      next();
    });
    server.middlewares.use('/api/shades-installation',(req,res)=>{res.writeHead(req.method==='GET'?200:405,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(req.method==='GET'?runtime.installation():{error:'method_not_allowed'}));});
    server.middlewares.use('/api/shades/manual',async(req,res)=>{
      const send=(status,body)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store',...(status===401?{'WWW-Authenticate':'Basic realm="Shade manual owner"'}:{})});res.end(JSON.stringify(body));};
      if(req.method!=='POST'){send(405,{error:'method_not_allowed'});return;}
      const remote=req.socket?.remoteAddress,loopback=['127.0.0.1','::1','::ffff:127.0.0.1'].includes(remote);
      let same=false;try{const origin=new URL(req.headers.origin);same=origin.host===req.headers.host&&origin.protocol===(req.socket?.encrypted===true?'https:':'http:');}catch{/* no browser origin */}
      if(!same||(!loopback&&req.socket?.encrypted!==true)||req.headers['content-type']?.split(';')[0]!=='application/json'){send(403,{error:'manual_request_forbidden'});return;}
      const authority=runtime.owner?.authenticateManual(req.headers.authorization);
      if(!authority){send(401,{error:'manual_authentication_required'});return;}
      try{
        const body=await new Promise((accept,reject)=>{let raw='',done=false;req.on('data',chunk=>{if(done)return;raw+=chunk;if(raw.length>2048){done=true;reject(Object.assign(new Error(),{status:413}));}});req.on('aborted',()=>reject(new Error()));req.on('error',reject);req.on('end',()=>{if(done)return;try{accept(uniqueJson(raw,2048));}catch{reject(new Error());}});});
        const expected=Array.isArray(body?.slots)?'command,request_id,requested_at_ms,slots':'command,request_id,requested_at_ms,slot';
        if(!body||Object.keys(body).sort().join(',')!==expected){send(400,{error:'invalid_manual_request'});return;}
        const result=await(Array.isArray(body.slots)?runtime.owner.requestManualBatch(body,authority):runtime.owner.requestManual(body,authority));send(200,result);
      }catch(error){send(error.status??400,{error:error.code??'manual_request_unavailable'});}
    });
    if(runtime.enabled&&server.httpServer){let stopped=false,timer;const synchronize=async()=>{try{await runtime.owner.synchronizePolicy();}catch{/* unavailable never authorizes automatic movement */}if(!stopped)timer=setTimeout(synchronize,5000);};synchronize();server.httpServer.once('close',()=>{stopped=true;clearTimeout(timer);});}
  }};
}
