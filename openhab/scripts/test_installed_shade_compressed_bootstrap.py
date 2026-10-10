"""Explicit compressed base bootstrap; readiness seams are not release evidence."""
import json
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical
from test_installed_shade_compressed_live_cli import compressed_settings,raw_settings


def test_compressed_bootstrap_factory_refuses_configured_registration(tmp_path):
    from thermal_model import installed_shade_publication as p
    api=getattr(p,'prepare_compressed_base_bootstrap',None)
    assert callable(api),'missing compressed base calibration bootstrap'
    refs=dict(schema='earthship-installed-shade-release-inputs/v4',registration_path='seal',candidate_path='model.installed-shade-candidate-v1.json',runtime_bundle_path='runtime',original_pairs_path=None)
    path=tmp_path/'refs';path.write_bytes(_canonical(refs));path.chmod(0o600)
    assert api(path).source_ready is False


def test_production_cannot_accept_compressed_base_bootstrap_type(monkeypatch):
    from thermal_model import installed_shade_publication as p
    cls=getattr(p,'PreparedCompressedBaseBootstrap',None)
    assert cls is not None,'missing distinct compressed bootstrap type'
    monkeypatch.setattr(p,'prepare_compressed_installed_qualification',lambda _:pytest.fail('bootstrap type reached production qualification'))
    value=p.build_compressed_installed_publication('missing',cls(None,None,True))
    assert value['status']=='unavailable' and value['release']['forecastQualified'] is False


def test_compressed_cli_bootstrap_explicitly_selects_source_worker(compressed_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live as live,installed_shade_live_inputs as inputs
    path,value,_=compressed_settings;backend=object()
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda *a,**kw:backend)
    def run(**kw):
        assert kw['backend'] is backend
        return dict(status='published',mode='shadow',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'run_compressed_bootstrap_live_cycle',run,raising=False)
    lock=path.parent/'lock';lock.touch(mode=0o600)
    assert cli.main(['--config',str(path),'--contract-version','3','--bootstrap-shadow','--shared-lock',str(lock)])==0
    assert json.loads(capsys.readouterr().out)['mode']=='shadow'


from copy import deepcopy
from datetime import datetime,timedelta
from test_installed_shade_raw_origin import candidate,raw_math_capture
from test_installed_shade_live import FakeBackend


@pytest.fixture
def base_cycle(raw_math_capture,tmp_path,monkeypatch):
    from test_installed_shade_raw_origin import build_source_origin_case
    from test_installed_shade_raw_publication_capture import deliver_source
    from thermal_model import installed_shade_live as live,installed_shade_publication as p,installed_shade_published_origin as captures,installed_shade_qualification as q
    issue=datetime.fromisoformat(raw_math_capture['issued_at'])
    source=build_source_origin_case(raw_math_capture,tmp_path,assessed_at=issue-timedelta(seconds=15))
    root,main,_,issue,_,args=deliver_source((source,tmp_path,monkeypatch,'base'),compressed=True)
    numeric=main['numeric_capture'];live._test_time=issue-timedelta(seconds=15)
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    monkeypatch.setattr(live,'_wait_until',lambda at:setattr(live,'_test_time',at))
    monkeypatch.setattr(p,'_clock',lambda:live._test_time);monkeypatch.setattr(captures,'_clock',lambda:live._test_time)
    report=q.qualify_compressed_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=live._test_time)
    # Mathematical readiness seam. Actual public factory replays original native
    # training/fit evidence; this fixture does not possess a qualifying fit.
    prepared=p.PreparedCompressedBaseBootstrap(_canonical(report),_canonical(numeric['candidate']),True,True,('thermal_intel.py',),True,str(root/'synthetic-refs.json'))
    monkeypatch.setattr(live,'prepare_compressed_base_bootstrap',lambda _:prepared)
    monkeypatch.setattr(p,'prepare_compressed_base_bootstrap',lambda _:prepared)
    monkeypatch.setattr(live,'build_runtime_binding',lambda *a:numeric['runtime']);monkeypatch.setattr(p,'build_runtime_binding',lambda *a:numeric['runtime'])
    class Backend(FakeBackend):
        def collect(self,*,issue,known_at):
            self.collected=True;self.m._test_time=self.issue-timedelta(seconds=5)
            values={key:deepcopy(numeric[key]) for key in ('forecast','current','origin_temperatures','action_snapshot')}
            return dict(values,native_source_paths=deepcopy(args['native_source_paths']))
    return live,p,root,issue,prepared,Backend(live,issue),monkeypatch,args


def test_compressed_base_bootstrap_retains_actual_shadow_receipts_without_calibration(base_cycle):
    from thermal_model.installed_shade_published_origin import read_compressed_source_publication_capture
    live,_,root,_,_,backend,_,_=base_cycle
    result=live.run_compressed_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['mode']=='shadow'
    record=read_compressed_source_publication_capture(result['capture_path'])
    assert record['schema']=='earthship-installed-shade-origin/v11' and record['numeric_capture']['schema']=='earthship-installed-shade-origin/v10'
    assert record['numeric_capture']['candidate']['schema']=='earthship-installed-shade-candidate/v1'
    assert record['numeric_publication']==backend.rows['Thermal_OriginalForecast_JSON'] and record['publication']==backend.rows['Thermal_Model_JSON']
    output=json.loads(record['publication']['state'])
    assert output['forecast']['prediction_intervals'] is None and output['release']['calibrationSha256'] is None
    assert output['release']['forecastQualified'] is False and output['release']['sourceQualificationSchema'] is None
    assert output['release']['automaticActuation'] is False


