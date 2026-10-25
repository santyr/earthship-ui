"""Coherent private handoff records bind actual previous service ownership."""
import importlib,json
from pathlib import Path
import pytest
from test_household_native_family import fixture as family_fixture
from test_household_cycle_deploy import write,encode,baseline_metadata_stage


def fixture(tmp_path,monkeypatch):
    family,args,settings,record,libraries,out=family_fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    legacy={**args,'stage':tmp_path/'previous','forecast_config':args['service_forecast_config']}
    legacy.pop('service_forecast_config');baseline_metadata_stage(legacy)
    previous=legacy['stage'];base=args['service_file'].parent;config=legacy['forecast_config']
    forecast_override=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf'
    forecast_override.parent.mkdir(mode=0o700);write(forecast_override,(previous/'service.conf').read_bytes())
    score_raw=(f'[Service]\nEnvironment="PYTHONPATH={previous}/sources/openhab/scripts:/home/sat/Solar_PV/analytics/src"\nExecStart=\nExecStart=/usr/bin/python3 {previous}/sources/openhab/scripts/household_forecast_score.py --config {config} --stage {previous}\n').encode()
    score_override=base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'
    score_override.parent.mkdir(mode=0o700);write(score_override,score_raw)
    caps='\n'.join(k+'='+('60' if k=='TimeoutStartSec' else v) for k,v in deploy.LIMITS.items())
    write(base/'thermal-provisional-score.service',('[Service]\n'+caps+'\n').encode(),0o644)
    write(base/'thermal-provisional-forecast.timer',b'[Timer]\nOnCalendar=*-*-* *:04/5:45 UTC\n',0o644)
    write(base/'thermal-provisional-score.timer',b'[Timer]\nOnCalendar=*-*-* *:00/5:10 UTC\nOnCalendar=*-*-* *:01/5:10 UTC\nOnCalendar=*-*-* *:02/5:10 UTC\nOnCalendar=*-*-* *:03/5:10 UTC\n',0o644)
    family.prepare(args['stage'],libraries,out,guard=lambda:None)
    module=importlib.import_module('household_native_handoff')
    def definition(path):
        dropins=[str(p) for p in (base/(path.name+'.d')).glob('*.conf')]
        return {'FragmentPath':str(path),'DropInPaths':' '.join(dropins)}
    monkeypatch.setattr(module,'_unit_definition',definition)
    def state(path):
        raw=(previous/'service.conf').read_bytes() if path.name=='thermal-provisional-forecast.service' else score_raw
        command=[r[10:] for r in raw.decode().splitlines() if r.startswith('ExecStart=') and r!='ExecStart='][0]
        return dict(deploy.EFFECTIVE_LIMITS,ExecStart=command,ActiveState='inactive',MainPID='0')
    monkeypatch.setattr(deploy,'_service_state',state)
    return module,args,previous,out,tmp_path/'handoff',base


