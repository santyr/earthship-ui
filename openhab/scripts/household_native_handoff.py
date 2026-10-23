"""Reconcile a private native handoff with both currently owned service stages.

This module seals and verifies proposed changes. It performs no installation,
unit reload, timer activation, model fitting, publication or physical action.
"""
from hashlib import sha256
import json
from pathlib import Path
import household_cycle_deploy as deploy
import household_native_family as family_api

SCHEMA='earthship-native-thermal-handoff/v1'
FILES={'forecast':'forecast.conf','score':'score.conf','score_timer':'score-timer.conf',
       'preparer_service':'thermal-native-geometry-prepare.service','preparer_timer':'thermal-native-geometry-prepare.timer'}


def _unit_definition(path):
    raw=deploy._systemctl('show',path.name,'--property=FragmentPath','--property=DropInPaths')
    return dict(row.split('=',1) for row in raw.splitlines() if '=' in row)


def _reference(path,*,private=False):
    path=deploy._path(path);raw=deploy._bytes(path,private=private)
    return dict(path=str(path),sha256=sha256(raw).hexdigest()),raw


def _score_override(stage,config):
    scripts=stage/'sources/openhab/scripts'
    return ('[Service]\nEnvironment="PYTHONPATH='+str(scripts)+':/home/sat/Solar_PV/analytics/src"\n'
        'ExecStart=\nExecStart=/usr/bin/python3 '+str(scripts/'household_forecast_score.py')+
        ' --config '+str(config)+' --stage '+str(stage)+'\n').encode()


def _rows(raw,key):
    return [row.split('=',1)[1] for row in raw.decode('utf-8').splitlines() if row.startswith(key+'=')]


