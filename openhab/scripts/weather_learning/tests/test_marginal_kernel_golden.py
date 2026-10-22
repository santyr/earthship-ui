"""Shared production math preserves the previous producer's declared numerics."""
from pathlib import Path
from datetime import timedelta
import json
import pytest
from test_probabilistic import POLICY,pairs,frame
from learning_fixtures import T
from weather_learning import probabilistic as kernel

GOLD=json.loads((Path(__file__).resolve().parents[4]/'tests/fixtures/marginal-kernel-a6a16d9.json').read_bytes())


def compare(actual,expected,tolerance):
 if isinstance(expected,dict):
  assert set(actual)==set(expected)
  for k,v in expected.items():compare(actual[k],v,tolerance)
 elif isinstance(expected,list):
  assert len(actual)==len(expected)
  for a,b in zip(actual,expected):compare(a,b,tolerance)
 elif type(expected) in (int,float):assert actual==pytest.approx(expected,abs=tolerance,rel=0)
 else:assert actual==expected


@pytest.mark.parametrize('case',GOLD['cases'],ids=[c['family']+'-'+c['kind'] for c in GOLD['cases']])
def test_original_fit_parameters_and_forecast_math_are_preserved(case):
 cutoff=T+timedelta(days=15)
 model=kernel.fit_marginal(pairs(case['kind']),family=case['family'],cutoff=cutoff,completed_at=cutoff+timedelta(minutes=1),policy=POLICY,ridge=1.)
 compare(model.to_dict()['parameters'],case['fitted_parameters'],GOLD['parameters_abs_tolerance'])
 value=kernel.predict_marginal(model,frame(15,kind=case['kind']),policy=POLICY).to_dict()
 compare({k:value[k] for k in case['prediction']},case['prediction'],GOLD['prediction_abs_tolerance'])
