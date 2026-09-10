# BMS Atomic Resources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the superseded resource manifest with an exact create-only, initially disabled deployment description for the approved observational source.

**Architecture:** A declarative manifest identifies two file transformations, two new Modbus data Things under the existing poller, two String input Items and one String output Item. Exact generic event triggers retain original provenance for the observer. This task does not implement or invoke an installer; runtime activation remains gated.

**Tech Stack:** JSON manifest, Node filesystem and Vitest; OpenHAB5.2.1 REST DTO fields.

## Global Constraints

- Approved atomic-source spec43ccb08/Hexmem8691 governs. Never deploy the superseded draft.
- Preserve existing poller, data Things, scaler, controls, thresholds, DMs, learned state and everyChange plus restoreOnStartup. Task82 remains held.
- No writeStart, writeType, writeValueType or write transformation configuration; no new periodic poller. Only String channels are linked.
- Manifest is create-only and new Things/rule are initially disabled. These are declarative requirements, not proof of installer enforcement.
- Generic event trigger source must be empty: observer must receive foreign events for invalidation rather than silently filter them out.
- No installation, resource API writes, merge, push, or reader migration in the worker task.

## File and interface boundaries

Modify only `openhab/bms-soc-evidence-resources.json` and the descriptor test
section of `tests/openhab/bms-soc-evidence.test.js`. Do not change the reviewed
observer or its tests. This task follows the completed observer review.

Later deployment code must remove manifest-only `enabled` and `source` fields
before assembling actual REST DTOs, check all resource names are absent before
creation, enforce disabled posture before adding links, and verify readback.
It must not blindly PUT the manifest over live resources. Normal creation must
not temporarily activate a linked source; create Things without links first,
disable and verify them, then add links and qualify source enablement separately.

Runtime preflight verified live `core.GenericEventTrigger` config keys are
`topic`, `source`, `types`, `payload`. `modbus:data` accepts `modbus:poller` bridges;
readStart is text, readTransform is multiple, and writeStart/writeType/
writeValueType have no defaults. JS appears in installed transformation services.
This is metadata verification, not installed execution of new transforms.

### Task 1: Create-only disabled observational manifest

**Files:**
- Modify: `openhab/bms-soc-evidence-resources.json`
- Modify/test: `tests/openhab/bms-soc-evidence.test.js` (descriptor section only)

**Interfaces:**
- Consumes reviewed observer Item names/channel suffixes and source-transform file names.
- Produces manifest version1 with createOnly, transformations, things, links, items, persistence and rule; additions are not live state.

- [ ] **Step 1: Replace the obsolete descriptor assertion with explicit safety assertions.** Keep observer tests unchanged. Use this descriptor block:

```js
describe('create-only disabled atomic source resources', () => {
  const descriptor = JSON.parse(readFileSync(descriptorUrl,'utf8'));
  const cases = [
    ['raw','socRawObservation','BMS_SOC_Raw_Observation_JSON','40255','uint16'],
    ['scale','socScaleObservation','BMS_SOC_Scale_Observation_JSON','40300','int16'],
  ];
  it('declares only three new String Items with existing persistence policy',()=>{
    expect(descriptor.version).toBe(1);
    expect(descriptor.createOnly).toBe(true);
    expect(descriptor.items.map(i=>i.name).sort()).toEqual([
      'BMS_SOC_Evidence_JSON','BMS_SOC_Raw_Observation_JSON','BMS_SOC_Scale_Observation_JSON']);
    expect(descriptor.items.every(i=>i.type==='String')).toBe(true);
    expect(descriptor.persistence).toEqual({serviceId:'jdbc',strategy:'everyChange',
      restoreOnStartup:true,items:descriptor.items.map(i=>i.name)});
  });
  it.each(cases)('maps %s to a disabled read-only child and exact original event',
    (field,suffix,item,register,valueType)=>{
      const uid=`modbus:data:schneiderBatterySunSpec:battery802Core:${suffix}`;
      const thing=descriptor.things.find(t=>t.UID===uid);
      expect(thing).toMatchObject({enabled:false,thingTypeUID:'modbus:data',
        bridgeUID:'modbus:poller:schneiderBatterySunSpec:battery802Core'});
      expect(thing.configuration).toEqual({readStart:register,readValueType:valueType,
        readTransform:[`JS(bms_soc_${field}_observation.js)`],updateUnchangedValuesEveryMillis:30000});
      expect(descriptor.links.find(l=>l.itemName===item)).toEqual({itemName:item,
        channelUID:`${uid}:string`,configuration:{profile:'system:default'}});
      expect(descriptor.rule.triggers.find(t=>t.id===field)).toEqual({id:field,
        type:'core.GenericEventTrigger',configuration:{topic:`openhab/items/${item}/state`,
          types:'ItemStateEvent',source:'',payload:''}});
      expect(descriptor.transformations.find(t=>t.uid===`bms_soc_${field}_observation.js`))
        .toEqual({uid:`bms_soc_${field}_observation.js`,type:'js',
          source:`openhab/transform/bms_soc_${field}_observation.js`});
    });
  it('has no extra resources, timestamp companions or control triggers',()=>{
    expect(descriptor.things).toHaveLength(2);
    expect(descriptor.links).toHaveLength(2);
    expect(descriptor.transformations).toHaveLength(2);
    expect(descriptor.rule).toMatchObject({uid:'hex_bms_soc_evidence',enabled:false,
      source:'openhab/rules/bms-soc-evidence.js'});
    expect(descriptor.rule.triggers.slice(2)).toEqual([
      {id:'comms',type:'core.ItemStateChangeTrigger',configuration:{itemName:'BMS_Comms_Status'}},
      {id:'device',type:'core.ItemStateChangeTrigger',configuration:{itemName:'BMS_DevicePresent'}},
      {id:'expiry',type:'timer.GenericCronTrigger',configuration:{cronExpression:'0 * * * * ?'}},
      {id:'startup',type:'core.SystemStartlevelTrigger',configuration:{startlevel:100}},
    ]);
  });
});
```