def _assemble(family,previous_forecast_stage,previous_score_stage,*,guard,previous_family=None,previous_deployment_sha256=None):
    family,forecast,score=map(deploy._directory,(family,previous_forecast_stage,previous_score_stage))
    guard();selected=family_api.verify(family,guard=guard);stage=deploy._directory(selected['stage'])
    serving=selected['schema'] in ('earthship-native-thermal-service-family/v2','earthship-native-thermal-service-family/v3')
    upgrade=previous_family is not None
    if upgrade!=(previous_deployment_sha256 is not None):raise ValueError('paired previous family and external pin required')
    old_family=None;old_selected=None;reset=False
    def previous_family_record():
        if reset:
            return family_api.verify_handoff_baseline(old_family,
                expected_deployment_sha256=previous_deployment_sha256,guard=guard)
        return family_api.verify(old_family,guard=guard)
    if upgrade:
        # Determine source transition only from the externally pinned original.
        deploy.verify_handoff_baseline(forecast,expected_deployment_sha256=previous_deployment_sha256)
        previous_cycle=json.loads(deploy._bytes(forecast/'cycle.json',private=True))
        previous_settings=json.loads(deploy._bytes(previous_cycle['forecast_config'],private=True,maximum=8192))
        reset=previous_settings.get('schema') not in deploy.GOOGLE_SCHEMAS
        old_family=deploy._directory(previous_family);old_selected=previous_family_record()
        if (not serving or old_selected['schema'] not in ('earthship-native-thermal-service-family/v2','earthship-native-thermal-service-family/v3') or
                old_selected['deployment_sha256']!=previous_deployment_sha256 or
                forecast!=score or str(forecast)!=old_selected['stage'] or forecast==stage):
            raise ValueError('explicit previous owned receipt family pin required')
    def stage_record(path):
        if upgrade and path==forecast:
            verifier=deploy.verify_handoff_baseline if reset else deploy.verify_stage
            return verifier(path,expected_deployment_sha256=previous_deployment_sha256)
        if path==stage:return deploy.verify_stage(path,**({'expected_deployment_sha256':selected['deployment_sha256']} if serving else {}))
        return deploy.verify_handoff_baseline(path)
    records=[stage_record(path) for path in (stage,forecast,score)]
    if serving:
        from household_forecast_score import read_score_dispatch
        dispatch=read_score_dispatch(stage,deployment_sha256=selected['deployment_sha256'],guard=guard)
        if reset:
            if dispatch['historical']:raise ValueError('initial Google cohort requires an empty score history')
        elif upgrade:
            previous_dispatch=read_score_dispatch(forecast,deployment_sha256=previous_deployment_sha256,guard=guard)
            required=[dict(stage=str(forecast),deployment_sha256=previous_deployment_sha256),*previous_dispatch['historical']]
            if any(row not in dispatch['historical'] for row in required):
                raise ValueError('upgrade must retain all Google native score backlogs')
    cycles=[json.loads(deploy._bytes(path/'cycle.json',private=True)) for path in (stage,forecast,score)]
    current,old_forecast,old_score=records
    stripped=lambda cycle:{k:v for k,v in cycle.items() if k not in ('evidence_directory','forecast_config')}
    if (any(record['service_file']!=current['service_file'] for record in records[1:]) or
        old_forecast['protected_runtime_sources']!=old_score['protected_runtime_sources'] or
        any(stripped(cycle)!=stripped(cycles[0]) for cycle in cycles[1:]) or cycles[1]['forecast_config']!=cycles[2]['forecast_config']):
        raise ValueError('same owned forecast inputs, cache and previous fitted sources required')
    configs=[deploy._path(cycle['forecast_config']) for cycle in cycles]
    settings=[json.loads(deploy._bytes(path,private=True,maximum=8192)) for path in configs]
    if set(settings[1])!=deploy._baseline_configuration_fields(settings[1].get('schema')):
        raise ValueError('closed original handoff baseline required')
    selection={'schema','candidate_path','evidence_directory','geometry_directory','artifact_sha256','runtime_sha256',
        'model_receipt_path','model_receipt_sha256'}
    if settings[1].get('schema') not in deploy.GOOGLE_SCHEMAS:
        selection|={'forecast_dsn_file','weather_source'}
    if {k:v for k,v in settings[0].items() if k not in selection}!={k:v for k,v in settings[1].items() if k not in selection}:
        raise ValueError('native selection cannot change source endpoints, credentials or shared lock')
    # Each stage already pins its own originals and fitted source closure.
    # A Google-only reset must not import or require the old model's runtime.
    # All local source selections and the shared lock remain equal above.
    service=deploy._path(current['service_file']);base=service.parent
    if service.name!='thermal-provisional-forecast.service':raise ValueError('fixed owned forecast service required')
    score_service=base/'thermal-provisional-score.service'
    forecast_timer=base/'thermal-provisional-forecast.timer';score_timer=base/'thermal-provisional-score.timer'
    targets={
        'forecast':base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf',
        'score':base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf',
        'score_timer':base/'thermal-provisional-score.timer.d'/'zzzz-household-native-timer.conf',
        'preparer_service':base/'thermal-native-geometry-prepare.service',
        'preparer_timer':base/'thermal-native-geometry-prepare.timer'}
    originals={};raws={}
    for role,path,private in (
        ('forecast_service',service,False),('score_service',score_service,False),
        ('forecast_timer',forecast_timer,False),('score_timer',score_timer,False),
        ('forecast_override',targets['forecast'],True),('score_override',targets['score'],True)):
        originals[role],raws[role]=_reference(path,private=private)
    previous_raws=([deploy._bytes(old_family/FILES[role],private=True) for role in ('forecast','score')]
        if upgrade else [deploy._bytes(forecast/'service.conf',private=True),_score_override(score,configs[2])])
    if upgrade:
        for role in ('score_timer','preparer_service','preparer_timer'):
            originals[role+'_override'],raws[role+'_override']=_reference(targets[role],private=True)
            if raws[role+'_override']!=deploy._bytes(old_family/FILES[role],private=True):
                raise ValueError('exact previous owned native family files required')
    if raws['forecast_override']!=previous_raws[0] or raws['score_override']!=previous_raws[1]:
        raise ValueError('exact previous owned forecast and score overrides required')
    for path,expected_dropins,expected_raw in ((service,[str(targets['forecast'])],previous_raws[0]),
            (score_service,[str(targets['score'])],previous_raws[1]),(forecast_timer,[],None),
            (score_timer,[str(targets['score_timer'])] if upgrade else [],None),
            *(((targets['preparer_service'],[],raws['preparer_service_override']),
               (targets['preparer_timer'],[],None)) if upgrade else ())):
        definition=_unit_definition(path)
        if definition.get('FragmentPath')!=str(path) or definition.get('DropInPaths','').split()!=expected_dropins:
            raise ValueError('owned unit fragment or drop-in inventory differs')
        if expected_raw is not None:
            state=deploy._service_state(path)
            limits=dict(deploy.EFFECTIVE_LIMITS)
            if b'CPUQuota=100%\n' in expected_raw:
                limits['CPUQuotaPerSecUSec']='1s'
            if any(state.get(k)!=v for k,v in limits.items()) or not deploy._entry_matches(state,expected_raw):
                raise ValueError('effective owned command or resource limits differ')
    expected_score_caps={**deploy.LIMITS,'TimeoutStartSec':'60'}
    if any(_rows(raws['score_service'],key)!=[value] for key,value in expected_score_caps.items()):
        raise ValueError('original scorer resource or timeout contract differs')
    if _rows(raws['forecast_timer'],'OnCalendar')!=[selected['original_forecast_warm_clock']]:
        raise ValueError('original forecast warm clock differs')
    if _rows(raws['score_timer'],'OnCalendar')!=['*-*-* *:'+slot+'/5:10 UTC' for slot in ('00','01','02','03')]:
        raise ValueError('original scorer clocks differ')
    files={'forecast':'forecast.conf','score':'score.conf','score_timer':'score-timer.conf',
        'preparer_service':'thermal-native-geometry-prepare.service','preparer_timer':'thermal-native-geometry-prepare.timer'}
    changes={}
    for role,target in targets.items():
        target=deploy._path(target)
        previous=originals.get(role+'_override')
        if previous is None and (target.exists() or target.is_symlink()):raise ValueError('new handoff target already exists')
        desired,_=_reference(family/files[role],private=True)
        changes[role]=dict(target=str(target),previous=previous,desired=desired)
    family_ref,_=_reference(family/'family.json',private=True)
    record=dict(schema=SCHEMA,family=str(family),family_sha256=family_ref['sha256'],
        previous_forecast_stage=str(forecast),previous_score_stage=str(score),
        previous_deployment_sha256={role:sha256(deploy._bytes(path/'deployment.json',private=True)).hexdigest()
            for role,path in (('forecast',forecast),('score',score))},
        deployment_sha256=selected['deployment_sha256'],artifact_sha256=selected['artifact_sha256'],
        runtime_sha256=selected['runtime_sha256'],originals=originals,changes=changes,
        creator_source_sha256=sha256(deploy._bytes(Path(__file__))).hexdigest(),
        live_units_changed=False,automatic_actuation=False)
    guard()
    if serving:record.update(schema='earthship-native-thermal-handoff/v2',model_verification=selected['model_verification'],score_dispatch=selected['score_dispatch'])
    if upgrade:
        previous_ref,_=_reference(old_family/'family.json',private=True)
        if previous_family_record()!=old_selected:raise ValueError('previous native family changed')
        record.update(schema='earthship-native-thermal-handoff/v3',previous_family=previous_ref)
    if any(stage_record(path)!=old for path,old in zip((stage,forecast,score),records)):
        raise ValueError('handoff stage originals changed')
    if family_api.verify(family,guard=guard)!=selected or any(_reference(row['path'],private=role.endswith('override'))[0]!=row for role,row in originals.items()):
        raise ValueError('handoff unit or family originals changed')
    record['handoff_sha256']=sha256(deploy._encode(record)).hexdigest()
    return record


