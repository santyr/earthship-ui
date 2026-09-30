import importlib.util
import json
from urllib.error import HTTPError
from datetime import datetime
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('night_average', Path(__file__).with_name('verify-live-bms-night-average.py'))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def test_completed_window_rollover_and_dst():
    for now, elapsed in [('2026-09-30T14:00:00+00:00', 9.5),
                         ('2026-03-08T14:00:00+00:00', 8.5),
                         ('2026-11-01T14:00:00+00:00', 10.5)]:
        start, end = q.night_window(datetime.fromisoformat(now))
        assert (end-start).total_seconds() == elapsed*3600
        assert end <= datetime.fromisoformat(now)
    assert q.night_window(datetime.fromisoformat('2026-09-30T11:00:00+00:00'))[1].day == 29


def test_only_exact_owned_triggerless_logging_rule_can_be_removed():
    start, end = q.night_window(datetime.fromisoformat('2026-09-30T14:00:00+00:00'))
    rule = q.definition('hex_diag_bms_avg_' + 'a'*24, 'marker:', start, end)
    actual = {**rule, 'editable': True}
    assert q.owned(rule, actual)
    for damage in [{'uid': 'hex_bms_ttd_smooth'}, {'tags': []}, {'editable': False},
                   {'triggers': [{'type': 'timer.GenericCronTrigger'}]}, {'actions': []}, {'actions':None}]:
        assert not q.owned(rule, {**actual, **damage})
    for extra in [{'inputs':{'unexpected':'binding'}},{'unexpected':'field'}]:
        assert not q.owned(rule,{**actual,'actions':[{**rule['actions'][0],**extra}]})
    script = rule['actions'][0]['configuration']['script']
    assert '.averageBetween(' in script
    assert 'toZDT("' not in script
    assert 'toEpochMilli()!=='+str(int(start.timestamp()*1000)) in script
    assert 'toEpochMilli()!=='+str(int(end.timestamp()*1000)) in script
    assert all(word not in script for word in ['postUpdate', 'sendCommand', '.persist(', 'setState'])
    with pytest.raises(ValueError):
        q.definition('hex_southoutlet_cycle', 'marker:', start, end)


def test_only_one_closed_valid_numeric_log_result_is_accepted():
    assert q.result_from_log('irrelevant private log', 'marker:') is None
    result = {'status':'ok','watts':172.5,'jdbcWatts':172.5,'jdbcLeftWatts':172.5,
              'reconstructedMillisWatts':172.5,'preciseWatts':172.517,
              'jdbcRows':1000,'defaultPageSize':1000,'begin':'2026-09-30T02:30:00Z',
              'first':'2026-09-30T02:30:01Z','last':'2026-09-30T04:00:00Z','end':'2026-09-30T12:00:00Z'}
    assert q.result_from_log('INFO marker:' + json.dumps(result), 'marker:') == result
    unlimited = {**result,'defaultPageSize':2147483647}
    assert q.result_from_log('marker:' + json.dumps(unlimited), 'marker:') == unlimited
    for raw in ['{"status":"failed","watts":null}', '{"status":"ok","watts":true}',
                '{"status":"ok","watts":-1}', '{"status":"ok","watts":20001}',
                '{"status":"ok","watts":172.5,"extra":"data"}']:
        with pytest.raises(RuntimeError):
            q.result_from_log('marker:' + raw, 'marker:')
    with pytest.raises(RuntimeError):
        q.result_from_log('marker:{"status":"ok","watts":1}\nmarker:{"status":"ok","watts":1}', 'marker:')
    for key,value in [('jdbcRows',20001),('jdbcRows',True),('jdbcLeftWatts',float('nan')),
                      ('defaultPageSize',0),('begin','private'),('last','2026-10-01T12:00:00Z')]:
        with pytest.raises(RuntimeError):
            q.result_from_log('marker:' + json.dumps({**result,key:value}), 'marker:')
    with pytest.raises(RuntimeError):
        q.result_from_log('marker:' + json.dumps(result) + '\nmarker:' + json.dumps(result), 'marker:')


@pytest.mark.parametrize('bad_log', [False, True])
def test_owned_diagnostic_cleanup_on_success_and_result_failure(monkeypatch, tmp_path, capsys, bad_log):
    fixed = datetime.fromisoformat('2026-09-30T14:00:00+00:00')
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed
    monkeypatch.setattr(q,'datetime',FixedClock)
    monkeypatch.setattr(q.secrets,'token_hex',lambda count:'a'*24)
    log = tmp_path/'openhab.log'
    log.write_text('preexisting unrelated line\n')
    monkeypatch.setattr(q,'Path',lambda _:log)
    monkeypatch.setattr(q.oh,'token',lambda:'synthetic-only')
    start,end = q.night_window(fixed)
    uid = 'hex_diag_bms_avg_'+'a'*24
    path = '/rules/'+uid
    marker = 'HEX_NIGHT_AVG_'+'a'*24+':'
    expected = q.definition(uid,marker,start,end)
    registered = False
    calls = []
    def get(target):
        assert target == path
        if not registered:
            raise HTTPError(target,404,'not found',{},None)
        return {**expected,'editable':True,'status':{'status':'IDLE'}}
    monkeypatch.setattr(q.oh,'get',get)
    class Response:
        def __init__(self,status):self.status=status
        def __enter__(self):return self
        def __exit__(self,*args):return False
    def request(req,timeout):
        nonlocal registered
        target = req.full_url.removeprefix(q.oh.BASE)
        calls.append((req.method,target))
        if target == '/rules':
            assert req.method=='POST' and json.loads(req.data)==expected
            registered=True
            return Response(201)
        if target==path+'/runnow':
            result={'status':'ok','watts':172.5,'jdbcWatts':172.5,'jdbcLeftWatts':172.5,
                    'reconstructedMillisWatts':172.5,'preciseWatts':172.517,
                    'jdbcRows':6454,'defaultPageSize':2147483647,
                    'begin':'2026-09-30T02:30:00Z','first':'2026-09-30T02:30:04Z',
                    'last':'2026-09-30T11:59:55Z','end':'2026-09-30T12:00:00Z'}
            with log.open('a') as stream:
                stream.write(marker+json.dumps({'status':'failed'} if bad_log else result)+'\n')
            return Response(200)
        assert req.method=='DELETE' and target==path
        registered=False
        return Response(204)
    monkeypatch.setattr(q,'urlopen',request)
    if bad_log:
        with pytest.raises(RuntimeError):q.main()
        assert capsys.readouterr().out==''
    else:
        q.main()
        result=json.loads(capsys.readouterr().out)
        assert result['ownedDiagnosticRemoved'] and result['itemWrites']==result['equipmentCommands']==0
    assert calls==[('POST','/rules'),('POST',path+'/runnow'),('DELETE',path)]
    assert not registered


def test_existing_uid_is_never_executed_or_removed(monkeypatch, tmp_path):
    log=tmp_path/'openhab.log'
    log.write_text('')
    monkeypatch.setattr(q,'Path',lambda _:log)
    monkeypatch.setattr(q.oh,'get',lambda _: {'uid':'existing'})
    def refuse(*args,**kwargs):pytest.fail('mutation during collision preflight')
    monkeypatch.setattr(q,'urlopen',refuse)
    with pytest.raises(RuntimeError,match='collision'):q.main()
