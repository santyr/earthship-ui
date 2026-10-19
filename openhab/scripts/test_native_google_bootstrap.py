"""Initial Google handoff verifies detached ownership, never old model/scoring APIs."""
from hashlib import sha256
import json
from pathlib import Path
import pytest
from test_native_serving_upgrade import fixture as upgrade, FILES
from test_household_cycle_deploy import write, encode


def render_family(directory, stage):
    import household_native_family as family
    meta=json.loads((directory/'family.json').read_bytes())
    libraries=Path(meta['libraries_path']);original=libraries.read_bytes()
    record=json.loads((stage/'deployment.json').read_bytes())
    cycle=json.loads((stage/'cycle.json').read_bytes());config=Path(cycle['forecast_config'])
    geometry=json.loads(Path(record['native_originals']['geometry']['path']).read_bytes())
    pin=sha256((stage/'deployment.json').read_bytes()).hexdigest()
    files=family._render(stage,config,libraries,deployment_sha256=pin)
    for name,raw in files.items():write(directory/name,raw)
    write(directory/'family.json',encode(family._metadata(stage,libraries,original,
        geometry['native_runtime'],record,files)))
    return pin


def fixture(tmp_path,monkeypatch):
    deploy,handoff,new_family,kwargs,targets,old_family=upgrade(tmp_path,monkeypatch)
    old_stage=kwargs['previous_forecast_stage'];old_manifest=old_stage/'deployment.json'
    old=json.loads(old_manifest.read_bytes());cycle=json.loads((old_stage/'cycle.json').read_bytes())
    current_config=Path(cycle['forecast_config']);settings=json.loads(current_config.read_bytes())
    settings.pop('weather_source');settings.update(schema='earthship-provisional-thermal-live-config/v3',
        forecast_dsn_file=str(tmp_path/'detached-forecast-credential-not-read'))
    previous_config=tmp_path/'detached-old-config.json';write(previous_config,encode(settings))
    old['original_bindings'].pop(str(current_config));old['original_bindings'][str(previous_config)]=sha256(previous_config.read_bytes()).hexdigest()
    cycle['forecast_config']=str(previous_config);write(old_stage/'cycle.json',encode(cycle))
    old['cycle_sha256']=sha256((old_stage/'cycle.json').read_bytes()).hexdigest()
    raw=(old_stage/'service.conf').read_bytes().replace(str(current_config).encode(),str(previous_config).encode())
    write(old_stage/'service.conf',raw);old['dropin_sha256']=sha256(raw).hexdigest()
    old_dispatch=Path(old['score_dispatch']['path'])
    write(old_dispatch,encode({'schema':'earthship-native-score-dispatch/v1','detached_only':True}))
    old['score_dispatch']['sha256']=sha256(old_dispatch.read_bytes()).hexdigest()
    old['original_bindings'][str(old_dispatch)]=old['score_dispatch']['sha256']
    write(old_manifest,encode(old));old_pin=render_family(old_family,old_stage)
    for role,path in targets.items():write(path,(old_family/FILES[role]).read_bytes())
    # A fresh source cohort has no retained Google model or old scoring queue.
    new_stage=Path(json.loads((new_family/'family.json').read_bytes())['stage'])
    record=json.loads((new_stage/'deployment.json').read_bytes());dispatch=Path(record['score_dispatch']['path'])
    write(dispatch,encode({'schema':'earthship-native-score-dispatch/v2','current':'current','historical':[]}))
    record['score_dispatch']['sha256']=sha256(dispatch.read_bytes()).hexdigest()
    record['original_bindings'][str(dispatch)]=record['score_dispatch']['sha256']
    write(new_stage/'deployment.json',encode(record));render_family(new_family,new_stage)
    kwargs.update(previous_deployment_sha256=old_pin)
    return deploy,handoff,new_family,kwargs,targets,old_family


def test_old_receipt_family_has_a_separate_pinned_metadata_verifier(tmp_path,monkeypatch):
    deploy,handoff,new_family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    import household_native_family as family
    with pytest.raises(ValueError):family.verify(old_family,guard=lambda:None)
    record=family.verify_handoff_baseline(old_family,
        expected_deployment_sha256=kwargs['previous_deployment_sha256'],guard=lambda:None)
    assert record['stage']==str(kwargs['previous_forecast_stage'])


