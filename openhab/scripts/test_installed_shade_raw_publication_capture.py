"""Raw numeric/main receipt contracts; synthetic delivery is not release proof."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from test_installed_shade_raw_origin import candidate,raw_math_capture
from test_installed_shade_origin import outcome
from test_installed_shade_calibration import synthetic_cycle_grid
from test_installed_shade_score_collection import RawBackend
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture
def raw_delivered(raw_math_capture,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture;artifact=record['candidate'];issue=datetime.fromisoformat(record['issued_at'])
    root=tmp_path/'receipts';root.mkdir(mode=0o700)
    path=origin.write_raw_calibrated_capture(root,record)
    # Numerical receipt fixture only. No actual production builder or DB delivery.
    output=dict(schema='earthship-installed-shade-publication/v2',version=5,status='shadow',
        generatedAt=issue.isoformat(),validUntil=(issue+timedelta(minutes=10)).isoformat(),
        model=dict(createdAt=artifact['created_at'],trainedThrough=artifact['trained_through'],codeRevision=artifact['code_revision']),
        forecast=deepcopy(record['output']),confidence=dict(grade='low',actionLabels='withheld'),reasons=['Qualification incomplete'],
        release=dict(schema='earthship-installed-shade-release/v2',qualifiedAt=(issue+timedelta(seconds=3)).isoformat(),
            expiresAt=None,artifactSha256=artifact['artifact_sha256'],runtimeSha256=_digest(record['runtime']),
            policySha256=None,reportSha256='1'*64,originCaptureSha256=record['capture_sha256'],
            calibrationSha256=artifact['calibration']['calibration_sha256'],sensorEpochs=record['source_epochs'],
            sensorEpochSemantics='declared_hardware_phase',forecastQualified=False,advisoryQualified=False,automaticActuation=False))
    publisher.validate_raw_installed_publication(output)
    numeric=dict(item='Thermal_OriginalForecast_JSON',time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(record['output']).decode())
    actual=dict(item='Thermal_Model_JSON',time=int((issue+timedelta(seconds=3)).timestamp()*1000),state=_canonical(output).decode())
    monkeypatch.setattr(published,'_clock',lambda:issue+timedelta(seconds=4))
    capture=published.build_raw_publication_capture(path,numeric_publication=numeric,publication=actual)
    return root,capture,output,issue


def test_raw_publication_capture_has_distinct_version_and_legacy_readers_refuse(raw_delivered):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_publication as publisher
    _,record,output,_=raw_delivered
    assert record['schema']=='earthship-installed-shade-origin/v5'
    assert record['numeric_capture']['schema']=='earthship-installed-shade-origin/v4'
    assert record['numeric_capture']['candidate']['schema']=='earthship-installed-shade-candidate/v3'
    with pytest.raises(ValueError):published.validate_publication_capture(record)
    with pytest.raises(ValueError):publisher.validate_installed_publication(output)


@pytest.mark.parametrize('hours',[1,24])
def test_raw_main_scoring_binds_both_original_receipts(raw_delivered,hours):
    from thermal_model import installed_shade_published_origin as published
    _,record,_,issue=raw_delivered;target=issue+timedelta(hours=hours)
    result=published.score_raw_publication_capture(record,publication=record['publication'],horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v5'
    assert result['original_capture_sha256']==record['capture_sha256']
    assert result['numeric_capture_sha256']==record['numeric_capture']['capture_sha256']
    assert result['publication_sha256']==_digest(record['publication'])
    assert result['numeric_publication_sha256']==_digest(record['numeric_publication'])
    assert result['publication_mode']=='shadow' and result['release_authorized'] is False


@pytest.mark.parametrize('damage',['numeric_receipt','main_receipt','late_main','base_numeric'])
def test_rehashed_raw_publication_receipt_changes_are_refused(raw_delivered,damage):
    from thermal_model import installed_shade_published_origin as published
    _,record,_,_=raw_delivered;record=deepcopy(record)
    if damage=='numeric_receipt':record['numeric_publication']['state']='{}'
    elif damage=='main_receipt':record['publication']['state']=record['numeric_publication']['state']
    elif damage=='late_main':record['publication']['time']+=180000
    else:record['numeric_capture']['schema']='earthship-installed-shade-origin/v2'
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):published.validate_raw_publication_capture(record)


def test_raw_publication_private_storage_keeps_numeric_and_main_receipts(raw_delivered):
    from thermal_model import installed_shade_published_origin as published
    root,record,_,_=raw_delivered
    path=published.write_raw_publication_capture(root,record)
    assert path.name==record['capture_sha256']+'.installed-shade-origin-v5.json'
    assert path.stat().st_mode&0o777==0o600
    assert published.read_raw_publication_capture(path)==record
    assert list(root.glob('*.installed-shade-origin-v4.json'))
    with pytest.raises(ValueError):published.read_publication_capture(path)


def test_raw_publication_collection_replays_original_native_queries(raw_delivered,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue=raw_delivered;path=published.write_raw_publication_capture(root,record)
    backend=RawBackend(record,root)
    monkeypatch.setattr(collector,'_clock',lambda:issue+timedelta(hours=24,minutes=10))
    monkeypatch.setattr(collector,'ERRORS',())
    result=collector.collect_raw_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored' and len(backend.native_source_paths)==8
    header=json.loads(Path(result['raw_packet_path']).read_text())
    assert header['schema']=='earthship-installed-shade-score-sources/v3'
    replay=sources.read_calibrated_raw_score_sources(Path(result['raw_packet_path']),assessed_at=issue+timedelta(hours=24,minutes=10))
    assert replay['score']['schema']=='earthship-installed-shade-source-scored-pair/v5'
    assert replay['score_packet']['publication']==record['publication']
    with pytest.raises(ValueError):sources.read_raw_score_sources(Path(result['raw_packet_path']),assessed_at=issue+timedelta(hours=24,minutes=10))
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):sources.read_calibrated_raw_score_sources(Path(result['raw_packet_path']),assessed_at=issue+timedelta(hours=24,minutes=10))



def test_strong_collector_refuses_receipt_only_backend_and_legacy_dispatch(raw_delivered,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from test_installed_shade_score_collection import Backend
    root,record,_,issue=raw_delivered;path=published.write_raw_publication_capture(root,record)
    (root/'.installed-shade-live.lock').touch(mode=0o600)
    before=set(root.iterdir());backend=Backend(record)
    monkeypatch.setattr(collector,'_clock',lambda:issue+timedelta(hours=24,minutes=10))
    result=collector.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='withheld' and backend.calls==[] and set(root.iterdir())==before
    result=collector.collect_raw_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='withheld' and result['release_authorized'] is False
    assert set(root.iterdir())==before


def test_raw_v3_sources_refuse_rehashed_temperature_receipt_changes(raw_delivered,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue=raw_delivered;path=published.write_raw_publication_capture(root,record)
    monkeypatch.setattr(collector,'_clock',lambda:issue+timedelta(hours=24,minutes=10))
    backend=RawBackend(record,root)
    result=collector.collect_raw_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    header=json.loads(Path(result['raw_packet_path']).read_text())
    cached=header['score_sources']['outcome']['receipt'];snapshot=cached['snapshotSha256'];cached['temperatureF']+=2
    assert cached['snapshotSha256']==snapshot
    header['native_binding']['score_sources_sha256']=_digest(header['score_sources'])
    changed=root/(_digest(header)+'.installed-shade-score-sources-v3.json')
    changed.write_bytes(_canonical(header));changed.chmod(0o600)
    with pytest.raises(ValueError,match='cached receipts differ from retained raw selection'):
        sources.read_calibrated_raw_score_sources(changed,assessed_at=issue+timedelta(hours=24,minutes=10))


from test_installed_shade_raw_origin import source_origin_case,source_base_args


@pytest.fixture(params=['base','calibrated'])
def source_delivery_case(source_origin_case,tmp_path,monkeypatch,request):
    return source_origin_case,tmp_path,monkeypatch,request.param


def deliver_source(case,*,base_candidate=None,compressed=False):
    """Actual source archives with mathematical candidate and receipt fixtures."""
    source_origin_case,tmp_path,monkeypatch,kind=case
    from thermal_model import installed_shade_origin as base
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_calibrated_origin as calibrated
    assert hasattr(publisher,'validate_source_installed_publication'),'missing source-bound main publication profile'
    assert hasattr(published,'build_source_publication_capture'),'missing source-bound actual main receipt capture'
    prepared,args=source_origin_case
    if kind=='base':
        prepared,args=source_base_args(source_origin_case)
        if base_candidate is not None:prepared=base.PreparedCandidate(_canonical(base_candidate),args['issued_at'])
    if compressed:
        from test_installed_shade_raw_origin import compressed_base_args
        assert kind=='base'
        prepared,args=compressed_base_args(source_origin_case)
        if base_candidate is not None:prepared=base.PreparedCandidate(_canonical(base_candidate),args['issued_at'])
    record=(base.build_compressed_source_issued_capture if compressed else base.build_source_issued_capture if kind=='base' else calibrated.build_source_calibrated_capture)(prepared,**args)
    root=tmp_path/'receipts';root.mkdir(mode=0o700)
    path=(base.write_compressed_source_issued_capture if compressed else base.write_source_issued_capture if kind=='base' else calibrated.write_source_calibrated_capture)(root,record)
    artifact=record['candidate'];issue=args['issued_at'];binding=_digest(record['native_origin_binding'])
    output=dict(schema='earthship-installed-shade-publication/v3',version=6,status='shadow',
        generatedAt=issue.isoformat(),validUntil=(issue+timedelta(minutes=10)).isoformat(),
        model=dict(createdAt=artifact['created_at'],trainedThrough=artifact['trained_through'],codeRevision=artifact['code_revision']),
        forecast=deepcopy(record['output']),confidence=dict(grade='low',actionLabels='withheld'),reasons=['Qualification incomplete'],
        release=dict(schema='earthship-installed-shade-release/v3',qualifiedAt=(issue+timedelta(seconds=3)).isoformat(),expiresAt=None,
            artifactSha256=artifact['artifact_sha256'],runtimeSha256=_digest(record['runtime']),policySha256=None,reportSha256='1'*64,
            originCaptureSha256=record['capture_sha256'],calibrationSha256=None if kind=='base' else artifact['calibration']['calibration_sha256'],
            sensorEpochs=record['source_epochs'],sensorEpochSemantics='declared_hardware_phase',forecastQualified=False,
            advisoryQualified=False,automaticActuation=False,nativeOriginBindingSha256=binding,sourceQualificationSchema=None))
    if compressed:
        output.update(schema='earthship-installed-shade-publication/v4',version=7)
        output['release']['schema']='earthship-installed-shade-release/v4'
    (publisher.validate_compressed_source_installed_publication if compressed else publisher.validate_source_installed_publication)(output)
    numeric=dict(item='Thermal_OriginalForecast_JSON',time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(record['output']).decode())
    actual=dict(item='Thermal_Model_JSON',time=int((issue+timedelta(seconds=3)).timestamp()*1000),state=_canonical(output).decode())
    monkeypatch.setattr(published,'_clock',lambda:issue+timedelta(seconds=4))
    capture=(published.build_compressed_source_publication_capture if compressed else published.build_source_publication_capture)(path,numeric_publication=numeric,publication=actual)
    return root,capture,output,issue,kind,args


def test_source_main_capture_binds_query_proof_and_refuses_legacy_readers(source_delivery_case):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as published
    root,record,output,_,kind,_=deliver_source(source_delivery_case)
    version=9 if kind=='base' else 7
    assert record['schema']==f'earthship-installed-shade-origin/v{version}'
    assert output['release']['nativeOriginBindingSha256']==_digest(record['numeric_capture']['native_origin_binding'])
    path=published.write_source_publication_capture(root,record)
    assert path.name==record['capture_sha256']+f'.installed-shade-origin-v{version}.json'
    assert published.read_source_publication_capture(path)==record
    with pytest.raises(ValueError):published.validate_raw_publication_capture(record)
    with pytest.raises(ValueError):publisher.validate_raw_installed_publication(output)
    with pytest.raises(ValueError):published.read_raw_publication_capture(path)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_source_main_scoring_replays_queries_and_binds_both_actual_receipts(source_delivery_case,hours):
    from thermal_model import installed_shade_published_origin as published
    _,record,_,issue,kind,args=deliver_source(source_delivery_case);target=issue+timedelta(hours=hours)
    values=dict(publication=record['publication'],horizon_hours=hours,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    score=published.score_source_publication_capture(record,**values)
    assert score['schema']==f"earthship-installed-shade-source-scored-pair/v{9 if kind=='base' else 7}"
    assert score['original_capture_sha256']==record['capture_sha256']
    assert score['numeric_capture_sha256']==record['numeric_capture']['capture_sha256']
    assert score['publication_sha256']==_digest(record['publication'])
    assert score['numeric_publication_sha256']==_digest(record['numeric_publication'])
    assert score['native_origin_binding_sha256']==_digest(record['numeric_capture']['native_origin_binding'])
    Path(args['native_source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):published.score_source_publication_capture(record,**values)


@pytest.mark.parametrize('damage',['query_digest','numeric_receipt','late_main','deleted_source','old_numeric'])
def test_source_main_rehashed_receipt_or_query_changes_are_refused(source_delivery_case,damage):
    from thermal_model import installed_shade_published_origin as published
    _,original,output,_,_,args=deliver_source(source_delivery_case);record=deepcopy(original)
    if damage=='query_digest':
        output=deepcopy(output);output['release']['nativeOriginBindingSha256']='a'*64
        record['publication']['state']=_canonical(output).decode()
    elif damage=='numeric_receipt':record['numeric_publication']['state']='{}'
    elif damage=='late_main':record['publication']['time']+=180000
    elif damage=='deleted_source':Path(args['native_source_paths']['mass']).unlink()
    else:record['numeric_capture']['schema']='earthship-installed-shade-origin/v4'
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises((ValueError,OSError)):published.validate_source_publication_capture(record)


def test_source_main_cannot_claim_activation_from_old_qualification(source_delivery_case):
    from thermal_model import installed_shade_publication as publisher
    _,_,output,issue,_,_=deliver_source(source_delivery_case);value=deepcopy(output)
    value['status']='forecast_active';value['confidence']['grade']='high';value['release']['forecastQualified']=True
    value['release']['policySha256']='2'*64;value['release']['expiresAt']=(issue+timedelta(hours=1)).isoformat()
    value['release']['sourceQualificationSchema']='earthship-installed-shade-qualification-report/v5'
    with pytest.raises(ValueError):publisher.validate_source_installed_publication(value)


def test_source_main_unavailable_carries_no_original_query_or_qualification_claim():
    from datetime import timezone
    from thermal_model import installed_shade_publication as publisher
    value=publisher.unavailable_source_installed_publication(datetime(2026,10,8,12,tzinfo=timezone.utc))
    assert value['schema']=='earthship-installed-shade-publication/v3' and value['version']==6
    assert value['status']=='unavailable' and value['forecast'] is None
    assert value['release']['nativeOriginBindingSha256'] is None
    assert value['release']['sourceQualificationSchema'] is None
    for field in ('nativeOriginBindingSha256','sourceQualificationSchema'):
        changed=deepcopy(value);changed['release'][field]='a'*64 if field=='nativeOriginBindingSha256' else publisher.SOURCE_QUALIFICATION_SCHEMA
        with pytest.raises(ValueError):publisher.validate_source_installed_publication(changed)


@pytest.mark.parametrize('source_delivery_case',['base'],indirect=True)
def test_source_main_base_cannot_activate_even_with_q6_marker(source_delivery_case):
    from thermal_model import installed_shade_publication as publisher
    _,_,output,issue,_,_=deliver_source(source_delivery_case);value=deepcopy(output)
    value['status']='forecast_active';value['confidence']['grade']='high'
    value['release'].update(forecastQualified=True,policySha256='2'*64,calibrationSha256='3'*64,
        expiresAt=(issue+timedelta(hours=1)).isoformat(),sourceQualificationSchema=publisher.SOURCE_QUALIFICATION_SCHEMA)
    with pytest.raises(ValueError):publisher.validate_source_installed_publication(value)


def test_source_main_refuses_query_loss_during_temporary_main_capture_write(source_delivery_case,monkeypatch):
    from thermal_model import installed_shade_published_origin as published,runtime_bundle
    root,record,_,_,kind,args=deliver_source(source_delivery_case);original=runtime_bundle._write_private
    def lost(path,raw):
        original(path,raw);Path(args['native_source_paths']['outdoor']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',lost)
    with pytest.raises((ValueError,OSError)):published.write_source_publication_capture(root,record)
    assert not list(root.glob(f"*.installed-shade-origin-v{9 if kind=='base' else 7}.json"))
    assert not list(root.glob('.calibration-*'))


@pytest.mark.parametrize('damage',[None,'issue_query','outcome_query','origin_digest'])
def test_source_score_archive_replays_issue_and_outcome_queries(source_delivery_case,monkeypatch,damage):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    assert hasattr(collector,'collect_source_published_score'),'missing query-bound scoring collector'
    assert hasattr(sources,'read_source_score_sources'),'missing query-bound scoring reader'
    root,record,_,issue,kind,args=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now)
    monkeypatch.setattr(collector,'ERRORS',())
    backend=RawBackend(record,root)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored' and result['release_authorized'] is False
    raw_path=Path(result['raw_packet_path']);header=json.loads(raw_path.read_text())
    assert header['schema']==('earthship-installed-shade-score-sources/v4' if kind=='base' else 'earthship-installed-shade-score-sources/v5')
    assert header['release_authority'] is False
    assert header['native_origin_binding_sha256']==_digest(record['numeric_capture']['native_origin_binding'])
    for reader in (sources.read_raw_score_sources,sources.read_calibrated_raw_score_sources):
        with pytest.raises(ValueError):reader(raw_path,assessed_at=now)
    if damage=='issue_query':Path(args['native_source_paths']['air']).unlink()
    elif damage=='outcome_query':Path(backend.native_source_paths[-1]).unlink()
    elif damage=='origin_digest':
        header['native_origin_binding_sha256']='0'*64
        raw_path=root/(_digest(header)+('.installed-shade-score-sources-v4.json' if kind=='base' else '.installed-shade-score-sources-v5.json'))
        raw_path.write_bytes(_canonical(header));raw_path.chmod(0o600)
    if damage is not None:
        with pytest.raises((ValueError,OSError)):sources.read_source_score_sources(raw_path,assessed_at=now)
    else:
        replay=sources.read_source_score_sources(raw_path,assessed_at=now)
        assert replay['score']['publication_sha256']==_digest(record['publication'])
        assert replay['score']['numeric_publication_sha256']==_digest(record['numeric_publication'])
        assert replay['score']['native_origin_binding_sha256']==header['native_origin_binding_sha256']
        assert replay['score']==json.loads(Path(result['score_path']).read_text())


@pytest.mark.parametrize('lost',['source','guard'])
def test_source_score_archive_rechecks_after_actual_temporary_write(source_delivery_case,monkeypatch,lost):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import runtime_bundle
    root,record,_,issue,kind,args=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now)
    backend=RawBackend(record,root)
    original=runtime_bundle._write_private
    def write_then_lose(target,raw):
        original(target,raw)
        value=json.loads(raw)
        if isinstance(value,dict) and value.get('schema') in (
                'earthship-installed-shade-score-sources/v4','earthship-installed-shade-score-sources/v5'):
            if lost=='source':Path(args['native_source_paths']['mass']).unlink()
            else:backend.damage='configuration'
    monkeypatch.setattr(runtime_bundle,'_write_private',write_then_lose)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='withheld' and result['release_authorized'] is False
    assert not list(root.glob('*.installed-shade-score-sources-v4.json'))
    assert not list(root.glob('*.installed-shade-score-sources-v5.json'))
    assert not list(root.glob('.calibration-*'))



def test_source_score_reader_refuses_outcome_source_lost_during_numerical_replay(source_delivery_case,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue,_,_=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now)
    backend=RawBackend(record,root)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    original=published.score_source_publication_capture
    def score_then_lose(*args,**kwargs):
        score=original(*args,**kwargs)
        Path(backend.native_source_paths[-1]).unlink()
        return score
    monkeypatch.setattr(published,'score_source_publication_capture',score_then_lose)
    with pytest.raises((ValueError,OSError)):
        sources.read_source_score_sources(Path(result['raw_packet_path']),assessed_at=now)


@pytest.mark.parametrize('lost',[None,'issue','outcome'])
def test_source_queue_replays_typed_completion_and_never_recollects_lost_sources(source_delivery_case,monkeypatch,lost):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_score_jobs as jobs
    assert hasattr(jobs,'collect_source_queued_score'),'missing original-query score queue'
    root,record,_,issue,_,args=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now);monkeypatch.setattr(jobs,'_clock',lambda:now)
    job=dict(origin_path=str(path),horizon_hours=1)
    queue=root/'jobs.json';queue.write_bytes(_canonical(dict(schema='earthship-installed-score-jobs/v3',jobs=[job])));queue.chmod(0o600)
    backend=RawBackend(record,root)
    before=set(root.iterdir())
    for old in (jobs.collect_queued_score,jobs.collect_raw_queued_score):
        assert old(queue_path=queue,output_directory=root,backend=backend)['status']=='withheld'
    assert set(root.iterdir())==before and backend.native_source_paths==[]
    result=jobs.collect_source_queued_score(queue_path=queue,output_directory=root,backend=backend)
    assert result['status']=='scored' and result['release_authorized'] is False
    marker=root/(_digest(job)+'.score-job-v3.json');saved=json.loads(marker.read_text())
    assert saved['schema']=='earthship-installed-score-job-completion/v3'
    assert saved['job']==job and saved['release_authority'] is False
    assert saved['raw_score_sources_sha256']==_digest(json.loads(Path(result['raw_packet_path']).read_text()))
    retained=list(backend.native_source_paths)
    if lost=='issue':Path(args['native_source_paths']['mass']).unlink()
    elif lost=='outcome':Path(retained[-1]).unlink()
    replay=jobs.collect_source_queued_score(queue_path=queue,output_directory=root,backend=backend)
    assert replay['status']==('completion_verified' if lost is None else 'withheld')
    assert replay['release_authorized'] is False and backend.native_source_paths==retained


def test_source_queue_deadline_reaches_original_query_replay_before_numerical_work(source_delivery_case,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_score_jobs as jobs
    from thermal_model import installed_shade_raw_score_sources as sources
    from thermal_model import installed_shade_origin as base
    assert hasattr(jobs,'collect_source_queued_score'),'missing original-query score queue'
    root,record,_,issue,_,_=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);clock={'seconds':0.}
    monkeypatch.setattr(collector,'_clock',lambda:now);monkeypatch.setattr(jobs,'_clock',lambda:now)
    monkeypatch.setattr(jobs,'monotonic',lambda:clock['seconds'])
    queue=root/'jobs.json';queue.write_bytes(_canonical(dict(schema='earthship-installed-score-jobs/v3',jobs=[dict(origin_path=str(path),horizon_hours=1)])));queue.chmod(0o600)
    replay=sources.replay_temperature_source
    def replay_then_expire(*args,**kwargs):
        grid=replay(*args,**kwargs);clock['seconds']=56.;return grid
    monkeypatch.setattr(sources,'replay_temperature_source',replay_then_expire)
    prediction=base._prediction
    def guarded_prediction(*args,**kwargs):
        if clock['seconds']>=55:pytest.fail('numerical work continued after the shared queue deadline')
        return prediction(*args,**kwargs)
    monkeypatch.setattr(base,'_prediction',guarded_prediction)
    backend=RawBackend(record,root)
    result=jobs.collect_source_queued_score(queue_path=queue,output_directory=root,backend=backend)
    assert result['status']=='withheld' and result['release_authorized'] is False
    assert not backend.native_source_paths and not list(root.glob('*.score-job-v3.json'))


@pytest.mark.parametrize('lost',['source','queue'])
def test_source_queue_cannot_publish_completion_after_temporary_write_loses_sources(source_delivery_case,monkeypatch,lost):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_score_jobs as jobs
    from thermal_model import runtime_bundle
    root,record,_,issue,_,args=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now);monkeypatch.setattr(jobs,'_clock',lambda:now)
    queue=root/'jobs.json';queue.write_bytes(_canonical(dict(schema='earthship-installed-score-jobs/v3',jobs=[dict(origin_path=str(path),horizon_hours=1)])));queue.chmod(0o600)
    original=runtime_bundle._write_private
    def write_then_lose(target,raw):
        original(target,raw);value=json.loads(raw)
        if isinstance(value,dict) and value.get('schema')=='earthship-installed-score-job-completion/v3':
            if lost=='source':Path(args['native_source_paths']['air']).unlink()
            else:queue.write_bytes(_canonical(dict(schema='earthship-installed-score-jobs/v3',jobs=[])))
    monkeypatch.setattr(runtime_bundle,'_write_private',write_then_lose)
    backend=RawBackend(record,root)
    result=jobs.collect_source_queued_score(queue_path=queue,output_directory=root,backend=backend)
    assert result['status']=='withheld' and result['release_authorized'] is False
    assert not list(root.glob('*.score-job-v3.json')) and not list(root.glob('.calibration-*'))


@pytest.mark.parametrize('damage',[None,'missing_issue','oversized_issue'])
def test_source_pair_replay_binds_issue_queries_and_bounds_them_before_math(source_delivery_case,monkeypatch,damage):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model import installed_shade_raw_score_sources as sources
    assert hasattr(qualification,'score_source_base_packets'),'missing source-pair replay for calibration'
    assert hasattr(qualification,'score_source_calibrated_packets'),'missing source-pair replay for release'
    root,record,_,issue,kind,args=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=RawBackend(record,root))
    assert result['status']=='scored'
    pairs=[dict(raw_score_sources_path=result['raw_packet_path'])]
    replay=qualification.score_source_base_packets if kind=='base' else qualification.score_source_calibrated_packets
    for old in (4,5):
        with pytest.raises(ValueError):qualification._score_packets(pairs,assessed_at=now,version=old)
    if damage is not None:
        query=Path(args['native_source_paths']['mass'])
        if damage=='missing_issue':query.unlink()
        else:
            with query.open('r+b') as file:file.truncate(8*1024*1024+1)
        def forbidden(*a,**kw):pytest.fail('unbounded or missing issue query reached numerical replay')
        monkeypatch.setattr(sources,'read_source_base_score_sources',forbidden)
        monkeypatch.setattr(sources,'read_source_calibrated_score_sources',forbidden)
        with pytest.raises((ValueError,OSError)):replay(pairs,assessed_at=now)
    else:
        scored=replay(pairs,assessed_at=now)
        assert scored['raw_native_issue_sources'] is True and scored['raw_native_score_sources'] is True
        assert scored['rows'][0]['persistence_error_f']==pytest.approx(-2.)
        # Seven flat historical cycles add zero change to issue air71;
        # both baselines therefore predict71 against the later outcome73.
        assert scored['rows'][0]['recent_cycle_error_f']==pytest.approx(-2.)
        assert scored['calibrated_intervals'] is (kind=='calibrated')
        assert scored['bindings'][0]['native_origin_binding_sha256']==_digest(record['numeric_capture']['native_origin_binding'])


def test_source_pair_replay_owns_nested_deadline_before_numerical_work(source_delivery_case,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model import installed_shade_raw_score_sources as sources
    from thermal_model import installed_shade_origin as base
    assert hasattr(qualification,'score_source_base_packets'),'missing source-pair replay for calibration'
    root,record,_,issue,kind,_=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=RawBackend(record,root))
    assert result['status']=='scored'
    clock={'seconds':0.};monkeypatch.setattr(qualification,'_replay_time',lambda:clock['seconds'])
    original=sources.replay_temperature_source
    def replay_then_expire(*args,**kwargs):
        value=original(*args,**kwargs);clock['seconds']=61.;return value
    monkeypatch.setattr(sources,'replay_temperature_source',replay_then_expire)
    prediction=base._prediction
    def guarded_prediction(*args,**kwargs):
        if clock['seconds']>=60:pytest.fail('source numerical work continued after qualification replay deadline')
        return prediction(*args,**kwargs)
    monkeypatch.setattr(base,'_prediction',guarded_prediction)
    replay=qualification.score_source_base_packets if kind=='base' else qualification.score_source_calibrated_packets
    with pytest.raises(ValueError):replay([dict(raw_score_sources_path=result['raw_packet_path'])],assessed_at=now)



def test_source_pair_replay_counts_aggregate_issue_query_bytes_before_math(source_delivery_case,monkeypatch):
    """Sparse inventory fixtures prove admission bounds, never source validity."""
    import os
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue,kind,_=deliver_source(source_delivery_case)
    path=published.write_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    result=collector.collect_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=RawBackend(record,root))
    assert result['status']=='scored'
    header=json.loads(Path(result['raw_packet_path']).read_text());references=[]
    for index in range(6):
        capture=deepcopy(record);numeric=capture['numeric_capture'];binding=numeric['native_origin_binding']
        for role in ('air','mass','outdoor'):
            query=root/(_digest([index,role])+'.native-temperature-sources-v1.json')
            fd=os.open(query,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:os.ftruncate(fd,8*1024*1024)
            finally:os.close(fd)
            binding['query_sources'][role]=str(query)
        digest=_digest(binding);numeric['output']['native_origin_binding_sha256']=digest
        numeric['capture_sha256']=_digest({k:v for k,v in numeric.items() if k!='capture_sha256'})
        capture['numeric_publication']['state']=_canonical(numeric['output']).decode()
        main=json.loads(capture['publication']['state']);main['forecast']=deepcopy(numeric['output'])
        main['release'].update(nativeOriginBindingSha256=digest,originCaptureSha256=numeric['capture_sha256'])
        capture['publication']['state']=_canonical(main).decode()
        capture['capture_sha256']=_digest({k:v for k,v in capture.items() if k!='capture_sha256'})
        origin=root/(capture['capture_sha256']+('.installed-shade-origin-v9.json' if kind=='base' else '.installed-shade-origin-v7.json'))
        origin.write_bytes(_canonical(capture));origin.chmod(0o600)
        packet=deepcopy(header);packet['native_origin_binding_sha256']=digest
        packet['score_sources'].update(origin_path=str(origin),publication=capture['publication'])
        packet['native_binding']['score_sources_sha256']=_digest(packet['score_sources'])
        source=root/(_digest(packet)+('.installed-shade-score-sources-v4.json' if kind=='base' else '.installed-shade-score-sources-v5.json'))
        source.write_bytes(_canonical(packet));source.chmod(0o600)
        references.append(dict(raw_score_sources_path=str(source)))
    def forbidden(*a,**kw):pytest.fail('aggregate issue-query inventory reached numerical replay')
    monkeypatch.setattr(sources,'read_source_base_score_sources',forbidden)
    monkeypatch.setattr(sources,'read_source_calibrated_score_sources',forbidden)
    replay=qualification.score_source_base_packets if kind=='base' else qualification.score_source_calibrated_packets
    with pytest.raises(ValueError,match='aggregate raw queries'):replay(references,assessed_at=now)


class CompressedRawBackend(RawBackend):
    def native(self,*args,**kwargs):
        from weather_temperature_sources import read_temperature_source,write_compressed_temperature_source
        rows=super().native(*args,**kwargs)
        path=Path(self.native_source_paths[-1])
        self.native_source_paths[-1]=str(write_compressed_temperature_source(path.parent,read_temperature_source(path.parent,path)))
        return rows


def compressed_delivery(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    assert hasattr(published,'build_compressed_source_publication_capture'),'missing compressed main receipt capture'
    return deliver_source((source_origin_case,tmp_path,monkeypatch,'base'),compressed=True)


def test_compressed_main_capture_binds_actual_receipts_and_refuses_old_readers(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_publication as publisher
    root,record,output,_,_,_=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    assert record['schema']=='earthship-installed-shade-origin/v11'
    assert record['numeric_capture']['schema']=='earthship-installed-shade-origin/v10'
    path=published.write_compressed_source_publication_capture(root,record)
    assert published.read_compressed_source_publication_capture(path)==record
    with pytest.raises(ValueError):published.read_source_publication_capture(path)
    with pytest.raises(ValueError):published.validate_source_publication_capture(record)
    with pytest.raises(ValueError):publisher.validate_source_installed_publication(output)


def test_compressed_main_scoring_replays_original_and_binds_both_receipts(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    _,record,_,issue,_,args=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    target=issue+timedelta(hours=1)
    values=dict(publication=record['publication'],horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,1),assessed_at=target+timedelta(minutes=10))
    score=published.score_compressed_source_publication_capture(record,**values)
    assert score['schema']=='earthship-installed-shade-source-scored-pair/v11'
    assert score['numeric_publication_sha256']==_digest(record['numeric_publication'])
    assert score['publication_sha256']==_digest(record['publication'])
    Path(args['native_source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):published.score_compressed_source_publication_capture(record,**values)


def test_compressed_score_archive_replays_issue_comparator_outcome_sources(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published,installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue,_,args=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    path=published.write_compressed_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now);monkeypatch.setattr(collector,'ERRORS',())
    result=collector.collect_compressed_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=CompressedRawBackend(record,root))
    assert result['status']=='scored' and result['release_authorized'] is False
    raw=Path(result['raw_packet_path']);header=json.loads(raw.read_text())
    assert header['schema']=='earthship-installed-shade-score-sources/v6'
    assert header['native_binding']['schema']=='earthship-installed-shade-native-score-binding/v2'
    replay=sources.read_compressed_source_base_score_sources(raw,assessed_at=now)
    assert replay['score']==json.loads(Path(result['score_path']).read_text())
    with pytest.raises(ValueError):sources.read_source_score_sources(raw,assessed_at=now)
    Path(args['native_source_paths']['mass']).unlink()
    with pytest.raises((ValueError,OSError)):sources.read_compressed_source_base_score_sources(raw,assessed_at=now)


def test_compressed_main_capture_refuses_source_lost_during_actual_temp_write(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published,runtime_bundle
    root,record,_,_,_,args=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    original=runtime_bundle._write_private
    def changed(path,raw):
        original(path,raw)
        if b'"schema":"earthship-installed-shade-origin/v11"' in raw:Path(args['native_source_paths']['outdoor']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    with pytest.raises((ValueError,OSError)):published.write_compressed_source_publication_capture(root,record)
    assert not list(root.glob('*.installed-shade-origin-v11.json'))
    assert not list(root.glob('.calibration-*'))


def test_compressed_main_cannot_activate_from_legacy_qualification_marker(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    _,_,output,_,_,_=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    output['release']['sourceQualificationSchema']='earthship-installed-shade-qualification-report/v6'
    with pytest.raises(ValueError):publisher.validate_compressed_source_installed_publication(output)


def test_compressed_main_unavailable_has_no_proof_claim():
    from thermal_model import installed_shade_publication as publisher
    assert hasattr(publisher,'unavailable_compressed_source_installed_publication'),'missing compressed unavailable contract'
    output=publisher.unavailable_compressed_source_installed_publication(datetime(2026,10,8,tzinfo=timezone.utc))
    assert output['schema']=='earthship-installed-shade-publication/v4' and output['version']==7
    assert output['status']=='unavailable' and output['forecast'] is None
    assert output['release']['nativeOriginBindingSha256'] is None and output['release']['sourceQualificationSchema'] is None


@pytest.mark.parametrize('lost',['issue','outcome'])
def test_compressed_score_archive_refuses_original_lost_after_actual_temp_write(source_origin_case,tmp_path,monkeypatch,lost):
    from thermal_model import installed_shade_published_origin as published,installed_shade_score_collection as collector,runtime_bundle
    root,record,_,issue,_,args=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    path=published.write_compressed_source_publication_capture(root,record)
    backend=CompressedRawBackend(record,root);now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now)
    original=runtime_bundle._write_private;written=[]
    def changed(path,raw):
        original(path,raw)
        if b'"schema":"earthship-installed-shade-score-sources/v6"' in raw:
            written.append(path)
            target=args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]
            Path(target).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',changed)
    result=collector.collect_compressed_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert written and result==dict(status='withheld',release_authorized=False)
    assert not list(root.glob('*.installed-shade-score-sources-v6.json'))
    assert not list(root.glob('.calibration-*'))


def test_compressed_score_readback_refuses_outcome_lost_after_numerical_replay(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published,installed_shade_score_collection as collector
    from thermal_model import installed_shade_raw_score_sources as sources
    root,record,_,issue,_,_=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    path=published.write_compressed_source_publication_capture(root,record)
    backend=CompressedRawBackend(record,root);now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(collector,'_clock',lambda:now)
    result=collector.collect_compressed_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    original=published.score_compressed_source_publication_capture;replayed=[]
    def changed(*args,**kwargs):
        score=original(*args,**kwargs);replayed.append(score)
        Path(backend.native_source_paths[-1]).unlink();return score
    monkeypatch.setattr(published,'score_compressed_source_publication_capture',changed)
    with pytest.raises((ValueError,OSError)):sources.read_compressed_source_base_score_sources(Path(result['raw_packet_path']),assessed_at=now)
    assert replayed


def test_compressed_base_cannot_activate_even_with_new_qualification_marker(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    _,_,output,_,_,_=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    output['status']='forecast_active';output['release']['sourceQualificationSchema']='earthship-installed-shade-qualification-report/v7'
    with pytest.raises(ValueError,match='uncalibrated'):publisher.validate_compressed_source_installed_publication(output)


def compressed_cohort_case(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as published,installed_shade_score_collection as collector
    root,record,_,issue,_,args=compressed_delivery(source_origin_case,tmp_path,monkeypatch)
    path=published.write_compressed_source_publication_capture(root,record)
    now=issue+timedelta(hours=24,minutes=10);monkeypatch.setattr(collector,'_clock',lambda:now)
    backend=CompressedRawBackend(record,root)
    result=collector.collect_compressed_source_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    return root,record,args,now,result,backend


@pytest.mark.parametrize('damage',[None,'missing_issue','oversized_issue','duplicate_archive'])
def test_compressed_cohort_admits_originals_before_math_and_replays_exact_scores(source_origin_case,tmp_path,monkeypatch,damage):
    from thermal_model import installed_shade_qualification as qualification,installed_shade_raw_score_sources as sources
    replay=getattr(qualification,'score_compressed_source_base_packets',None)
    assert callable(replay),'missing compressed cohort scoring admission'
    _,record,args,now,result,_=compressed_cohort_case(source_origin_case,tmp_path,monkeypatch)
    references=[dict(raw_score_sources_path=result['raw_packet_path'])]
    for old in (qualification.score_source_base_packets,qualification.score_source_calibrated_packets):
        with pytest.raises(ValueError):old(references,assessed_at=now)
    if damage is not None:
        if damage=='missing_issue':Path(args['native_source_paths']['mass']).unlink()
        elif damage=='oversized_issue':
            from weather_temperature_sources import MAX_CONTAINER_BYTES
            with Path(args['native_source_paths']['mass']).open('r+b') as file:file.truncate(MAX_CONTAINER_BYTES+1)
        else:references*=2
        def forbidden(*a,**kw):pytest.fail('invalid compressed inventory reached numerical replay')
        monkeypatch.setattr(sources,'read_compressed_source_base_score_sources',forbidden)
        with pytest.raises((ValueError,OSError)):replay(references,assessed_at=now)
    else:
        identity=dict(artifact_sha256=record['numeric_capture']['candidate']['artifact_sha256'],
            runtime_sha256=_digest(record['numeric_capture']['runtime']),sensor_epochs=record['numeric_capture']['source_epochs'])
        scored=replay(references,assessed_at=now,candidate=identity)
        assert scored['raw_native_issue_sources'] is True and scored['raw_native_score_sources'] is True
        assert scored['rows'][0]['persistence_error_f']==pytest.approx(-2.)
        assert scored['rows'][0]['recent_cycle_error_f']==pytest.approx(-2.)
        assert scored['calibrated_intervals'] is False
        assert scored['bindings'][0]['native_origin_binding_sha256']==_digest(record['numeric_capture']['native_origin_binding'])


def test_compressed_cohort_inherits_deadline_before_numerical_work(source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_qualification as qualification,installed_shade_raw_score_sources as sources,installed_shade_origin as base
    replay=getattr(qualification,'score_compressed_source_base_packets',None)
    assert callable(replay),'missing compressed cohort scoring admission'
    _,_,_,now,result,_=compressed_cohort_case(source_origin_case,tmp_path,monkeypatch)
    clock={'seconds':0.};monkeypatch.setattr(qualification,'_replay_time',lambda:clock['seconds'])
    original=sources.replay_temperature_source
    def expire(*args,**kwargs):
        value=original(*args,**kwargs);clock['seconds']=61.;return value
    monkeypatch.setattr(sources,'replay_temperature_source',expire)
    prediction=base._prediction
    def guarded(*args,**kwargs):
        if clock['seconds']>=60:pytest.fail('compressed source math continued after cohort deadline')
        return prediction(*args,**kwargs)
    monkeypatch.setattr(base,'_prediction',guarded)
    with pytest.raises(ValueError):replay([dict(raw_score_sources_path=result['raw_packet_path'])],assessed_at=now)


def test_compressed_cohort_bounds_aggregate_physical_query_storage_before_math(source_origin_case,tmp_path,monkeypatch):
    import os
    from weather_temperature_sources import MAX_CONTAINER_BYTES
    from thermal_model import installed_shade_qualification as qualification,installed_shade_raw_score_sources as sources
    replay=getattr(qualification,'score_compressed_source_base_packets',None)
    assert callable(replay),'missing compressed cohort scoring admission'
    root,record,_,now,result,_=compressed_cohort_case(source_origin_case,tmp_path,monkeypatch)
    header=json.loads(Path(result['raw_packet_path']).read_text());references=[]
    # Sparse metadata fixtures exercise physical admission, not source validity.
    for index in range(6):
        capture=deepcopy(record);numeric=capture['numeric_capture'];binding=numeric['native_origin_binding']
        for role in ('air','mass','outdoor'):
            query=root/(_digest([index,role])+'.native-temperature-sources-v2.json.gz')
            fd=os.open(query,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:os.ftruncate(fd,MAX_CONTAINER_BYTES)
            finally:os.close(fd)
            binding['query_sources'][role]=str(query)
        digest=_digest(binding);numeric['output']['native_origin_binding_sha256']=digest
        numeric['capture_sha256']=_digest({k:v for k,v in numeric.items() if k!='capture_sha256'})
        capture['numeric_publication']['state']=_canonical(numeric['output']).decode()
        main=json.loads(capture['publication']['state']);main['forecast']=deepcopy(numeric['output'])
        main['release'].update(nativeOriginBindingSha256=digest,originCaptureSha256=numeric['capture_sha256'])
        capture['publication']['state']=_canonical(main).decode()
        capture['capture_sha256']=_digest({k:v for k,v in capture.items() if k!='capture_sha256'})
        origin=root/(capture['capture_sha256']+'.installed-shade-origin-v11.json');origin.write_bytes(_canonical(capture));origin.chmod(0o600)
        packet=deepcopy(header);packet['native_origin_binding_sha256']=digest
        packet['score_sources'].update(origin_path=str(origin),publication=capture['publication'])
        packet['native_binding']['score_sources_sha256']=_digest(packet['score_sources'])
        source=root/(_digest(packet)+'.installed-shade-score-sources-v6.json');source.write_bytes(_canonical(packet));source.chmod(0o600)
        references.append(dict(raw_score_sources_path=str(source)))
    def forbidden(*a,**kw):pytest.fail('oversized compressed physical inventory reached numerical replay')
    monkeypatch.setattr(sources,'read_compressed_source_base_score_sources',forbidden)
    with pytest.raises(ValueError,match='aggregate raw queries'):replay(references,assessed_at=now)
