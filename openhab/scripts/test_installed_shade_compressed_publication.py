"""Compressed publication preparation; fixtures never establish release readiness."""
from datetime import datetime,timezone
import pytest
from thermal_model.forcing_capture import _canonical


@pytest.mark.parametrize('schema',['earthship-installed-shade-release-inputs/v3','earthship-installed-shade-qualification-report/v7'])
def test_compressed_factory_rejects_legacy_references_and_saved_report(tmp_path,schema):
    from thermal_model import installed_shade_publication as p
    api=getattr(p,'prepare_compressed_installed_qualification',None)
    assert callable(api),'missing source-replayed compressed publication preparation'
    path=tmp_path/'references.json';path.write_bytes(_canonical(dict(schema=schema,registration_path=None,candidate_path='candidate',runtime_bundle_path='runtime',original_pairs_path=None)));path.chmod(0o600)
    prepared=api(path)
    assert isinstance(prepared,p.PreparedCompressedInstalledQualification)
    assert prepared.source_ready is False


def test_compressed_publisher_requires_distinct_preparation_and_never_saved_report():
    from thermal_model import installed_shade_publication as p
    api=getattr(p,'build_compressed_installed_publication',None)
    assert callable(api),'missing compressed source-qualified publication builder'
    now=datetime(2026,10,10,tzinfo=timezone.utc)
    for weaker in ({'forecast_qualified':True},p.PreparedRawInstalledQualification(None,None,True),p.PreparedInstalledQualification(None,None,True)):
        value=api('missing',weaker)
        assert value['version']==7 and value['status']=='unavailable'
        assert value['release']['forecastQualified'] is False
        assert value['release']['sourceQualificationSchema'] is None
        p.validate_compressed_source_installed_publication(value)


from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from test_installed_shade_raw_origin import candidate,raw_math_capture,source_origin_case
from test_installed_shade_publication import release_case
from test_installed_shade_complete_raw_publication import raw_release_math
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture(scope='module')
def compressed_release_math(raw_release_math):
    # Report-selection math only: there are no original development/calibration/
    # release archives for this fixture. Source loaders are explicit seams below.
    from thermal_model import installed_shade_qualification as q
    from thermal_model.graduation_policy import derive_policy
    from thermal_model.graduation_statistics import assess_current_predictive_skill
    artifact,report,numeric,now=deepcopy(raw_release_math)
    learned=report['candidate_bundle']['calibration']
    learned.update(schema='earthship-installed-shade-calibration/v4',source_contract='earthship-installed-shade-score-sources/v6')
    for b in learned['source_pair_bindings']:b['native_origin_binding_sha256']='a'*64
    learned['calibration_sha256']=_digest({k:v for k,v in learned.items() if k!='calibration_sha256'})
    artifact['schema']='earthship-installed-shade-candidate/v5'
    artifact['calibration'].update(schema=learned['schema'],source_contract=learned['source_contract'],calibration_sha256=learned['calibration_sha256'])
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    old=report['policy'];metadata=dict(old['candidate'],artifact_sha256=artifact['artifact_sha256'])
    policy=derive_policy(old['development'],declared_at=old['declared_at'],intervals=old['intervals'],candidate=metadata,regimes=old['regimes'])
    for row in report['scored_pairs']:row['artifact_sha256']=artifact['artifact_sha256']
    for key in ('registration_source_bindings','original_pair_bindings'):
        for b in report[key]:b['native_origin_binding_sha256']='b'*64
    report.update(schema=q.COMPRESSED_SCHEMA,candidate_schema=artifact['schema'],candidate=metadata,policy=policy,
        gates={name:True for name in q._report_gates(7)},statistics=assess_current_predictive_skill(policy,report['scored_pairs'],now=report['assessed_at']))
    report['candidate_bundle']['artifact']=artifact
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    q.validate_compressed_installed_shade_qualification_report(report)
    numeric.update(schema='earthship-installed-shade-origin/v12',candidate=artifact,native_origin_binding={'synthetic_math_seam':True})
    numeric['output'].update(schema='earthship-installed-shade-forecast/v7',artifact_sha256=artifact['artifact_sha256'],native_origin_binding_sha256=_digest(numeric['native_origin_binding']))
    for band in numeric['output']['prediction_intervals']:band['calibration_sha256']=learned['calibration_sha256']
    numeric['capture_sha256']=_digest({k:v for k,v in numeric.items() if k!='capture_sha256'})
    return artifact,report,numeric,now