def test_bootstrap_uses_detached_baseline_and_five_owned_files_without_old_scoring(tmp_path,monkeypatch):
    deploy,handoff,new_family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    import household_forecast_score as score
    original_verify=deploy.verify_stage;original_dispatch=score.read_score_dispatch
    previous=kwargs['previous_forecast_stage']
    def active(stage,**kw):
        if Path(stage)==previous:pytest.fail('old family entered active model verification')
        return original_verify(stage,**kw)
    def dispatch(stage,**kw):
        if Path(stage)==previous:pytest.fail('old scoring dispatch was interpreted')
        return original_dispatch(stage,**kw)
    monkeypatch.setattr(deploy,'verify_stage',active);monkeypatch.setattr(score,'read_score_dispatch',dispatch)
    handoff.prepare(new_family,**kwargs);record=handoff.verify(kwargs['output'],guard=lambda:None)
    assert record['schema']=='earthship-native-thermal-handoff/v3'
    assert all(row['previous'] is not None for row in record['changes'].values())
    assert record['automatic_actuation'] is False and record['live_units_changed'] is False


@pytest.mark.parametrize('damage',['pin','source','override','config_extra','endpoint','history','library_runtime'])
def test_bootstrap_preserves_existing_integrity_and_source_boundaries(tmp_path,monkeypatch,damage):
    deploy,handoff,new_family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    old_stage=kwargs['previous_forecast_stage']
    if damage=='pin':kwargs['previous_deployment_sha256']='f'*64
    elif damage=='source':(old_stage/'sources/untracked.py').write_text('# not bound')
    elif damage=='override':targets['preparer_service'].write_bytes(b'unowned change')
    elif damage=='library_runtime':
        path=old_family/'family.json';meta=json.loads(path.read_bytes())
        meta['native_library_runtime']['collector_sha256']='f'*64;write(path,encode(meta))
    elif damage in ('config_extra','endpoint'):
        cycle=json.loads((old_stage/'cycle.json').read_bytes());path=Path(cycle['forecast_config']);settings=json.loads(path.read_bytes())
        settings['extra']='unbound' if damage=='config_extra' else None
        if damage=='endpoint':settings.pop('extra');settings['openhab_base']='http://other.invalid/rest'
        write(path,encode(settings));record=json.loads((old_stage/'deployment.json').read_bytes())
        record['original_bindings'][str(path)]=sha256(path.read_bytes()).hexdigest();write(old_stage/'deployment.json',encode(record))
        kwargs['previous_deployment_sha256']=render_family(old_family,old_stage)
        for role,target in targets.items():write(target,(old_family/FILES[role]).read_bytes())
    else:
        import household_forecast_score as score
        original=score.read_score_dispatch
        def foreign(stage,**kw):
            value=original(stage,**kw)
            if Path(stage)!=old_stage:value['historical']=[{'stage':str(old_stage),'deployment_sha256':kwargs['previous_deployment_sha256']}]
            return value
        monkeypatch.setattr(score,'read_score_dispatch',foreign)
    with pytest.raises(ValueError):handoff.prepare(new_family,**kwargs)
    assert not kwargs['output'].exists()


def test_retired_family_does_not_run_the_current_collector_to_requalify_old_geometry(tmp_path,monkeypatch):
    deploy,handoff,new_family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    import household_native_family as family,astro_geometry_worker as worker
    monkeypatch.setattr(worker,'runtime_identity',lambda *a,**kw:pytest.fail('retired native execution was requalified'))
    family.verify_handoff_baseline(old_family,
        expected_deployment_sha256=kwargs['previous_deployment_sha256'],guard=lambda:None)


def test_bootstrap_installs_five_owned_files_without_active_retired_verification(tmp_path,monkeypatch):
    deploy,handoff,new_family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    import household_native_install as install
    original=deploy.verify_stage;previous=kwargs['previous_forecast_stage']
    def active(stage,**kw):
        if Path(stage)==previous:pytest.fail('retired family entered active installation verification')
        return original(stage,**kw)
    monkeypatch.setattr(deploy,'verify_stage',active)
    handoff.prepare(new_family,**kwargs)
    result=install._install_files(kwargs['output'],guard=lambda:None)
    assert result['file_count']==5 and result['automatic_actuation'] is False
    for role,path in targets.items():assert path.read_bytes()==(new_family/FILES[role]).read_bytes()
