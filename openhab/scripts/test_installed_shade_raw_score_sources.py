"""Cached score receipts must match selection from retained raw query packets."""
from datetime import timedelta
import importlib
import pytest
from test_thermal_sensor_epoch_history import sources,EPOCHS
from test_weather_temperature_reader import AT
from weather_temperature_config import load_temperature_receiver_configuration
from weather_temperature_sources import build_temperature_source,write_temperature_source,replay_temperature_source
from thermal_model.forcing_capture import _canonical
import json


def module():
    assert importlib.util.find_spec('thermal_model.installed_shade_raw_score_sources') is not None,'missing raw score binding'
    return importlib.import_module('thermal_model.installed_shade_raw_score_sources')


def inputs(tmp_path,monkeypatch):
    policy_path,rows=sources(tmp_path,monkeypatch);policies,_=load_temperature_receiver_configuration(str(policy_path))
    tmp_path.chmod(0o700);issue=AT+timedelta(minutes=2);target=issue+timedelta(hours=1)
    # Shift unchanged whole snapshots and embedded original receipt clocks for
    # a later synthetic outcome, without copying a selected scalar receipt.
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_evidence import MODELS
    collector=TemperatureCollector({'indoor':policies['indoor']},sensor_epochs={'indoor':EPOCHS['air']},clock=lambda:target-timedelta(seconds=30),monotonic=lambda:1000,process_id=lambda:1)
    p=policies['indoor'];collector.observe({'model':p.model,'id':str(p.sensor_id),MODELS[p.model][1]:'73'})
    outcome_rows=[(target-timedelta(seconds=20),json.dumps(collector.snapshot()))]
    paths=[];grids=[]
    for raw,targets,assessed in [(rows[:1],[AT+timedelta(seconds=60)],issue),(outcome_rows,[target],target+timedelta(minutes=10))]:
        packet=build_temperature_source(rows=raw,targets=targets,assessed_at=assessed,stream='indoor',policy=p,sensor_epoch=EPOCHS['air'])
        paths.append(str(write_temperature_source(tmp_path,packet)));grids.append(json.loads(_canonical(replay_temperature_source(packet))))
    score=dict(origin_path='/fixture/origin',publication={'fixture':True},horizon_hours=1,outcome={'target_at':target.isoformat(),'receipt':grids[1][0][1]},recent_cycle_grid=grids[0])
    return dict(score_packet=score,source_paths=paths,issue_at=issue,sensor_epoch=EPOCHS['air'],assessed_at=target+timedelta(minutes=10))


def test_binding_replays_raw_sources_without_trusting_cached_receipts(tmp_path,monkeypatch):
    m=module();args=inputs(tmp_path,monkeypatch);binding=m.build_native_score_binding(**args)
    assert binding['release_authority'] is False
    assert m.replay_native_score_binding(binding,args['score_packet'],issue_at=args['issue_at'],sensor_epoch=args['sensor_epoch'],assessed_at=args['assessed_at'])==binding


@pytest.mark.parametrize('damage',['changed_outcome','changed_comparator','missing_query','duplicate_query','phase','future_assessment','deleted_source'])
def test_wrong_or_missing_raw_sources_refuse_binding(tmp_path,monkeypatch,damage):
    from pathlib import Path
    m=module();args=inputs(tmp_path,monkeypatch)
    if damage=='changed_outcome':args['score_packet']['outcome']['receipt']['temperatureF']=99.
    elif damage=='changed_comparator':args['score_packet']['recent_cycle_grid'][0][1]['temperatureF']=99.
    elif damage=='missing_query':args['source_paths'].pop()
    elif damage=='duplicate_query':args['source_paths'].append(args['source_paths'][0])
    elif damage=='phase':args['sensor_epoch']=EPOCHS['mass']
    elif damage=='future_assessment':args['assessed_at']=args['issue_at']
    else:Path(args['source_paths'][0]).unlink()
    with pytest.raises((ValueError,OSError)):m.build_native_score_binding(**args)