def test_handoff_binds_one_native_family_and_both_previous_owned_stages(tmp_path,monkeypatch):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    # A fresh Google fit owns different source bytes from its retired baseline.
    assert deploy.verify_stage(args['stage'])['protected_runtime_sources']!=deploy.verify_handoff_baseline(previous)['protected_runtime_sources']
    selected=json.loads(args['forecast_config'].read_bytes())
    assert selected['schema']=='earthship-weathernext-thermal-live-config/v1'
    result=m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    assert result['status']=='native_handoff_staged' and result['live_units_changed'] is False
    checked=m.verify(out,guard=lambda:None)
    assert checked['previous_forecast_stage']==str(previous) and checked['previous_score_stage']==str(previous)
    assert len(checked['changes'])==5 and checked['automatic_actuation'] is False
    assert {row['target'] for row in checked['changes'].values()}=={
        str(base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf'),
        str(base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'),
        str(base/'thermal-provisional-score.timer.d'/'zzzz-household-native-timer.conf'),
        str(base/'thermal-native-geometry-prepare.service'),str(base/'thermal-native-geometry-prepare.timer')}
    assert not (base/'thermal-native-geometry-prepare.service').exists()


@pytest.mark.parametrize('damage',['override','effective','extra_dropin','timer','collision','family','cache'])
def test_handoff_refuses_unreconciled_originals_before_creating_output(tmp_path,monkeypatch,damage):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    if damage=='override':(base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf').write_text('changed')
    elif damage=='effective':monkeypatch.setattr(deploy,'_service_state',lambda path:{**deploy.EFFECTIVE_LIMITS,'ExecStart':'unowned command'})
    elif damage=='extra_dropin':write(base/'thermal-provisional-score.service.d'/'zzzzz-other.conf',b'[Service]\n')
    elif damage=='timer':(base/'thermal-provisional-forecast.timer').write_text('[Timer]\nOnCalendar=hourly\n')
    elif damage=='collision':write(base/'thermal-native-geometry-prepare.service',b'existing')
    elif damage=='family':(family/'score.conf').write_text('resealed unsafe command')
    else:
        path=previous/'cycle.json';value=json.loads(path.read_bytes());value['observation_cache']=str(base/'other-cache');path.write_bytes(encode(value))
    with pytest.raises((ValueError,OSError)):m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    assert not out.exists()


def test_resealed_handoff_targets_cannot_redirect_writes(tmp_path,monkeypatch):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    path=out/'handoff.json';value=json.loads(path.read_bytes());value['changes']['forecast']['target']=str(base/'unrelated.service')
    from hashlib import sha256
    value['handoff_sha256']=sha256(encode({k:v for k,v in value.items() if k!='handoff_sha256'})).hexdigest();path.write_bytes(encode(value))
    with pytest.raises(ValueError):m.verify(out,guard=lambda:None)


def retirement_upgrade_fixture(tmp_path,monkeypatch):
    """Actual upgrade assembly plus actual history inventory, private originals."""
    from test_native_serving_upgrade import fixture as upgrade
    from test_native_active_score_history import fixture as history_fixture
    from household_native_training import save,directory
    from household.codec import identity
    from datetime import datetime,timezone
    import household_native_history as history
    import household_forecast_score as scorer
    deploy,handoff,family,kwargs,targets,old_family=upgrade(tmp_path,monkeypatch)
    verify_stage=deploy.verify_stage
    history_root=directory(tmp_path/'history-fixture')
    _,refs,binding,old_now=history_fixture(history_root,monkeypatch)
    verify_history=deploy.verify_stage;stages={row['stage'] for row in refs}
    monkeypatch.setattr(deploy,'verify_stage',lambda stage,**kw:verify_history(stage,**kw) if str(stage) in stages else verify_stage(stage,**kw))
    now=datetime.now(timezone.utc);body=json.loads(binding.read_bytes());body['issued_at']=now.isoformat()
    body['binding_sha256']=identity({k:v for k,v in body.items() if k!='binding_sha256'})
    folder=directory(binding.parent.parent/('origins-'+now.strftime('%Y%m%d')))
    path=folder/binding.name;binding.unlink();save(path,body)
    incumbent={'stage':str(kwargs['previous_forecast_stage']),'deployment_sha256':kwargs['previous_deployment_sha256']}
    proof=history.assess([*refs,incumbent],now=now,guard=lambda:None)
    proof_path=tmp_path/'retirement-proof.json';save(proof_path,proof);kwargs['history_proof']=proof_path
    read_dispatch=scorer.read_score_dispatch
    selected={'historical':[*refs[1:],incumbent]}
    def dispatch(stage,**kw):
        value=read_dispatch(stage,**kw)
        value['historical']=refs if Path(stage)==kwargs['previous_forecast_stage'] else selected['historical']
        return value
    monkeypatch.setattr(scorer,'read_score_dispatch',dispatch)
    return handoff,family,kwargs,proof,refs,path,selected


@pytest.mark.parametrize('damage',['overlap','duplicate','unknown_field','missing_partition','missing_field','foreign_reference'])
def test_handoff_rejects_malformed_or_overlapping_history_partition(tmp_path,monkeypatch,damage):
    from household_native_training import save
    handoff,family,kwargs,proof,refs,binding,selected=retirement_upgrade_fixture(tmp_path,monkeypatch)
    if damage=='overlap':
        proof['retired'].append(refs[1]);selected['historical'].remove(refs[1])
    elif damage=='duplicate':proof['retained'].append(refs[1])
    elif damage=='unknown_field':proof['retirement_authorized']=True
    elif damage=='missing_field':del proof['references']
    elif damage=='foreign_reference':proof['retired'][0]=dict(refs[0],deployment_sha256='f'*64)
    else:proof['retained'].remove(refs[2])
    save(kwargs['history_proof'],proof)
    with pytest.raises(ValueError,match='partition|closed history'):
        handoff.prepare(family,**kwargs)
    assert not kwargs['output'].exists()


@pytest.mark.parametrize('target',['retained','retired'])
def test_handoff_rescans_new_binding_and_preserves_additive_retained_history(tmp_path,monkeypatch,target):
    from household_native_training import save
    from household.codec import identity
    handoff,family,kwargs,proof,refs,binding,selected=retirement_upgrade_fixture(tmp_path,monkeypatch)
    row=refs[1] if target=='retained' else refs[0]
    body=json.loads(binding.read_bytes());body.update(stage=row['stage'],deployment_sha256=row['deployment_sha256'],capture_sha256='e'*64)
    body['binding_sha256']=identity({k:v for k,v in body.items() if k!='binding_sha256'})
    save(binding.parent/('e'*64+'.native-serving-model-binding-v1.json'),body)
    if target=='retired':
        with pytest.raises(ValueError,match='retired selection|still required'):handoff.prepare(family,**kwargs)
        assert not kwargs['output'].exists()
    else:
        handoff.prepare(family,**kwargs)
        assert handoff.verify(kwargs['output'],guard=lambda:None)['history_proof']['path']==str(kwargs['history_proof'])


def test_handoff_uses_fresh_omission_result_instead_of_supplied_retired_list(tmp_path,monkeypatch):
    import household_native_history as history
    handoff,family,kwargs,proof,refs,binding,selected=retirement_upgrade_fixture(tmp_path,monkeypatch)
    revalidate=history.revalidate
    def freshly_required(*args,**kw):
        current=revalidate(*args,**kw)
        # Exercise the consumer of the independent result, separately from its
        # own partition/inventory tests: the final result must be authoritative.
        current['retired'].remove(refs[0]);current['retained'].append(refs[0]);return current
    monkeypatch.setattr(history,'revalidate',freshly_required)
    with pytest.raises(ValueError,match='still required'):handoff.prepare(family,**kwargs)
    assert not kwargs['output'].exists()
