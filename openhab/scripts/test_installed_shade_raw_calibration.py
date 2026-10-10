"""Production calibration needs original raw queries, not receipt-only diagnostics."""
from copy import deepcopy
import pytest
from test_installed_shade_origin import candidate,prepared,original
from test_installed_shade_qualification import source_case
from test_installed_shade_calibration import create


def test_legacy_calibration_accepts_changed_receipt_without_raw_query_authority(candidate,source_case):
    packet=deepcopy(source_case[0])
    snapshot=packet['outcome']['receipt']['snapshotSha256']
    before=create(candidate,source_case)
    packet['outcome']['receipt']['temperatureF']+=2
    after=create(candidate,source_case,original_pairs=[packet])
    assert packet['outcome']['receipt']['snapshotSha256']==snapshot
    assert before['source_pair_bindings']!=after['source_pair_bindings']
    assert after['schema']=='earthship-installed-shade-calibration/v1'
    assert after['release_authorized'] is False


def test_production_raw_calibration_refuses_receipt_only_pairs(candidate,source_case):
    from thermal_model import installed_shade_calibration as calibration
    packet,_,assessed=source_case
    from test_installed_shade_origin import ISSUE
    from datetime import timedelta
    from thermal_model.installed_shade_artifact import _digest
    with pytest.raises(ValueError,match='raw'):
        calibration.build_raw_calibration(bundle=candidate[0],inputs=candidate[1],
            expected_runtime_revision=_digest(candidate[2]),original_pairs=[packet],
            calibration_start=ISSUE,calibration_end=ISSUE+timedelta(hours=1),
            regimes=['warm'],created_at=assessed)


@pytest.fixture
def raw_routing_case(candidate,source_case,tmp_path,monkeypatch):
    # Isolated routing/storage fixture. It does not establish raw-query authority.
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model.installed_shade_artifact import _digest
    from test_installed_shade_origin import ISSUE
    from datetime import timedelta
    packet,_,assessed=source_case
    scored=qualification._score_packets([packet],assessed_at=assessed)
    scored['raw_native_score_sources']=True
    for binding in scored['bindings']:
        binding.update(native_binding_sha256='a'*64,raw_score_sources_sha256='b'*64)
    def raw_only(pairs,*,assessed_at,candidate=None,version=1):
        if version!=4:raise ValueError('raw source profile not selected')
        return deepcopy(scored)
    monkeypatch.setattr(qualification,'_score_packets',raw_only)
    values=dict(bundle=candidate[0],inputs=candidate[1],expected_runtime_revision=_digest(candidate[2]),
        original_pairs=[{'raw_score_sources_path':str(tmp_path/'original.installed-shade-score-sources-v2.json')}],
        calibration_start=ISSUE,calibration_end=ISSUE+timedelta(hours=1),regimes=['warm'],created_at=assessed)
    return calibration,values


def test_raw_calibration_uses_distinct_contract_and_legacy_reader_refuses_it(raw_routing_case):
    calibration,values=raw_routing_case
    record=calibration.build_raw_calibration(**values)
    assert record['schema']=='earthship-installed-shade-calibration/v2'
    assert record['source_contract']=='earthship-installed-shade-score-sources/v2'
    assert record['summary']['complete'] is False and record['release_authorized'] is False
    calibration.validate_raw_calibration(record,**{key:values[key] for key in
        ('bundle','inputs','expected_runtime_revision','original_pairs')},assessed_at=values['created_at'])
    with pytest.raises(ValueError):
        calibration.validate_calibration(record,**{key:values[key] for key in
            ('bundle','inputs','expected_runtime_revision','original_pairs')},assessed_at=values['created_at'])


def test_raw_calibration_storage_has_distinct_typed_index_and_readback(raw_routing_case,tmp_path):
    calibration,values=raw_routing_case
    root=tmp_path/'raw-calibration';root.mkdir(mode=0o700)
    record=calibration.build_raw_calibration(**values)
    parameters={key:values[key] for key in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    path=calibration.write_raw_calibration(root,record,**parameters,assessed_at=values['created_at'])
    assert path.name==record['calibration_sha256']+'.installed-shade-calibration-v2.json'
    assert path.stat().st_mode&0o777==0o600
    assert calibration.read_raw_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],
        assessed_at=values['created_at'])==record
    assert list(root.glob('*.installed-shade-calibration-sources-v2.json'))
    with pytest.raises(ValueError):calibration.read_calibration(path,
        expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])


