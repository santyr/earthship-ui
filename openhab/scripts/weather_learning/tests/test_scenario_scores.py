"""Dependence scores use complete original local trajectories, never hourly ranks."""
from copy import deepcopy
from datetime import timedelta
from math import sqrt,fsum
import importlib
import pytest
from test_household_weather_scenarios import context,residual_blocks,ORIGIN,POLICY
from weather_learning.scenarios import joint_scenarios,stress_cases
from weather_learning.contracts import instant


def example():
 c=context();joint=joint_scenarios(**c,blocks=residual_blocks(),cohort_sha256='c'*64)
 pos=next(s for s in joint['scenarios'] if s.to_dict()['block_original']['residuals'][0]['temperature_c']>0)
 neg=next(s for s in joint['scenarios'] if s.to_dict()['block_original']['residuals'][0]['temperature_c']<0)
 obs=[dict(at=r['at'],temperature_c=(r['tempF']-32)/1.8,wind_m_s=r['windMph']*.44704,ghi_wm2=r['radiationWm2'],solar_quantity='physical_global_horizontal_irradiance',available_at=(instant(r['at'])+timedelta(minutes=5)).isoformat(),measurement_cohort_sha256='c'*64,original_sha256='d'*64) for r in c['forcing']['rows']]
 return [pos,neg],obs

def api():return importlib.import_module('weather_learning.scenario_scores')


def test_empirical_energy_score_uses_whole_scaled_vectors_and_keeps_date_support_small():
 scenarios,obs=example();before=[s.content for s in scenarios]
 r=api().assess_joint(scenarios,observations=obs,assessed_at=ORIGIN+timedelta(hours=4))
 n=len(obs)-1
 radius=sqrt(fsum((.2*(i+1)/5)**2+(.1*(i+1)/3)**2+(6*(i+1)/300)**2 for i in range(1,len(obs)))/n)
 assert r['candidate']['energy_score']==pytest.approx(radius/2)
 assert r['raw_mean_reference']['energy_score']==pytest.approx(0)
 assert r['candidate']['variogram_score_p05']>=0
 assert r['support']=={'forecast_origins':1,'targets':3,'local_dates':1,'scenarios':2}
 assert r['disposition']=='insufficient_evidence'
 assert r['probability_claim'] is r['automatic_actuation'] is False
 assert [s.content for s in scenarios]==before
 assert r['candidate']['hourly_ramp_mae']['temperature_c']>=0


@pytest.mark.parametrize('damage',['future','proxy','missing','cohort','duplicate','stress'])
def test_mismatched_labels_or_non_joint_members_cannot_be_scored_as_joint_ensemble(damage):
 scenarios,obs=example()
 if damage=='future':obs[-1]['available_at']=(ORIGIN+timedelta(days=1)).isoformat()
 elif damage=='proxy':obs[-1]['solar_quantity']='reported_local_proxy'
 elif damage=='missing':obs.pop()
 elif damage=='cohort':obs[-1]['measurement_cohort_sha256']='e'*64
 elif damage=='duplicate':scenarios.append(scenarios[0])
 else:scenarios=list(stress_cases(**context()))
 with pytest.raises(ValueError):api().assess_joint(scenarios,observations=obs,assessed_at=ORIGIN+timedelta(hours=4))


def test_constant_series_correlation_is_explicitly_undefined_not_zero_skill():
 scenarios,obs=example();r=api().assess_joint(scenarios,observations=obs,assessed_at=ORIGIN+timedelta(hours=4))
 assert r['observed_dependence']['lag1']['temperature_c']['correlation'] is None
 assert r['observed_dependence']['cross_variable']['temperature_c:ghi_wm2']['correlation'] is None
 assert r['trajectory_range_coverage']['all_targets_and_variables_inside'] is True
 assert 'reserve_breach_probability' not in r
