import { describe, expect, it } from 'vitest';
import { canonicalOwnerJson, signOwnerCommand, signOwnerPolicy } from '../src/lib/shades/ownerWire.js';
import fixture from './fixtures/dd7066-owner-wire-v1.json';

describe('owner wire contract matches the actual Python adapter golden',()=>{
 it('signs the immutable manual command with the same ASCII canonical bytes',()=>{
  expect(signOwnerCommand(fixture.command,Buffer.from(fixture.key,'ascii'))).toEqual(fixture.signed_command);
 });
 it('uses a separate authentication domain for policy and command',()=>{
  expect(signOwnerPolicy(fixture.policy,Buffer.from(fixture.key,'ascii'))).toEqual(fixture.signed_policy);
  expect(signOwnerPolicy(fixture.command,Buffer.from(fixture.key,'ascii')).signature).not.toBe(fixture.signed_command.signature);
 });
 it('escapes Unicode consistently and does not mutate the input',()=>{
  const input={b:'é🔒',a:[1,true,null]};expect(canonicalOwnerJson(input)).toBe('{"a":[1,true,null],"b":"\\u00e9\\ud83d\\udd12"}');
  expect(input.b).toBe('é🔒');
 });
 it.each([NaN,Infinity,-Infinity,1.5,9007199254740992,undefined,()=>{}])('refuses unsupported numeric or callable values',value=>{
  expect(()=>canonicalOwnerJson({value})).toThrow();
 });
 it('bounds keys, nesting, encoded size and owner key material',()=>{
  let value={};for(let i=0;i<18;i++)value={child:value};expect(()=>canonicalOwnerJson(value)).toThrow();
  expect(()=>canonicalOwnerJson({secret:'x'.repeat(20000)})).toThrow();
  expect(()=>signOwnerCommand(fixture.command,Buffer.from('short'))).toThrow();
 });
});
