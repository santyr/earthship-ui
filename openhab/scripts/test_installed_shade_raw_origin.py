"""Versioned raw-calibrated issuance math is not household release evidence."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_installed_shade_calibrated import candidate,mathematical_candidate
from test_installed_shade_origin import ISSUE,native,weather,actions,outcome
from test_installed_shade_calibration import synthetic_cycle_grid
from thermal_model.installed_shade_artifact import _digest
from thermal_model.forcing_capture import _canonical


@pytest.fixture(scope='module')
def raw_math_capture(candidate):
    # Deliberate pure numerical fixture with no calibration source archive.
    # It cannot establish source-ready preparation or release qualification.
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    artifact=mathematical_candidate(candidate)
    artifact['schema']='earthship-installed-shade-candidate/v3'
    artifact['calibration'].update(schema='earthship-installed-shade-calibration/v2',
        source_contract='earthship-installed-shade-score-sources/v2')
    for name in RAW_RUNTIME_PATHS-artifact['runtime']['source_manifest'].keys():artifact['runtime']['source_manifest'][name]='7'*64
    artifact['runtime_revision']=_digest(artifact['runtime'])
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    issue=ISSUE+timedelta(days=40)
    prepared=origin.PreparedRawCalibratedCandidate(_canonical(artifact),issue)
    current,proof=native(issue)
    return origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
        published_at=issue+timedelta(seconds=2),runtime=artifact['runtime'],forecast=weather(issue),
        current=current,origin_temperatures=proof,action_snapshot=actions(issue))


def test_raw_issue_has_distinct_schema_and_legacy_reader_refuses(raw_math_capture):
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture
    assert record['schema']=='earthship-installed-shade-origin/v4'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v3'
    assert record['output']['status']=='shadow' and record['output']['release_authorized'] is False
    assert record['output']['automatic_actuation'] is False
    assert len(record['output']['prediction_intervals'])==4
    assert record['output']['artifact_sha256']==record['candidate']['artifact_sha256']
    with pytest.raises(ValueError):origin.validate_calibrated_capture(record)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_raw_issue_scoring_preserves_as_issued_intervals_and_identity(raw_math_capture,hours):
    from datetime import datetime
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture;issue=datetime.fromisoformat(record['issued_at']);target=issue+timedelta(hours=hours)
    publication=dict(time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(record['output']).decode())
    result=origin.score_raw_calibrated_capture(record,publication=publication,horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v4'
    assert result['original_capture_sha256']==record['capture_sha256']
    assert result['publication_sha256']==_digest(publication)
    assert result['scored_pair']['artifact_sha256']==record['candidate']['artifact_sha256']
    assert result['scored_pair']['interval_width_f']==pytest.approx(64.)
    assert result['release_authorized'] is False


@pytest.mark.parametrize('damage',['band','raw_contract','runtime','candidate_schema'])
def test_rehashed_raw_issue_changes_refuse_original_replay(raw_math_capture,damage):
    from thermal_model import installed_shade_calibrated_origin as origin
    record=deepcopy(raw_math_capture)
    if damage=='band':record['output']['prediction_intervals'][0]['upper_air_f']+=1
    elif damage=='runtime':record['runtime']['source_manifest']['weather_temperature_sources.py']='a'*64
    else:
        if damage=='raw_contract':record['candidate']['calibration']['source_contract']='earthship-installed-shade-score-sources/v1'
        else:record['candidate']['schema']='earthship-installed-shade-candidate/v2'
        record['candidate']['artifact_sha256']=_digest({k:v for k,v in record['candidate'].items() if k!='artifact_sha256'})
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):origin.validate_raw_calibrated_capture(record)


def test_raw_issue_private_readback_is_typed_and_immutable(raw_math_capture,tmp_path):
    from thermal_model import installed_shade_calibrated_origin as origin
    tmp_path.chmod(0o700)
    path=origin.write_raw_calibrated_capture(tmp_path,raw_math_capture)
    assert path.name==raw_math_capture['capture_sha256']+'.installed-shade-origin-v4.json'
    assert path.stat().st_mode&0o777==0o600
    assert origin.read_raw_calibrated_capture(path)==raw_math_capture
    assert origin.write_raw_calibrated_capture(tmp_path,raw_math_capture)==path
    with pytest.raises(ValueError):origin.read_calibrated_capture(path)



from test_installed_shade_raw_calibration import retained_raw_case,collection,issued,release_case
from test_installed_shade_calibrated import runtime


def test_public_raw_preparation_replays_queries_and_partial_support_cannot_issue(retained_raw_case,candidate):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    calibration,source_values,backend,_,_=retained_raw_case
    record=calibration.build_raw_calibration(**source_values)
    new=runtime(candidate)
    for name in RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    values=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=record,
        original_pairs=source_values['original_pairs'],base_runtime=candidate[2],runtime=new,
        created_at=source_values['created_at'])
    aggregate=artifact.build_raw_calibrated_candidate(**values)
    parameters={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    prepared=origin.prepare_raw_calibrated_candidate(aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])
    assert isinstance(prepared,origin.PreparedRawCalibratedCandidate)
    issue=values['created_at']+timedelta(days=1);current,proof=native(issue)
    with pytest.raises(ValueError,match='independent calibration support incomplete'):
        origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
            published_at=issue+timedelta(seconds=2),runtime=new,forecast=weather(issue),
            current=current,origin_temperatures=proof,action_snapshot=actions(issue))
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):origin.prepare_raw_calibrated_candidate(aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])



@pytest.mark.parametrize('damage',['legacy_prepared_type','future_preparation'])
def test_raw_issue_refuses_wrong_preparation_type_or_future_proof(raw_math_capture,damage):
    from datetime import datetime
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture;issue=datetime.fromisoformat(record['issued_at'])
    if damage=='legacy_prepared_type':prepared=origin.PreparedCalibratedCandidate(_canonical(record['candidate']),issue)
    else:prepared=origin.PreparedRawCalibratedCandidate(_canonical(record['candidate']),issue+timedelta(seconds=1))
    with pytest.raises(ValueError,match='source-verified calibrated candidate unavailable at issue'):
        origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
            published_at=record['published_at'],runtime=record['runtime'],forecast=record['forecast'],
            current=record['current'],origin_temperatures=record['origin_temperatures'],action_snapshot=record['action_snapshot'])


@pytest.fixture
def source_origin_case(raw_math_capture,tmp_path):
    return build_source_origin_case(raw_math_capture,tmp_path)


def build_source_origin_case(raw_math_capture,tmp_path):
    """Real raw native issue queries; candidate is only a math fixture."""
    from datetime import datetime
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_sources import build_temperature_source,write_temperature_source,replay_temperature_source
    from thermal_model.temperature_history import STREAMS,POLICY
    from thermal_model.dataset import latent_mass_from_series
    from thermal_temperature_runtime import shadow_temperatures_v2
    from thermal_model import installed_shade_calibrated_origin as origin
    tmp_path.chmod(0o700);issue=datetime.fromisoformat(raw_math_capture['issued_at'])
    policies={s:TemperaturePolicy(m,i,**POLICY) for s,m,i in STREAMS.values()}
    phases={values[0]:raw_math_capture['source_epochs'][r] for r,values in STREAMS.items()}
    clock={'at':issue-timedelta(minutes=5),'tick':1000}
    collector=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:1)
    rows=[]
    for at,value in [(issue-timedelta(minutes=5),70),(issue-timedelta(seconds=30),71)]:
        clock.update(at=at,tick=clock['tick']+300)
        for policy in policies.values():collector.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:str(value)})
        rows.append((at,json.dumps(collector.snapshot())))
    rows.insert(1,(issue-timedelta(minutes=2),None));paths={};saved=[]
    def grid(stream,targets,assessed):
        role=next(r for r,v in STREAMS.items() if v[0]==stream)
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=assessed,stream=stream,policy=policies[stream],sensor_epoch=phases[stream])
        paths[role]=str(write_temperature_source(tmp_path,packet))
        return replay_temperature_source(packet)
    selected=shadow_temperatures_v2(issue,grid,sensor_epochs=raw_math_capture['source_epochs'],origin_observer=saved.append)
    current={role:v['current'] for role,v in selected.items()}
    history=list(selected['mass']['history']);reading=current['mass']
    if not history or reading['at']>history[-1][0]:history.append((reading['at'],reading['value']))
    latent=latent_mass_from_series(history)
    if latent is not None:current['mass']['value']=latent[1]
    prepared=origin.PreparedRawCalibratedCandidate(_canonical(raw_math_capture['candidate']),issue)
    return prepared,dict(issued_at=issue,inputs_available_at=issue,published_at=issue+timedelta(seconds=2),
        runtime=raw_math_capture['runtime'],forecast=weather(issue),current=current,
        origin_temperatures=saved[0],action_snapshot=actions(issue),native_source_paths=paths)


def test_source_origin_binds_raw_queries_and_old_readers_refuse(source_origin_case,tmp_path):
    from thermal_model import installed_shade_calibrated_origin as origin
    assert hasattr(origin,'build_source_calibrated_capture'),'missing query-bound numeric capture'
    prepared,args=source_origin_case;record=origin.build_source_calibrated_capture(prepared,**args)
    assert record['schema']=='earthship-installed-shade-origin/v6'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v4'
    assert record['output']['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert record['output']['status']=='shadow' and record['output']['release_authorized'] is False
    assert record['output']['automatic_actuation'] is False
    path=origin.write_source_calibrated_capture(tmp_path,record)
    assert path.name==record['capture_sha256']+'.installed-shade-origin-v6.json'
    assert path.stat().st_mode&0o777==0o600
    assert origin.read_source_calibrated_capture(path)==record
    with pytest.raises(ValueError):origin.validate_raw_calibrated_capture(record)
    with pytest.raises(ValueError):origin.read_raw_calibrated_capture(path)


@pytest.mark.parametrize('damage',['missing_query','changed_grid','binding','deleted_after_write','initial'])
def test_source_origin_refuses_rehashed_or_missing_issue_sources(source_origin_case,tmp_path,damage):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    assert hasattr(origin,'build_source_calibrated_capture'),'missing query-bound numeric capture'
    prepared,args=source_origin_case
    if damage=='missing_query':
        args['native_source_paths'].pop('air')
        with pytest.raises(ValueError):origin.build_source_calibrated_capture(prepared,**args)
        return
    record=origin.build_source_calibrated_capture(prepared,**args)
    if damage=='deleted_after_write':
        path=origin.write_source_calibrated_capture(tmp_path,record);Path(args['native_source_paths']['air']).unlink()
        with pytest.raises((ValueError,OSError)):origin.read_source_calibrated_capture(path)
        return
    if damage=='changed_grid':record['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF']+=1
    elif damage=='initial':record['current']['mass']['value']+=1
    else:record['native_origin_binding']['release_authority']=True
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):origin.validate_source_calibrated_capture(record)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_source_origin_scoring_replays_queries_and_actual_issued_bands(source_origin_case,hours):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    assert hasattr(origin,'build_source_calibrated_capture'),'missing query-bound numeric capture'
    prepared,args=source_origin_case;record=origin.build_source_calibrated_capture(prepared,**args)
    issue=args['issued_at'];target=issue+timedelta(hours=hours)
    values=dict(publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),
        horizon_hours=hours,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    result=origin.score_source_calibrated_capture(record,**values)
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v6'
    assert result['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert result['original_capture_sha256']==record['capture_sha256']
    assert result['publication_sha256']==_digest(values['publication'])
    assert result['scored_pair']['interval_width_f']==pytest.approx(64.)
    Path(args['native_source_paths']['mass']).unlink()
    with pytest.raises((ValueError,OSError)):origin.score_source_calibrated_capture(record,**values)


@pytest.mark.parametrize('operation',['validation','scoring'])
def test_source_origin_rechecks_queries_after_numerical_work(source_origin_case,monkeypatch,operation):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    prepared,args=source_origin_case;record=origin.build_source_calibrated_capture(prepared,**args)
    original=origin._core_view;calls=0
    def changed_source(value):
        nonlocal calls
        result=original(value);calls+=1
        if calls==(1 if operation=='validation' else 2):Path(args['native_source_paths']['air']).unlink()
        return result
    monkeypatch.setattr(origin,'_core_view',changed_source)
    with pytest.raises((ValueError,OSError)):
        if operation=='validation':origin.validate_source_calibrated_capture(record)
        else:
            issue=args['issued_at'];target=issue+timedelta(hours=1)
            origin.score_source_calibrated_capture(record,publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),
                horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
                recent_cycle_grid=synthetic_cycle_grid(issue,1),assessed_at=target+timedelta(minutes=10))


def test_source_origin_refuses_source_loss_during_temporary_write(source_origin_case,tmp_path,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model import runtime_bundle
    prepared,args=source_origin_case;record=origin.build_source_calibrated_capture(prepared,**args)
    original=runtime_bundle._write_private
    def changed_source(path,raw):
        original(path,raw)
        Path(args['native_source_paths']['outdoor']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed_source)
    with pytest.raises((ValueError,OSError)):origin.write_source_calibrated_capture(tmp_path,record)
    assert not list(tmp_path.glob('*.installed-shade-origin-v6.json'))
    assert not list(tmp_path.glob('.calibration-*'))


def source_base_args(source_origin_case):
    from thermal_model import installed_shade_origin as base
    prepared,args=source_origin_case;artifact=deepcopy(json.loads(prepared.artifact_json)['base_candidate'])
    artifact['runtime_revision']=_digest(args['runtime'])
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    return base.PreparedCandidate(_canonical(artifact),args['issued_at']),args


def test_source_base_has_explicit_query_bound_shadow_contract(source_origin_case,tmp_path):
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_source_issued_capture'),'missing query-bound base issuance'
    prepared,args=source_base_args(source_origin_case);record=base.build_source_issued_capture(prepared,**args)
    assert record['schema']=='earthship-installed-shade-origin/v8'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v5'
    assert record['output']['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert record['output']['status']=='shadow' and record['output']['prediction_intervals'] is None
    assert record['output']['release_authorized'] is False and record['output']['automatic_actuation'] is False
    path=base.write_source_issued_capture(tmp_path,record)
    assert path.name==record['capture_sha256']+'.installed-shade-origin-v8.json'
    assert base.read_source_issued_capture(path)==record
    with pytest.raises(ValueError):base.validate_issued_capture(record)
    with pytest.raises(ValueError):base.read_issued_capture(path)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_source_base_scores_actual_query_bound_numeric_receipt(source_origin_case,hours):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_source_issued_capture'),'missing query-bound base issuance'
    prepared,args=source_base_args(source_origin_case);record=base.build_source_issued_capture(prepared,**args)
    issue=args['issued_at'];target=issue+timedelta(hours=hours)
    values=dict(publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    score=base.score_source_issued_capture(record,**values)
    assert score['schema']=='earthship-installed-shade-source-scored-pair/v8'
    assert score['original_capture_sha256']==record['capture_sha256'] and score['publication_sha256']==_digest(values['publication'])
    assert score['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert score['scored_pair']['interval_width_f'] is None and score['release_authorized'] is False
    Path(args['native_source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):base.score_source_issued_capture(record,**values)


@pytest.mark.parametrize('damage',['initial','grid','binding','closure'])
def test_source_base_refuses_rehashed_source_or_observer_changes(source_origin_case,damage):
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_source_issued_capture'),'missing query-bound base issuance'
    prepared,args=source_base_args(source_origin_case);record=base.build_source_issued_capture(prepared,**args)
    if damage=='initial':record['current']['mass']['value']+=1
    elif damage=='grid':record['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF']+=1
    elif damage=='binding':record['native_origin_binding']['release_authority']=True
    else:
        record['runtime']['source_manifest'].pop('weather_temperature_sources.py')
        record['candidate']['runtime_revision']=_digest(record['runtime'])
        record['candidate']['artifact_sha256']=_digest({k:v for k,v in record['candidate'].items() if k!='artifact_sha256'})
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):base.validate_source_issued_capture(record)


@pytest.mark.parametrize('operation',['validation','scoring'])
def test_source_base_rechecks_retained_queries_after_numerical_work(source_origin_case,monkeypatch,operation):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base
    prepared,args=source_base_args(source_origin_case);record=base.build_source_issued_capture(prepared,**args)
    original=base._source_core;calls=0
    def changed(value):
        nonlocal calls
        result=original(value);calls+=1
        if calls==(1 if operation=='validation' else 2):Path(args['native_source_paths']['mass']).unlink()
        return result
    monkeypatch.setattr(base,'_source_core',changed)
    with pytest.raises((ValueError,OSError)):
        if operation=='validation':base.validate_source_issued_capture(record)
        else:
            issue=args['issued_at'];target=issue+timedelta(hours=1)
            base.score_source_issued_capture(record,publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),horizon_hours=1,
                outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),recent_cycle_grid=synthetic_cycle_grid(issue,1),assessed_at=target+timedelta(minutes=10))


def test_source_base_refuses_source_loss_during_temporary_write(source_origin_case,tmp_path,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base,runtime_bundle
    prepared,args=source_base_args(source_origin_case);record=base.build_source_issued_capture(prepared,**args)
    original=runtime_bundle._write_private
    def changed(path,raw):
        original(path,raw);Path(args['native_source_paths']['outdoor']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    with pytest.raises((ValueError,OSError)):base.write_source_issued_capture(tmp_path,record)
    assert not list(tmp_path.glob('*.installed-shade-origin-v8.json')) and not list(tmp_path.glob('.calibration-*'))


def compressed_base_args(source_origin_case):
    from pathlib import Path
    from weather_temperature_sources import read_temperature_source,write_compressed_temperature_source
    prepared,args=source_base_args(source_origin_case);args=deepcopy(args)
    args['native_source_paths']={role:str(write_compressed_temperature_source(Path(name).parent,
        read_temperature_source(Path(name).parent,Path(name)))) for role,name in args['native_source_paths'].items()}
    return prepared,args


def test_compressed_base_capture_is_distinct_and_roundtrips_original_queries(source_origin_case,tmp_path):
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_compressed_source_issued_capture'),'missing compressed numeric capture'
    prepared,args=compressed_base_args(source_origin_case);record=base.build_compressed_source_issued_capture(prepared,**args)
    assert record['schema']=='earthship-installed-shade-origin/v10'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v6'
    assert record['native_origin_binding']['schema']=='earthship-installed-shade-native-origin-binding/v2'
    assert record['output']['status']=='shadow' and record['output']['release_authorized'] is False
    path=base.write_compressed_source_issued_capture(tmp_path,record)
    assert path.name==record['capture_sha256']+'.installed-shade-origin-v10.json'
    assert base.read_compressed_source_issued_capture(path)==record
    with pytest.raises(ValueError):base.validate_source_issued_capture(record)
    with pytest.raises(ValueError):base.read_source_issued_capture(path)
    with pytest.raises(ValueError):base.validate_issued_capture(record)


def test_compressed_base_scoring_binds_actual_numeric_receipt_and_original_queries(source_origin_case):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_compressed_source_issued_capture'),'missing compressed numeric capture'
    prepared,args=compressed_base_args(source_origin_case);record=base.build_compressed_source_issued_capture(prepared,**args)
    issue=args['issued_at'];target=issue+timedelta(hours=1)
    values=dict(publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),
        horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,1),assessed_at=target+timedelta(minutes=10))
    score=base.score_compressed_source_issued_capture(record,**values)
    assert score['schema']=='earthship-installed-shade-source-scored-pair/v10'
    assert score['original_capture_sha256']==record['capture_sha256']
    assert score['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert score['publication_sha256']==_digest(values['publication'])
    assert score['scored_pair']['interval_width_f'] is None and score['release_authorized'] is False
    Path(args['native_source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):base.score_compressed_source_issued_capture(record,**values)


def test_compressed_base_capture_rechecks_original_after_actual_temporary_write(source_origin_case,tmp_path,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base,runtime_bundle
    assert hasattr(base,'build_compressed_source_issued_capture'),'missing compressed numeric capture'
    prepared,args=compressed_base_args(source_origin_case);record=base.build_compressed_source_issued_capture(prepared,**args)
    original=runtime_bundle._write_private
    def changed(path,raw):
        original(path,raw);Path(args['native_source_paths']['outdoor']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    with pytest.raises((ValueError,OSError)):base.write_compressed_source_issued_capture(tmp_path,record)
    assert not list(tmp_path.glob('*.installed-shade-origin-v10.json'))
    assert not list(tmp_path.glob('.calibration-*'))


def test_compressed_base_capture_rechecks_original_after_numerical_work(source_origin_case,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_origin as base
    assert hasattr(base,'build_compressed_source_issued_capture'),'missing compressed numeric capture'
    prepared,args=compressed_base_args(source_origin_case);record=base.build_compressed_source_issued_capture(prepared,**args)
    original=base._source_core
    def changed(value):
        result=original(value);Path(args['native_source_paths']['mass']).unlink();return result
    monkeypatch.setattr(base,'_source_core',changed)
    with pytest.raises((ValueError,OSError)):base.validate_compressed_source_issued_capture(record)


@pytest.fixture
def compressed_calibrated_origin_case(source_origin_case):
    """Numerical fixture only: no complete calibration source/release claim."""
    from pathlib import Path
    from weather_temperature_sources import read_temperature_source,write_compressed_temperature_source
    from thermal_model import installed_shade_calibrated_origin as origin
    kind=getattr(origin,'PreparedCompressedCalibratedCandidate',None)
    prepared,args=source_origin_case
    if kind is None:return prepared,deepcopy(args)
    args=deepcopy(args);artifact=json.loads(prepared.artifact_json)
    artifact['schema']='earthship-installed-shade-candidate/v5'
    artifact['calibration'].update(schema='earthship-installed-shade-calibration/v4',source_contract='earthship-installed-shade-score-sources/v6')
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    args['native_source_paths']={role:str(write_compressed_temperature_source(Path(name).parent,
        read_temperature_source(Path(name).parent,Path(name)))) for role,name in args['native_source_paths'].items()}
    return kind(_canonical(artifact),args['issued_at']),args


def test_compressed_calibrated_numeric_capture_has_distinct_contract_and_readback(compressed_calibrated_origin_case,tmp_path):
    from thermal_model import installed_shade_calibrated_origin as origin
    api=getattr(origin,'build_compressed_source_calibrated_capture',None)
    assert callable(api),'missing compressed calibrated capture'
    prepared,args=compressed_calibrated_origin_case;record=api(prepared,**args)
    assert record['schema']=='earthship-installed-shade-origin/v12'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v7'
    assert record['native_origin_binding']['schema']=='earthship-installed-shade-native-origin-binding/v2'
    assert len(record['output']['prediction_intervals'])==4
    assert record['output']['status']=='shadow' and record['output']['release_authorized'] is False
    path=origin.write_compressed_source_calibrated_capture(tmp_path,record)
    assert origin.read_compressed_source_calibrated_capture(path)==record
    for reader in (origin.read_calibrated_capture,origin.read_raw_calibrated_capture,origin.read_source_calibrated_capture):
        with pytest.raises(ValueError):reader(path)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_compressed_calibrated_numeric_scoring_preserves_actual_intervals_and_originals(compressed_calibrated_origin_case,hours):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    prepared,args=compressed_calibrated_origin_case;record=origin.build_compressed_source_calibrated_capture(prepared,**args)
    issue=args['issued_at'];target=issue+timedelta(hours=hours)
    values=dict(publication=dict(time=int(args['published_at'].timestamp()*1000),state=_canonical(record['output']).decode()),
        horizon_hours=hours,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    scored=origin.score_compressed_source_calibrated_capture(record,**values)
    assert scored['schema']=='earthship-installed-shade-source-scored-pair/v12'
    assert scored['native_origin_binding_sha256']==_digest(record['native_origin_binding'])
    assert scored['publication_sha256']==_digest(values['publication'])
    assert scored['scored_pair']['interval_width_f']==pytest.approx(64.)
    Path(args['native_source_paths']['mass']).unlink()
    with pytest.raises((ValueError,OSError)):origin.score_compressed_source_calibrated_capture(record,**values)


def test_compressed_calibrated_numeric_refuses_incomplete_bands_and_old_preparation(compressed_calibrated_origin_case):
    from thermal_model import installed_shade_calibrated_origin as origin
    prepared,args=compressed_calibrated_origin_case;artifact=json.loads(prepared.artifact_json)
    artifact['calibration']['bands']['24']['overall']=None
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    incomplete=origin.PreparedCompressedCalibratedCandidate(_canonical(artifact),prepared.validated_at)
    with pytest.raises(ValueError,match='support incomplete'):origin.build_compressed_source_calibrated_capture(incomplete,**args)
    old=origin.PreparedRawCalibratedCandidate(prepared.artifact_json,prepared.validated_at)
    with pytest.raises(ValueError):origin.build_compressed_source_calibrated_capture(old,**args)


def test_compressed_calibrated_numeric_refuses_original_lost_after_actual_temp_write(compressed_calibrated_origin_case,tmp_path,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin,runtime_bundle
    prepared,args=compressed_calibrated_origin_case;record=origin.build_compressed_source_calibrated_capture(prepared,**args)
    original=runtime_bundle._write_private;written=[]
    def changed(path,raw):
        original(path,raw);written.append(path);Path(args['native_source_paths']['air']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    with pytest.raises((ValueError,OSError)):origin.write_compressed_source_calibrated_capture(tmp_path,record)
    assert written and not list(tmp_path.glob('*.installed-shade-origin-v12.json'))
    assert not list(tmp_path.glob('.calibration-*'))


def test_compressed_calibrated_numeric_rechecks_originals_after_numerical_work(compressed_calibrated_origin_case,monkeypatch):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_origin as origin
    prepared,args=compressed_calibrated_origin_case;record=origin.build_compressed_source_calibrated_capture(prepared,**args)
    original=origin._core_view
    def changed(value):
        result=original(value);Path(args['native_source_paths']['outdoor']).unlink();return result
    monkeypatch.setattr(origin,'_core_view',changed)
    with pytest.raises((ValueError,OSError)):origin.validate_compressed_source_calibrated_capture(record)


def test_compressed_preparation_bounds_original_index_before_copying_or_validating(monkeypatch):
    from thermal_model import installed_shade_calibrated_origin as origin
    api=getattr(origin,'prepare_compressed_source_calibrated_candidate',None)
    assert callable(api),'missing original-source compressed candidate preparation'
    parameters=dict(base_bundle={},inputs={},calibration={},original_pairs=[dict(raw_score_sources_path='/'+'x'*1024)],
        expected_runtime_revision='1'*64,assessed_at='2026-10-08T00:00:00+00:00')
    monkeypatch.setattr(origin,'deepcopy',lambda *a,**kw:pytest.fail('unbounded compressed preparation reached copy'))
    with pytest.raises(ValueError):api({},**parameters)
