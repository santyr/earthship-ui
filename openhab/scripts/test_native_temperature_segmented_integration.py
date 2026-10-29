"""Small synthetic source-bound successor integrations; no private observations."""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_native_thermal_forecast import context, originals, ISSUE
from test_installed_shade_inputs import EPOCHS
from thermal_model.forcing_capture import _canonical
from thermal_model.temperature_history import STREAMS, POLICY
from weather_temperature_evidence import TemperaturePolicy
import weather_temperature_source_segments as segments


def binding_api():
    assert importlib.util.find_spec('weather_temperature_segmented_binding') is not None, \
        'missing complete shared-source origin binding'
    return importlib.import_module('weather_temperature_segmented_binding')


def retained_inputs(root, inputs, monkeypatch):
    """Existing independent collector fixture supplies approved complete originals."""
    import test_thermal_sensor_epoch_origins as old
    from thermal_temperature_runtime import shadow_temperatures_v2
    from weather_temperature_reader import select_temperature_grid_v2
    rows_saved = []
    def reader(rows, **kwargs):
        if not rows_saved:
            rows_saved.extend(rows)
        return select_temperature_grid_v2(rows, **kwargs)
    saved = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old, 'NOW', ISSUE)
        patch.setattr(old, 'select_temperature_grid_v2', reader)
        selected = shadow_temperatures_v2(ISSUE, old.native_grid(), sensor_epochs=EPOCHS,
                                         origin_observer=saved.append)
    targets = [row[0] for row in saved[0]['roles']['air']['grid']]
    contexts = {role: dict(stream=stream, policy=TemperaturePolicy(model, sensor, **POLICY),
                           sensor_epoch=EPOCHS[role])
                for role, (stream, model, sensor) in STREAMS.items()}
    root.mkdir(mode=0o700)
    source = segments.build_shared_temperature_source(rows=rows_saved, targets=targets,
        assessed_at=ISSUE, contexts=contexts)
    path = segments.write_shared_temperature_source(root, source)
    # Three small independently encoded children exercise every inventory edge
    # without using dense multi-MiB or resource-exhaustion fixtures here.
    from test_weather_temperature_source_segments import documents,rewrite_segments
    manifest,parts=documents(root,path);part=parts[0];rows=part['native_rows']
    path=rewrite_segments(root,manifest,[dict(part,native_rows=rows[:96]),
        dict(part,native_rows=rows[96:192]),dict(part,native_rows=rows[192:])])
    inputs.update(current={role: row['current'] for role, row in selected.items()},
                  origin_temperatures=saved[0], native_source_paths={role: str(path) for role in STREAMS})
    return path


def test_shared_binding_replays_exact_all_role_grids_and_inventory(tmp_path, monkeypatch):
    inputs = {};path = retained_inputs(tmp_path/'query', inputs, monkeypatch)
    api = binding_api()
    value = api.build_segmented_native_origin_binding(inputs['origin_temperatures'],
        source_paths=inputs['native_source_paths'], issue_at=ISSUE)
    assert value['schema'] == 'earthship-installed-shade-native-origin-binding/v3'
    assert value['release_authority'] is False
    assert api.replay_segmented_native_origin_binding(value, inputs['origin_temperatures'], issue_at=ISSUE) == value
    expected = segments.shared_temperature_source_files(segments.read_shared_temperature_source(path.parent, path))
    assert api.segmented_native_origin_files(value) == expected
    from thermal_model.installed_shade_raw_score_sources import replay_compressed_native_origin_binding
    with pytest.raises(ValueError):
        replay_compressed_native_origin_binding(value, inputs['origin_temperatures'], issue_at=ISSUE)


@pytest.mark.parametrize('damage', ['grid', 'phase', 'role', 'policy', 'assessed', 'split_path'])
def test_shared_binding_refuses_detached_role_context(tmp_path, monkeypatch, damage):
    inputs = {};path = retained_inputs(tmp_path/'query', inputs, monkeypatch)
    api = binding_api()
    if damage == 'grid': inputs['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF'] += 1
    elif damage == 'phase': inputs['origin_temperatures']['roles']['mass']['identity']['sensor_epoch'] = EPOCHS['air']
    elif damage == 'role': inputs['native_source_paths'].pop('outdoor')
    elif damage == 'policy': inputs['origin_temperatures']['roles']['air']['identity']['sensor_id'] = True
    elif damage == 'assessed': inputs['origin_temperatures']['assessed_at'] = ISSUE + timedelta(seconds=1)
    else: inputs['native_source_paths']['mass'] = str(path.parent/'elsewhere.json')
    with pytest.raises((ValueError, OSError)):
        api.build_segmented_native_origin_binding(inputs['origin_temperatures'],
            source_paths=inputs['native_source_paths'], issue_at=ISSUE)