from test_installed_shade_score_collection import collection,issued,release_case,RawBackend


@pytest.fixture
def retained_raw_case(collection,candidate,monkeypatch):
    """Actual raw query replay; only acquisition and runtime ports are synthetic."""
    from datetime import timedelta
    from pathlib import Path
    import json
    from thermal_model import installed_shade_calibrated_origin as calibrated
    from thermal_model import installed_shade_origin as base
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model.forcing_capture import _canonical
    from thermal_model.installed_shade_artifact import _digest
    collector,root,_,record,issue=collection
    numeric=calibrated._core_view(record['numeric_capture'])
    assert numeric['candidate']==candidate[0]['artifact']
    path=base.write_issued_capture(root,numeric)
    report=qualification.qualify_installed_shade_candidate(registration_path=None,candidate_path=None,
        runtime_bundle_path=None,original_pairs=[],now=issue)
    ready=publisher.PreparedInstalledQualification(_canonical(report),_canonical(numeric['candidate']),True,True,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(publisher,'_clock',lambda:issue+timedelta(seconds=3))
    monkeypatch.setattr(publisher,'ERRORS',())
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:numeric['runtime'])
    output=publisher.build_installed_publication(path,ready)
    assert output['status']=='shadow'
    actual=dict(item='Thermal_Model_JSON',time=int((issue+timedelta(seconds=3)).timestamp()*1000),state=_canonical(output).decode())
    original_receipt=dict(item='Thermal_OriginalForecast_JSON',time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(numeric['output']).decode())
    monkeypatch.setattr(published,'_clock',lambda:issue+timedelta(seconds=4))
    capture=published.build_publication_capture(path,numeric_publication=original_receipt,publication=actual)
    published_path=published.write_publication_capture(root,capture)
    backend=RawBackend(capture,root)
    monkeypatch.setattr(collector,'ERRORS',())
    result=collector.collect_published_score(origin_path=published_path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored' and len(backend.native_source_paths)==8
    values=dict(bundle=candidate[0],inputs=candidate[1],expected_runtime_revision=_digest(candidate[2]),
        original_pairs=[dict(raw_score_sources_path=result['raw_packet_path'])],
        calibration_start=issue,calibration_end=issue+timedelta(hours=1),regimes=['warm'],
        created_at=issue+timedelta(hours=24,minutes=10))
    return calibration,values,backend,root,json.loads(Path(result['raw_packet_path']).read_text())


def test_raw_calibration_replays_original_queries_and_binds_their_identity(retained_raw_case):
    calibration,values,_,_,header=retained_raw_case
    from thermal_model.installed_shade_artifact import _digest
    record=calibration.build_raw_calibration(**values)
    assert record['summary']['bands']['1']['overall']['raw_pairs']==1
    assert record['summary']['bands']['1']['overall']['independent_days']==1
    assert record['summary']['complete'] is False and record['release_authorized'] is False
    binding=record['source_pair_bindings'][0]
    assert binding['native_binding_sha256']==_digest(header['native_binding'])
    assert binding['raw_score_sources_sha256']==_digest(header)


@pytest.mark.parametrize('damage',['changed_receipt','deleted_query'])
def test_raw_calibration_refuses_rehashed_receipt_changes_and_lost_queries(retained_raw_case,damage):
    calibration,values,backend,root,header=retained_raw_case
    from pathlib import Path
    from thermal_model.installed_shade_artifact import _digest
    from thermal_model.forcing_capture import _canonical
    if damage=='changed_receipt':
        receipt=header['score_sources']['outcome']['receipt']
        original_snapshot=receipt['snapshotSha256'];receipt['temperatureF']+=2
        assert receipt['snapshotSha256']==original_snapshot
        # Rehash both containers so rejection must reach raw selection equality.
        header['native_binding']['score_sources_sha256']=_digest(header['score_sources'])
        path=root/(_digest(header)+'.installed-shade-score-sources-v2.json')
        path.write_bytes(_canonical(header));path.chmod(0o600)
        values['original_pairs']=[dict(raw_score_sources_path=str(path))]
        with pytest.raises(ValueError,match='cached receipts differ from retained raw selection'):
            calibration.build_raw_calibration(**values)
    else:
        Path(backend.native_source_paths[0]).unlink()
        with pytest.raises((ValueError,OSError)):
            calibration.build_raw_calibration(**values)



def test_raw_calibration_readback_requires_original_query_files(retained_raw_case):
    from pathlib import Path
    calibration,values,backend,root,_=retained_raw_case
    record=calibration.build_raw_calibration(**values)
    archive=root/'calibration';archive.mkdir(mode=0o700)
    parameters={key:values[key] for key in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    path=calibration.write_raw_calibration(archive,record,**parameters,assessed_at=values['created_at'])
    assert calibration.read_raw_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],
        assessed_at=values['created_at'])==record
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):
        calibration.read_raw_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],
            assessed_at=values['created_at'])


