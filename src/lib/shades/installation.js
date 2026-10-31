import { SHADE_GROUPS, SHADE_SLOTS } from './catalog.js';

export const SHADE_MAPPING_FIELDS = Object.freeze(['positionItem','availabilityItem','stateItem','serviceAvailabilityItem','bridgeAvailabilityItem','serviceStateItem','bridgeStateItem','serviceThingUID']);
const SOURCE_FIELDS = ['sourceIdentity','commissionedEpoch','adapterShadeId'];
const OPTIONAL_MAPPING_FIELDS = ['resultItem'];
const applicationId = value => value===null || (typeof value==='string' && /^[a-z][a-z0-9_-]{0,47}$/.test(value));
const sourceHash = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const epochId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const operations = new Set(['UP','DOWN','STOP']);
const itemName = value => value === null || (typeof value === 'string' && /^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(value));
const thingName = value => value === null || (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,256}$/.test(value));
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export function emptyShadeInstallation() {
  return {schemaVersion:1,automaticReleased:false,manualOwnerAvailable:false,contextId:null,
    slots:SHADE_SLOTS.map(slot=>({...slot,resultItem:null,adapterShadeId:null,sourceIdentity:null,commissionedEpoch:null,commissioned:false,manualReleased:false,operations:[],percentage:false}))};
}

// Deliberately inspect partial/malformed mappings too: once a real mapping has
// appeared, a failed response must not silently return the screen to simulation.
export function hasInstallationMapping(value) {
  return Array.isArray(value?.slots) && value.slots.some(slot=>object(slot)
    && [...SHADE_MAPPING_FIELDS,...OPTIONAL_MAPPING_FIELDS,...SOURCE_FIELDS].some(key=>slot[key] !== null && slot[key] !== undefined));
}

export function validateShadeInstallation(value) {
  if (!object(value) || value.schemaVersion !== 1 || value.automaticReleased !== false
      || typeof value.manualOwnerAvailable !== 'boolean' || !Array.isArray(value.slots)
      || value.slots.length !== SHADE_SLOTS.length
      || (value.contextId !== undefined && value.contextId !== null
          && (typeof value.contextId !== 'string' || !value.contextId || value.contextId.length > 256))) return null;
  const deviceItems = new Set();
  const applicationIds = new Set();
  const slots = [];
  for (const [index, base] of SHADE_SLOTS.entries()) {
    const slot = value.slots[index];
    if (!object(slot) || slot.number !== base.number || slot.room !== base.room || slot.label !== base.label
        || !SHADE_MAPPING_FIELDS.every(key=>(key==='serviceThingUID' ? thingName : itemName)(slot[key]))
        || !itemName(slot.resultItem??null) || !applicationId(slot.adapterShadeId??null)
        || !(slot.sourceIdentity===null || sourceHash(slot.sourceIdentity))
        || !(slot.commissionedEpoch===null || epochId(slot.commissionedEpoch))
        || (slot.commissioned===true && (!sourceHash(slot.sourceIdentity) || !epochId(slot.commissionedEpoch)))
        || typeof slot.commissioned !== 'boolean' || typeof slot.manualReleased !== 'boolean'
        || typeof slot.percentage !== 'boolean' || !Array.isArray(slot.operations)
        || slot.operations.length > 3 || new Set(slot.operations).size !== slot.operations.length
        || !slot.operations.every(op=>operations.has(op))) return null;
    for (const key of ['positionItem','availabilityItem','stateItem','resultItem']) {
      const name = slot[key];
      if (name !== null && name !== undefined) { if (deviceItems.has(name)) return null; deviceItems.add(name); }
    }
    if(slot.adapterShadeId!=null){if(applicationIds.has(slot.adapterShadeId))return null;applicationIds.add(slot.adapterShadeId);}
    slots.push({...base,resultItem:slot.resultItem??null,adapterShadeId:slot.adapterShadeId??null,...Object.fromEntries(SHADE_MAPPING_FIELDS.map(key=>[key,slot[key]])),
      sourceIdentity:slot.sourceIdentity,commissionedEpoch:slot.commissionedEpoch,
      commissioned:slot.commissioned,manualReleased:slot.manualReleased,operations:[...slot.operations],percentage:slot.percentage});
  }
  return {schemaVersion:1,automaticReleased:false,manualOwnerAvailable:value.manualOwnerAvailable,
    contextId:value.contextId ?? null,slots};
}

export function manualShadeTargets(installation) {
  if (installation?.manualOwnerAvailable !== true) return [];
  const eligible = (installation.slots ?? []).filter(slot=>slot.commissioned === true && slot.manualReleased === true
    && sourceHash(slot.sourceIdentity) && epochId(slot.commissionedEpoch)
    && SHADE_MAPPING_FIELDS.every(key=>typeof slot[key] === 'string' && slot[key].length));
  if (!eligible.length) return [];
  return [{id:'all',label:`All eligible shades (${eligible.length})`,slots:eligible,individual:false},
    ...SHADE_GROUPS.flatMap(group=>{
      const members=eligible.filter(slot=>slot.room===group.id);
      return members.length ? [{id:group.id,label:`${group.label} (${members.length} eligible)`,slots:members,individual:false}] : [];
    }),...eligible.map(slot=>({id:`shade-${slot.number}`,label:slot.label,slots:[slot],individual:true}))];
}

export function manualShadeRequest(target, command, {requestId,requestedAtMs}) {
  if (!target?.slots?.length || new Set(target.slots.map(slot=>slot.number)).size !== target.slots.length) throw new Error('No eligible shades');
  let native = command;
  if (object(command)) {
    if (!Number.isInteger(command.openPercent) || command.openPercent < 0 || command.openPercent > 100
        || !target.slots.every(slot=>slot.percentage === true)) throw new Error('Percentage unavailable');
    native = 100-command.openPercent;
  } else if (!operations.has(command) || !target.slots.every(slot=>slot.operations.includes(command))) throw new Error('Operation unavailable');
  if (typeof requestId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)
      || !Number.isSafeInteger(requestedAtMs) || requestedAtMs < 0) throw new Error('Invalid request identity');
  const members=target.slots.map(slot=>slot.number);
  return {request_id:requestId,requested_at_ms:requestedAtMs,
    ...(target.individual ? {slot:members[0]} : {slots:members}),command:native};
}

export function manualResultPresentation(data, request) {
  const labels={published_awaiting_adapter_result:'Published · awaiting adapter result',publication_uncertain_no_retry:'Publication uncertain · no retry',rejected:'Rejected',expired:'Expired'};
  const selected=request.slots ?? [request.slot];
  const validIdentity=data?.request_id===request.request_id;
  const summary=validIdentity && data.status==='published_awaiting_adapter_result'
    ? 'Request published · awaiting adapter result. Position remains based on reports.'
    : validIdentity && data.status==='partially_published' ? 'Some requests published; review each shade. Position remains based on reports.'
    : validIdentity && data.status==='not_published' ? 'No requests published.'
    : 'Publication uncertain · outcome unknown. No retry was sent.';
  const rows=Array.isArray(request.slots) ? selected.map(slot=>{
    const matches=validIdentity && Array.isArray(data.results) ? data.results.filter(row=>row?.slot===slot) : [];
    return {slot,label:matches.length===1 && labels[matches[0].status] ? labels[matches[0].status] : 'Result unavailable · outcome unknown'};
  }) : [];
  return {summary,rows};
}
