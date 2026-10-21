"""Matched baselines must use the exact qualified outcome and original forcing."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from native_solar_fixtures import T,SITE,ARRAY,HORIZON,snapshot,geometry
from weather_learning.native_forecast import make_native_component_forecast
from weather_learning.contracts import identity


def inputs():
    origin=T+timedelta(hours=1);start=origin+timedelta(minutes=5);end=start+timedelta(minutes=5)
    f=make_native_component_forecast(snapshot(),origin=origin,horizon_hours=1,available_by=origin,site=SITE)
    label=dict(start=start.isoformat(),end=end.isoformat(),origin=origin.isoformat(),forecast_sha256=f['snapshot_sha256'],
        energy_source_sha256='e'*64,outcome_w=123.,potential_proxy_eligible=True)
    observation=dict(start=label['start'],end=label['end'],source_sha256='e'*64,outcome_w=123.,
        available_at=(end+timedelta(days=3)).isoformat(),potential_proxy_eligible=True,cohort_sha256='c'*64)
    return dict(labels=[label],observations={(label['start'],label['end']):observation},forcing=f,
        positions=geometry(count=36),array=ARRAY,horizon_profile=HORIZON,timezone_name='UTC',fixed_gain_by_sector={str(i):1.1 for i in range(0,360,45)},fixed_gain_source_sha256='f'*64)

def api():return importlib.import_module('weather_learning.solar_pairing')

def test_native_and_total_baseline_pair_uses_one_exact_outcome_and_keeps_actual_capture():
    values=inputs();rows=api().component_pairs(**values)
    assert len(rows)==1;row=rows[0]
    assert row['outcome_w']==123 and row['native_w']<row['total_only_w']
    assert row['fixed_gain']==1.1 and row['fixed_gain_source_sha256']=='f'*64
    assert row['native_supported'] is True and row['fallback_reason'] is None
    assert row['outcome_available_at']==values['observations'][(row['start'],row['end'])]['available_at']
    assert row['pair_sha256']==identity({k:v for k,v in row.items() if k!='pair_sha256'})


@pytest.mark.parametrize('change',[{'outcome_w':124},{'source_sha256':'a'*64},{'potential_proxy_eligible':False}])
def test_original_outcome_or_censoring_mismatch_cannot_enter_a_new_pair(change):
    values=inputs();next(iter(values['observations'].values())).update(change)
    with pytest.raises(ValueError):api().component_pairs(**values)


def test_wrong_forecast_or_missing_qualified_measurement_cannot_be_repaired_with_a_label():
    values=inputs();values['labels'][0]['forecast_sha256']='a'*64
    with pytest.raises(ValueError):api().component_pairs(**values)
    values=inputs();values['observations'].clear()
    with pytest.raises(ValueError):api().component_pairs(**values)
