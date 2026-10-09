"""Archive reports replay immutable sources rather than scheduling hints."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
from zoneinfo import ZoneInfo
import pytest
from forecast_input_capture import _instant
from forecast_temperature_score import write_sources
from test_forecast_temperature_origin import setup
from test_forecast_temperature_score import case


def report(root,archive):
    module=importlib.import_module('forecast_temperature_score')
    assert hasattr(module,'report_archive'), 'missing replayed archive report'
    return module.report_archive(root,archive)


def test_retry_selects_first_qualified_without_counting_extra_attempts(case,tmp_path):
    root,p=case;archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    withheld={**p,'native_rows':[]};write_sources(archive,withheld)
    first=deepcopy(p);first['assessed_at']=(_instant(p['assessed_at'])+timedelta(minutes=1)).isoformat()
    first_path=write_sources(archive,first)
    later=deepcopy(first);later['assessed_at']=(_instant(p['assessed_at'])+timedelta(minutes=2)).isoformat()
    v=json.loads(later['native_rows'][0][1]);v['records']['outdoor']['temperatureF']=64.
    later['native_rows'][0][1]=json.dumps(v);write_sources(archive,later)
    (archive/'fake.qualified-target-v1.json').write_text('{"status":"qualified"}')
    r=report(root,archive)
    assert r['retained_attempt_count']==3 and r['additional_attempt_count']==2
    assert r['summary']['qualified_observation_count']==1
    assert r['summary']['groups'][0]['metrics']['corrected']['mae_f']==6.
    assert r['selected_sources']==[first_path.name]
    assert r['release_authority'] is False


def test_no_qualified_attempt_selects_earliest_assessment(case,tmp_path):
    root,p=case;archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    first={**p,'native_rows':[]};path=write_sources(archive,first)
    later={**first,'assessed_at':(_instant(p['assessed_at'])+timedelta(minutes=1)).isoformat()}
    write_sources(archive,later)
    r=report(root,archive)
    assert r['selected_sources']==[path.name]
    assert r['summary']['withheld_observation_count']==1
    assert r['summary']['qualified_observation_count']==0


def test_corrupted_attempt_refuses_entire_report(case,tmp_path):
    root,p=case;archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    path=write_sources(archive,p);path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):report(root,archive)


def test_attempt_limit_refuses_instead_of_silently_truncating(case,tmp_path,monkeypatch):
    root,p=case;archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    for minute in (0,1,2):
        write_sources(archive,{**p,'assessed_at':(_instant(p['assessed_at'])+timedelta(minutes=minute)).isoformat()})
    module=importlib.import_module('forecast_temperature_score')
    monkeypatch.setattr(module,'MAX_PACKETS',2)
    with pytest.raises(ValueError,match='bounded original-source attempts'):report(root,archive)


def test_same_target_in_different_offsets_is_one_pair(case,tmp_path):
    root,p=case;archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    original=write_sources(archive,p)
    alternate={**p,'target':_instant(p['target']).astimezone(ZoneInfo('America/Denver')).isoformat(),
        'assessed_at':(_instant(p['assessed_at'])+timedelta(minutes=1)).isoformat()}
    write_sources(archive,alternate)
    r=report(root,archive)
    assert r['selected_sources']==[original.name]
    assert r['retained_attempt_count']==2 and r['additional_attempt_count']==1
    assert r['summary']['source_packet_count']==1
