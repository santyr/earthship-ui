"""Chronological counts preserve original clocks, versions and absence."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib
import pytest
from household.codec import identity,canonical
from household.control_contracts import instant
from test_household_pipeline import pipeline,NOW
from test_household_observation import observe,materializer_fixture


def api():return importlib.import_module('household_chronology')
def shifted(at=NOW,hours=24):
    record=pipeline();view=observe(record)
    # Summary fixtures move original clocks together; no replay is bypassed in production.
    record=deepcopy(record);record['inputs']['now']=at.isoformat();record['inputs']['config']['horizon_hours']=hours
    record['receipt_sha256']=identity({k:v for k,v in record.items() if k!='receipt_sha256'})
    view.update(receipt_sha256=record['receipt_sha256'],decision_at=at.isoformat(),snapshot_as_of=at.isoformat(),valid_until=(at+timedelta(minutes=5)).isoformat())
    return record,view


def sample(at=NOW,hours=24):return api().admit(*shifted(at,hours))


def test_counts_deduplicate_originals_and_do_not_count_dense_decisions_as_windows():
    a=sample();b=sample(NOW+timedelta(minutes=5));c=sample(NOW+timedelta(days=1))
    r=api().summarize([a,a,b,c],generated_at=NOW+timedelta(days=1,minutes=1))
    assert r['counts']['raw_decisions']==3
    assert r['counts']['origin_days']==2 and r['counts']['non_overlapping_windows']==2
    assert r['counts']['planner_available']==3
    assert r['families']['RUN_FEEDER_CYCLE']['raw_decisions']==0
    assert r['families']['RUN_GREYWATER_CYCLE']['raw_decisions']==0
    assert r['families']['SET_NIGHT_LOAD_OVERRIDE']['raw_decisions']==0
    assert r['statistical_independence_assessed'] is False and r['release_authorized'] is False and r['automatic_actuation'] is False
    assert r['counts']['hard_blocked']==0


def test_versions_are_separate_and_expired_reverification_cannot_renew_a_decision():
    record=pipeline();a=api().admit(record,observe(record));later=api().admit(record,observe(record,at=NOW+timedelta(minutes=10)))
    assert a==later
    b=sample(NOW+timedelta(hours=1));b=deepcopy(b);b['versions']['config_sha256']='b'*64;b['admission_sha256']=identity({k:v for k,v in b.items() if k!='admission_sha256'})
    r=api().summarize([a,b],generated_at=NOW+timedelta(hours=2))
    assert len(r['version_groups'])==2 and all(g['counts']['raw_decisions']==1 for g in r['version_groups'])


def test_rolling_window_and_future_or_corrupt_admission_are_not_silently_counted():
    a=sample();old=sample(NOW-timedelta(days=8))
    assert api().summarize([a,old],generated_at=NOW)['counts']['raw_decisions']==1
    for bad in [sample(NOW+timedelta(seconds=1)),dict(a,automatic_actuation=True),dict(a,raw='/private/path')]:
        with pytest.raises(ValueError):api().summarize([bad],generated_at=NOW)


def test_post_replay_collection_is_private_immutable_and_optional(tmp_path,monkeypatch):
    source,target,record=materializer_fixture(tmp_path)
    from household_observation import materialize
    result=materialize(source,target,clock=lambda:NOW)
    assert result['chronology_status']=='written'
    report=__import__('json').loads((target.parent/'chronological-summary.json').read_bytes())
    assert report['counts']['raw_decisions']==1
    admissions=list((target.parent/'chronological-admissions').glob('*/*.json'))
    assert len(admissions)==1 and admissions[0].stat().st_mode&0o777==0o600
    original=admissions[0].read_bytes()
    materialize(source,target,clock=lambda:NOW+timedelta(minutes=10))
    assert admissions[0].read_bytes()==original
    assert __import__('json').loads((target.parent/'chronological-summary.json').read_bytes())['counts']['raw_decisions']==1
    def refused(*a,**k):raise ValueError('not public diagnostic')
    monkeypatch.setattr(api(),'retain_and_summarize',refused)
    assert materialize(source,target,clock=lambda:NOW)['chronology_status']=='unavailable'
    assert target.exists()


def test_tampered_retained_admission_refuses_summary_without_overwriting_previous(tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    from household_observation import materialize
    materialize(source,target,clock=lambda:NOW)
    report=target.parent/'chronological-summary.json';before=report.read_bytes()
    retained=next((target.parent/'chronological-admissions').glob('*/*.json'));retained.write_bytes(b'{}')
    result=materialize(source,target,clock=lambda:NOW+timedelta(minutes=1))
    assert result['chronology_status']=='unavailable' and report.read_bytes()==before


def test_shorter_original_horizons_form_maximum_non_overlapping_set():
    rows=[sample(),sample(NOW+timedelta(hours=1),6),sample(NOW+timedelta(hours=7),6)]
    report=api().summarize(rows,generated_at=NOW+timedelta(hours=8))
    assert report['counts']['non_overlapping_windows']==2


def test_counts_exact_original_policy_comparisons_without_inventing_skill():
    from test_household_observation import policy_record as qualification_record
    r=qualification_record();v=observe(r,at=instant(r['inputs']['now']))
    row=api().admit(r,v);report=api().summarize([row],generated_at=instant(r['inputs']['now']))
    expected={key:sum(c['status']==key for c in v['policy_comparison']['comparisons']) for key in api().POLICY}
    assert report['policy_comparisons']==expected
    assert report['missing_evidence']==api().MISSING


def test_admission_store_refuses_symlinks_without_overwriting_operator_files(tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    from household_observation import materialize
    unrelated=tmp_path/'operator';unrelated.mkdir(mode=0o700)
    (target.parent/'chronological-admissions').symlink_to(unrelated,target_is_directory=True)
    result=materialize(source,target,clock=lambda:NOW)
    assert result['chronology_status']=='unavailable' and list(unrelated.iterdir())==[]


def test_malformed_retained_structure_is_optional_not_a_cycle_failure(tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    from household_observation import materialize
    materialize(source,target,clock=lambda:NOW)
    retained=next((target.parent/'chronological-admissions').glob('*/*.json'))
    malformed=__import__('json').loads(retained.read_bytes());malformed['families']=None;malformed['receipt_sha256']='d'*64
    malformed['admission_sha256']=identity({k:v for k,v in malformed.items() if k!='admission_sha256'})
    (retained.parent/('d'*64+'.json')).write_bytes(canonical(malformed));(retained.parent/('d'*64+'.json')).chmod(0o600)
    assert materialize(source,target,clock=lambda:NOW+timedelta(minutes=1))['chronology_status']=='unavailable'


def test_seven_elapsed_days_includes_all_nine_denver_dates_at_spring_forward(tmp_path):
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    generated=datetime(2026,3,15,6,30,tzinfo=timezone.utc)
    rows=[sample(datetime(2026,3,8,6,45,tzinfo=timezone.utc))]
    rows.extend(sample(datetime(2026,3,d,18,tzinfo=timezone.utc)) for d in range(8,15))
    current=shifted(generated);rows.append(api().admit(*current))
    root=tmp_path/'private';root.mkdir(mode=0o700);store=root/'chronological-admissions';store.mkdir(mode=0o700)
    for row in rows:
        folder=store/instant(row['decision_at']).astimezone(ZoneInfo('America/Denver')).date().isoformat();folder.mkdir(mode=0o700,exist_ok=True)
        path=folder/(row['receipt_sha256']+'.json');path.write_bytes(canonical(row));path.chmod(0o600)
    report=api().retain_and_summarize(*current,directory=root,generated_at=generated,guard=lambda:None)
    assert report['counts']['raw_decisions']==9 and report['counts']['origin_days']==9


def test_deeply_nested_optional_history_keeps_previous_report_and_success_result(tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    from household_observation import materialize
    materialize(source,target,clock=lambda:NOW)
    report=target.parent/'chronological-summary.json';before=report.read_bytes()
    retained=next((target.parent/'chronological-admissions').glob('*/*.json'))
    extra=retained.parent/('e'*64+'.json');extra.write_bytes(b'['*10000+b']'*10000);extra.chmod(0o600)
    result=materialize(source,target,clock=lambda:NOW+timedelta(minutes=1))
    assert result['status']=='observation_written' and result['chronology_status']=='unavailable'
    assert report.read_bytes()==before and target.exists()