def new_capture(tmp_path, monkeypatch, originals):
    import native_thermal_forecast as forecasts
    import native_thermal_artifact as artifacts
    c, inputs, kwargs = context(tmp_path, monkeypatch, originals)
    runtime=deepcopy(kwargs['runtime'])
    runtime['native_source_manifest']['openhab/scripts/native_thermal_forecast.py']=sha256(Path(forecasts.__file__).read_bytes()).hexdigest()
    runtime['native_source_manifest']['openhab/scripts/native_thermal_score.py']=sha256(Path(forecasts.__file__).with_name('native_thermal_score.py').read_bytes()).hexdigest()
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    c=artifacts.build_native_candidate(originals={role:Path(ref['path']) for role,ref in c['originals'].items()},
        runtime=runtime,created_at=c['created_at'])
    kwargs.update(runtime=runtime,expected_artifact_sha256=c['artifact_sha256'])
    retained_inputs(tmp_path/'query', inputs, monkeypatch)
    value = forecasts.build_capture(c, inputs, source_profile='segmented-v1', **kwargs)
    return value, kwargs


def test_old_runtime_cannot_select_new_explicit_source_profile(tmp_path, monkeypatch, originals):
    import native_thermal_forecast as forecasts
    c, inputs, kwargs = context(tmp_path, monkeypatch, originals)
    retained_inputs(tmp_path/'query',inputs,monkeypatch)
    with pytest.raises(ValueError):forecasts.build_capture(c,inputs,source_profile='segmented-v1',**kwargs)


def test_conditioned_successor_keeps_same_numeric_output_and_prepared_distinction(tmp_path,monkeypatch,originals):
    import native_thermal_forecast as forecasts
    import native_thermal_artifact as artifacts
    import test_thermal_weather_conditioning as conditioning
    from thermal_weather_source import collect_context
    from household.weather_context import prepare_native_cycle_contexts
    from household.thermal_model import project
    value,kwargs=new_capture(tmp_path,monkeypatch,originals)
    monkeypatch.setattr(conditioning,'ISSUE',ISSUE)
    args,_=conditioning.bound_fixture(tmp_path/'weather',monkeypatch,forecast=value['inputs']['forecast'],
        geometry=kwargs['geometry'],sensor_epoch=value['candidate']['fit']['sensor_epochs']['outdoor'])
    proof=collect_context(**args)
    new=forecasts.build_capture(value['candidate'],value['inputs'],source_profile='segmented-v1',weather_conditioning=proof,**kwargs)
    old=forecasts.build_capture(value['candidate'],value['inputs'],weather_conditioning=proof,**kwargs)
    assert new['schema']=='earthship-provisional-thermal-origin/v5' and old['schema']=='earthship-provisional-thermal-origin/v3'
    assert new['output']==old['output']
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kw:deepcopy(kwargs['runtime']))
    thermal,weather=prepare_native_cycle_contexts(new,code_revision='a'*40,runtime=kwargs['runtime'],
        expected_artifact_sha256=kwargs['expected_artifact_sha256'],expected_capture_sha256=new['capture_sha256'])
    assert thermal.to_dict()['schema']=='earthship-household-prepared-thermal/v3'
    assert weather.original_capture==new and project(thermal)['output']==new['output']


def test_explicit_successor_capture_roundtrip_and_child_deletion(tmp_path, monkeypatch, originals):
    import native_thermal_forecast as forecasts
    value, kwargs = new_capture(tmp_path, monkeypatch, originals)
    assert value['schema'] == 'earthship-provisional-thermal-origin/v4'
    pins = dict(runtime=kwargs['runtime'], expected_artifact_sha256=kwargs['expected_artifact_sha256'],
                expected_capture_sha256=value['capture_sha256'])
    path = forecasts.persist(tmp_path, value)
    assert path.name == value['capture_sha256'] + '.native-provisional-origin-v4.json'
    assert forecasts.read_capture(path, **pins) == value
    files = forecasts.origin_source_files(value)
    assert len(files)==4
    files[-1].unlink()
    with pytest.raises((ValueError, OSError)): forecasts.read_capture(path, **pins)


