from datetime import timedelta
from copy import deepcopy
import pytest
from weather_learning.tests.learning_fixtures import T
from weather_learning.contracts import identity


def rows(days=12):
 result=[]
 for day in range(days):
  origin=T+timedelta(days=day,hours=9)
  for lead in (1,6,12):
   r=dict(schema='earthship-historical-learning-pair/v1',kind='outdoor_temperature_c',origin=origin.isoformat(),target_at=(origin+timedelta(hours=lead)).isoformat(),
      lead_hours=lead,availability_basis='retrospective_assumed_full_cycle_9h',forecast_sha256=str(day%10)*64,
      features=dict(google_c=10.+day*.1,lead_days=lead/24),baseline=10.+day*.1,outcome=12.+day*.1,
      label=dict(snapshotSha256='a'*64),origin_labels={},prospective_score=False,automatic_actuation=False)
   r['pair_sha256']=identity(r);result.append(r)
 return result


def api():
 from weather_learning import site_calibration
 return site_calibration


def test_historical_residual_fit_improves_later_untouched_outcomes():
 dataset=rows();cutoff=T+timedelta(days=8)
 model=api().fit_residual(dataset,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=T+timedelta(days=20),correction_limit=6.)
 assert model['sample_count']==24
 assert model['training_end']<cutoff.isoformat()
 report=api().evaluate(model,dataset,holdout_start=cutoff,holdout_end=T+timedelta(days=12))
 assert report['pairs']==12;assert report['origin_days']==4
 assert report['baseline_mae']==pytest.approx(2)
 assert report['candidate_mae']<1e-6
 assert report['prospective_score'] is False
 future=deepcopy(dataset[-1]);future['origin']=(T+timedelta(days=21)).isoformat();future['target_at']=(T+timedelta(days=21,hours=6)).isoformat()
 assert api().predict(model,future['features'],baseline=future['baseline'],origin=T+timedelta(days=21))==pytest.approx(future['baseline']+2)
 with pytest.raises(ValueError,match='available'):api().predict(model,future['features'],baseline=10,origin=T+timedelta(days=10))


def test_holdout_does_not_train_on_earlier_issues_with_future_targets():
 dataset=rows();cutoff=T+timedelta(days=8)
 model=api().fit_residual(dataset,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=T+timedelta(days=20),correction_limit=6.)
 change=deepcopy(dataset)
 for r in change:
  if r['target_at']>=cutoff.isoformat():r['outcome']+=100;r.pop('pair_sha256');r['pair_sha256']=identity(r)
 other=api().fit_residual(change,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=T+timedelta(days=20),correction_limit=6.)
 assert model==other


def test_changed_pair_or_model_identity_is_refused():
 dataset=rows();dataset[0]['outcome']=999
 with pytest.raises(ValueError):api().fit_residual(dataset,kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=20),correction_limit=6.)
 model=api().fit_residual(rows(),kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=20),correction_limit=6.)
 model['intercept']+=1
 with pytest.raises(ValueError):api().predict(model,dict(google_c=10,lead_days=1),baseline=10,origin=T+timedelta(days=21))
