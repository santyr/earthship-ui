"""Pure qualification accounting; no production services or containers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import thermal_qualification_evidence as evidence


def pair(issue, *, hours=24, artifact='a'*64, error=1, baseline=2, recent=3):
    return dict(issue_at=issue.isoformat(), target_at=(issue.astimezone(timezone.utc)+timedelta(hours=hours)).isoformat(),
        artifact_sha256=artifact, revision='b'*12, model_metadata_id='c'*64,
        confidence='low', model_error_f=error, persistence_error_f=baseline,
        interval_covered=True, interval_width_f=4, outdoor_forecast_error_f=None,
        nonoverlap_selected=False,
        recent_cycle_baseline=dict(status='available', signed_error_f=recent))


def test_overlapping_rows_do_not_inflate_independent_windows():
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc)
    rows=[pair(origin), pair(origin+timedelta(hours=1),error=99),
          pair(origin+timedelta(days=1),error=-3)]
    report=evidence.summarize_pairs(rows,horizon_hours=24,artifact_sha256='a'*64)
    assert report['raw_pair_count']==3
    assert report['independent_window_count']==2
    assert report['metrics']['model']==dict(mae_f=2,rmse_f=pytest.approx(5**0.5),bias_f=-1)
    assert report['metrics']['persistence']==dict(mae_f=2,rmse_f=2,bias_f=2)
    assert report['metrics']['recent_cycle']==dict(mae_f=3,rmse_f=3,bias_f=3)
    assert report['release_qualification_claimed'] is False


def test_single_candidate_is_not_pooled_with_other_revisions():
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc)
    rows=[pair(origin),pair(origin+timedelta(days=1),artifact='d'*64,error=40)]
    report=evidence.summarize_pairs(rows,horizon_hours=24,artifact_sha256='a'*64)
    assert report['raw_pair_count']==1
    assert report['independent_window_count']==1
    assert report['metrics']['model']['mae_f']==1
    assert report['excluded_other_artifact_count']==1
    with pytest.raises(ValueError,match='single artifact'):
        evidence.summarize_pairs(rows,horizon_hours=24)


def test_local_days_do_not_replace_utc_independence_across_dst():
    zone=ZoneInfo('America/Denver')
    rows=[pair(datetime(2026,3,day,8,45,tzinfo=zone)) for day in (7,8,9)]
    report=evidence.summarize_pairs(rows,horizon_hours=24)
    assert report['unique_local_days']==3
    assert report['independent_window_count']==2


def test_independent_windows_with_missing_comparator_are_not_imputed():
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc)
    row=pair(origin);row['recent_cycle_baseline']={'status':'insufficient_qualified_history'}
    report=evidence.summarize_pairs([row],horizon_hours=24)
    assert report['independent_window_count']==1
    assert report['paired_three_predictor_count']==0
    assert report['metrics']['recent_cycle'] is None


@pytest.mark.parametrize('damage',['duplicate','naive','future_target','nonfinite','boolean','artifact'])
def test_invalid_pair_cannot_become_evidence(damage):
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc)
    rows=[pair(origin)]
    if damage=='duplicate':rows.append(deepcopy(rows[0]))
    elif damage=='naive':rows[0]['issue_at']=origin.replace(tzinfo=None).isoformat()
    elif damage=='future_target':rows[0]['target_at']=(origin+timedelta(hours=30)).isoformat()
    elif damage=='nonfinite':rows[0]['model_error_f']=float('nan')
    elif damage=='boolean':rows[0]['model_error_f']=True
    elif damage=='artifact':rows[0]['artifact_sha256']='short'
    with pytest.raises(ValueError):evidence.summarize_pairs(rows,horizon_hours=24)


def capsule(tmp_path):
    tmp_path.chmod(0o700)
    files={'source-receipt-queries.json':b'[]','report.json':b'{"results":{}}',
           'repeat-report.json':b'{"results":{}}'}
    for name,raw in files.items():
        p=tmp_path/name;p.write_bytes(raw);p.chmod(0o600)
    manifest=dict(schema='earthship-thermal-qualification-capsule/v1',
        assessed_at='2026-10-07T15:54:12+00:00',purpose='development_reassessment_not_release_holdout',
        exact_repeat=True,repeat_normalization='only verifier_runtime_root location; all scores and source hashes equal',
        runtime_revision='a'*64,requested_horizons=[1,6,12,24,48],production_writes=0,source_queries=0,
        files={name:sha256(raw).hexdigest() for name,raw in files.items()})
    (tmp_path/'manifest.json').write_text(json.dumps(manifest));(tmp_path/'manifest.json').chmod(0o600)
    return manifest


def test_verified_capsule_is_explicitly_development_not_a_release_claim(tmp_path):
    capsule(tmp_path)
    result=evidence.verify_capsule(tmp_path)
    assert result['purpose']=='development_reassessment_not_release_holdout'
    assert result['release_qualification_claimed'] is False


@pytest.mark.parametrize('damage',['source','report','escape','symlink','unsafe_mode','extra'])
def test_changed_or_unsafe_source_capsule_refuses(tmp_path,damage):
    manifest=capsule(tmp_path)
    if damage=='source':(tmp_path/'source-receipt-queries.json').write_bytes(b'changed')
    elif damage=='report':(tmp_path/'report.json').write_bytes(b'changed')
    elif damage=='escape':manifest['files']['../outside']='b'*64
    elif damage=='symlink':
        (tmp_path/'source-receipt-queries.json').unlink()
        (tmp_path/'source-receipt-queries.json').symlink_to(tmp_path/'report.json')
    elif damage=='unsafe_mode':(tmp_path/'source-receipt-queries.json').chmod(0o666)
    elif damage=='extra':manifest['active']=True
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):evidence.verify_capsule(tmp_path)


@pytest.mark.parametrize('damage',[None,'epoch','late_storage','target','future_assessment'])
def test_native_receipt_and_query_identity_are_verified(tmp_path,damage):
    manifest=capsule(tmp_path)
    target=datetime(2026,10,6,12,tzinfo=timezone.utc)
    receipt=dict(temperatureF=70,receivedAt=(target-timedelta(seconds=30)).isoformat(),
        storedAt=(target-timedelta(seconds=20)).isoformat(),validUntil=(target+timedelta(seconds=90)).isoformat(),
        streamEpoch='864142d5-99ee-4b7a-b5fc-e6a96e7274d8',snapshotSha256='b'*64)
    request=dict(stream='indoor',targets=[target.isoformat()],assessed_at=target.isoformat())
    row=[target.isoformat(),receipt]
    if damage=='epoch':receipt['streamEpoch']='unbound'
    elif damage=='late_storage':receipt['storedAt']=(target+timedelta(seconds=1)).isoformat()
    elif damage=='target':row[0]=(target-timedelta(seconds=1)).isoformat()
    elif damage=='future_assessment':request['assessed_at']=(target-timedelta(seconds=1)).isoformat()
    raw=json.dumps([dict(request=request,result=[row])]).encode()
    (tmp_path/'source-receipt-queries.json').write_bytes(raw)
    manifest['files']['source-receipt-queries.json']=sha256(raw).hexdigest()
    manifest['source_queries']=1
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    if damage:
        with pytest.raises(ValueError):evidence.verify_capsule(tmp_path)
    else:
        result=evidence.verify_capsule(tmp_path)
        assert result['qualified_native_receipts']=={'indoor':1}
        assert result['native_stream_epochs']=={'indoor':['864142d5-99ee-4b7a-b5fc-e6a96e7274d8']}
        assert result['release_qualification_claimed'] is False


def captured_capsule(tmp_path):
    import gzip
    manifest=capsule(tmp_path)
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc); target=origin+timedelta(days=1)
    output=dict(version=1,status='shadow',generatedAt=origin.isoformat(),
        model={'codeRevision':'b'*64},current={'hallwayF':68},
        forecast={'trajectory':[dict(at=target.isoformat(),hallwayF=71,lowF=69,highF=73)]})
    values=dict(output=output,current={'air':{'value':68}},raw_forecast={'fixture':True},
        forecast_rows=[{'at':target.isoformat(),'tempF':60,'mode':'fall_charge'}],
        artifact={'schema':'earthship-thermal-model/v4','code_revision':'b'*64})
    canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digests={name:sha256(canonical(value)).hexdigest() for name,value in values.items()}
    capture=dict(schema='earthship-thermal-shadow-forcing-capture/v2',
        decision_at=origin.isoformat(),inputs_available_at=origin.isoformat(),
        published_at=(origin+timedelta(seconds=1)).isoformat(),sha256=digests,**values)
    record=pair(origin,artifact=digests['artifact'],error=1,baseline=-2)
    record['recent_cycle_baseline']={'status':'insufficient_qualified_history'}
    report={'results':{'24':{'pairs':[record]}}}
    receipt=dict(temperatureF=70,receivedAt=(target-timedelta(seconds=30)).isoformat(),
        storedAt=(target-timedelta(seconds=20)).isoformat(),validUntil=(target+timedelta(seconds=90)).isoformat(),
        streamEpoch='864142d5-99ee-4b7a-b5fc-e6a96e7274d8',snapshotSha256='b'*64)
    queries=[dict(request=dict(stream='indoor',targets=[target.isoformat()],assessed_at=target.isoformat()),
                  result=[[target.isoformat(),receipt]])]
    bodies={'report.json':canonical(report),'repeat-report.json':canonical(report),
        'source-receipt-queries.json':canonical(queries),
        'captures/2026-10/fixture.json.gz':gzip.compress(canonical(capture),mtime=0)}
    for name,raw in bodies.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        p.write_bytes(raw);p.chmod(0o600)
    manifest['source_queries']=1
    manifest['files']={name:sha256(raw).hexdigest() for name,raw in bodies.items()}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    return manifest,report,capture


@pytest.mark.parametrize('damage',[None,'reported_error','outcome_digest','forcing_digest'])
def test_score_must_bind_exact_capture_and_native_outcome(tmp_path,damage):
    import gzip
    manifest,report,capture=captured_capsule(tmp_path)
    if damage=='reported_error':
        report['results']['24']['pairs'][0]['model_error_f']=0
        for name in ('report.json','repeat-report.json'):
            raw=json.dumps(report).encode();(tmp_path/name).write_bytes(raw)
            manifest['files'][name]=sha256(raw).hexdigest()
    elif damage=='outcome_digest':
        queries=json.loads((tmp_path/'source-receipt-queries.json').read_bytes())
        queries[0]['result'][0][1]['temperatureF']=69
        raw=json.dumps(queries).encode();(tmp_path/'source-receipt-queries.json').write_bytes(raw)
        manifest['files']['source-receipt-queries.json']=sha256(raw).hexdigest()
    elif damage=='forcing_digest':
        capture['forecast_rows'][0]['tempF']=62
        raw=gzip.compress(json.dumps(capture).encode(),mtime=0)
        (tmp_path/'captures/2026-10/fixture.json.gz').write_bytes(raw)
        manifest['files']['captures/2026-10/fixture.json.gz']=sha256(raw).hexdigest()
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    if damage:
        with pytest.raises(ValueError):evidence.verify_capsule(tmp_path)
    else:
        result=evidence.verify_capsule(tmp_path)
        assert result['verified_as_issued_pairs']==1
        assert result['release_qualification_claimed'] is False


def test_regime_support_is_counted_on_independent_windows():
    origin=datetime(2026,10,1,12,tzinfo=timezone.utc)
    rows=[pair(origin),pair(origin+timedelta(hours=1)),pair(origin+timedelta(days=1))]
    rows[0]['regime']='warm';rows[1]['regime']='winter';rows[2]['regime']='shoulder'
    report=evidence.summarize_pairs(rows,horizon_hours=24)
    assert report['independent_regime_counts']=={'warm':1,'shoulder':1,'winter':0,'unbound':0}
    assert report['independent_local_days']==2