from test_installed_shade_raw_origin import raw_math_capture


@pytest.fixture
def source_calibration_origin_case(raw_math_capture,tmp_path):
    from test_installed_shade_raw_origin import build_source_origin_case
    return build_source_origin_case(raw_math_capture,tmp_path)


@pytest.fixture
def retained_source_calibration_case(source_calibration_origin_case,candidate,tmp_path,monkeypatch,compressed=False):
    """Real source replay and numerical fit checks; synthetic data never qualify release."""
    from datetime import timedelta
    from thermal_model import installed_shade_artifact as artifact
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    import json
    from test_installed_shade_raw_origin import source_base_args
    from test_installed_shade_raw_publication_capture import deliver_source
    prepared,args=source_base_args(source_calibration_origin_case)
    model=json.loads(prepared.artifact_json);bundle=deepcopy(candidate[0])
    # Only the fixture runtime changes. Preserve measured fit/refit values and
    # rebind their payload identity; production validation recomputes them.
    evidence=bundle['fit_evidence'];evidence['candidate_payload_sha256']=artifact._digest(artifact._payload(model))
    evidence['fit_evidence_sha256']=artifact._digest({k:v for k,v in evidence.items() if k!='fit_evidence_sha256'})
    model['fit_evidence_sha256']=evidence['fit_evidence_sha256']
    model['artifact_sha256']=artifact._digest({k:v for k,v in model.items() if k!='artifact_sha256'})
    bundle['artifact']=model
    root,record,_,issue,_,args=deliver_source((source_calibration_origin_case,tmp_path,monkeypatch,'base'),base_candidate=model,compressed=compressed)
    writer=published.write_compressed_source_publication_capture if compressed else published.write_source_publication_capture
    path=writer(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    from test_installed_shade_raw_publication_capture import CompressedRawBackend
    backend=(CompressedRawBackend if compressed else RawBackend)(record,root)
    collect=collector.collect_compressed_source_published_score if compressed else collector.collect_source_published_score
    result=collect(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    values=dict(bundle=bundle,inputs=candidate[1],expected_runtime_revision=artifact._digest(args['runtime']),
        original_pairs=[dict(raw_score_sources_path=result['raw_packet_path'])],calibration_start=issue,
        calibration_end=issue+timedelta(hours=1),regimes=['warm'],created_at=now)
    return values,root,record,args,backend


def test_source_calibration_has_distinct_contract_and_keeps_independent_support_gate(retained_source_calibration_case):
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model.installed_shade_artifact import _digest
    assert hasattr(calibration,'build_source_calibration'),'missing original-query calibration'
    values,_,capture,_,_=retained_source_calibration_case
    record=calibration.build_source_calibration(**values)
    assert record['schema']=='earthship-installed-shade-calibration/v3'
    assert record['source_contract']=='earthship-installed-shade-score-sources/v4'
    assert record['summary']['bands']['1']['overall']['raw_pairs']==1
    assert record['summary']['bands']['1']['overall']['independent_days']==1
    assert record['summary']['bands']['1']['overall']['radius_f'] is None
    assert record['method']['minimum_independent_days']==35
    assert record['summary']['complete'] is False and record['release_authorized'] is False
    assert record['coverage_guaranteed'] is False
    assert record['source_pair_bindings'][0]['native_origin_binding_sha256']==_digest(capture['numeric_capture']['native_origin_binding'])
    parameters={k:values[k] for k in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    for validator in (calibration.validate_calibration,calibration.validate_raw_calibration):
        with pytest.raises(ValueError):validator(record,**parameters,assessed_at=values['created_at'])


@pytest.mark.parametrize('damage',['issue','outcome','old_profile'])
def test_source_calibration_refuses_missing_original_queries_and_older_profiles(retained_source_calibration_case,monkeypatch,damage):
    from pathlib import Path
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model.installed_shade_artifact import _digest
    from thermal_model.forcing_capture import _canonical
    import json
    assert hasattr(calibration,'build_source_calibration'),'missing original-query calibration'
    values,root,_,args,backend=retained_source_calibration_case
    if damage=='issue':Path(args['native_source_paths']['air']).unlink()
    elif damage=='outcome':Path(backend.native_source_paths[-1]).unlink()
    else:
        header=json.loads(Path(values['original_pairs'][0]['raw_score_sources_path']).read_text())
        header.pop('native_origin_binding_sha256');header['schema']='earthship-installed-shade-score-sources/v2'
        path=root/(_digest(header)+'.installed-shade-score-sources-v2.json');path.write_bytes(_canonical(header));path.chmod(0o600)
        values['original_pairs']=[dict(raw_score_sources_path=str(path))]
    monkeypatch.setattr(calibration,'validate_candidate_bundle',lambda *a,**kw:pytest.fail('missing or incompatible source inventory reached numerical fit replay'))
    with pytest.raises((ValueError,OSError)):calibration.build_source_calibration(**values)


@pytest.mark.parametrize('lost',['issue','outcome'])
def test_source_calibration_rechecks_originals_after_learning_summary(retained_source_calibration_case,monkeypatch,lost):
    from pathlib import Path
    from thermal_model import installed_shade_calibration as calibration
    values,_,_,args,backend=retained_source_calibration_case
    original=calibration._summarize
    def summarize_then_lose(*a,**kw):
        summary=original(*a,**kw)
        Path(args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]).unlink()
        return summary
    monkeypatch.setattr(calibration,'_summarize',summarize_then_lose)
    with pytest.raises((ValueError,OSError)):calibration.build_source_calibration(**values)


@pytest.mark.parametrize('case',['unchanged','readback_issue','index_issue','record_outcome'])
def test_source_calibration_storage_replays_originals_and_guards_actual_temporary_writes(retained_source_calibration_case,monkeypatch,case):
    from pathlib import Path
    from thermal_model import installed_shade_calibration as calibration,runtime_bundle
    import json
    assert hasattr(calibration,'write_source_calibration'),'missing original-query calibration retention'
    assert hasattr(calibration,'read_source_calibration'),'missing original-query calibration readback'
    values,root,_,args,backend=retained_source_calibration_case
    record=calibration.build_source_calibration(**values)
    archive=root/'calibration';archive.mkdir(mode=0o700)
    params={k:values[k] for k in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    original=runtime_bundle._write_private
    def write_then_lose(path,raw):
        original(path,raw);value=json.loads(raw)
        if case=='index_issue' and isinstance(value,list) and value and isinstance(value[0],dict) and 'raw_score_sources_path' in value[0]:
            Path(args['native_source_paths']['mass']).unlink()
        elif case=='record_outcome' and isinstance(value,dict) and value.get('schema')=='earthship-installed-shade-calibration/v3':
            Path(backend.native_source_paths[-1]).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',write_then_lose)
    if case in ('index_issue','record_outcome'):
        with pytest.raises((ValueError,OSError)):
            calibration.write_source_calibration(archive,record,**params,assessed_at=values['created_at'])
        assert not list(archive.glob('*.installed-shade-calibration-v3.json'))
        assert not list(archive.glob('.calibration-*'))
        if case=='index_issue':assert not list(archive.glob('*.installed-shade-calibration-sources-v3.json'))
    else:
        path=calibration.write_source_calibration(archive,record,**params,assessed_at=values['created_at'])
        assert path.name==record['calibration_sha256']+'.installed-shade-calibration-v3.json'
        assert path.stat().st_mode&0o777==0o600
        assert list(archive.glob('*.installed-shade-calibration-sources-v3.json'))
        for reader in (calibration.read_calibration,calibration.read_raw_calibration):
            with pytest.raises(ValueError):reader(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])
        if case=='readback_issue':Path(args['native_source_paths']['outdoor']).unlink()
        if case=='readback_issue':
            with pytest.raises((ValueError,OSError)):calibration.read_source_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])
        else:assert calibration.read_source_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])==record


