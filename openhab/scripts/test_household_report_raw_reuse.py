"""Raw reuse must not introduce per-row retained coordinator guard I/O."""
import ast
from hashlib import sha256
from pathlib import Path
from datetime import timedelta
import json
import pytest
from test_weather_temperature_reader import AT,raw,POLICY
from test_weather_temperature_sources import case


def extracted(module,parent,name,namespace):
    """Execute the exact original nested callback, never its scoring caller."""
    tree=ast.parse(Path(module.__file__).read_text())
    enclosing=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==parent)
    node=next(node for node in ast.walk(enclosing) if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),module.__file__,'exec'),namespace)
    return namespace[name]


def retained_context(tmp_path,monkeypatch,exercise):
    import household_forecast_score as coordinator,household_retained_native_score as retained
    import household_cycle_deploy as deploy,native_thermal_live as native,native_model_serving_receipt as serving
    from household_observation import _private_file
    stage=tmp_path/'stage';stage.mkdir(mode=0o700)
    settings={'schema':native.SERVING_SCHEMA,'shared_lock':str(tmp_path/'lock')}
    (tmp_path/'lock').write_bytes(b'');(tmp_path/'lock').chmod(0o600)
    config=tmp_path/'config.json';config.write_text(json.dumps(settings));config.chmod(0o600)
    cycle=stage/'cycle.json';cycle.write_text(json.dumps({'forecast_config':str(config)}));cycle.chmod(0o600)
    manifest=stage/'deployment.json';manifest.write_text('{"private_fixture":true}');manifest.chmod(0o600)
    script=stage/'archived-coordinator.py';script.write_bytes(Path(coordinator.__file__).read_bytes());script.chmod(0o644)
    own=stage/'current-coordinator.py';own.write_bytes(Path(coordinator.__file__).read_bytes());own.chmod(0o644)
    helper=stage/'household_retained_native_score.py';helper.write_bytes(Path(retained.__file__).read_bytes());helper.chmod(0o644)
    ticks=[10.];pressure_refused=[False];counts={'source':0,'pressure':0,'private_config':0}
    namespace=dict(deploy=deploy,stage=stage)
    read_manifest=extracted(coordinator,'run_retained_worker','read_manifest',namespace)
    namespace.update(own_path=own,own=own.read_bytes(),script=script,original=script.read_bytes(),read_manifest=read_manifest,
        manifest=manifest.read_bytes(),cycle_path=cycle,cycle_raw=cycle.read_bytes(),config=config,config_raw=config.read_bytes(),
        sha256=sha256,_policy_source_bytes=coordinator._policy_source_bytes,helper=helper,
        RETAINED_COORDINATOR_SHA256=coordinator.RETAINED_COORDINATOR_SHA256)
    original_source_guard=extracted(coordinator,'run_retained_worker','source_guard',namespace)
    def source_guard():counts['source']+=1;original_source_guard()
    def private_file(*a,**kw):counts['private_config']+=1;return _private_file(*a,**kw)
    monkeypatch.setattr('household_observation._private_file',private_file)
    class Pressure:
        def check(self,**kw):
            counts['pressure']+=1
            if pressure_refused[0]:raise ValueError('publication memory pressure unavailable')
    monkeypatch.setattr(native,'load_settings',lambda path:settings)
    monkeypatch.setattr(serving,'load_serving_selection',lambda *a,**kw:object())
    monkeypatch.setattr(serving,'read_serving_model',lambda *a,**kw:object())
    def no_scoring(*a,**kw):
        remaining=extracted(retained,'score_jobs','remaining',dict(guard=kw['guard'],deadline=kw['deadline'],monotonic=kw['monotonic']))
        exercise(kw['guard'],remaining,counts,ticks,pressure_refused,config)
        return {'status':'private_guard_exercised'}
    monkeypatch.setattr(retained,'score_jobs',no_scoring)
    return retained.run(config,stage=stage,deployment_sha256='a'*64,deadline=130.,resource_preflight=lambda:None,
        pressure_factory=Pressure,source_guard=source_guard,verify_archive=source_guard,
        clock=lambda:AT.replace(minute=1),monotonic=lambda:ticks[0])


def test_snapshots_do_not_amplify_real_retained_guard_and_queries_keep_boundaries(tmp_path,monkeypatch):
    import household_score_report_reuse as reuse,weather_temperature_reader as reader,weather_temperature_sources as sources
    from thermal_model.replay_budget import shared_replay_budget
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch))
    def exercise(guard,remaining,counts,*_):
        with shared_replay_budget(remaining),reuse._temperature_reads(guard):
            before=dict(counts)
            for i in range(100):
                assert reader._snapshot(raw(offset=i),AT+timedelta(seconds=i),'indoor',POLICY)[1]['temperatureF']==70
                reader._snapshot(raw(offset=i),AT+timedelta(seconds=i),'indoor',POLICY)
            assert counts==before,'pure per-row reuse introduced retained lock/pressure/source/config I/O'
            sources.replay_temperature_source(packet);sources.replay_temperature_source(packet)
            assert counts['source']-before['source']==4,'query miss/hit must retain both explicit guards'
            assert counts['private_config']-before['private_config']==4
    assert retained_context(tmp_path,monkeypatch,exercise)['status']=='private_guard_exercised'


@pytest.mark.parametrize('refusal',['deadline','pressure','source'])
def test_real_retained_guard_refuses_at_query_boundary_and_restores_hooks(tmp_path,monkeypatch,refusal):
    import household_score_report_reuse as reuse,weather_temperature_reader as reader,weather_temperature_sources as sources
    from thermal_model.replay_budget import shared_replay_budget
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));snapshot=reader._snapshot;query=sources.replay_temperature_source
    def exercise(guard,remaining,counts,ticks,pressure_refused,config):
        with shared_replay_budget(remaining),reuse._temperature_reads(guard):
            sources.replay_temperature_source(packet)
            if refusal=='deadline':ticks[0]=131.
            elif refusal=='pressure':pressure_refused[0]=True
            else:config.write_bytes(config.read_bytes()+b' ')
            sources.replay_temperature_source(packet)
    with pytest.raises(ValueError):retained_context(tmp_path,monkeypatch,exercise)
    assert reader._snapshot is snapshot and sources.replay_temperature_source is query