def prepare(family,*,previous_forecast_stage,previous_score_stage,output,guard,previous_family=None,previous_deployment_sha256=None):
    output=deploy._path(output)
    record=_assemble(family,previous_forecast_stage,previous_score_stage,guard=guard,previous_family=previous_family,previous_deployment_sha256=previous_deployment_sha256)
    if output.exists() or output.is_symlink():raise ValueError('distinct private handoff output required')
    deploy._directory(output.parent);output.mkdir(mode=0o700)
    deploy._write(output/'handoff.json',deploy._encode(record))
    if verify(output,guard=guard)!=record:raise ValueError('private handoff readback differs')
    return dict(status='native_handoff_staged',handoff_sha256=record['handoff_sha256'],live_units_changed=False,automatic_actuation=False)


def verify(output,*,guard):
    output=deploy._directory(output)
    if {p.name for p in output.iterdir()}!={'handoff.json'}:raise ValueError('closed private handoff directory required')
    raw=deploy._bytes(output/'handoff.json',private=True)
    from household.codec import loads
    record=loads(raw)
    upgrade=record.get('schema')=='earthship-native-thermal-handoff/v3'
    kwargs={}
    if upgrade:
        ref=record['previous_family'];path=deploy._path(ref['path'])
        if path.name!='family.json' or _reference(path,private=True)[0]!=ref:raise ValueError('previous family reference differs')
        kwargs=dict(previous_family=path.parent,previous_deployment_sha256=record['previous_deployment_sha256']['forecast'])
    expected=_assemble(record['family'],record['previous_forecast_stage'],record['previous_score_stage'],guard=guard,**kwargs)
    if deploy._encode(record)!=deploy._encode(expected) or deploy._bytes(output/'handoff.json',private=True)!=raw:
        raise ValueError('native handoff differs from original bindings')
    return record