def test_successor_cycle_retains_child_custody_after_replay(tmp_path, monkeypatch, originals):
    import native_thermal_forecast as forecasts
    import household_cycle as cycle
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM, PUBLICATION_ITEM
    value, kwargs = new_capture(tmp_path, monkeypatch, originals)
    origin = forecasts.persist(tmp_path, value)
    receipts = {name: dict(item=name, time=int((ISSUE+timedelta(seconds=3+n)).timestamp()*1000), state=json.dumps(body))
        for n, (name, body) in enumerate(((NUMERIC_ITEM,value['output']), (PUBLICATION_ITEM,forecasts.publication(value))))}
    delivery = dict(schema='earthship-provisional-thermal-delivery/v2', issued_at=ISSUE.isoformat(),
        capture_path=str(origin),capture_sha256=value['capture_sha256'],artifact_sha256=kwargs['expected_artifact_sha256'],
        runtime_sha256=value['candidate']['runtime_sha256'],geometry_series_sha256=value['geometry_series_sha256'],receipts=receipts)
    delivery['delivery_sha256']=forecasts.digest(delivery,'delivery_sha256')
    path=tmp_path/(delivery['delivery_sha256']+'.native-provisional-delivery-v2.json')
    path.write_bytes(_canonical(delivery));path.chmod(0o600)
    archive=cycle.load_cycle_delivery(dict(status='published',delivery_verified=True,origin_path=str(origin),delivery_path=str(path)),
        issue=ISSUE,guard=lambda:None,runtime=kwargs['runtime'],expected_artifact_sha256=kwargs['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])
    child=forecasts.origin_source_files(value)[-1];raw=child.read_bytes();child.unlink();child.write_bytes(raw);child.chmod(0o600)
    with pytest.raises((ValueError,OSError)): archive['verify_unchanged']()


def test_successor_versions_are_closed_and_conditioning_is_distinct():
    import native_thermal_forecast as forecasts
    assert forecasts.capture_fields({'schema':'earthship-provisional-thermal-origin/v4'}) == forecasts.CAPTURE_FIELDS
    assert forecasts.capture_fields({'schema':'earthship-provisional-thermal-origin/v5'}) == forecasts.CAPTURE_FIELDS|{'weather_conditioning'}
    with pytest.raises(ValueError):forecasts.capture_fields({'schema':'earthship-provisional-thermal-origin/v6'})


def test_successor_backend_uses_one_snapshot_and_keeps_every_child(tmp_path, monkeypatch):
    assert importlib.util.find_spec('weather_learning.native_segmented_backend') is not None, \
        'missing explicitly selected shared native backend'
    from weather_learning.native_segmented_backend import make_segmented_native_backend, SCHEMA
    from weather_learning.tests.learning_fixtures import SITE
    from test_thermal_sensor_epoch_history import sources
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT
    from weather_temperature_reader import select_temperature_grid_v2
    from thermal_model.installed_shade_live_inputs import SOURCE_PATHS
    from weather_temperature_config import load_temperature_receiver_configuration
    import hourly_temperature_runtime
    policy, rows = sources(tmp_path, monkeypatch)
    config = dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic-test-only')
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _:config)
    settings = dict(schema=SCHEMA,openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(tmp_path))
    for name in SOURCE_PATHS:
        if name == 'native_policy':settings[name]=str(policy);continue
        path=tmp_path/name
        path.write_text('host=127.0.0.1 dbname=openhab user=fixture_reader password=synthetic' if name=='journal_dsn_file' else '{}')
        path.chmod(0o600);settings[name]=str(path)
    backend=make_segmented_native_backend(settings,archive=None,site=SITE,shared_lock_guard=lambda:None)
    connections=[]
    def connect(_):
        connection=Connection(rows=rows);connections.append(connection);return connection
    monkeypatch.setattr(backend,'_connect',connect)
    targets=[AT,AT+timedelta(minutes=5)];assessed=targets[-1]
    policies,epochs=load_temperature_receiver_configuration(str(policy))
    for role,(stream,_,_) in STREAMS.items():
        selected=backend._temperature_grid(stream,targets,assessed)
        expected=select_temperature_grid_v2(rows,targets=targets,assessed_at=assessed,
            history_start=targets[0]-timedelta(seconds=120),stream=stream,policy=policies[stream],sensor_epoch=epochs[stream])
        assert selected==expected
    assert len(connections)==1 and connections[0].closed
    assert connections[0].session==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    assert len(set(backend._native_source_paths.values()))==1
    manifest=Path(backend._native_source_paths['air'])
    child=segments.shared_temperature_source_files(segments.read_shared_temperature_source(tmp_path,manifest))[-1]
    backend.verify_unchanged();child.unlink()
    with pytest.raises((ValueError,OSError)):backend.verify_unchanged()


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_successor_source_score_keeps_original_endpoint_contract_and_equations(tmp_path,monkeypatch,originals,hours):
    import native_thermal_forecast as forecasts
    import native_thermal_score as scores
    import test_native_thermal_score_sources as endpoint_fixture
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    value,kwargs=new_capture(tmp_path,monkeypatch,originals)
    receipts={name:dict(item=name,time=int((ISSUE+timedelta(seconds=3+n)).timestamp()*1000),state=json.dumps(body))
        for n,(name,body) in enumerate(((NUMERIC_ITEM,value['output']),(PUBLICATION_ITEM,forecasts.publication(value))))}
    pins=dict(runtime=kwargs['runtime'],expected_artifact_sha256=kwargs['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])
    monkeypatch.setattr(endpoint_fixture,'issued',lambda *a:(value,receipts,pins))
    args=endpoint_fixture.queried(tmp_path,monkeypatch,originals,hours=hours)
    record=scores.build_source_score(**args)
    assert record['query_binding']['schema']=='earthship-native-thermal-score-query-binding/v1'
    assert record['pair']['errors']['model']==value['output']['trajectory'][hours-1]['air_f']-75
    assert record['pair']['errors']['persistence']==-1
    assert scores.validate_source_score(record,**pins,expected_source_score_sha256=record['source_score_sha256'])==record
    real_score=scores.score
    def replace_after_replay(*a,**kw):
        result=real_score(*a,**kw)
        child=forecasts.origin_source_files(value)[2]
        raw=child.read_bytes();child.unlink();child.write_bytes(raw);child.chmod(0o600)
        return result
    monkeypatch.setattr(scores,'score',replace_after_replay)
    with pytest.raises((ValueError,OSError)):scores.build_source_score(**args)


@pytest.mark.parametrize('version,accepted',[(4,False),(5,True)])
def test_successor_correction_bootstrap_keeps_conditioned_population(tmp_path,version,accepted):
    from weather_learning.correction_monitor import retain_native_delivery_reference
    from test_weather_correction_monitor import state
    from weather_learning.contracts import identity
    original=dict(schema='earthship-provisional-thermal-origin/v'+str(version))
    original['capture_sha256']=identity(original)
    capture=tmp_path/(original['capture_sha256']+'.native-provisional-origin-v'+str(version)+'.json')
    capture.write_bytes(_canonical(original));capture.chmod(0o600)
    header=dict(schema='earthship-provisional-thermal-delivery/v2',capture_path=str(capture),capture_sha256=original['capture_sha256'],issued_at=ISSUE.isoformat())
    header['delivery_sha256']=identity(header)
    path=tmp_path/(header['delivery_sha256']+'.native-provisional-delivery-v2.json');path.write_bytes(_canonical(header));path.chmod(0o600)
    result=retain_native_delivery_reference(state(tmp_path),path,indexed_at=ISSUE+timedelta(days=1),origin='historical_header_bootstrap')
    assert (result==header['delivery_sha256']) if accepted else result is None


def test_serving_report_reuse_keeps_every_shared_child_in_final_inventory(tmp_path,monkeypatch,originals):
    binding_api()
    import native_thermal_forecast as forecasts
    import test_native_serving_score as serving_fixture
    from test_native_serving_forecast import context as serving_context
    from test_household_score_report_reuse import report_fixture
    from household_forecast_score import production_score_policy
    values=list(serving_context(tmp_path,originals,monkeypatch))
    retained_inputs(tmp_path/'shared-query',values[4],monkeypatch)
    values[5]=dict(values[5],source_profile='segmented-v1')
    values[6]=values[4]['native_source_paths']
    monkeypatch.setattr(serving_fixture,'context',lambda *a,**kw:tuple(values))
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    capture=json.loads(Path(args['capture_path']).read_bytes())
    assert capture['schema']=='earthship-provisional-thermal-origin/v4'
    with production_score_policy():
        assert scores.reconcile_serving_source_report(entries,**kwargs)==expected
    assert len(calls)==1
    calls.clear();child=forecasts.origin_source_files(capture)[2];raw=child.read_bytes();mutated=[]
    def guard():
        if calls and not mutated:
            child.unlink();child.write_bytes(raw);child.chmod(0o600);mutated.append(True)
    with pytest.raises((ValueError,OSError)):
        with production_score_policy():scores.reconcile_serving_source_report(entries,check_budget=guard,**kwargs)
    assert mutated


def test_resealed_successor_cannot_detach_input_paths_from_original_binding(tmp_path,monkeypatch,originals):
    import native_thermal_forecast as forecasts
    value,kwargs=new_capture(tmp_path,monkeypatch,originals)
    value['inputs']['native_source_paths']['mass']=str(tmp_path/'unrelated.native-temperature-shared-v1.json')
    value['capture_sha256']=forecasts.digest(value,'capture_sha256')
    with pytest.raises(ValueError):
        forecasts.validate_capture(value,runtime=kwargs['runtime'],
            expected_artifact_sha256=kwargs['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])


def test_approved_float_policy_bounds_keep_actual_context_and_strict_identities(tmp_path,monkeypatch):
    from astro_geometry import _instant
    from test_weather_temperature_source_segments import documents
    from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source
    from thermal_model.installed_shade_raw_score_sources import build_compressed_native_origin_binding
    inputs={};path=retained_inputs(tmp_path/'integers',inputs,monkeypatch)
    manifest,parts=documents(path.parent,path)
    rows=[(_instant(at),raw) for part in parts for at,raw in part['native_rows']]
    targets=list(map(_instant,manifest['context']['targets']))
    contexts={role:dict(stream=stream,policy=TemperaturePolicy(model,sensor,float(POLICY['minimum_f']),
        float(POLICY['maximum_f']),POLICY['validity_seconds']),sensor_epoch=EPOCHS[role])
        for role,(stream,model,sensor) in STREAMS.items()}
    root=tmp_path/'floats';root.mkdir(mode=0o700)
    legacy_paths={}
    for role,context in contexts.items():
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=ISSUE,**context)
        legacy_paths[role]=str(write_compressed_temperature_source(root,packet))
    # The unchanged historical binding independently admits these exact policies.
    old=build_compressed_native_origin_binding(inputs['origin_temperatures'],source_paths=legacy_paths,issue_at=ISSUE)
    assert old['release_authority'] is False
    source=segments.build_shared_temperature_source(rows=rows,targets=targets,assessed_at=ISSUE,contexts=contexts)
    shared=segments.write_shared_temperature_source(root,source)
    paths={role:str(shared) for role in STREAMS};api=binding_api()
    value=api.build_segmented_native_origin_binding(inputs['origin_temperatures'],source_paths=paths,issue_at=ISSUE)
    assert value['source_manifest_sha256']==sha256(source.manifest_bytes).hexdigest()
    assert value['context_sha256']==json.loads(source.manifest_bytes)['context_sha256']
    assert b'"minimum_f":-40.0' in source.manifest_bytes and shared.read_bytes()==source.manifest_bytes
    assert api.replay_segmented_native_origin_binding(value,inputs['origin_temperatures'],issue_at=ISSUE)==value
    for sensor in (True,float(STREAMS['air'][2])):
        damaged=deepcopy(inputs['origin_temperatures']);damaged['roles']['air']['identity']['sensor_id']=sensor
        with pytest.raises(ValueError):api.build_segmented_native_origin_binding(damaged,source_paths=paths,issue_at=ISSUE)
    for field,invalid in (('release_authority',0),('schema',True),('context_sha256','0'*64)):
        damaged=deepcopy(value);damaged[field]=invalid
        with pytest.raises(ValueError):api.replay_segmented_native_origin_binding(damaged,inputs['origin_temperatures'],issue_at=ISSUE)