def test_raw_calibration_index_bounds_paths_before_encoding(monkeypatch):
    from thermal_model import installed_shade_calibration as calibration
    monkeypatch.setattr(calibration,'_canonical',lambda *a,**kw:pytest.fail('invalid raw source path serialized before bounding'))
    with pytest.raises(ValueError):calibration._raw_packet_digest([dict(raw_score_sources_path='/'+'x'*1024)])


@pytest.fixture
def retained_compressed_calibration_case(source_calibration_origin_case,candidate,tmp_path,monkeypatch):
    return retained_source_calibration_case.__wrapped__(source_calibration_origin_case,candidate,tmp_path,monkeypatch,compressed=True)


def test_compressed_calibration_bad_inventory_refuses_before_fit(tmp_path,monkeypatch):
    from thermal_model import installed_shade_calibration as calibration
    api=getattr(calibration,'build_compressed_source_calibration',None)
    assert callable(api),'missing compressed calibration contract'
    tmp_path.chmod(0o700)
    monkeypatch.setattr(calibration,'validate_candidate_bundle',lambda *a,**kw:pytest.fail('missing compressed source reached numerical fit'))
    values=dict(bundle={},inputs={},expected_runtime_revision='1'*64,
        original_pairs=[dict(raw_score_sources_path=str(tmp_path/'missing'))],
        calibration_start='2026-10-08T00:00:00+00:00',calibration_end='2026-10-09T00:00:00+00:00',
        regimes=['warm'],created_at='2026-10-09T01:00:00+00:00')
    with pytest.raises((ValueError,OSError)):api(**values)