@pytest.fixture
def compressed_active_routing(compressed_release_math,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as p,installed_shade_qualification as q
    artifact,report,numeric,now=deepcopy(compressed_release_math);tmp_path.chmod(0o700)
    refs=dict(schema='earthship-installed-shade-release-inputs/v4',registration_path='seal',candidate_path='model.installed-shade-candidate-v5.json',runtime_bundle_path='runtime',original_pairs_path=None)
    path=tmp_path/'refs.json';path.write_bytes(_canonical(refs));path.chmod(0o600)
    state={'valid':True,'calls':0}
    def qualify(**kwargs):
        state['calls']+=1
        assert kwargs['candidate_path'].name.endswith('.installed-shade-candidate-v5.json')
        if not state['valid']:raise ValueError('synthetic original source lost')
        return deepcopy(report)
    monkeypatch.setattr(q,'qualify_compressed_installed_shade_candidate',qualify)
    monkeypatch.setattr(p,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(p,'build_runtime_binding',lambda *a:artifact['runtime'])
    monkeypatch.setattr(p,'_clock',lambda:now)
    monkeypatch.setattr(p,'_read_origin',lambda *a,**kw:(deepcopy(numeric),lambda current:(deepcopy(numeric['output']),deepcopy(artifact['sensor_epochs']))))
    prepared=p.prepare_compressed_installed_qualification(path)
    assert prepared.source_ready is True
    return p,path,prepared,report,numeric,state,monkeypatch


def test_compressed_active_selection_replays_fresh_qualification_and_withholds_advice(compressed_active_routing):
    p,path,prepared,report,numeric,state,monkeypatch=compressed_active_routing
    assert state['calls']==1
    output=p.build_compressed_installed_publication('synthetic-origin',prepared)
    assert state['calls']==2
    assert output['status']==report['recommended_stage']=='forecast_active'
    assert output['forecast']==numeric['output'] and output['version']==7
    assert output['release']['sourceQualificationSchema']==report['schema']
    assert output['release']['reportSha256']==report['report_sha256']
    assert output['release']['advisoryQualified'] is False and output['release']['automaticActuation'] is False
    assert p.prepare_raw_installed_qualification(path).source_ready is False
    with pytest.raises(ValueError):p.validate_raw_installed_publication(output)


@pytest.mark.parametrize('damage',['source_lost','expired','manual_gate','current_runtime'])
def test_compressed_active_routing_fails_closed_on_fresh_source_or_release_failure(compressed_active_routing,damage):
    p,_,prepared,report,_,state,monkeypatch=compressed_active_routing
    if damage=='source_lost':state['valid']=False
    elif damage=='expired':monkeypatch.setattr(p,'_clock',lambda:datetime.fromisoformat(report['qualification_expires_at']))
    elif damage=='manual_gate':
        report['gates']['raw_native_issue_sources']=False
        report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    else:monkeypatch.setattr(p,'build_runtime_binding',lambda *a:dict(changed_runtime=True))
    output=p.build_compressed_installed_publication('synthetic-origin',prepared)
    assert output['status']=='unavailable' and output['forecast'] is None


def test_compressed_real_current_queries_bind_shadow_bootstrap_and_refuse_original_loss(source_origin_case,tmp_path,monkeypatch):
    from test_installed_shade_raw_publication_capture import compressed_calibrated_delivery
    from thermal_model import installed_shade_publication as p,installed_shade_qualification as q
    root,main,_,issue,_,args=compressed_calibrated_delivery(source_origin_case,tmp_path,monkeypatch)
    numeric=main['numeric_capture'];path=root/(numeric['capture_sha256']+'.installed-shade-origin-v12.json')
    report=q.qualify_compressed_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=issue)
    # Prepared readiness is an explicit math seam; a real one-day calibration
    # cannot pass the public factory's independent-support gate.
    prepared=p.PreparedCompressedInstalledQualification(_canonical(report),_canonical(numeric['candidate']),True,True,('thermal_intel.py',),True,str(root/'synthetic-refs.json'))
    monkeypatch.setattr(p,'prepare_compressed_installed_qualification',lambda _:prepared)
    monkeypatch.setattr(p,'build_runtime_binding',lambda *a:numeric['runtime'])
    monkeypatch.setattr(p,'_clock',lambda:issue+timedelta(seconds=3))
    output=p.build_compressed_installed_publication(path,prepared)
    assert output['status']=='shadow' and output['forecast']==numeric['output']
    assert output['release']['nativeOriginBindingSha256']==_digest(numeric['native_origin_binding'])
    original_reader=p._read_origin
    def lose_after_math(*a,**kw):
        record,predict=original_reader(*a,**kw)
        def guarded(current):
            result=predict(current)
            Path(args['native_source_paths']['air']).unlink()
            return result
        return record,guarded
    monkeypatch.setattr(p,'_read_origin',lose_after_math)
    assert p.build_compressed_installed_publication(path,prepared)['status']=='unavailable'
    assert p.build_compressed_installed_publication(path,prepared)['status']=='unavailable'



def test_compressed_preparation_and_publication_inherit_expired_parent_before_reading(monkeypatch):
    from thermal_model import installed_shade_publication as p
    from thermal_model.replay_budget import shared_replay_budget
    monkeypatch.setattr(p,'_read_private',lambda _:pytest.fail('expired budget reached original reference reader'))
    clock={'remaining':60}
    with shared_replay_budget(lambda:clock['remaining']):
        clock['remaining']=0
        assert p.prepare_compressed_installed_qualification('unused').source_ready is False
        assert p.build_compressed_installed_publication('unused',{} )['status']=='unavailable'


def test_compressed_factory_reuses_just_replayed_candidate_and_checks_runtime_at_return(compressed_active_routing):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    p,path,_,_,numeric,state,monkeypatch=compressed_active_routing
    monkeypatch.setattr(artifact,'read_compressed_source_calibrated_candidate',lambda *a,**kw:pytest.fail('registered candidate was redundantly fitted'))
    assert p.prepare_compressed_installed_qualification(path).source_ready is True
    calls={'count':0}
    def runtime(*args):
        calls['count']+=1
        return numeric['runtime'] if calls['count']==1 else dict(changed_runtime=True)
    monkeypatch.setattr(p,'build_runtime_binding',runtime)
    assert p.prepare_compressed_installed_qualification(path).source_ready is False
    assert calls['count']==2


def test_compressed_publication_refuses_native_expiry_during_final_original_read(compressed_active_routing):
    p,_,prepared,_,numeric,_,monkeypatch=compressed_active_routing
    reader=p._read_origin;calls={'count':0}
    def elapsed(*args,**kwargs):
        result=reader(*args,**kwargs);calls['count']+=1
        if calls['count']==2:
            monkeypatch.setattr(p,'_clock',lambda:datetime.fromisoformat(numeric['issued_at'])+timedelta(minutes=3))
        return result
    monkeypatch.setattr(p,'_read_origin',elapsed)
    assert p.build_compressed_installed_publication('synthetic-origin',prepared)['status']=='unavailable'


def test_compressed_delivery_retains_the_report_from_its_final_source_requalification(compressed_active_routing):
    p,_,prepared,_,_,_,_=compressed_active_routing
    reports=[]
    output=p.build_compressed_installed_publication('synthetic-origin',prepared,report_sink=lambda report:reports.append(report))
    assert output['status']=='forecast_active' and len(reports)==1
    assert reports[0]['report_sha256']==output['release']['reportSha256']



def test_python_compressed_active_publication_matches_browser_contract(compressed_active_routing):
    import subprocess,json
    p,_,prepared,_,_,_,_=compressed_active_routing
    output=p.build_compressed_installed_publication('synthetic-origin',prepared)
    assert output['status']=='forecast_active'
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node','--max-old-space-size=128',str(root/'scripts/verify-compressed-installed-ui.mjs'),'--publication'],
        input=json.dumps(dict(publication=output,now=int(datetime.fromisoformat(output['generatedAt']).timestamp()*1000))),text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==dict(state='ready',mode='forecast_active',badge='FORECAST',uncertaintyMode='calibrated_targets')
