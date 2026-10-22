"""Original local rain predictions survive scoring without refitting."""
from datetime import datetime,timezone
from importlib import import_module
import pytest
from test_rain_two_part import balanced,fit,future
from test_rain_calibration import POLICY
from weather_learning.contracts import canonical,identity,instant


def api():return import_module('weather_learning.rain_issues')


def test_supported_local_issue_retains_exact_interval_model_and_probabilities(balanced):
 model=fit(balanced)['model'];f=future(.25);cohort=balanced[1][0].to_dict()['cohort_sha256']
 issue=api().make_issue(f,model=model,observation_cohort_sha256=cohort,policy=POLICY,prepared_at=datetime(2026,6,16,tzinfo=timezone.utc),mode='causal_retrospective_experiment')
 value=issue.to_dict();assert value['model']['model_sha256']==model['model_sha256']
 assert value['local_prediction']['probability_wet']>.5
 assert value['local_prediction']['native_google_probability'] is False
 assert value['prospective_score'] is value['automatic_actuation'] is False
 assert api().RainIssue(issue.content).to_dict()==value
 value['local_prediction']['probability_wet']=0.;value['issue_sha256']=identity({k:v for k,v in value.items() if k!='issue_sha256'})
 with pytest.raises(ValueError):api().RainIssue(canonical(value))


def test_missing_model_retains_raw_rain_without_zero_probability_or_gain(balanced):
 f=future(.25);issue=api().make_issue(f,model=None,observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY,prepared_at=datetime(2026,6,16,tzinfo=timezone.utc),mode='causal_retrospective_experiment')
 value=issue.to_dict();assert value['local_prediction']['probability_wet'] is None
 assert value['fallback_mean_mm']==f.to_dict()['products_mm']['total_precipitation_1hr']
 assert value['gain_prediction_mm'] is None and value['raw_production_rain_retained'] is True


def test_historical_preparation_cannot_be_labeled_prospective_shadow(balanced):
 with pytest.raises(ValueError,match='prospective'):
  api().make_issue(future(.25),model=None,observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY,prepared_at=datetime(2026,6,16,tzinfo=timezone.utc),mode='prospective_shadow')


def test_retained_issue_validation_uses_its_original_numerical_identity(balanced,monkeypatch):
 from weather_learning import rain_two_part as kernel
 model=fit(balanced)['model'];issue=api().make_issue(future(.25),model=model,observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY,prepared_at=datetime(2026,6,16,tzinfo=timezone.utc),mode='causal_retrospective_experiment')
 monkeypatch.setattr(kernel,'numerical_sources',lambda:{'next-source.py':'0'*64})
 # This validates an already retained prediction, not a fresh model invocation.
 assert api().RainIssue(issue.content).to_dict()['local_prediction']==issue.to_dict()['local_prediction']
 with pytest.raises(ValueError,match='numerical sources'):kernel.predict_two_part(model,future(.25),observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY)