def test_compressed_calibration_keeps_independent_support_and_original_identity(retained_compressed_calibration_case):
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model.installed_shade_artifact import _digest
    assert hasattr(calibration,'build_compressed_source_calibration'),'missing compressed calibration contract'
    values,_,capture,_,_=retained_compressed_calibration_case
    record=calibration.build_compressed_source_calibration(**values)
    assert record['schema']=='earthship-installed-shade-calibration/v4'
    assert record['source_contract']=='earthship-installed-shade-score-sources/v6'
    assert record['summary']['bands']['1']['overall']['independent_days']==1
    assert record['summary']['bands']['1']['overall']['radius_f'] is None
    assert record['method']['minimum_independent_days']==35
    assert record['summary']['complete'] is False and record['release_authorized'] is False
    assert record['coverage_guaranteed'] is False
    assert record['source_pair_bindings'][0]['native_origin_binding_sha256']==_digest(capture['numeric_capture']['native_origin_binding'])
    parameters={k:values[k] for k in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    for validator in (calibration.validate_calibration,calibration.validate_raw_calibration,calibration.validate_source_calibration):
        with pytest.raises(ValueError):validator(record,**parameters,assessed_at=values['created_at'])


@pytest.mark.parametrize('lost',['issue','outcome'])
def test_compressed_calibration_rechecks_originals_after_learning(retained_compressed_calibration_case,monkeypatch,lost):
    from pathlib import Path
    from thermal_model import installed_shade_calibration as calibration
    assert hasattr(calibration,'build_compressed_source_calibration'),'missing compressed calibration contract'
    values,_,_,args,backend=retained_compressed_calibration_case
    original=calibration._summarize
    def changed(*args2,**kwargs):
        result=original(*args2,**kwargs)
        Path(args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]).unlink()
        return result
    monkeypatch.setattr(calibration,'_summarize',changed)
    with pytest.raises((ValueError,OSError)):calibration.build_compressed_source_calibration(**values)


