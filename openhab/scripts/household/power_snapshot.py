"""Expanded frozen household facts; software power epochs are not bank epochs."""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from .codec import canonical,loads,identity
from .evidence import epoch,digest,ROLES,utc
from .snapshot import HouseholdSnapshot
from .replay import compile_inputs,_instant,MAX_BYTES
from earthship_energy.power_evidence import parse_power_evidence
from earthship_energy.ac_evidence import parse_ac_evidence

SOURCES={'power':('Power_Evidence_JSON',parse_power_evidence),
         'inverter_ac':('Inverter_AC_Evidence_JSON',parse_ac_evidence)}
POWER_ROLES={'battery_power_w':('power','battery.dc_power_w'),'pv_input_power_w':('power','pv.input_power_w'),
             'pv_output_power_w':('power','pv.output_power_w'),'inverter_output_w':('inverter_ac','inverter.ac_output_w')}
UNKNOWN={
 'energy':{'usable_battery_kwh':'kWh','physical_bank_epoch':'identity','predicted_pv_kwh':'kWh',
           'estimated_load_w':'W','overnight_trough_pct':'percent','curtailment_state':'state','generator_state':'state'},
 'thermal':{'solar_radiation_wm2':'W_m2','relative_humidity':'percent','shade_state':'state','ventilation_state':'state'},
 'weather':{'forecast_issue':'identity','outdoor_trajectory':'degF_trajectory','radiation_trajectory':'W_m2_trajectory',
            'precipitation':'inch','wind_speed':'mph','daylight':'state','season_mode':'state'},
 'authority':{'openhab_source_freshness':'state','owner_rule_availability':'owner_map','release_mode':'state',
              'hardware_epochs':'epoch_map','disabled_capabilities':'capability_list','planner_mode':'state'},
}
ALL_ROLES=set(ROLES)|set(POWER_ROLES)|{name for rows in UNKNOWN.values() for name in rows}
SOURCE_FIELDS={'kind','source_identity','expected_epoch','expected_sha256','persisted_at','raw'}
BUNDLE_FIELDS={'schema','base_inputs','power_sources','power_policy'}
RECEIPT_FIELDS={'schema','inputs','runtime_manifest','snapshot','registry','automatic_actuation','receipt_sha256'}


@dataclass(frozen=True)
class PowerSnapshot(HouseholdSnapshot):
    def __post_init__(self):
        super().__post_init__();value=loads(self.content)
        if value.get('schema')!='earthship-household-snapshot/v2' or value.get('planner_authority')!='none':
            raise ValueError('expanded observational snapshot required')
        digest(value['base_snapshot_id']);digest(value['source_inputs_sha256'])


def _policy(value,base):
    if not isinstance(value,dict) or set(value)!={'requirements','max_age_seconds','max_skew_seconds'}:
        raise ValueError('closed expanded temporal policy required')
    requirements=value['requirements'];ages=value['max_age_seconds'];skew=value['max_skew_seconds']
    if not isinstance(requirements,dict) or not 1<=len(requirements)<=16 or set(requirements)&set(base['requirements']):
        raise ValueError('distinct bounded expanded capabilities required')
    import re
    for name,roles in requirements.items():
        if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}',name) or not isinstance(roles,list) or not roles or any(not isinstance(role,str) or role not in ALL_ROLES for role in roles) or len(roles)!=len(set(roles)):
            raise ValueError('explicit expanded capability sources required')
    if not isinstance(ages,dict) or any(role not in POWER_ROLES or type(age) is not int or not 1<=age<=120 for role,age in ages.items()):
        raise ValueError('bounded per-power-source age required')
    if type(skew) is not int or not 0<=skew<=300:raise ValueError('bounded explicit expanded skew required')
    return dict(requirements={**base['requirements'],**requirements},max_age_seconds={**base['max_age_seconds'],**ages},
                max_skew_seconds=min(base['max_skew_seconds'],skew))


def _sources(entries):
    if not isinstance(entries,list) or len(entries)>len(SOURCES):raise ValueError('bounded fixed power sources required')
    result={}
    for row in entries:
        if not isinstance(row,dict) or set(row)!=SOURCE_FIELDS:raise ValueError('closed original power context required')
        kind=row['kind']
        if not isinstance(kind,str) or kind not in SOURCES or kind in result or row['source_identity']!=SOURCES[kind][0]:
            raise ValueError('unique fixed original power identity required')
        epoch(row['expected_epoch']);_instant(row['persisted_at']);raw=row['raw']
        if raw is None:
            if row['expected_sha256'] is not None:raise ValueError('missing power source cannot have digest')
        elif not isinstance(raw,str) or len(raw.encode())>4096 or sha256(raw.encode()).hexdigest()!=digest(row['expected_sha256']):
            raise ValueError('bounded exact original power bytes required')
        result[kind]=row
    return result


