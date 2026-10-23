"""The operational worker switches only under a source-bound reviewed v2 release."""
import json
from hashlib import sha256
import pytest
from test_production_forecast import serving,original,NOW
from test_production_selection import selected,private
import test_production_worker as worker_tests
from learning_fixtures import receipt
from weather_learning.contracts import identity


@pytest.fixture
def cutover(selected):
 case=worker_tests.ProductionWorkerTests('test_default_is_readonly_even_with_synthetic_complete_review');case.setUp()
 try:
  case.now=NOW;case.archive.store_snapshot(original(hours=360));path,profile,state=selected
  profile=dict(profile,archive=str(case.archive.root));private(path,profile);pin=sha256(path.read_bytes()).hexdigest()
  case.config.update(schema='earthship-weather-production-config/v2',selected_profile_path=str(path),selected_profile_sha256=pin)
  case.release.update(schema='earthship-weather-reviewed-release/v2',selected_profile_sha256=pin,authorization_policy_sha256=profile['authorization_policy_sha256'],deployment_mode='direct_production_replacement',forecast_detail_version=3)
  case.write_release()
  yield case,path,profile,state
 finally:case.doCleanups()


def test_v2_default_preflight_has_no_forecast_writes_or_new_retention(cutover):
 case,path,profile,state=cutover;before={p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
 result=case.run_worker(temperature_reader=lambda *args:pytest.fail('preflight read observations'))
 assert result['status']=='PREFLIGHT_PASSED' and case.puts()==[]
 assert result['selected_profile_sha256']==sha256(path.read_bytes()).hexdigest()
 assert all(p.read_bytes()==raw for p,raw in before.items()) and not (state.root/'production-issues').exists()


def test_v2_selected_models_reach_actual_worker_transport_and_confirmed_emission(cutover):
 case,path,profile,state=cutover
 result=case.run_worker(publish=True,temperature_reader=lambda at,policy,epoch:receipt(at,epoch=epoch))
 assert result['status']=='PUBLISHED' and result['production_retention_status']=='CONFIRMED'
 assert float(case.server.states['Forecast_Temp'].split()[0])==pytest.approx(53.6,abs=.9)
 detail=json.loads(case.server.states['Forecast_10Day_JSON'])
 assert detail['version']==3 and detail['productionModel']['issueSha256']==result['production_issue_sha256']
 assert (state.root/'production-emissions'/(result['production_emission_sha256']+'.json')).is_file()
 assert (state.root/'production-scores.sqlite3').is_file()


def test_changed_release_profile_or_forbidden_parallel_shadow_refuses_before_http(cutover):
 case,path,profile,state=cutover
 path.write_bytes(path.read_bytes()+b'\n')
 with pytest.raises(ValueError):case.run_worker(publish=True)
 assert case.server.requests==[]
 private(path,profile)
 with pytest.raises(ValueError):case.run_worker(publish=True,near_term_config_path='/unused/parallel-shadow.json')
 assert case.server.requests==[]


def test_release_cannot_relabel_the_selected_product_as_legacy_or_bypass_policy(cutover):
 case,path,profile,state=cutover
 for change in [dict(forecast_detail_version=2),dict(authorization_policy_sha256='f'*64),dict(selected_profile_sha256='f'*64)]:
  old=dict(case.release);case.release.update(change);case.write_release()
  with pytest.raises(ValueError):case.run_worker(publish=True)
  assert case.server.requests==[]
  case.release=old;case.write_release()


def test_cli_nonzero_after_success_preserves_the_published_result_and_emission(cutover,monkeypatch,capsys):
 import weather_publish
 from weather_learning.production_selection import ProductionSelection
 case,path,profile,state=cutover;retain=ProductionSelection.retain
 def fail_after_success(self,product,provider,attempt,result):
  value=retain(self,product,provider,attempt,result)
  if result is not None:raise OSError('synthetic post-success failure')
  return value
 monkeypatch.setattr(ProductionSelection,'retain',fail_after_success)
 monkeypatch.setattr(weather_publish,'run_worker',lambda config,**kwargs:case.run_worker(temperature_reader=lambda at,policy,epoch:receipt(at,epoch=epoch),**kwargs))
 status=weather_publish.main(['--config',str(case.config_path),'--publish'])
 output=json.loads(capsys.readouterr().out)
 assert status==1 and output['status']=='PUBLISHED' and output['production_retention_status']=='FAILED_AFTER_PUBLICATION'
 assert json.loads(case.server.states['Forecast_10Day_JSON'])['providerStatus']=='AVAILABLE'
 assert len(list((state.root/'production-emissions').glob('*.json')))==1