def origin_inputs(tmp_path,monkeypatch,*,observed=None):
    from thermal_model.temperature_history import STREAMS
    from thermal_temperature_runtime import shadow_temperatures_v2
    policy_path,rows=sources(tmp_path,monkeypatch)
    policies,_=load_temperature_receiver_configuration(str(policy_path))
    tmp_path.chmod(0o700);paths={};saved=[]
    observed=observed or AT+timedelta(minutes=6)
    # A null barrier must remain in the original source, even when a later
    # healthy snapshot supplies the current reading.
    def earlier(value):
        from datetime import datetime
        if isinstance(value,dict):return {k:earlier(v) for k,v in value.items()}
        if isinstance(value,list):return [earlier(v) for v in value]
        if isinstance(value,str) and value.startswith('2026-09-10T'):
            return (datetime.fromisoformat(value)-timedelta(seconds=60)).isoformat()
        return value
    rows[0]=(AT-timedelta(seconds=60),json.dumps(earlier(json.loads(rows[0][1]))))
    rows.insert(1,(AT-timedelta(seconds=30),None))
    def grid(stream,targets,assessed):
        role=next(r for r,v in STREAMS.items() if v[0]==stream)
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=assessed,
            stream=stream,policy=policies[stream],sensor_epoch=EPOCHS[role])
        paths[role]=str(write_temperature_source(tmp_path,packet))
        return replay_temperature_source(packet)
    shadow_temperatures_v2(observed,grid,sensor_epochs=EPOCHS,origin_observer=saved.append)
    return dict(origin_temperatures=saved[0],source_paths=paths,issue_at=observed+timedelta(seconds=30))


def test_origin_binding_requires_replay_of_each_original_role_query(tmp_path,monkeypatch):
    m=module();assert hasattr(m,'build_native_origin_binding'),'missing original issue-query proof'
    args=origin_inputs(tmp_path,monkeypatch);binding=m.build_native_origin_binding(**args)
    assert binding['release_authority'] is False
    assert binding['schema']=='earthship-installed-shade-native-origin-binding/v1'
    assert m.replay_native_origin_binding(binding,args['origin_temperatures'],issue_at=args['issue_at'])==binding


@pytest.mark.parametrize('damage',['grid','missing_role','role_swap','future_query','deleted_source','barrier','targets','identity','schema','query_extra'])
def test_origin_binding_refuses_summary_or_revised_query_substitutions(tmp_path,monkeypatch,damage):
    from pathlib import Path
    from weather_temperature_sources import read_temperature_source
    m=module();assert hasattr(m,'build_native_origin_binding'),'missing original issue-query proof'
    args=origin_inputs(tmp_path,monkeypatch);proof=args['origin_temperatures'];paths=args['source_paths']
    if damage=='grid':proof['roles']['air']['grid'][-1][1]['temperatureF']=99.
    elif damage=='missing_role':paths.pop('mass')
    elif damage=='role_swap':paths['air'],paths['mass']=paths['mass'],paths['air']
    elif damage=='deleted_source':Path(paths['air']).unlink()
    elif damage=='identity':proof['roles']['air']['identity']['sensor_epoch']=EPOCHS['mass']
    elif damage=='schema':proof['schema']='earthship-thermal-origin-temperatures/v1'
    elif damage=='query_extra':paths['extra']=paths['air']
    else:
        path=Path(paths['air']);packet=read_temperature_source(path.parent,path)
        if damage=='future_query':packet['assessed_at']=(args['issue_at']+timedelta(seconds=1)).isoformat()
        elif damage=='targets':packet['targets']=packet['targets'][-1:];packet['history_start']=(AT+timedelta(minutes=4)).isoformat();packet['native_rows']=packet['native_rows'][-1:]
        else:packet['native_rows'].pop(1)
        paths['air']=str(write_temperature_source(tmp_path,packet))
    with pytest.raises((ValueError,OSError)):m.build_native_origin_binding(**args)


