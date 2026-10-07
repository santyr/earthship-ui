"""Origin evidence must retain original native identity without changing inputs."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone

import pytest

from thermal_temperature_runtime import shadow_temperatures

NOW=datetime(2026,8,13,12,tzinfo=timezone.utc)
EPOCH='864142d5-99ee-4b7a-b5fc-e6a96e7274d8'
VALUES={'indoor':74,'north_wall':72,'outdoor':50}


def grid(stream,targets,assessed):
    assert assessed==NOW
    return [(at,dict(temperatureF=VALUES[stream],receivedAt=at-timedelta(seconds=30),
        storedAt=at-timedelta(seconds=20),validUntil=at+timedelta(seconds=90),
        streamEpoch=EPOCH,snapshotSha256='a'*64)) for at in targets]


def test_origin_observer_preserves_native_grid_and_leaves_values_unchanged():
    saved=[]
    plain=shadow_temperatures(NOW,grid)
    observed=shadow_temperatures(NOW,grid,origin_observer=saved.append)
    assert observed==plain
    assert len(saved)==1
    assert saved[0]['schema']=='earthship-thermal-origin-temperatures/v1'
    assert saved[0]['assessed_at']==NOW
    assert set(saved[0]['roles'])=={'air','mass','outdoor'}
    assert saved[0]['roles']['air']['identity']==dict(stream='indoor',model='Fineoffset-WH32B',sensor_id=235)
    assert saved[0]['roles']['air']['grid'][-1][1]['streamEpoch']==EPOCH
    assert saved[0]['roles']['air']['grid'][-1][1]['snapshotSha256']=='a'*64
    assert set(observed['air'])=={'history','current'}
    assert set(observed['air']['current'])=={'at','value','validUntil'}


def test_origin_observer_gets_no_partial_proof_on_unqualified_final_role():
    saved=[]
    def missing(stream,targets,assessed):
        rows=grid(stream,targets,assessed)
        if stream=='outdoor':rows[-1]=(rows[-1][0],None)
        return rows
    with pytest.raises(ValueError,match='unqualified current'):
        shadow_temperatures(NOW,missing,origin_observer=saved.append)
    assert saved==[]


def test_observer_cannot_rewrite_the_selected_numeric_input():
    def mutate(proof):proof['roles']['air']['grid'][-1][1]['temperatureF']=99
    result=shadow_temperatures(NOW,grid,origin_observer=mutate)
    assert result['air']['current']['value']==74


def capture_inputs():
    from test_thermal_artifacts import valid_artifact
    from test_thermal_schema import valid_shadow_payload
    saved=[]; selected=shadow_temperatures(NOW,grid,origin_observer=saved.append)
    artifact=valid_artifact();output=valid_shadow_payload()
    output['model']=dict(codeRevision=artifact.code_revision,
        createdAt=artifact.created_at,trainedThrough=artifact.trained_through)
    output['provenance']['currentAgeMinutes'].update(air=.5,mass=.5,outdoor=.5)
    current={role:entry['current'] for role,entry in selected.items()}
    runtime=dict(schema='earthship-thermal-runtime-binding/v1',code_revision='f'*64,
        observer_revision='e'*64,interpreter_sha256='d'*64,python_version='3.12.0',
        dependencies={'numpy':'2.0.0','scipy':'1.15.1','psycopg2':'2.9.10'},
        source_manifest={'thermal_intel.py':'c'*64,'thermal_model/origin_capture.py':'e'*64})
    return dict(output=output,artifact=artifact,snapshot={'fixture_weather':True},
        rows=[{'at':NOW,'tempF':50,'mode':'warm'}],current=current,
        origin_temperatures=saved[0],runtime=runtime,known_actions=None,
        inputs_available_at=NOW,published_at=NOW+timedelta(seconds=2))


def test_new_capture_binds_native_epochs_runtime_and_original_input_digests():
    from thermal_model.origin_capture import build_origin_capture,validate_origin_capture
    record=build_origin_capture(**capture_inputs())
    validate_origin_capture(record)
    assert record['schema']=='earthship-thermal-origin-capture/v1'
    assert record['source_epochs']=={'air':EPOCH,'mass':EPOCH,'outdoor':EPOCH}
    assert record['runtime']['code_revision']=='f'*64
    assert record['artifact']['code_revision']!=record['runtime']['code_revision']
    assert record['known_actions'] is None
    assert record['output']['status']=='shadow'
    assert set(record['sha256'])=={'output','artifact','raw_forecast','forecast_rows',
        'current','origin_temperatures','runtime','known_actions','source_epochs'}


@pytest.mark.parametrize('damage',['epoch','future_receipt','source_identity','initial_air',
    'initial_mass','runtime','future_inputs','expired','partial_grid'])
def test_origin_capture_refuses_unbound_or_changed_initial_inputs(damage):
    from thermal_model.origin_capture import build_origin_capture
    data=capture_inputs()
    if damage=='epoch':data['origin_temperatures']['roles']['air']['grid'][-1][1]['streamEpoch']='unbound'
    elif damage=='future_receipt':data['origin_temperatures']['roles']['air']['grid'][-1][1]['storedAt']=NOW+timedelta(seconds=1)
    elif damage=='source_identity':data['origin_temperatures']['roles']['air']['identity']['sensor_id']=193
    elif damage=='initial_air':data['current']['air']['value']=99
    elif damage=='initial_mass':data['current']['mass']['value']=99
    elif damage=='runtime':data['runtime']['code_revision']='short'
    elif damage=='future_inputs':data['inputs_available_at']=NOW+timedelta(seconds=1)
    elif damage=='expired':data['published_at']=NOW+timedelta(minutes=3)
    elif damage=='partial_grid':data['origin_temperatures']['roles']['mass']['grid'].pop(3)
    with pytest.raises(ValueError):build_origin_capture(**data)


def test_origin_capture_validates_internal_digests_after_outer_rehash():
    from thermal_model.origin_capture import build_origin_capture,validate_origin_capture
    record=build_origin_capture(**capture_inputs())
    record['raw_forecast']['fixture_weather']=False
    with pytest.raises(ValueError,match='digest'):validate_origin_capture(record)


def test_current_state_assembler_retains_origin_proof_without_public_metadata(monkeypatch):
    import thermal_intel
    import thermal_temperature_runtime as runtime
    from thermal_model.schema import THERMAL_ITEMS
    saved=[]
    monkeypatch.setenv('THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE','1')
    monkeypatch.delenv('THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE',raising=False)
    monkeypatch.setattr(runtime,'_configured_grid_reader',lambda env,budget:grid)
    def state(item):
        return dict(name=item,state='60',lastStateUpdate=(NOW-timedelta(seconds=30)).timestamp()*1000)
    current=thermal_intel._current_states(NOW,series_reader=lambda *_:[],
        state_reader=state,origin_observer=saved.append)
    assert len(saved)==1
    assert current['air']['value']==74 and current['mass']['value']==72
    assert set(current)=={'air','mass','glazing','outdoor','radiation','observed'}
    assert set(current['air'])=={'at','value','validUntil'}


def test_private_origin_capture_roundtrip_is_immutable_and_old_reader_refuses(tmp_path):
    from thermal_model.origin_capture import build_origin_capture,write_origin_capture,read_origin_capture
    from thermal_model.forcing_capture import verify_capture
    tmp_path.chmod(0o700)
    data=capture_inputs();record=build_origin_capture(**data)
    path=write_origin_capture(tmp_path,record)
    assert read_origin_capture(path)==record
    assert path.stat().st_mode & 0o777==0o600
    assert path.parent.stat().st_mode & 0o777==0o700
    assert write_origin_capture(tmp_path,record)==path
    with pytest.raises(ValueError,match='schema'):verify_capture(path)
    changed=deepcopy(data);changed['snapshot']['fixture_weather']=False
    with pytest.raises(ValueError,match='different'):
        write_origin_capture(tmp_path,build_origin_capture(**changed))
    assert read_origin_capture(path)==record


@pytest.mark.parametrize('damage',['root_mode','file_mode','symlink'])
def test_origin_archive_refuses_unowned_or_unsafe_storage(tmp_path,damage):
    from thermal_model.origin_capture import build_origin_capture,write_origin_capture,read_origin_capture
    tmp_path.chmod(0o700);record=build_origin_capture(**capture_inputs())
    if damage=='root_mode':
        tmp_path.chmod(0o755)
        with pytest.raises(ValueError):write_origin_capture(tmp_path,record)
        return
    path=write_origin_capture(tmp_path,record)
    if damage=='file_mode':path.chmod(0o644)
    else:
        alias=path.parent/'alias.json.gz';alias.symlink_to(path);path=alias
    with pytest.raises(ValueError):read_origin_capture(path)


def runtime_tree(tmp_path,monkeypatch):
    import shutil,sys
    from pathlib import Path
    root=tmp_path/'runtime';root.mkdir(mode=0o700)
    (root/'thermal_model').mkdir(mode=0o700)
    (root/'thermal_intel.py').write_bytes(b'# fixture publication core\n')
    (root/'thermal_intel.py').chmod(0o600)
    observer=root/'thermal_model/origin_capture.py';observer.write_bytes(b'# fixture observer\n');observer.chmod(0o600)
    executable=tmp_path/'qualified-python';shutil.copyfile(Path(sys.executable).resolve(),executable);executable.chmod(0o700)
    monkeypatch.setattr(sys,'executable',str(executable))
    return root,executable


def test_runtime_binding_hashes_actual_source_closure_and_executable(tmp_path,monkeypatch):
    from hashlib import sha256
    import sys
    from thermal_model.origin_capture import build_runtime_binding
    root,executable=runtime_tree(tmp_path,monkeypatch)
    binding=build_runtime_binding(root,('thermal_intel.py',))
    name=b'thermal_intel.py';body=b'# fixture publication core\n'
    expected=sha256(len(name).to_bytes(4,'big')+name+len(body).to_bytes(8,'big')+body).hexdigest()
    assert binding['code_revision']==expected
    assert binding['interpreter_sha256']==sha256(executable.read_bytes()).hexdigest()
    assert binding['observer_revision']==sha256(b'# fixture observer\n').hexdigest()
    assert binding['python_version']=='.'.join(map(str,sys.version_info[:3]))
    assert set(binding['dependencies'])=={'numpy','scipy','psycopg2'}
    (root/'thermal_intel.py').write_bytes(b'# changed source\n')
    assert build_runtime_binding(root,('thermal_intel.py',))['code_revision']!=expected


@pytest.mark.parametrize('problem',['missing','escape','config','writable_source','writable_executable','duplicate'])
def test_unqualified_runtime_closure_refuses_capture_binding(tmp_path,monkeypatch,problem):
    from thermal_model.origin_capture import build_runtime_binding
    root,executable=runtime_tree(tmp_path,monkeypatch)
    paths=('thermal_intel.py',)
    if problem=='missing':paths=('thermal_intel.py','missing.py')
    elif problem=='escape':paths=('thermal_intel.py','../outside.py')
    elif problem=='config':paths=('thermal_intel.py','private.json')
    elif problem=='writable_source':(root/'thermal_intel.py').chmod(0o666)
    elif problem=='writable_executable':executable.chmod(0o775)
    elif problem=='duplicate':paths=('thermal_intel.py','thermal_intel.py')
    with pytest.raises(ValueError):build_runtime_binding(root,paths)


def test_runtime_drift_during_binding_cannot_seal_a_mixed_source_closure(tmp_path,monkeypatch):
    import thermal_model.origin_capture as capture
    root,_=runtime_tree(tmp_path,monkeypatch)
    real=capture._source_bytes
    def changed(path,**kwargs):
        result=real(path,**kwargs)
        if path.name=='origin_capture.py':(root/'thermal_intel.py').write_bytes(b'# changed during capture\n')
        return result
    monkeypatch.setattr(capture,'_source_bytes',changed)
    with pytest.raises(ValueError,match='changed'):
        capture.build_runtime_binding(root,('thermal_intel.py',))


def test_native_origin_identity_requires_integer_sensor_id():
    from thermal_model.origin_capture import build_origin_capture
    data=capture_inputs();data['origin_temperatures']['roles']['air']['identity']['sensor_id']=235.0
    with pytest.raises(ValueError,match='identity'):build_origin_capture(**data)
