// Private operational receipts only. Loading never constructs a command queue.
import { constants, openSync, fstatSync, readFileSync, writeFileSync, closeSync, fsyncSync, renameSync, unlinkSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
const MAX_BYTES=16*1024*1024;
function valid(value) {
  return value?.schema==='earthship-shade-owner-ledger/v1'&&Array.isArray(value.commands)&&value.commands.length<=538&&Array.isArray(value.batches)&&value.batches.length<=64;
}
export function createOwnerLedger(path) {
  path=resolve(path);
  function load() {
    let fd;try{fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);}catch(error){if(error.code==='ENOENT')return null;throw new Error('Owner journal unavailable');}
    try{
      const info=fstatSync(fd);
      if(!info.isFile()||(info.mode&0o777)!==0o600||info.uid!==process.getuid()||info.nlink!==1||info.size>MAX_BYTES)throw new Error();
      const value=JSON.parse(readFileSync(fd,'utf8'));if(!valid(value))throw new Error();return value;
    }catch{throw new Error('Owner journal invalid');}finally{closeSync(fd);}
  }
  function save(value) {
    if(!valid(value))throw new Error('Owner journal capacity exceeded');
    const raw=JSON.stringify(value);if(Buffer.byteLength(raw)>MAX_BYTES)throw new Error('Owner journal capacity exceeded');
    // Never overwrite a corrupt/writable original or follow a replaced link.
    load();
    const parent=dirname(path),directory=statSync(parent);
    if(!directory.isDirectory()||directory.uid!==process.getuid()||(directory.mode&0o022)!==0)throw new Error('Private owner state directory required');
    const temporary=path+'.'+randomUUID()+'.tmp';let fd;
    try{
      fd=openSync(temporary,constants.O_CREAT|constants.O_EXCL|constants.O_WRONLY|constants.O_NOFOLLOW,0o600);
      writeFileSync(fd,raw+'\n');fsyncSync(fd);closeSync(fd);fd=undefined;
      renameSync(temporary,path);
      const parentFd=openSync(parent,constants.O_RDONLY|constants.O_DIRECTORY);try{fsyncSync(parentFd);}finally{closeSync(parentFd);}
    }finally{if(fd!==undefined)closeSync(fd);try{unlinkSync(temporary);}catch{/* already renamed or absent */}}
  }
  return {load,save};
}
