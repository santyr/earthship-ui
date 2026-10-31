import { describe, expect, it } from 'vitest';
import { mkdtempSync, writeFileSync, readFileSync, chmodSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createOwnerLedger } from '../src/lib/shades/ownerLedger.js';

describe('private durable owner ledger',()=>{
 it('atomically retains command identities without storing any executable queue',()=>{
  const dir=mkdtempSync(join(tmpdir(),'shade-ledger-'));try{
   const ledger=createOwnerLedger(join(dir,'owner.json'));expect(ledger.load()).toBeNull();
   const value={schema:'earthship-shade-owner-ledger/v1',commands:[],batches:[]};ledger.save(value);expect(ledger.load()).toEqual(value);expect(readFileSync(join(dir,'owner.json'),'utf8')).not.toContain('ownerKey');
  }finally{rmSync(dir,{recursive:true,force:true});}
 });
 it('preserves corrupt originals and refuses symlinks or non-private files',()=>{
  const dir=mkdtempSync(join(tmpdir(),'shade-ledger-'));try{
   const path=join(dir,'owner.json');writeFileSync(path,'broken original',{mode:0o600});const ledger=createOwnerLedger(path);
   expect(()=>ledger.load()).toThrow();expect(()=>ledger.save({schema:'earthship-shade-owner-ledger/v1',commands:[],batches:[]})).toThrow();expect(readFileSync(path,'utf8')).toBe('broken original');
   chmodSync(path,0o644);expect(()=>ledger.load()).toThrow();symlinkSync(path,join(dir,'link'));expect(()=>createOwnerLedger(join(dir,'link')).load()).toThrow();
  }finally{rmSync(dir,{recursive:true,force:true});}
 });
 it('bounds receipt count and encoded size instead of silently dropping identities',()=>{
  const dir=mkdtempSync(join(tmpdir(),'shade-ledger-'));try{
   const ledger=createOwnerLedger(join(dir,'owner.json'));
   expect(()=>ledger.save({schema:'earthship-shade-owner-ledger/v1',commands:Array(539).fill({}),batches:[]})).toThrow();
   expect(()=>ledger.save({schema:'earthship-shade-owner-ledger/v1',commands:[],batches:Array(65).fill({})})).toThrow();
  }finally{rmSync(dir,{recursive:true,force:true});}
 });
});
