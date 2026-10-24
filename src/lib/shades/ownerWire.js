// Server-only adapter authentication contract. Never import this from browser UI.
import { createHmac } from 'node:crypto';

export function canonicalOwnerJson(value) {
  let nodes=0;
  const ancestors=new Set();
  function encode(node,depth) {
    if (++nodes>2048 || depth>16) throw new TypeError('Invalid owner contract');
    if (node===null || typeof node==='boolean') return JSON.stringify(node);
    if (typeof node==='number') {
      if (!Number.isSafeInteger(node)) throw new TypeError('Invalid owner contract');
      return JSON.stringify(node);
    }
    if (typeof node==='string') return JSON.stringify(node).replace(/[\u007f-\uffff]/g,character=>`\\u${character.charCodeAt(0).toString(16).padStart(4,'0')}`);
    if (!node || typeof node!=='object' || ancestors.has(node)) throw new TypeError('Invalid owner contract');
    ancestors.add(node);
    let result;
    if (Array.isArray(node)) result=`[${node.map(item=>encode(item,depth+1)).join(',')}]`;
    else {
      if (![Object.prototype,null].includes(Object.getPrototypeOf(node))) throw new TypeError('Invalid owner contract');
      result=`{${Object.keys(node).sort().map(key=>`${encode(key,depth+1)}:${encode(node[key],depth+1)}`).join(',')}}`;
    }
    ancestors.delete(node);
    return result;
  }
  const result=encode(value,0);
  if (result.length>16384) throw new TypeError('Invalid owner contract');
  return result;
}
function sign(envelope,key,domain) {
  if (!Buffer.isBuffer(key) || key.length<32 || key.length>4096) throw new TypeError('Owner authentication unavailable');
  const canonical=canonicalOwnerJson(envelope);
  return {envelope:JSON.parse(canonical),signature:createHmac('sha256',key).update(domain+'\0','ascii').update(canonical,'ascii').digest('hex')};
}
export const signOwnerCommand=(envelope,key)=>sign(envelope,key,'dooya-owner-command/v1');
export const signOwnerPolicy=(envelope,key)=>sign(envelope,key,'dooya-owner-policy/v1');
