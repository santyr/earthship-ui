"""Raw numeric/main receipt contracts; synthetic delivery is not release proof."""
from copy import deepcopy
from datetime import datetime,timedelta
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
