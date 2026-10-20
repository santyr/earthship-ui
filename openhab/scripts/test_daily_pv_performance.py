from copy import deepcopy
from datetime import timedelta
import pytest
from test_daily_pv_monitor import forecast,START,END
from test_weather_energy_history import source
from weather_learning.contracts import identity,instant


def retained(soc=80):
    from daily_pv_monitor import score_hour
    s=score_hour(forecast(),source(soc),assessed_at=END+timedelta(minutes=6))
    s['runtime_manifest']={'daily_pv_monitor.py':'e'*64};s['original_file_sha256']='f'*64
    s['score_sha256']=identity({k:v for k,v in s.items() if k!='score_sha256'})
    return s


def test_coverage_distinguishes_charge_limits_missing_measurements_and_darkness():
    from daily_pv_monitor import score_hour
    good=retained();high=retained(99)
    assert good['bin_accounting']['eligible_bins']==12
    assert high['bin_accounting']['censored_bins']==12 and high['candidate_mae_w'] is None
    incomplete=source();incomplete['rows']['soc']=[];incomplete['source_sha256']=identity({k:v for k,v in incomplete.items() if k!='source_sha256'})
    missing=score_hour(forecast(),incomplete,assessed_at=END+timedelta(minutes=6))
    assert missing['bin_accounting']['unqualified_bins']==12
    # Companion packet identities are not guessed; use an explicit summary fixture.
    import daily_pv_monitor as monitor
    from weather_learning.energy_history import summarize_hour
    bins=summarize_hour(source())
    for b in bins:b['potential_proxy_eligible']=False;b['fields']['pv.input_power_w']['positive_kwh']=0.
    from unittest.mock import patch
    with patch.object(monitor,'summarize_hour',return_value=bins):night=score_hour(forecast(),source(),assessed_at=END+timedelta(minutes=6))
    assert night['bin_accounting']['low_generation_bins']==12 and night['candidate_mae_w'] is None


def test_report_retains_null_metrics_for_censored_periods_and_separates_versions():
    from daily_pv_performance import build_view
    a=retained(99);b=deepcopy(a);b['calibration_policy_sha256']='b'*64;b['schema']='earthship-pv-prospective-hour-score/v3';b['score_sha256']=identity({k:v for k,v in b.items() if k!='score_sha256'})
    view=build_view([a,b],generated_at=END+timedelta(minutes=10))
    assert len(view['cohorts'])==2 and view['status']=='collecting'
    for c in view['cohorts']:
        assert c['censored_bins']==12 and c['baseline_mae_w'] is None and c['candidate_mae_w'] is None
    assert view['automatic_actuation'] is False and view['physical_calibration_qualified'] is False


def test_report_combines_duration_weighted_errors_and_marks_legacy_coverage_unknown():
    from daily_pv_performance import build_view
    a=retained();b=deepcopy(a)
    for key in ('window_start','window_end','assessed_at'):b[key]=(instant(b[key])+timedelta(hours=1)).isoformat()
    b['pairs']=b['pairs'][:6]
    for p in b['pairs']:
        for key in ('start','end'):p[key]=(instant(p[key])+timedelta(hours=1)).isoformat()
        p['candidate_w']=900.
    b.update(eligible_bins=6,adjusted_bins=6,covered_seconds=1800.,candidate_mae_w=100.)
    b['bin_accounting'].update(eligible_bins=6,low_generation_bins=6)
    b['score_sha256']=identity({k:v for k,v in b.items() if k!='score_sha256'})
    v=build_view([a,b],generated_at=END+timedelta(hours=1,minutes=10));c=v['cohorts'][0]
    assert c['eligible_bins']==18 and c['covered_seconds']==5400
    assert c['candidate_mae_w']==pytest.approx(100/3) and c['baseline_mae_w']==200
    legacy=retained(99);legacy.pop('bin_accounting');legacy['schema']='earthship-pv-prospective-hour-score/v1';legacy['score_sha256']=identity({k:v for k,v in legacy.items() if k!='score_sha256'})
    old=build_view([legacy],generated_at=END+timedelta(minutes=10))['cohorts'][0]
    assert old['unknown_coverage_bins']==12 and old['censored_bins']==0


@pytest.mark.parametrize('damage',['identity','future','pair_metric','duplicate_pair'])
def test_report_rejects_changed_noncausal_or_inconsistent_originals(damage):
    from daily_pv_performance import build_view
    s=retained()
    if damage=='identity':s['candidate_mae_w']=99
    elif damage=='future':s['assessed_at']=(END+timedelta(days=1)).isoformat()
    elif damage=='pair_metric':s['candidate_mae_w']=99
    else:s['pairs'][1]=deepcopy(s['pairs'][0])
    if damage!='identity':s['score_sha256']=identity({k:v for k,v in s.items() if k!='score_sha256'})
    with pytest.raises(ValueError):build_view([s],generated_at=END+timedelta(minutes=10))