def _power_row(role,source,as_of,age):
    result=dict(value=None,unit='W',reason='missing_source',evidence=None)
    if source is None:return result
    kind,field=POWER_ROLES[role];available=_instant(source['persisted_at']);raw=source['raw']
    record=None if raw is None else SOURCES[kind][1](raw,available)
    reason='missing_source' if raw is None else 'source_unqualified' if record is None else None
    reading=None if record is None else record.fields[field]
    if record is not None:
        if record.stream_epoch!=source['expected_epoch']:reason='wrong_epoch'
        elif available>as_of:reason='future_source'
        elif reading is None:reason='field_unavailable'
        elif as_of>=reading.valid_until:reason='expired_source'
        elif as_of-reading.observed_at>timedelta(seconds=age):reason='source_too_old'
    result['reason']=reason
    result['value']=reading.watts if reason is None else None
    result['evidence']=dict(source_role=role,source_identity=source['source_identity']+':'+field,digest=source['expected_sha256'],
        source_epoch=None if record is None else record.stream_epoch,hardware_epoch=None,
        observed_at=None if reading is None else reading.observed_at,received_at=None if record is None else record.recorded_at,
        available_at=available,valid_until=None if reading is None else reading.valid_until,assessed_at=as_of,
        quality='qualified' if reason is None else 'unavailable',reason=reason,parent_digests=[])
    return result


def compile_power_inputs(bundle,*,managed,ownership,code_revision,runtime_manifest):
    if not isinstance(bundle,dict) or set(bundle)!=BUNDLE_FIELDS or bundle['schema']!='earthship-household-power-inputs/v1' or len(canonical(bundle))>MAX_BYTES:
        raise ValueError('closed bounded expanded original inputs required')
    base=compile_inputs(bundle['base_inputs'],managed=managed,ownership=ownership,code_revision=code_revision,runtime_manifest=runtime_manifest)
    snap=loads(canonical(base['snapshot']));base_id=snap.pop('snapshot_id');as_of=_instant(snap['as_of'])
    policy=_policy(bundle['power_policy'],snap['temporal_policy']);sources=_sources(bundle['power_sources'])
    for domain,fields in UNKNOWN.items():
        target=snap['domains'].setdefault(domain,{})
        for role,unit in fields.items():target[role]=dict(value=None,unit=unit,reason='missing_source',evidence=None)
    for role,(kind,_) in POWER_ROLES.items():
        if kind in sources and role not in policy['max_age_seconds']:raise ValueError('original power role lacks explicit age policy')
        snap['domains']['energy'][role]=_power_row(role,sources.get(kind),as_of,policy['max_age_seconds'].get(role,120))
    rows={role:row for domain in snap['domains'].values() for role,row in domain.items()}
    complete={};reasons={}
    for name,roles in policy['requirements'].items():
        valid=all(rows[role]['value'] is not None and rows[role]['reason'] is None for role in roles)
        reason=None if valid else 'required_source_unavailable'
        if valid:
            clocks=[]
            for role in roles:
                clock=rows[role]['evidence']['observed_at'] or rows[role]['evidence']['received_at']
                clocks.append(_instant(clock) if isinstance(clock,str) else utc(clock))
            if (max(clocks)-min(clocks)).total_seconds()>policy['max_skew_seconds']:valid=False;reason='source_skew'
        complete[name]=valid;reasons[name]=reason
    snap.update(schema='earthship-household-snapshot/v2',base_snapshot_id=base_id,source_inputs_sha256=identity(bundle),
        temporal_policy=policy,config_revision=identity(policy),completeness=complete,capability_reasons=reasons)
    snapshot=PowerSnapshot(canonical(snap))
    result=dict(schema='earthship-household-power-snapshot-receipt/v1',inputs=dict(bundle=bundle,managed=managed,ownership=ownership,code_revision=code_revision),
        runtime_manifest=runtime_manifest,snapshot=snapshot.to_dict(),registry=base['registry'],automatic_actuation=False)
    result['receipt_sha256']=identity(result)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded expanded original receipt required')
    return loads(canonical(result))


def replay_power_snapshot(receipt,*,runtime_manifest):
    if not isinstance(receipt,dict) or set(receipt)!=RECEIPT_FIELDS or receipt['schema']!='earthship-household-power-snapshot-receipt/v1' or len(canonical(receipt))>MAX_BYTES:
        raise ValueError('closed bounded original expanded receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256'] or canonical(runtime_manifest)!=canonical(receipt['runtime_manifest']):
        raise ValueError('original receipt or executing runtime differs')
    value=receipt['inputs']
    if not isinstance(value,dict) or set(value)!={'bundle','managed','ownership','code_revision'}:raise ValueError('closed original expanded context required')
    replayed=compile_power_inputs(value['bundle'],managed=value['managed'],ownership=value['ownership'],code_revision=value['code_revision'],runtime_manifest=runtime_manifest)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived expanded snapshot differs')
    return replayed