@pytest.mark.parametrize('damage',['registered','calibrated_type','missing_source'])
def test_compressed_base_bootstrap_withdraws_invalid_mode_or_original_sources(base_cycle,damage):
    from dataclasses import replace
    live,p,root,_,prepared,backend,monkeypatch,args=base_cycle
    if damage=='registered':prepared=replace(prepared,registration_absent=False)
    elif damage=='calibrated_type':prepared=p.PreparedCompressedInstalledQualification(prepared.report_json,prepared.candidate_json,True,True,prepared.runtime_paths,True,prepared.reference_path)
    else:Path(args['native_source_paths']['air']).unlink()
    monkeypatch.setattr(live,'prepare_compressed_base_bootstrap',lambda _:prepared)
    result=live.run_compressed_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn' and not list(root.glob('*.installed-shade-origin-v11.json'))
    assert backend.puts[-1][1]['version']==7 and backend.puts[-1][1]['status']=='unavailable'


def test_compressed_bootstrap_factory_reads_native_base_fit_without_calibration(base_cycle):
    live,p,root,_,prepared,_,monkeypatch,_=base_cycle
    artifact=json.loads(prepared.candidate_json);runtime=live.build_runtime_binding(None,None)
    refs=dict(schema=p.COMPRESSED_REFERENCE_SCHEMA,registration_path=None,candidate_path='model.installed-shade-candidate-v1.json',runtime_bundle_path='runtime',original_pairs_path=None)
    path=root/'base-refs';path.write_bytes(_canonical(refs));path.chmod(0o600)
    # Original-fit loader routing seam only, not a source-qualified learning fit.
    monkeypatch.setattr(p,'read_runtime_bundle',lambda _:dict(runtime=runtime,revision_paths=['thermal_intel.py']))
    state={'fit':True,'reads':0}
    def read(path,**kwargs):
        assert path.name.endswith('.installed-shade-candidate-v1.json') and kwargs['expected_runtime_revision']==artifact['runtime_revision']
        state['reads']+=1;return dict(artifact=artifact,fit_evidence=dict(fit_gates_passed=state['fit']))
    monkeypatch.setattr(p,'read_candidate_bundle',read)
    # Restore the actual factory replaced by the cycle's readiness seam.
    from thermal_model.installed_shade_calibration import _source_operation
    result=_source_operation(p._prepare_compressed_base_bootstrap,path)
    assert result.source_ready is True and state['reads']==1
    assert json.loads(result.report_json)['forecast_qualified'] is False
    state['fit']=False
    assert _source_operation(p._prepare_compressed_base_bootstrap,path).source_ready is False
    calls={'count':0}
    def drift(*a):
        calls['count']+=1;return runtime if calls['count']==1 else dict(changed_runtime=True)
    monkeypatch.setattr(p,'build_runtime_binding',drift)
    with pytest.raises(ValueError):_source_operation(p._prepare_compressed_base_bootstrap,path)


def test_compressed_bootstrap_received_origin_can_feed_source6_baseline_calibration(base_cycle):
    from thermal_model import installed_shade_published_origin as captures,installed_shade_score_collection as collector,installed_shade_qualification as q
    from test_installed_shade_raw_publication_capture import CompressedRawBackend
    live,_,root,issue,_,backend,monkeypatch,_=base_cycle
    result=live.run_compressed_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published'
    record=captures.read_compressed_source_publication_capture(result['capture_path'])
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    score=collector.collect_compressed_source_published_score(origin_path=result['capture_path'],horizon_hours=1,output_directory=root,backend=CompressedRawBackend(record,root))
    assert score['status']=='scored'
    values=q.score_compressed_source_base_packets([dict(raw_score_sources_path=score['raw_packet_path'])],assessed_at=now)
    assert values['raw_native_issue_sources'] is True and values['raw_native_score_sources'] is True
    assert values['calibrated_intervals'] is False and len(values['rows'])==1
    assert values['rows'][0]['artifact_sha256']==record['numeric_capture']['candidate']['artifact_sha256']



def test_python_compressed_base_publication_matches_browser_shadow_contract(base_cycle):
    import subprocess
    live,_,root,_,_,backend,_,_=base_cycle
    result=live.run_compressed_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published'
    output=backend.puts[-1][1]
    repo=Path(__file__).resolve().parents[2]
    readback=subprocess.run(['node','--max-old-space-size=128',str(repo/'scripts/verify-compressed-installed-ui.mjs'),'--publication'],
        input=json.dumps(dict(publication=output,now=int(datetime.fromisoformat(output['generatedAt']).timestamp()*1000))),text=True,capture_output=True,timeout=10)
    assert readback.returncode==0,readback.stderr
    assert json.loads(readback.stdout)==dict(state='ready',mode='shadow',badge='SHADOW',uncertaintyMode='none')
