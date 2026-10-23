"""New production scores consume confirmed outputs and original measured targets."""
from datetime import timedelta
import pytest
from test_production_forecast import serving,NOW
from test_production_emissions import published
from weather_learning.shadow import ShadowStore
from weather_learning.contracts import instant,identity
from weather_learning.marginal_outcomes import temperature_observation
from learning_fixtures import receipt,EPOCH


def original(serving,tmp_path):
 from weather_learning.production_emissions import retain_prepared,confirm_publication
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'score-state')
 retain_prepared(state,product,provider=serving['provider'],now=NOW)
 emission=confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)
 target=next(r for r in emission['score_rows'] if r['kind']=='temperature')
 at=instant(target['at']);observation=temperature_observation(receipt(at,celsius=12),target=at,acquired_at=at+timedelta(minutes=3),sensor_epoch=EPOCH,observation_policy_sha256='c'*64)
 return state,emission,target,observation


def test_scoring_uses_the_confirmed_original_without_refit_or_current_selector(serving,tmp_path):
 from weather_learning.production_scoring import score_emitted
 state,emission,target,observation=original(serving,tmp_path)
 value=score_emitted(state,emission_sha256=emission['emission_sha256'],row_sha256=target['row_sha256'],observation=observation,assessed_at=instant(observation.to_dict()['available_at']))
 assert value['status']=='scored' and value['raw']['absolute_error']==2
 assert value['local']['absolute_error']<.5 and value['local']['interval_score_80']>=0
 assert value['local']['crps'] is not None and value['local']['local_coverage_qualified'] is False
 assert value['production_prediction_sha256'] and value['emission_sha256']==emission['emission_sha256']
 assert value['issued_prediction_used'] is True and value['model_retrained'] is False
 assert value['observation']['observation_sha256']==observation.to_dict()['observation_sha256']


def test_wrong_target_or_unpublished_row_never_gets_a_production_score(serving,tmp_path):
 from weather_learning.production_scoring import score_emitted
 state,emission,target,observation=original(serving,tmp_path);at=instant(target['at'])+timedelta(hours=1)
 other=temperature_observation(receipt(at),target=at,acquired_at=at+timedelta(minutes=3),sensor_epoch=EPOCH,observation_policy_sha256='c'*64)
 for row,obs in [(target['row_sha256'],other),('f'*64,observation)]:
  with pytest.raises(ValueError):score_emitted(state,emission_sha256=emission['emission_sha256'],row_sha256=row,observation=obs,assessed_at=at+timedelta(hours=1))


def test_new_sensor_phase_is_reported_as_incompatible_instead_of_matching_old_model_skill(serving,tmp_path):
 from weather_learning.production_scoring import score_emitted
 state,emission,target,observation=original(serving,tmp_path);at=instant(target['at']);epoch='00000000-0000-4000-8000-000000000009'
 changed=temperature_observation(receipt(at,epoch=epoch),target=at,acquired_at=at+timedelta(minutes=3),sensor_epoch=epoch,observation_policy_sha256='c'*64)
 value=score_emitted(state,emission_sha256=emission['emission_sha256'],row_sha256=target['row_sha256'],observation=changed,assessed_at=at+timedelta(minutes=4))
 assert value['status']=='observation_cohort_mismatch' and value['raw'] is None and value['local'] is None


def test_scoring_cannot_read_an_observation_before_its_actual_acquisition(serving,tmp_path):
 from weather_learning.production_scoring import score_emitted
 state,emission,target,observation=original(serving,tmp_path)
 with pytest.raises(ValueError,match='available|mature'):
  score_emitted(state,emission_sha256=emission['emission_sha256'],row_sha256=target['row_sha256'],observation=observation,assessed_at=instant(target['at'])+timedelta(minutes=2))