- [ ] **Step 2: Record RED.** Run `npm test -- tests/openhab/bms-soc-evidence.test.js`; new manifest assertions must fail against the original staged descriptor, while corrected observer tests remain green. Record counts.

- [ ] **Step 3: Replace the manifest with this exact JSON.** It declares resources only; no installer runs here.

```json
{
  "version": 1,
  "createOnly": true,
  "transformations": [
    {"uid":"bms_soc_raw_observation.js","type":"js","source":"openhab/transform/bms_soc_raw_observation.js"},
    {"uid":"bms_soc_scale_observation.js","type":"js","source":"openhab/transform/bms_soc_scale_observation.js"}
  ],
  "things": [
    {"UID":"modbus:data:schneiderBatterySunSpec:battery802Core:socRawObservation","thingTypeUID":"modbus:data",
      "bridgeUID":"modbus:poller:schneiderBatterySunSpec:battery802Core","label":"BMS raw SoC observation source","enabled":false,
      "configuration":{"readStart":"40255","readValueType":"uint16","readTransform":["JS(bms_soc_raw_observation.js)"],"updateUnchangedValuesEveryMillis":30000}},
    {"UID":"modbus:data:schneiderBatterySunSpec:battery802Core:socScaleObservation","thingTypeUID":"modbus:data",
      "bridgeUID":"modbus:poller:schneiderBatterySunSpec:battery802Core","label":"BMS scale observation source","enabled":false,
      "configuration":{"readStart":"40300","readValueType":"int16","readTransform":["JS(bms_soc_scale_observation.js)"],"updateUnchangedValuesEveryMillis":30000}}
  ],
  "links": [
    {"itemName":"BMS_SOC_Raw_Observation_JSON","channelUID":"modbus:data:schneiderBatterySunSpec:battery802Core:socRawObservation:string","configuration":{"profile":"system:default"}},
    {"itemName":"BMS_SOC_Scale_Observation_JSON","channelUID":"modbus:data:schneiderBatterySunSpec:battery802Core:socScaleObservation:string","configuration":{"profile":"system:default"}}
  ],
  "items": [
    {"name":"BMS_SOC_Evidence_JSON","type":"String","label":"Validated BMS SoC evidence","category":"","tags":[],"groupNames":[]},
    {"name":"BMS_SOC_Raw_Observation_JSON","type":"String","label":"BMS raw SoC source observation","category":"","tags":[],"groupNames":[]},
    {"name":"BMS_SOC_Scale_Observation_JSON","type":"String","label":"BMS scale source observation","category":"","tags":[],"groupNames":[]}
  ],
  "persistence":{"serviceId":"jdbc","strategy":"everyChange","restoreOnStartup":true,
    "items":["BMS_SOC_Evidence_JSON","BMS_SOC_Raw_Observation_JSON","BMS_SOC_Scale_Observation_JSON"]},
  "rule": {
    "uid":"hex_bms_soc_evidence","name":"Validated BMS SoC evidence","enabled":false,"source":"openhab/rules/bms-soc-evidence.js",
    "triggers": [
      {"id":"raw","type":"core.GenericEventTrigger","configuration":{"topic":"openhab/items/BMS_SOC_Raw_Observation_JSON/state","types":"ItemStateEvent","source":"","payload":""}},
      {"id":"scale","type":"core.GenericEventTrigger","configuration":{"topic":"openhab/items/BMS_SOC_Scale_Observation_JSON/state","types":"ItemStateEvent","source":"","payload":""}},
      {"id":"comms","type":"core.ItemStateChangeTrigger","configuration":{"itemName":"BMS_Comms_Status"}},
      {"id":"device","type":"core.ItemStateChangeTrigger","configuration":{"itemName":"BMS_DevicePresent"}},
      {"id":"expiry","type":"timer.GenericCronTrigger","configuration":{"cronExpression":"0 * * * * ?"}},
      {"id":"startup","type":"core.SystemStartlevelTrigger","configuration":{"startlevel":100}}
    ]
  }
}
```

- [ ] **Step 4: Verify GREEN and no observer changes.** Run `npm test -- tests/openhab/bms-soc-evidence.test.js tests/openhab/bms-observation-transforms.test.js`, `npm test`, `git diff --check`, and inspect `git diff -- openhab/rules/bms-soc-evidence.js` (must be empty). Check the exact manifest has no write configuration or existing resource UID targets.

- [ ] **Step 5: Commit exactly the descriptor and tests.**

```bash
git add openhab/bms-soc-evidence-resources.json tests/openhab/bms-soc-evidence.test.js
git commit --only -m "feat: define disabled atomic BMS observation resources" -- openhab/bms-soc-evidence-resources.json tests/openhab/bms-soc-evidence.test.js
git status --short
```

Save an ignored report at `.superpowers/sdd/bms-atomic-resources-task-1-report.md`.
Root performs task and whole-branch review. No merge, push or deployment here.

## Self-review

All source names align with the observer plan and reviewed transformations.
The manifest preserves the existing persistence contract and poller, includes
only three new Items, two read-only children and two String links, and explicitly
keeps the observer disabled. Installed-engine qualification and enforcement by
an actual create-only installer remain separate release gates.
