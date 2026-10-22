"""Private observability uses actual clocks and counts, never serving authority."""
from datetime import timedelta
import json
import pytest
from capability_fixtures import reader
from learning_fixtures import T,SITE,EPOCH,REVISION,full_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.worker import collect_once
from weather_learning.shadow import ShadowStore,shadow_once


def test_core_collection_exposes_the_same_bounded_archive_runway_as_optional_groups(tmp_path):
 r,now=reader();a=Archive(tmp_path/'archive')
 result=collect_once(r,a,probe=False,horizon=360,free_bytes=10**9,clock=lambda:now[0])
 assert result['archive_capacity']['maximum_new_objects_per_cycle']==1
 assert result['archive_capacity']['objects']==1
 assert result['archive_capacity']['conservative_complete_cycles_remaining']>0


def test_ingestion_diagnostic_preserves_original_availability_and_unknown_costs(tmp_path):
 from weather_learning.operations import ingestion_diagnostic,persist_ingestion
 r,now=reader();a=Archive(tmp_path/'archive')
 result=collect_once(r,a,probe=False,horizon=360,clock=lambda:now[0],free_bytes=10**9)
 result.update(requests=r.transport.requests,bytes_received=r.transport.bytes_received)
 value=ingestion_diagnostic(a,result,profiles=(),now=now[0])
 original=a.read(result['snapshot_sha256'])
 assert value['original_ingestion_lag_seconds']==( __import__('datetime').datetime.fromisoformat(original['ingestion_completed_at'])-__import__('datetime').datetime.fromisoformat(original['initialized_at'])).total_seconds()
 assert value['provider_revision'] is None and value['eecu_used'] is value['eecu_remaining'] is None
 assert value['accounting']['requests']==r.transport.requests
 assert value['accounting']['response_bytes']==r.transport.bytes_received
 assert value['source_available_at']==original['ingestion_completed_at']
 later=ingestion_diagnostic(a,result,profiles=(),now=now[0]+timedelta(minutes=5))
 assert later['source_available_at']==value['source_available_at']
 assert later['source_age_seconds']==value['source_age_seconds']+300
 assert later['enabled_groups']==['core-v1']
 persist_ingestion(a,result,profiles=(),now=now[0]);p=a.root/'ingest-status.json'
 assert p.stat().st_mode&0o777==0o600
 assert json.loads(p.read_bytes())==value


def test_optional_refusals_and_retries_are_explicit_without_promoting_usage_to_eecu(tmp_path):
 from weather_learning.operations import ingestion_diagnostic
 r,now=reader();r.ee.fail_band='station_head_temperature_2m_p25';a=Archive(tmp_path/'archive')
 result=collect_once(r,a,probe=False,horizon=360,clock=lambda:now[0],free_bytes=10**9,optional_profiles=('uncertainty-v1',))
 value=ingestion_diagnostic(a,result,profiles=('uncertainty-v1',),now=now[0])
 assert value['enabled_groups']==['core-v1','uncertainty-v1']
 assert value['optional_groups'][0]['status']=='unavailable'
 assert value['optional_groups'][0]['reason']=='partial_delivery'
 assert value['optional_groups'][0]['retry_at'] is not None
 assert value['eecu_used'] is None


def test_failed_collection_does_not_adopt_an_older_success_as_the_current_original(tmp_path):
 from weather_learning.operations import ingestion_diagnostic
 a=Archive(tmp_path/'archive');a.store_snapshot(full_snapshot(hours=360))
 value=ingestion_diagnostic(a,{'status':'UNAVAILABLE','reason':'AccessRefused','requests':0,'bytes_received':0},profiles=(),now=T+timedelta(hours=1))
 assert value['source_sha256'] is value['source_available_at'] is value['original_ingestion_lag_seconds'] is None
 assert value['status']=='UNAVAILABLE' and value['accounting']['requests']==0


def test_monitor_private_summary_preserves_queue_scope_and_selection_absence(tmp_path):
 from weather_learning.monitoring import monitor_once
 a=Archive(tmp_path/'archive');s=ShadowStore(tmp_path/'state');a.store_snapshot(full_snapshot(hours=80));issued=T+timedelta(minutes=30)
 shadow_once(a,s,now=issued,site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,horizon=48,clock=lambda:issued+timedelta(seconds=1))
 def temperature(targets,assessed_at):return {at:receipt(at,12) for at in targets}
 kwargs=dict(now=T+timedelta(hours=3),site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,observation_policy_sha256='a'*64,read_temperature=temperature,read_solar=lambda *a:None,read_rain=lambda *a:None)
 monitor_once(a,s,**kwargs);assert not (s.root/'operations.json').exists()
 performance=monitor_once(a,s,apply=True,**kwargs);value=json.loads((s.root/'operations.json').read_bytes())
 assert value['evaluation']['source_report_sha256']==performance['report_sha256']
 assert value['evaluation']['temperature_states']==performance['temperature']['work']['states']
 assert value['evaluation']['pending_daily_windows']==performance['pending']
 assert value['selected_models']['native_temperature']['status']=='not_selected'
 assert value['selected_models']['historical_temperature']['status']=='not_selected'
 assert value['ingestion']['status']=='unavailable'
 assert value['automatic_actuation'] is value['release_authorized'] is False
 assert (s.root/'operations.json').stat().st_mode&0o777==0o600


