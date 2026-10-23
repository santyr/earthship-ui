"""Transport tests: original numerical replay is covered by scenario_reporting tests."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import importlib,json
import pytest
from test_scenario_reporting import args,ORIGIN
from weather_learning.scenario_reporting import prepare_report
from weather_learning.contracts import canonical,identity


def api():return importlib.import_module('weather_learning.scenario_retention')


def test_factored_original_round_trips_exact_bytes_and_reuses_source_chunks(tmp_path):
 report=prepare_report(**args());state=tmp_path/'state'
 saved=api().retain_compact(state,report,parents={},clock=lambda:ORIGIN+timedelta(seconds=2))
 assert saved['cached'] and saved['retained']
 restored=api().restore_compact(state,report.to_dict()['report_sha256'])
 assert restored.content==report.content
 source_files=list((state/'scenario-reports').glob('source-*.json'));assert source_files
 before={p.name:p.read_bytes() for p in (state/'scenario-reports').glob('*.json')}
 cache=(state/'scenario-advisory.json').read_bytes()
 api().retain_compact(state,report,parents={},clock=lambda:ORIGIN+timedelta(seconds=3))
 assert before=={p.name:p.read_bytes() for p in (state/'scenario-reports').glob('*.json')}
 assert (state/'scenario-advisory.json').read_bytes()==cache
 receipt=json.loads((state/'scenario-reports'/('view-'+json.loads(cache)['report_sha256']+'.json')).read_bytes())
 assert receipt['cache_bytes_sha256']==sha256(cache).hexdigest()
 assert receipt['original_report_sha256']==report.to_dict()['report_sha256']
 assert receipt['published_at']==(ORIGIN+timedelta(seconds=2)).isoformat()
 assert receipt['automatic_actuation'] is False


def test_parent_references_restore_exact_value_and_refuse_byte_changed_original(tmp_path):
 # Factoring is transport only. These sealed receipt-shaped data exercise both
 # occurrences of retained native parents; they make no numerical model claim.
 value=dict(schema='earthship-original-weather-scenario-report/v1',runtime=dict(source_package={'x':'old-source'}),
  inputs=dict(owned_sources=dict(energy={'n':1},plan={'n':2}),household_inputs=dict(thermal_context=dict(original_source_package={'x':'native-source'},owned_sources=dict(energy={'n':1},plan={'n':2})))),output={})
 value['report_sha256']=identity(value)
 paths={}
 for key,n in [('energy',1),('plan',2)]:
  path=tmp_path/(key+'.json');path.write_text(json.dumps({'n':n},indent=2));path.chmod(0o600);paths[key]=path
 api().archive_compact(tmp_path/'state',canonical(value),parents=paths)
 assert api().restore_compact(tmp_path/'state',value['report_sha256']).content==canonical(value)
 paths['plan'].write_text('{"n":2}')
 with pytest.raises(ValueError,match='parent'):api().restore_compact(tmp_path/'state',value['report_sha256'])


@pytest.mark.parametrize('damage',['chunk','capsule','symlink'])
def test_damaged_original_is_refused(tmp_path,damage):
 report=prepare_report(**args());state=tmp_path/'state'
 api().archive_compact(state,report.content,parents={})
 if damage=='capsule':target=state/'scenario-reports'/('original-'+report.to_dict()['report_sha256']+'.json')
 else:target=next((state/'scenario-reports').glob('source-*.json'))
 if damage=='symlink':
  other=tmp_path/'other';other.write_bytes(target.read_bytes());target.unlink();target.symlink_to(other)
 else:
  value=json.loads(target.read_bytes());value['damage']=True;target.write_bytes(canonical(value))
 with pytest.raises(ValueError):api().restore_compact(state,report.to_dict()['report_sha256'])


def test_optional_capacity_failure_does_not_publish_cache(tmp_path,monkeypatch):
 report=prepare_report(**args());state=tmp_path/'state'
 monkeypatch.setattr(api(),'OPTIONAL_MAX_BYTES',1)
 with pytest.raises(ValueError,match='capacity'):api().retain_compact(state,report,parents={},clock=lambda:ORIGIN+timedelta(seconds=2))
 assert not (state/'scenario-advisory.json').exists()


def test_shared_core_reserve_refuses_optional_growth(tmp_path):
 from weather_learning.shadow import ShadowStore
 state=ShadowStore(tmp_path/'state')
 with (state.root/'issues'/('a'*64+'.json')).open('wb') as file:file.truncate(2*1024**3-300*1024**2)
 report=prepare_report(**args())
 with pytest.raises(ValueError,match='reserve'):api().archive_compact(state.root,report.content,parents={})
 assert not (state.root/'scenario-advisory.json').exists()


def test_expired_original_is_retained_without_cache_or_confirmation(tmp_path):
 report=prepare_report(**args());state=tmp_path/'state'
 saved=api().retain_compact(state,report,parents={},clock=lambda:ORIGIN+timedelta(days=1))
 assert saved['retained'] and not saved['cached']
 assert not list((state/'scenario-reports').glob('view-*.json'))
 assert not (state/'scenario-advisory.json').exists()


def test_guard_failure_after_cache_write_has_no_confirmed_view(tmp_path):
 report=prepare_report(**args());state=tmp_path/'state'
 def guard():
  if (state/'scenario-advisory.json').exists():raise TimeoutError('interrupted')
 with pytest.raises(TimeoutError):api().retain_compact(state,report,parents={},clock=lambda:ORIGIN+timedelta(seconds=2),guard=guard)
 assert not list((state/'scenario-reports').glob('view-*.json'))