@pytest.mark.parametrize('damage',['authority','digest','issue','assessed','source_deleted'])
def test_origin_binding_rechecks_sources_and_immutable_context(tmp_path,monkeypatch,damage):
    from pathlib import Path
    m=module();args=origin_inputs(tmp_path,monkeypatch);binding=m.build_native_origin_binding(**args)
    if damage=='authority':binding['release_authority']=True
    elif damage=='digest':binding['origin_temperatures_sha256']='0'*64
    elif damage=='issue':binding['issue_at']=(args['issue_at']+timedelta(seconds=1)).isoformat()
    elif damage=='assessed':binding['assessed_at']=args['issue_at'].isoformat()
    else:Path(args['source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):m.replay_native_origin_binding(binding,args['origin_temperatures'],issue_at=args['issue_at'])


def test_origin_binding_freezes_input_before_budget_callbacks(tmp_path,monkeypatch):
    from thermal_model.installed_shade_artifact import _digest
    m=module();args=origin_inputs(tmp_path,monkeypatch);expected=_digest(args['origin_temperatures'])
    def guard():args['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF']=99.
    binding=m.build_native_origin_binding(**args,check_budget=guard)
    assert binding['origin_temperatures_sha256']==expected


def test_origin_binding_refuses_oversized_grid_before_copy_or_serialization(tmp_path,monkeypatch):
    m=module();args=origin_inputs(tmp_path,monkeypatch)
    class OversizedGrid(list):
        def __deepcopy__(self,memo):pytest.fail('oversized supplied grid copied before bounding')
    args['origin_temperatures']['roles']['air']['grid']=OversizedGrid([None]*290)
    with pytest.raises(ValueError):m.build_native_origin_binding(**args)


def test_origin_binding_accepts_exactly_aligned_288_target_queries(tmp_path,monkeypatch):
    args=origin_inputs(tmp_path,monkeypatch,observed=AT+timedelta(minutes=5))
    assert all(len(value['grid'])==288 for value in args['origin_temperatures']['roles'].values())
    binding=module().build_native_origin_binding(**args)
    assert binding['assessed_at']=='2026-09-10T12:05:00+00:00'


@pytest.mark.parametrize('field',['path','identity'])
def test_origin_binding_bounds_paths_and_identity_before_copy(tmp_path,monkeypatch,field):
    m=module();args=origin_inputs(tmp_path,monkeypatch)
    class Malformed(list):
        def __deepcopy__(self,memo):pytest.fail('malformed input copied before validation')
    if field=='path':args['source_paths']['air']=Malformed([None]*1000)
    else:args['origin_temperatures']['roles']['air']['identity']['model']=Malformed([None]*1000)
    with pytest.raises(ValueError):m.build_native_origin_binding(**args)


def compressed_inputs(args):
    from pathlib import Path
    from weather_temperature_sources import read_temperature_source,write_compressed_temperature_source
    sources=args['source_paths']
    def convert(name):
        path=Path(name)
        return str(write_compressed_temperature_source(path.parent,read_temperature_source(path.parent,path)))
    args['source_paths']={role:convert(path) for role,path in sources.items()} if isinstance(sources,dict) else [convert(path) for path in sources]
    return args


@pytest.mark.parametrize('role',['origin','score'])
def test_compressed_binding_replays_exact_original_and_legacy_refuses(tmp_path,monkeypatch,role):
    m=module();args=compressed_inputs((origin_inputs if role=='origin' else inputs)(tmp_path,monkeypatch))
    builder=getattr(m,'build_compressed_native_'+role+'_binding',None)
    replay=getattr(m,'replay_compressed_native_'+role+'_binding',None)
    assert callable(builder) and callable(replay),'missing explicitly compressed binding profile'
    binding=builder(**args)
    assert binding['schema']==f'earthship-installed-shade-native-{role}-binding/v2'
    assert binding['release_authority'] is False
    replay_args={k:v for k,v in args.items() if k!='source_paths'}
    packet=replay_args.pop('origin_temperatures' if role=='origin' else 'score_packet')
    assert replay(binding,packet,**replay_args)==binding
    with pytest.raises(ValueError):getattr(m,'replay_native_'+role+'_binding')(binding,packet,**replay_args)
    with pytest.raises(ValueError):getattr(m,'build_native_'+role+'_binding')(**args)


@pytest.mark.parametrize('role',['origin','score'])
def test_compressed_binding_requires_retained_original_queries(tmp_path,monkeypatch,role):
    from pathlib import Path
    m=module();args=compressed_inputs((origin_inputs if role=='origin' else inputs)(tmp_path,monkeypatch))
    builder=getattr(m,'build_compressed_native_'+role+'_binding',None)
    replay=getattr(m,'replay_compressed_native_'+role+'_binding',None)
    assert callable(builder) and callable(replay),'missing explicitly compressed binding profile'
    binding=builder(**args)
    sources=args['source_paths'];path=next(iter(sources.values())) if role=='origin' else sources[0]
    Path(path).unlink()
    replay_args={k:v for k,v in args.items() if k!='source_paths'}
    packet=replay_args.pop('origin_temperatures' if role=='origin' else 'score_packet')
    with pytest.raises((ValueError,OSError)):replay(binding,packet,**replay_args)


@pytest.mark.parametrize('role',['origin','score'])
def test_compressed_binding_rejects_changed_cache(tmp_path,monkeypatch,role):
    m=module();args=compressed_inputs((origin_inputs if role=='origin' else inputs)(tmp_path,monkeypatch))
    builder=getattr(m,'build_compressed_native_'+role+'_binding',None)
    assert callable(builder),'missing explicitly compressed binding profile'
    if role=='origin':args['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF']=99.
    else:args['score_packet']['outcome']['receipt']['temperatureF']=99.
    with pytest.raises(ValueError):builder(**args)