def _monitor_context(tmp_path):
 from weather_learning.monitoring import monitor_once
 a=Archive(tmp_path/'archive');s=ShadowStore(tmp_path/'state');a.store_snapshot(full_snapshot(hours=80));issued=T+timedelta(minutes=30)
 shadow_once(a,s,now=issued,site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,horizon=48,clock=lambda:issued+timedelta(seconds=1))
 performance=monitor_once(a,s,now=T+timedelta(hours=3),site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,observation_policy_sha256='a'*64,
  read_temperature=lambda targets,assessed_at:{at:receipt(at,12) for at in targets},read_solar=lambda *a:None,read_rain=lambda *a:None)
 return a,s,performance


def test_collection_failure_before_reader_setup_replaces_previous_operational_success(tmp_path,monkeypatch,capsys):
 from weather_learning.operations import persist_ingestion
 import weathernext_ingest
 import weather_learning.openhab as oh
 a=Archive(tmp_path/'archive')
 persist_ingestion(a,{'status':'UNAVAILABLE','reason':'prior'},profiles=(),now=T)
 def failed(*args):raise OSError('credential-like-private-detail')
 monkeypatch.setattr(oh,'oh_get',failed)
 assert weathernext_ingest.main(['--collect','--archive',str(a.root)])==1
 value=json.loads((a.root/'ingest-status.json').read_bytes())
 assert value['reason']=='OSError' and value['generated_at']!=T.isoformat()
 assert 'credential-like-private-detail' not in json.dumps(value)+capsys.readouterr().out


def test_stale_ingestion_and_malformed_auxiliary_counts_never_become_current(tmp_path):
 from weather_learning.operations import persist_ingestion,monitor_diagnostic
 a,s,p=_monitor_context(tmp_path)
 persist_ingestion(a,{'status':'UNAVAILABLE','reason':'old'},profiles=(),now=T)
 s._write(s.root/'rain-performance.json',{'schema':'wrong','generated_at':T.isoformat(),'valid_until':(T+timedelta(hours=2)).isoformat(),'pending':-1,'automatic_actuation':False})
 value=monitor_diagnostic(a,s,p,now=T+timedelta(hours=3),sensor_epoch=EPOCH,guard=lambda:None)
 assert value['ingestion']['status']=='stale'
 assert value['ingestion']['value']['generated_at']==T.isoformat()
 assert value['auxiliary_scores']['rain']['status']=='unavailable'
 assert value['auxiliary_scores']['rain']['counts'] is None


def test_owner_deadlines_are_not_hidden_by_optional_diagnostics(tmp_path):
 from weather_learning.operations import persist_monitor
 a,s,p=_monitor_context(tmp_path)
 def stop():raise TimeoutError('owner deadline')
 with pytest.raises(TimeoutError):persist_monitor(a,s,p,now=T+timedelta(hours=3),sensor_epoch=EPOCH,guard=stop)


def test_actual_diagnostic_write_failure_does_not_rewrite_or_hide_performance(tmp_path,monkeypatch):
 from weather_learning.operations import persist_monitor
 a,s,p=_monitor_context(tmp_path);writes=[]
 def failed(path,value,**kwargs):writes.append(path.name);raise OSError('disk full')
 monkeypatch.setattr(s,'_write',failed)
 assert persist_monitor(a,s,p,now=T+timedelta(hours=3),sensor_epoch=EPOCH,guard=lambda:None) is False
 assert writes==['operations.json'] and not (s.root/'operations.json').exists()


def test_configured_native_model_retains_original_identity_without_claiming_admission(tmp_path):
 from weather_learning.operations import monitor_diagnostic
 from weather_learning.training import fit_bias
 from weather_learning.contracts import identity
 from learning_fixtures import pair
 a,s,p=_monitor_context(tmp_path)
 fitted_at=T+timedelta(hours=2,minutes=1)
 model=fit_bias([pair()],cutoff=fitted_at,code_revision=REVISION)
 s.install_model(model,fitted_at=fitted_at)
 original=s.current_model()
 value=monitor_diagnostic(a,s,p,now=T+timedelta(hours=3),sensor_epoch=EPOCH,guard=lambda:None)
 selection=value['selected_models']['native_temperature']
 assert selection['status']=='validated_configuration_not_serving_admission'
 assert selection['model_sha256']==model['artifact_sha256']
 assert selection['selection_original_sha256']==identity(original)
 assert selection['procedure']['training_policy_sha256'] is None
 assert value['release_authorized'] is False
 assert s.current_model()==original


def test_invalid_historical_selection_is_unavailable_rather_than_unselected(tmp_path):
 from weather_learning.operations import monitor_diagnostic
 a,s,p=_monitor_context(tmp_path)
 s._write(s.root/'historical-outdoor.json',{'schema':'unrecognized','model_sha256':'a'*64})
 value=monitor_diagnostic(a,s,p,now=T+timedelta(hours=3),sensor_epoch=EPOCH,guard=lambda:None)
 assert value['selected_models']['historical_temperature']['status']=='unavailable'
 assert value['selected_models']['historical_temperature']['model_sha256'] is None
 assert value['selected_models']['historical_wind']['status']=='not_selected'
