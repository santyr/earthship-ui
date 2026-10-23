"""Selected points cross the held writer boundary only with retained originals."""
from datetime import timedelta
import json
import pytest
from test_production_forecast import serving,prepare,NOW
from test_production_runtime import LocalOpenHAB
from weather_learning.archive import Archive
from weather_learning.shadow import ShadowStore
from weather_learning.production_runtime import run_publication,ProductionTransport
from openhab_runtime_io import ReadBudget


def runtime(serving,tmp_path,*,after=None,before=None,owner=None):
 from weather_learning.production_emissions import retain_prepared,confirm_publication
 server=LocalOpenHAB();state=ShadowStore(tmp_path/'selected-state');elapsed=[0.]
 def sleep(value):elapsed[0]+=value
 transport=ProductionTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic-local-token',budget=ReadBudget(85,clock=lambda:elapsed[0],sleeper=sleep,max_requests=96),opener=server.open)
 (tmp_path/'attempts').mkdir(mode=0o700)
 lock=tmp_path/'writer.lock';lock.write_bytes(b'');lock.chmod(0o600)
 def retain(product,provider,attempt,result):
  if result is None:
   if before is not None:before()
   return retain_prepared(state,product,provider=provider,now=NOW)
  receipt=confirm_publication(state,product,provider=provider,attempt=attempt,result=result)
  if after is not None:after()
  return receipt
 args=dict(archive=Archive.open_readonly(serving['read_source'].__self__.root),site=__import__('learning_fixtures').SITE,
  evidence_directory=tmp_path/'attempts',shared_lock=lock,code_revision='a'*40,transport=transport,authorize=lambda p:True,guard=lambda:None,
  clock=lambda:NOW+timedelta(seconds=elapsed[0]),required_horizon=timedelta(hours=48),
  production_preparer=lambda decision,provider:prepare(serving,provider=provider),production_retainer=retain,
  production_guard=(lambda product:True) if owner is None else owner)
 return args,server,state


def test_runtime_publishes_selected_values_and_confirms_the_original_before_evaluation(serving,tmp_path):
 from weather_learning.production_emissions import read_emission
 args,server,state=runtime(serving,tmp_path);result=run_publication(**args)
 assert result['status']=='PUBLISHED' and result['production_retention_status']=='CONFIRMED'
 assert json.loads(server.states['Forecast_10Day_JSON'])['version']==3
 assert float(server.states['Forecast_Temp'].split()[0])==pytest.approx(53.6,abs=.9)
 emission=read_emission(state,result['production_emission_sha256'])
 assert emission['result_sha256']==result['result_sha256']
 assert result['production_issue_sha256']==emission['issue_sha256']


def test_prepublication_retention_failure_prevents_any_forecast_put(serving,tmp_path):
 def fail():raise OSError('synthetic disk refusal')
 args,server,state=runtime(serving,tmp_path,before=fail)
 with pytest.raises(OSError,match='synthetic disk refusal'):run_publication(**args)
 assert not any(method=='PUT' for method,path in server.requests)


def test_current_model_owner_is_rechecked_after_preparation_before_transport(serving,tmp_path):
 args,server,state=runtime(serving,tmp_path,owner=lambda product:False)
 with pytest.raises(ValueError,match='production'):run_publication(**args)
 assert not any(method=='PUT' for method,path in server.requests)


def test_failure_after_confirmed_publication_preserves_actual_success_and_original_emission(serving,tmp_path):
 def fail():raise OSError('synthetic nonzero after successful durable emission')
 args,server,state=runtime(serving,tmp_path,after=fail);result=run_publication(**args)
 assert result['status']=='PUBLISHED' and result['production_retention_status']=='FAILED_AFTER_PUBLICATION'
 assert json.loads(server.states['Forecast_10Day_JSON'])['providerStatus']=='AVAILABLE'
 assert len(list((state.root/'production-emissions').glob('*.json')))==1
 original=json.loads(__import__('pathlib').Path(result['result_path']).read_text())
 assert original['status']=='PUBLISHED' and original['publication']['status']=='PUBLISHED'
