"""Original declared bank/topology context; no physical capacity calibration."""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from .codec import canonical,loads,identity
from .control_contracts import instant
from .evidence import utc,digest
from .energy_outcome_sources import _bank

MAX_BYTES=73728
SOURCES={'bank_source':('Solar_PV/config/system-epochs.json',65536),
         'load_topology_source':('Solar_PV/config/ac-evidence.json',4096)}
SOURCE_FIELDS={'source_identity','raw','sha256','available_at'}
FIELDS={'schema','bank_source','load_topology_source','as_of','created_at','configuration_sha256'}
BASIS='inverter_only_no_bypass_or_generator'


def _validate(value):
    if set(value)!=FIELDS or value['schema']!='earthship-household-energy-configuration/v1':
        raise ValueError('closed original configuration context required')
    if identity({k:v for k,v in value.items() if k!='configuration_sha256'})!=value['configuration_sha256']:
        raise ValueError('original configuration context differs')
    as_of=instant(value['as_of']);created=instant(value['created_at'])
    if not as_of<=created<=as_of+timedelta(seconds=15):raise ValueError('bounded original configuration collection clock required')
    for key,(name,maximum) in SOURCES.items():
        row=value[key]
        if not isinstance(row,dict) or set(row)!=SOURCE_FIELDS or row['source_identity']!=name:
            raise ValueError('fixed original configuration source required')
        if instant(row['available_at'])>as_of:raise ValueError('future configuration source refused')
        raw=row['raw']
        if raw is None:
            if row['sha256'] is not None:raise ValueError('absent configuration cannot have a digest')
        elif (not isinstance(raw,str) or not 0<=len(raw.encode())<=maximum or
              sha256(raw.encode()).hexdigest()!=digest(row['sha256'])):
            raise ValueError('bounded exact original configuration bytes required')


@dataclass(frozen=True)
class PreparedEnergyConfiguration:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or not 1<=len(self.content)<=MAX_BYTES:
            raise ValueError('bounded immutable configuration context required')
        _validate(loads(self.content))

    def to_dict(self):return loads(self.content)


def prepare_energy_configuration(*,bank_config_raw,ac_policy_raw,bank_available_at,topology_available_at,as_of,created_at):
    sources={}
    for key,raw,at in (('bank_source',bank_config_raw,bank_available_at),('load_topology_source',ac_policy_raw,topology_available_at)):
        if raw is not None and not isinstance(raw,str):raise ValueError('original configuration text required')
        sources[key]=dict(source_identity=SOURCES[key][0],raw=raw,
            sha256=None if raw is None else sha256(raw.encode()).hexdigest(),available_at=utc(at))
    value=dict(schema='earthship-household-energy-configuration/v1',**sources,as_of=utc(as_of),created_at=utc(created_at))
    value['configuration_sha256']=identity(value)
    return PreparedEnergyConfiguration(canonical(value))


def _unavailable(reason):return dict(status='unavailable',reason=reason)


def _declared_bank(raw,at):
    if raw is None:return _unavailable('missing_source')
    try:
        value=loads(raw);rows=value['epochs']
        if not isinstance(rows,list) or not 1<=len(rows)<=32 or any(not isinstance(row,dict) for row in rows):
            raise ValueError('bounded original bank rows required')
        current=[row for row in rows if row.get('current_analytics') is True]
        if len(current)!=1:raise ValueError('one current declared physical bank required')
        row=current[0];start,end=_bank(raw,row['id'])
        if not start<=at or end is not None and at>=end:return _unavailable('bank_window_mismatch')
        return dict(status='declared',reason=None,epoch_id=row['id'],effective_from=start.isoformat(),
            effective_until=None if end is None else end.isoformat(),nominal_usable_kwh=row.get('nominal_usable_kwh'),
            nominal_capacity_ah=row.get('nominal_capacity_ah'),basis='original_declared_configuration',physical_calibration_qualified=False)
    except (ValueError,TypeError,KeyError):return _unavailable('invalid_configuration')


def _topology(raw,at):
    if raw is None:return _unavailable('missing_source')
    try:
        value=loads(raw)
        if (set(value)!={'version','policy','item_name','cutover','topology'} or type(value['version']) is not int or
            value['version']!=1 or value['policy']!='qualified_inverter_ac_output_v1' or value['item_name']!='Inverter_AC_Evidence_JSON'):
            raise ValueError('original AC policy identity required')
        row=value['topology']
        if not isinstance(row,dict) or set(row)!={'basis','effective_from','effective_until'} or row['basis']!=BASIS:
            raise ValueError('explicit original inverter-only topology required')
        cutover=instant(value['cutover']);start=instant(row['effective_from'])
        end=None if row['effective_until'] is None else instant(row['effective_until'])
        if start<cutover or end is not None and end<=start:raise ValueError('ordered original topology interval required')
        if not start<=at or end is not None and at>=end:return _unavailable('topology_window_mismatch')
        return dict(status='attested',reason=None,basis=BASIS,cutover=cutover.isoformat(),effective_from=start.isoformat(),
            effective_until=None if end is None else end.isoformat(),valid_at_origin=True)
    except (ValueError,TypeError,KeyError):return _unavailable('invalid_configuration')


def project_energy_configuration(context,*,as_of=None):
    if not isinstance(context,PreparedEnergyConfiguration):raise ValueError('frozen original configuration required')
    value=context.to_dict();at=instant(value['as_of']) if as_of is None else utc(as_of)
    if at<instant(value['as_of']):raise ValueError('configuration cannot be backdated')
    result=dict(schema='earthship-household-energy-configuration-projection/v1',
        configuration_sha256=value['configuration_sha256'],as_of=at.isoformat(),
        bank=_declared_bank(value['bank_source']['raw'],at),load_topology=_topology(value['load_topology_source']['raw'],at),
        context_quality='retained_configuration_context',usable_energy_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result)
    return result
