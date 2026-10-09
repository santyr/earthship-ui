"""Bounded diagnostic sampling and batch behavior with original raw fixtures."""
from datetime import timedelta
import importlib,importlib.util,os
from pathlib import Path
import pytest
from test_forecast_temperature_origin import setup
from test_forecast_temperature_score import case
from test_forecast_temperature_collection import Sources
from forecast_input_capture import _instant


def module():
    assert importlib.util.find_spec('forecast_temperature_batch') is not None,'missing bounded original batch collector'
    return importlib.import_module('forecast_temperature_batch')


def test_daily_sampling_is_archive_order_not_error_selection(tmp_path):
    root=tmp_path/'origins';root.mkdir(mode=0o700)
    for digest,at in [('a'*64,1791554400),('b'*64,1791558000),('c'*64,1791640800)]:
        p=root/(digest+'.temperature-origin-v1.json');p.write_text('fixture');p.chmod(0o600);os.utime(p,(at,at))
    assert module().daily_origins(root)==['a'*64,'c'*64]


def test_batch_collects_then_uses_only_scheduling_hints(case,tmp_path):
    root,p=case;out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Sources(p)
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=backend)
    assert r['attempted']==1 and r['qualified']==1 and r['release_authority'] is False
    again=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=backend)
    assert again['attempted']==0 and backend.reads==2


def test_withheld_packet_does_not_block_other_targets_forever(case,tmp_path):
    root,p=case;out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Sources({**p,'native_rows':[]})
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=backend)
    assert r['withheld']==1 and r['qualified']==0
    again=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=backend)
    assert again['attempted']==0


def test_pending_targets_do_not_read_backend(case,tmp_path):
    root,p=case;out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Sources(p)
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=(_instant(p['target'])+timedelta(minutes=4)).isoformat(),backend=backend)
    assert r['attempted']==0 and backend.reads==0


def test_budget_exhaustion_stops_before_reading_origins(case,tmp_path):
    root,p=case;out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Sources(p)
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=backend,deadline=1,clock=lambda:2)
    assert r['status']=='budget_exhausted' and backend.reads==0


def test_four_target_limit_leaves_fifth_for_next_batch(setup,tmp_path):
    from test_forecast_temperature_score import make_case
    root,p=make_case(setup,times=['2026-10-10T12:00','2026-10-10T13:00','2026-10-10T14:00','2026-10-10T15:00','2026-10-10T16:00'])
    out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Sources(p)
    assessed='2026-10-10T22:05:00+00:00'
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=assessed,backend=backend)
    assert r['attempted']==4 and backend.reads==8
    again=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=assessed,backend=backend)
    assert again['attempted']==1 and backend.reads==10


def test_invalid_original_does_not_prevent_valid_original_collection(case,tmp_path):
    root,p=case;bad=root/('f'*64+'.temperature-origin-v1.json');bad.write_text('invalid original');bad.chmod(0o600)
    os.utime(bad,(1791468000,1791468000))
    out=tmp_path/'packets';out.mkdir(mode=0o700)
    r=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=Sources(p))
    assert r['source_errors']==1 and r['qualified']==1


def test_failed_old_origin_cools_down_without_starving_valid_origins(setup,tmp_path):
    from datetime import datetime,timezone
    from test_forecast_temperature_score import make_case
    root,old=make_case(setup,times=['2026-10-10T12:00','2026-10-10T13:00','2026-10-10T14:00','2026-10-10T15:00','2026-10-10T16:00'],issue_at=datetime(2026,10,8,13,tzinfo=timezone.utc))
    os.utime(root/(old['origin_sha256']+'.temperature-origin-v1.json'),(1791468000,1791468000))
    root,good=make_case(setup);out=tmp_path/'packets';out.mkdir(mode=0o700)
    class Backend(Sources):
        def publication(self,origin):
            if origin['publication_started_at'].startswith('2026-10-08'):raise ValueError('original receipt unavailable')
            return super().publication(origin)
    backend=Backend(good);at='2026-10-10T22:05:00+00:00'
    result=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=at,backend=backend)
    assert result['failed']==1 and result['qualified']==1
    repeated=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=at,backend=backend)
    assert repeated['attempted']==0
    retry=module().collect_batch(origin_directory=root,output_directory=out,assessed_at='2026-10-10T22:36:00+00:00',backend=backend)
    assert retry['attempted']==1 and retry['failed']==1


def test_missing_weather_units_is_isolated_before_other_valid_original(case,setup,tmp_path):
    from datetime import datetime,timezone
    from test_forecast_temperature_score import make_case
    root,p=case
    _,bad=make_case(setup,units=None,issue_at=datetime(2026,10,8,13,tzinfo=timezone.utc))
    os.utime(root/(bad['origin_sha256']+'.temperature-origin-v1.json'),(1791468000,1791468000))
    out=tmp_path/'packets';out.mkdir(mode=0o700)
    result=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=Sources(p))
    assert result['source_errors']==1 and result['qualified']==1


def test_failed_origins_also_obey_four_attempt_limit(setup,tmp_path):
    from datetime import datetime,timezone
    from test_forecast_temperature_score import make_case
    for day in range(1,6):
        root,p=make_case(setup,issue_at=datetime(2026,10,day,13,tzinfo=timezone.utc))
        clock=datetime(2026,10,day,14,tzinfo=timezone.utc).timestamp()
        os.utime(root/(p['origin_sha256']+'.temperature-origin-v1.json'),(clock,clock))
    class Backend(Sources):
        def publication(self,origin):raise ValueError('original receipt unavailable')
    out=tmp_path/'packets';out.mkdir(mode=0o700)
    result=module().collect_batch(origin_directory=root,output_directory=out,assessed_at=p['assessed_at'],backend=Backend(p))
    assert result['attempted']==4 and result['failed']==4


def test_long_failed_backlog_cannot_starve_unattempted_valid_origin(setup,tmp_path):
    from datetime import datetime,timezone
    from test_forecast_temperature_score import make_case
    for day in range(1,15):
        root,p=make_case(setup,times=['2026-10-15T12:00'],issue_at=datetime(2026,10,day,13,tzinfo=timezone.utc))
        at=datetime(2026,10,day,14,tzinfo=timezone.utc).timestamp()
        os.utime(root/(p['origin_sha256']+'.temperature-origin-v1.json'),(at,at))
    class Backend(Sources):
        def publication(self,origin):
            if not origin['publication_started_at'].startswith('2026-10-14'):raise ValueError('original receipt unavailable')
            return super().publication(origin)
    out=tmp_path/'packets';out.mkdir(mode=0o700);backend=Backend(p);results=[]
    for minute in (5,15,25,35):
        assessed=datetime(2026,10,15,18,minute,tzinfo=timezone.utc).isoformat()
        results.append(module().collect_batch(origin_directory=root,output_directory=out,assessed_at=assessed,backend=backend))
    assert sum(r['qualified'] for r in results)==1
    assert all(r['attempted']<=4 for r in results)