@pytest.mark.parametrize('case',['unchanged','index_issue','record_outcome'])
def test_compressed_calibration_storage_guards_actual_write_and_typed_readback(retained_compressed_calibration_case,monkeypatch,case):
    from pathlib import Path
    import json
    from thermal_model import installed_shade_calibration as calibration,runtime_bundle
    assert hasattr(calibration,'build_compressed_source_calibration'),'missing compressed calibration contract'
    values,root,_,args,backend=retained_compressed_calibration_case
    record=calibration.build_compressed_source_calibration(**values)
    archive=root/'calibration';archive.mkdir(mode=0o700)
    params={k:values[k] for k in ('bundle','inputs','expected_runtime_revision','original_pairs')}
    original=runtime_bundle._write_private
    def changed(path,raw):
        original(path,raw);value=json.loads(raw)
        if case=='index_issue' and isinstance(value,list) and value and isinstance(value[0],dict) and 'raw_score_sources_path' in value[0]:
            Path(args['native_source_paths']['mass']).unlink()
        elif case=='record_outcome' and isinstance(value,dict) and value.get('schema')=='earthship-installed-shade-calibration/v4':
            Path(backend.native_source_paths[-1]).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    if case!='unchanged':
        with pytest.raises((ValueError,OSError)):calibration.write_compressed_source_calibration(archive,record,**params,assessed_at=values['created_at'])
        assert not list(archive.glob('*.installed-shade-calibration-v4.json'))
        assert not list(archive.glob('.calibration-*'))
        if case=='index_issue':assert not list(archive.glob('*.installed-shade-calibration-sources-v4.json'))
    else:
        path=calibration.write_compressed_source_calibration(archive,record,**params,assessed_at=values['created_at'])
        assert path.name==record['calibration_sha256']+'.installed-shade-calibration-v4.json'
        assert path.stat().st_mode&0o777==0o600
        assert calibration.read_compressed_source_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])==record
        for reader in (calibration.read_calibration,calibration.read_raw_calibration,calibration.read_source_calibration):
            with pytest.raises(ValueError):reader(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])
        Path(args['native_source_paths']['outdoor']).unlink()
        with pytest.raises((ValueError,OSError)):calibration.read_compressed_source_calibration(path,expected_runtime_revision=values['expected_runtime_revision'],assessed_at=values['created_at'])


@pytest.mark.parametrize('damage',['issue','outcome','old_profile'])
def test_compressed_calibration_missing_query_or_old_profile_refuses_before_fit(retained_compressed_calibration_case,monkeypatch,damage):
    from pathlib import Path
    import json
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model.installed_shade_artifact import _digest
    from thermal_model.forcing_capture import _canonical
    values,root,_,args,backend=retained_compressed_calibration_case
    if damage=='issue':Path(args['native_source_paths']['air']).unlink()
    elif damage=='outcome':Path(backend.native_source_paths[-1]).unlink()
    else:
        header=json.loads(Path(values['original_pairs'][0]['raw_score_sources_path']).read_text())
        header['schema']='earthship-installed-shade-score-sources/v4'
        path=root/(_digest(header)+'.installed-shade-score-sources-v4.json');path.write_bytes(_canonical(header));path.chmod(0o600)
        values['original_pairs']=[dict(raw_score_sources_path=str(path))]
    monkeypatch.setattr(calibration,'validate_candidate_bundle',lambda *a,**kw:pytest.fail('invalid compressed original reached numerical fit'))
    with pytest.raises((ValueError,OSError)):calibration.build_compressed_source_calibration(**values)


def test_compressed_calibration_inherits_expired_budget_after_fit(retained_compressed_calibration_case,monkeypatch):
    from thermal_model import installed_shade_calibration as calibration,installed_shade_qualification as qualification
    from thermal_model.replay_budget import shared_replay_budget
    values,_,_,_,_=retained_compressed_calibration_case
    remaining={'seconds':30.};fitted=[];original=calibration.validate_candidate_bundle
    def fit_then_expire(*args,**kwargs):
        result=original(*args,**kwargs);fitted.append(True);remaining['seconds']=0.;return result
    monkeypatch.setattr(calibration,'validate_candidate_bundle',fit_then_expire)
    monkeypatch.setattr(qualification,'score_compressed_source_base_packets',lambda *a,**kw:pytest.fail('expired fit budget reached score replay'))
    with shared_replay_budget(lambda:remaining['seconds']):
        with pytest.raises(ValueError):calibration.build_compressed_source_calibration(**values)
    assert fitted
