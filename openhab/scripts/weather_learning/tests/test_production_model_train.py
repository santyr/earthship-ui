"""Current-time historical fitting creates only retained production artifacts."""
import gzip,json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from learning_fixtures import T
from test_probabilistic import POLICY
from test_production_training import historical,context,cohort,CUTOFF
from test_production_model_admission import AUTH
from weather_learning.contracts import canonical,identity


def population(tmp_path):
 rows=historical();pin=cohort(context())
 value=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[asdict(p) for p in rows],
  partitions={},metadata={'quality_contexts':{pin:dict(kind='temperature',measurement_quality=context()['measurement_quality'],retrospective_cohort_only=True)}},source_scope='synthetic bounded original fixture')
 value['population_sha256']=identity(value);p=tmp_path/(value['population_sha256']+'.population.json.gz');p.write_bytes(gzip.compress(canonical(value),mtime=0));p.chmod(0o600);return p,pin


def test_explicit_historical_retraining_preview_then_retention_never_activates_selectors(tmp_path):
 from production_model_train import run
 p,pin=population(tmp_path);state=tmp_path/'production';clock=lambda:CUTOFF+timedelta(minutes=1)
 kwargs=dict(population=p,cohort_sha256=pin,state_root=state,family='temperature_normal',policy=POLICY,authorization=AUTH,clock=clock)
 preview=run(**kwargs)
 assert preview['status']=='production_fit_prepared' and preview['training_availability_basis']=='historical_assumed_availability'
 assert not state.exists()
 actual=run(apply=True,**kwargs)
 assert actual['artifact']['bundle_sha256']==actual['bundle_sha256'] and actual['retained'] is True
 assert actual['kind']==preview['kind']=='temperature'
 assert actual['production_installed'] is False and actual['selection_installed'] is False
 assert not (state/'production-current.json').exists()
 before={str(p):p.read_bytes() for p in state.rglob('*') if p.is_file()}
 run(**kwargs)
 assert {str(p):p.read_bytes() for p in state.rglob('*') if p.is_file()}==before


def test_a_sparse_training_result_is_an_explicit_refusal_with_no_state_creation(tmp_path):
 from production_model_train import run
 p,pin=population(tmp_path);state=tmp_path/'cold'
 result=run(population=p,cohort_sha256=pin,state_root=state,family='temperature_normal',policy=POLICY,authorization=AUTH,apply=True,clock=lambda:T+timedelta(days=20))
 assert result['status']=='insufficient_training_support' and result['retained'] is False and not state.exists()
