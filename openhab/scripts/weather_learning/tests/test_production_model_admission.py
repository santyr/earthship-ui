"""Direct production selection is a new receipt, not a relabeled shadow original."""
from datetime import timedelta
from dataclasses import replace
import copy
import pytest
from learning_fixtures import T
from test_probabilistic import POLICY,frame
from test_probabilistic_artifacts import fitted
from weather_learning.contracts import identity

AUTH=dict(schema='earthship-weathernext-deployment-policy/v2',deployment_mode='direct_production_replacement',production_model_replacement_authorized=True,historical_retraining_authorized=True,parallel_shadow_required=False,advance_superiority_required_for_deployment=False,automatic_promotion=False,automatic_actuation=False,scientific_qualification_changed=False)
NOW=T+timedelta(days=15,minutes=2)


def test_explicit_production_receipt_serves_one_selected_method_without_rewriting_training():
 from weather_learning.production_model_admission import prepare_admission,predict_production
 prepared=fitted();before=prepared.bundle.to_dict();model=before['models']['temperature_normal']
 admission=prepare_admission(prepared.bundle,family='temperature_normal',expected_model_sha256=model['model_sha256'],policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)
 assert admission['admission_sha256']!=before['bundle_sha256']
 assert admission['method_family']=='temperature_normal' and admission['model_sha256']==model['model_sha256']
 assert admission['parallel_shadow_required'] is False and admission['local_coverage_qualified'] is False
 result=predict_production(prepared.bundle,admission,frame(15),policy=POLICY,authorize=lambda receipt:True)
 assert result['status']=='production_prediction' and result['point_estimate']==pytest.approx(12,abs=.5)
 assert result['point_estimate_kind']=='model_mean' and result['target_kind']=='outdoor_temperature_c'
 assert result['raw_mean']==10 and result['raw_median'] is None
 assert result['probability_claim'] is result['automatic_actuation'] is False
 assert prepared.bundle.to_dict()==before and prepared.training_dict()['training_inputs_sha256']==before['training_inputs_sha256']


def test_production_preparation_cannot_choose_a_cold_model_or_forge_authorization():
 from weather_learning.production_model_admission import prepare_admission
 original=fitted();pin=original.bundle.to_dict()['models']['temperature_normal']['model_sha256']
 for auth,expected in [(dict(AUTH,production_model_replacement_authorized=False),None),(AUTH,'f'*64)]:
  with pytest.raises(ValueError):prepare_admission(original.bundle,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=auth,authorization_sha256=identity(auth) if expected is None else expected,admitted_at=NOW)
 from test_probabilistic import pairs
 late=[replace(p,outcome_ready_at=(T+timedelta(days=30)).isoformat(),actual_outcome_available_at=(T+timedelta(days=30)).isoformat()) for p in pairs()]
 cold=fitted(late)
 with pytest.raises(ValueError,match='fitted'):prepare_admission(cold.bundle,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)


def test_live_owner_admission_and_original_expiry_are_required_for_predictions():
 from weather_learning.production_model_admission import prepare_admission,predict_production
 b=fitted().bundle;pin=b.to_dict()['models']['adaptive']['model_sha256']
 admission=prepare_admission(b,family='adaptive',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)
 for authorize in (None,lambda receipt:False):
  with pytest.raises(ValueError,match='owner'):predict_production(b,admission,frame(15),policy=POLICY,authorize=authorize)
 late=frame(31)
 with pytest.raises(ValueError,match='expired|lifetime'):predict_production(b,admission,late,policy=POLICY,authorize=lambda r:True)
 changed=copy.deepcopy(admission);changed['model_sha256']='f'*64;changed['admission_sha256']=identity({k:v for k,v in changed.items() if k!='admission_sha256'})
 with pytest.raises(ValueError,match='model'):predict_production(b,changed,frame(15),policy=POLICY,authorize=lambda r:True)
 value=predict_production(b,admission,frame(15),policy=POLICY,authorize=lambda r:True)
 assert value['status']=='production_prediction' and value['point_estimate_kind']=='adaptive_point'
 assert value['source_forecast_sha256']==frame(15).forecast_sha256


def test_a_new_sensor_cohort_is_refused_instead_of_silently_using_old_coefficients():
 from weather_learning.production_model_admission import prepare_admission,predict_production
 b=fitted().bundle;pin=b.to_dict()['models']['temperature_normal']['model_sha256']
 admission=prepare_admission(b,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)
 with pytest.raises(ValueError,match='cohort'):predict_production(b,admission,replace(frame(15),cohort_sha256='f'*64),policy=POLICY,authorize=lambda r:True)


def test_production_runs_only_the_selected_family_not_parallel_shadow_predictions(monkeypatch):
 from weather_learning.production_model_admission import prepare_admission,predict_production
 from weather_learning import probabilistic as kernel
 b=fitted().bundle;pin=b.to_dict()['models']['temperature_normal']['model_sha256'];calls=[]
 admission=prepare_admission(b,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)
 original=kernel.predict_marginal
 def record(model,*args,**kwargs):calls.append(model.to_dict()['family']);return original(model,*args,**kwargs)
 monkeypatch.setattr(kernel,'predict_marginal',record)
 predict_production(b,admission,frame(15),policy=POLICY,authorize=lambda r:True)
 assert calls==['temperature_normal']


@pytest.mark.parametrize('kind,target',[
 ('wind','local_station_hour_mean_wind_m_s'),
 ('solar_proxy','qualified_lux_proxy_hour_mean_w_m2'),
])
def test_nonnegative_targets_keep_their_actual_measurement_scope(kind,target):
 from weather_learning.production_model_admission import prepare_admission,predict_production
 from test_probabilistic import pairs
 b=fitted(pairs(kind)).bundle;pin=b.to_dict()['models']['nonnegative']['model_sha256']
 admission=prepare_admission(b,family='nonnegative',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=NOW)
 value=predict_production(b,admission,frame(15,kind=kind),policy=POLICY,authorize=lambda r:True)
 assert value['target_kind']==target and value['point_estimate']>=0 and value['point_estimate_kind']=='model_mean'
 assert value['probability_claim'] is False


def test_new_production_admission_does_not_renew_original_model_lifetime():
 from weather_learning.production_model_admission import prepare_admission
 b=fitted().bundle;body=b.to_dict();pin=body['models']['temperature_normal']['model_sha256']
 kwargs=dict(family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH))
 a=prepare_admission(b,admitted_at=NOW,**kwargs)
 later=prepare_admission(b,admitted_at=NOW+timedelta(days=1),**kwargs)
 assert a['valid_until']==later['valid_until']==body['expires_at']
 with pytest.raises(ValueError,match='lifetime'):prepare_admission(b,admitted_at=T+timedelta(days=15),**kwargs)
