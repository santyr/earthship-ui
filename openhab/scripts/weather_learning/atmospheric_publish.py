"""Closed v2 supplemental projection with independent atmospheric provenance."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import re
from .atmospheric_context import VARIABLES,build_atmospheric_series,_field,_compatible,wind_from,vapor_pressure_hpa
from .contracts import canonical,identity,instant,finite,digest
from .evidence import utc
from .features import prospective_snapshot
from .moisture_context import build_moisture_context
from household_job_budget import AdmissionDeferred

SCHEMA='earthship-weathernext-capabilities/v2'
GROUP_SCHEMA='earthship-atmospheric-display/v1'
METHOD='raw-native-atmosphere/v1'
RH_SCOPE='diagnostic_from_mean_T_and_mean_Td_not_ensemble_mean_RH'
WIND_SCOPE='scalar_mean_speed_and_mean_vector_are_distinct; neither_is_gust'
CLOUD_SCOPE='independent_layer_cover; layers_overlap_and_are_not_summed'
SOURCE_FIELDS={'ref_sha256','snapshot_sha256','source_digest','grid_sha256','native_grid','run_id','initialized_at','first_seen_at','available_at'}
GROUP_FIELDS={'schema','method','valid_until','sources','hours','moisture','rh_scope','pressure_basis','wind_scope','cloud_scope','temperature_model_uses_fields','selection_truncated','withheld_sources'}
ROW_FIELDS={'valid_at','fields','relative_humidity_pct','relative_humidity_reason','wind_from_degrees','vector_magnitude_m_s','direction_reason'}
MOISTURE_FIELDS={'schema','assessed_at','outdoor_target_at','mode','outdoor_vapor_pressure_hpa','indoor_vapor_pressure_hpa','indoor_temperature_c',
    'indoor_relative_humidity_pct','comparison','valid_until','indoor_evidence_sha256s','indoor_context_sha256','missing_dependencies','scope','condensation_assessed','automatic_actuation','release_authorized','context_sha256'}
MOISTURE_SCOPE='forecast_outdoor_vapor_pressure_vs_current_indoor_at_comparable_local_total_pressure'
MISSING={'qualified_indoor_temperature_and_relative_humidity','compatible_same_zone_indoor_temperature_and_humidity','forecast_dewpoint','outdoor_target_within_two_hours','indoor_temperature_outside_diagnostic_domain'}


def _targets(decision):
    first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    return tuple(first+timedelta(hours=i) for i in range(24))


def _select(archive,decision,targets,site,guard):
    if getattr(archive,'missing',False):return [],False,0
    with archive._connect() as db:
        refs=db.execute('SELECT digest FROM snapshots WHERE historical=0 AND completed<=? AND initialized>? ORDER BY initialized DESC,completed DESC,digest LIMIT 33',
            (decision.isoformat(),(decision-timedelta(hours=24)).isoformat())).fetchall()
    needed={(value[0],at) for value in VARIABLES.values() for at in targets};names={value[0]:name for name,value in VARIABLES.items()};covered=set();chosen=[];withheld=0
    for (pin,) in refs[:32]:
        guard()
        try:
            raw=archive.read(pin)
            keys={(p['variable'],instant(p['valid_at'])) for p in raw['points'] if p['statistic']=='mean' and p['value'] is not None}&needed
            if not keys-covered:continue
            body=prospective_snapshot(raw,issued_at=decision)
            if body['site']!=site.__dict__:raise ValueError('atmospheric original site differs')
            keys={(p['variable'],instant(p['valid_at'])) for p in body['points'] if p['statistic']=='mean' and p['variable'] in names and _field(body,p,names[p['variable']]) is not None}&needed
            if not keys-covered:continue
            chosen.append(body);covered|=keys
            if covered==needed or len(chosen)==8:break
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (ValueError,TypeError,KeyError,OSError):withheld+=1
    return chosen,len(refs)>32 or len(chosen)==8 and covered!=needed,withheld


def _expand(field,sources,at,name):
    if field is None:return None
    source=sources[field['source_ref']]
    return dict(value=field['value'],unit=VARIABLES[name][2],valid_at=at,source_sha256=source['snapshot_sha256'],
        native_asset_sha256=field['native_asset_sha256'],**{k:source[k] for k in ('run_id','initialized_at','grid_sha256','available_at')})


def _derive(fields,sources,at):
    t=_expand(fields['temperature'],sources,at,'temperature');d=_expand(fields['dewpoint'],sources,at,'dewpoint')
    rh=None;reason='compatible_station_pair_unavailable'
    if _compatible(t,d):
        if d['value']>t['value']:reason='dewpoint_above_temperature'
        else:rh=100*vapor_pressure_hpa(d['value'])/vapor_pressure_hpa(t['value']);reason=None
    u=_expand(fields['u'],sources,at,'u');v=_expand(fields['v'],sources,at,'v')
    vector=wind_from(u['value'],v['value']) if _compatible(u,v) else wind_from(None,None)
    return dict(relative_humidity_pct=rh,relative_humidity_reason=reason,wind_from_degrees=vector['from_degrees'],vector_magnitude_m_s=vector['magnitude_m_s'],direction_reason=vector['reason'])


def build_atmospheric_report(archive,*,decision,site,horizons=(24,336),indoor=None,zone=None,guard=lambda:None):
    from .capability_publish import build_capability_report,validate_capability_report
    decision=utc(decision);base=build_capability_report(archive,decision=decision,site=site,horizons=horizons,guard=guard)
    targets=_targets(decision);bodies,truncated,withheld=_select(archive,decision,targets,site,guard)
    contexts=build_atmospheric_series(bodies,decision=decision,targets=targets,site=site,guard=guard);sources={};hours=[]
    for context in contexts:
        guard();fields={};originals=dict(temperature=context['temperature'],dewpoint=context['dewpoint'],pressure=context['pressure'],speed=context['wind']['scalar_speed'],
            u=context['wind']['vector']['u'],v=context['wind']['vector']['v'],**context['clouds'])
        for name,field in originals.items():
            if field is None:fields[name]=None;continue
            source={k:field[k] for k in ('source_digest','grid_sha256','run_id','initialized_at','first_seen_at','available_at')}
            source.update(snapshot_sha256=field['source_sha256'],native_grid=VARIABLES[name][1]);ref=identity(source);source['ref_sha256']=ref;sources[ref]=source
            fields[name]=dict(value=field['value'],source_ref=ref,native_asset_sha256=field['native_asset_sha256'])
        if any(f is not None for f in fields.values()):hours.append(dict(valid_at=context['valid_at'],fields=fields,**_derive(fields,sources,context['valid_at'])))
    until=min([instant(base['valid_until']),*(instant(s['initialized_at'])+timedelta(hours=24) for s in sources.values())])
    moisture=build_moisture_context(outdoor=next(c for c in contexts if c['valid_at']==hours[0]['valid_at']),indoor=indoor,zone=zone,decision=decision) if hours else None
    group=dict(schema=GROUP_SCHEMA,method=METHOD,valid_until=until.isoformat(),sources=[sources[k] for k in sorted(sources)],hours=hours,moisture=moisture,
        rh_scope=RH_SCOPE,pressure_basis='mean_sea_level',wind_scope=WIND_SCOPE,cloud_scope=CLOUD_SCOPE,temperature_model_uses_fields=False,
        selection_truncated=truncated,withheld_sources=withheld)
    value=deepcopy(base);value['schema']=SCHEMA;value['groups']['atmosphere']=group
    value['status']='available' if value['groups']['temperature']['hours'] or hours else 'unavailable'
    value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
    return validate_capability_report(value)


def _same_number(a,b):
    return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=1e-9*max(1.,abs(a),abs(b))


def _run_init(run):
    if not isinstance(run,str) or len(run)>128:raise ValueError('known bounded native run identity required')
    if run.startswith('ee:'):return instant(run[3:])
    if re.fullmatch(r'\d{8}_\d{2}hr_\d{2}_preds',run):return datetime.strptime(run[:11],'%Y%m%d_%H').replace(tzinfo=timezone.utc)
    raise ValueError('known native run identity required')


def _validate_moisture(m,group,sources,generated):
    if not group['hours']:
        if m is not None:raise ValueError('no moisture claim without atmospheric target')
        return
    if (not isinstance(m,dict) or set(m)!=MOISTURE_FIELDS or m['schema']!='earthship-forecast-moisture-context/v1' or
            m['scope']!=MOISTURE_SCOPE or m['condensation_assessed'] is not False or m['automatic_actuation'] is not False or m['release_authorized'] is not False or
            m['context_sha256']!=identity({k:v for k,v in m.items() if k!='context_sha256'}) or instant(m['assessed_at'])!=generated or
            m['outdoor_target_at']!=group['hours'][0]['valid_at'] or not isinstance(m['missing_dependencies'],list) or not set(m['missing_dependencies'])<=MISSING):
        raise ValueError('closed source-bound read-only moisture context required')
    dew=group['hours'][0]['fields']['dewpoint'];expected=None if dew is None else vapor_pressure_hpa(dew['value'])
    if not _same_number(expected,m['outdoor_vapor_pressure_hpa']):raise ValueError('original forecast dewpoint moisture diagnostic differs')
    if m['mode']=='outdoor_only':
        if (not m['missing_dependencies'] or any(m[k] is not None for k in ('indoor_vapor_pressure_hpa','indoor_temperature_c','indoor_relative_humidity_pct','comparison','valid_until','indoor_context_sha256')) or m['indoor_evidence_sha256s']!=[]):
            raise ValueError('unqualified indoor moisture comparison refused')
    elif m['mode']=='qualified_comparison':
        if (m['missing_dependencies'] or not finite(m['indoor_temperature_c']) or not -100<=m['indoor_temperature_c']<=70 or
                not finite(m['indoor_relative_humidity_pct']) or not 0<=m['indoor_relative_humidity_pct']<=100 or expected is None or
                not generated<instant(m['outdoor_target_at'])<=generated+timedelta(hours=2) or not generated<instant(m['valid_until'])<=generated+timedelta(seconds=120) or
                not isinstance(m['indoor_evidence_sha256s'],list) or len(m['indoor_evidence_sha256s'])!=2):raise ValueError('current qualified indoor moisture evidence required')
        for pin in [m['indoor_context_sha256'],*m['indoor_evidence_sha256s']]:digest(pin)
        indoor=vapor_pressure_hpa(m['indoor_temperature_c'])*m['indoor_relative_humidity_pct']/100;difference=expected-indoor
        comparison='forecast_air_drier' if difference<-.5 else 'forecast_air_wetter' if difference>.5 else 'similar_vapor_pressure'
        if not _same_number(indoor,m['indoor_vapor_pressure_hpa']) or comparison!=m['comparison']:raise ValueError('moisture comparison differs from declared diagnostic')
    else:raise ValueError('known moisture evidence mode required')


def validate_atmospheric_report(value,*,now=None):
    from .capability_publish import validate_capability_report,MAX_BYTES,SCHEMA as V1
    fields={'schema','provider','generated_at','valid_until','timezone','status','sources','groups','automatic_actuation','release_authorized','report_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!=SCHEMA or len(canonical(value))>MAX_BYTES or
            value['report_sha256']!=identity({k:v for k,v in value.items() if k!='report_sha256'}) or
            not isinstance(value['groups'],dict) or set(value['groups'])!={'temperature','atmosphere'}):raise ValueError('closed original v2 capability report required')
    legacy=deepcopy(value);legacy['schema']=V1;legacy['groups']={'temperature':value['groups']['temperature']}
    legacy['status']='available' if legacy['groups']['temperature']['hours'] else 'unavailable';legacy['report_sha256']=identity({k:v for k,v in legacy.items() if k!='report_sha256'})
    validate_capability_report(legacy,now=now)
    group=value['groups']['atmosphere'];generated=instant(value['generated_at']);end=instant(value['valid_until'])
    if (not isinstance(group,dict) or set(group)!=GROUP_FIELDS or group['schema']!=GROUP_SCHEMA or group['method']!=METHOD or
            group['rh_scope']!=RH_SCOPE or group['pressure_basis']!='mean_sea_level' or group['wind_scope']!=WIND_SCOPE or group['cloud_scope']!=CLOUD_SCOPE or
            group['temperature_model_uses_fields'] is not False or type(group['selection_truncated']) is not bool or
            type(group['withheld_sources']) is not int or not 0<=group['withheld_sources']<=32 or
            not generated<instant(group['valid_until'])<=end or not isinstance(group['sources'],list) or len(group['sources'])>16 or
            not isinstance(group['hours'],list) or len(group['hours'])>24):raise ValueError('bounded raw atmospheric group required')
    sources={}
    for s in group['sources']:
        if not isinstance(s,dict) or set(s)!=SOURCE_FIELDS or s['ref_sha256']!=identity({k:v for k,v in s.items() if k!='ref_sha256'}):raise ValueError('closed original atmospheric source reference required')
        for name in ('ref_sha256','snapshot_sha256','source_digest','grid_sha256'):digest(s[name])
        init,seen,available=map(instant,(s['initialized_at'],s['first_seen_at'],s['available_at']))
        if (s['native_grid'] not in ('station','gridded') or _run_init(s['run_id'])!=init or not init<=seen<=available<=generated<init+timedelta(hours=24) or
                instant(group['valid_until'])>init+timedelta(hours=24) or s['ref_sha256'] in sources):raise ValueError('atmospheric source availability/grid/lifetime differs')
        sources[s['ref_sha256']]=s
    used=set();times=[]
    for row in group['hours']:
        if not isinstance(row,dict) or set(row)!=ROW_FIELDS or not isinstance(row['fields'],dict) or set(row['fields'])!=set(VARIABLES):raise ValueError('closed atmospheric point quantities required')
        at=instant(row['valid_at']);times.append(at)
        if not generated<at<=generated+timedelta(hours=24):raise ValueError('declared near-term atmospheric target required')
        any_field=False
        for name,field in row['fields'].items():
            if field is None:continue
            if not isinstance(field,dict) or set(field)!={'value','source_ref','native_asset_sha256'} or field['source_ref'] not in sources:raise ValueError('original atmospheric quantity reference required')
            variable,grid,unit,low,high=VARIABLES[name];s=sources[field['source_ref']];digest(field['native_asset_sha256'])
            if not finite(field['value']) or not low<=field['value']<=high or s['native_grid']!=grid or at>instant(s['initialized_at'])+timedelta(hours=360):raise ValueError('native atmospheric quantity domain differs')
            used.add(field['source_ref']);any_field=True
        if not any_field:raise ValueError('empty atmospheric target refused')
        expected=_derive(row['fields'],sources,row['valid_at'])
        if any(not _same_number(row[k],v) if k in ('relative_humidity_pct','wind_from_degrees','vector_magnitude_m_s') else row[k]!=v for k,v in expected.items()):
            raise ValueError('derived atmospheric diagnostic differs from original means')
    if times!=sorted(set(times)) or used!=set(sources):raise ValueError('unique ordered atmospheric targets and used sources required')
    _validate_moisture(group['moisture'],group,sources,generated)
    if value['status']!=('available' if value['groups']['temperature']['hours'] or group['hours'] else 'unavailable'):raise ValueError('truthful v2 group availability required')
    return value


def validate_moisture_original(value,prepared):
    """Recompute the public comparison from its exact private qualified context."""
    group=value['groups']['atmosphere'];moisture=group['moisture'];original=prepared.to_dict()
    wanted=set(moisture['indoor_evidence_sha256s'])
    selected=[(key,row) for key,row in original['observations'].items() if row['evidence'] is not None and identity(row['evidence']) in wanted]
    if (len(wanted)!=2 or len(selected)!=2 or {key.rsplit(':',1)[-1] for key,row in selected}!={'air_temperature','relative_humidity'} or
            len({row['zone'] for key,row in selected})!=1):raise ValueError('exact same-zone indoor temperature/humidity originals required')
    first=group['hours'][0];sources={s['ref_sha256']:s for s in group['sources']}
    outdoor=dict(schema='earthship-atmospheric-context/v1',assessed_at=value['generated_at'],valid_at=first['valid_at'],
        dewpoint=_expand(first['fields']['dewpoint'],sources,first['valid_at'],'dewpoint'),automatic_actuation=False)
    outdoor['context_sha256']=identity(outdoor)
    expected=build_moisture_context(outdoor=outdoor,indoor=prepared,zone=selected[0][1]['zone'],decision=instant(value['generated_at']))
    if moisture!=expected:raise ValueError('public moisture claim differs from original qualified observations')
    return value
