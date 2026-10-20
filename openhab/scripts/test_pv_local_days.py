"""Independent PV support is counted on Denver dates, never timestamp prefixes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from weather_learning.contracts import identity
from weather_learning.pv_calibration import fit_gain, assess_gain
from weather_learning.pv_directional_calibration import fit_directional, assess_directional
from weather_learning.pv_refresh import directional_if_changed, effective_if_changed, compare_incumbent


def pairs(starts, *, outcome=1200., repetitions=8):
    result=[]
    for stamp in starts:
        for i in range(repetitions):
            start=datetime.fromisoformat(stamp)+timedelta(minutes=i)
            row=dict(start=start.isoformat(),end=(start+timedelta(seconds=30)).isoformat(),
                origin=(start-timedelta(hours=1)).isoformat(),baseline_w=1000.,outcome_w=outcome,
                azimuth_degrees=110.,lead_hours=1.,forecast_sha256='a'*64,
                energy_source_sha256='b'*64,potential_proxy_eligible=True)
            row['pair_sha256']=identity(row);result.append(row)
    return result


CUTOFF=datetime(2026,6,4,tzinfo=timezone.utc)
TRAIN=['2026-06-01T23:00:00+00:00','2026-06-02T01:00:00+00:00','2026-06-03T01:00:00+00:00']
SUPPORTED=['2026-05-28T18:00:00+00:00','2026-05-29T18:00:00+00:00','2026-05-30T18:00:00+00:00']
HOLDOUT=['2026-06-05T23:00:00+00:00','2026-06-06T01:00:00+00:00']


def test_two_denver_training_days_cannot_satisfy_three_day_sector_support():
    rows=pairs(TRAIN)
    scalar=fit_gain(rows,cutoff=CUTOFF,trained_at=CUTOFF)
    model=fit_directional(rows,cutoff=CUTOFF,trained_at=CUTOFF)
    assert scalar['training_days']==model['training_days']==2
    assert model['sectors']['90']['pairs']==24
    assert model['sectors']['90']['training_days']==2
    assert model['sectors']['90']['supported'] is False
    assert model['sectors']['90']['gain']==1.


@pytest.mark.parametrize('fit,assess',[(fit_gain,assess_gain),(fit_directional,assess_directional)])
def test_one_denver_holdout_day_cannot_select_an_improved_candidate(fit,assess):
    model=fit(pairs(SUPPORTED),cutoff=CUTOFF,trained_at=CUTOFF)
    report=assess(model,pairs(HOLDOUT,repetitions=12),holdout_start=CUTOFF,
        holdout_end=CUTOFF+timedelta(days=3))
    assert report['pairs']==24
    assert report['candidate_mae_w']<report['baseline_mae_w']
    assert report['independent_target_days']==1
    assert report['selected'] is False


def test_incumbent_challenger_requires_two_denver_holdout_days():
    candidate=fit_directional(pairs(SUPPORTED),cutoff=CUTOFF,trained_at=CUTOFF)
    incumbent=fit_directional(pairs(SUPPORTED,outcome=1000.),cutoff=CUTOFF,trained_at=CUTOFF)
    report=compare_incumbent(candidate,incumbent,pairs(HOLDOUT,repetitions=12),
        holdout_start=CUTOFF,holdout_end=CUTOFF+timedelta(days=3))
    assert report['pairs']==24
    assert report['candidate_mae_w']<report['incumbent_mae_w']
    assert report['independent_target_days']==1
    assert report['selected'] is False


@pytest.mark.parametrize('stamps,want',[
    (['2026-03-08T01:30:00-07:00','2026-03-08T03:30:00-06:00'],1),
    (['2026-11-01T01:30:00-06:00','2026-11-01T01:30:00-07:00'],1),
    (['2026-06-01T23:30:00-06:00','2026-06-02T05:45:00+00:00'],1),
    (['2026-06-02T05:30:00+00:00','2026-06-02T06:30:00+00:00'],2),
])
def test_independent_days_normalize_mixed_offsets_and_both_dst_changes(stamps,want):
    rows=pairs(stamps,repetitions=1)
    cutoff=datetime(2027,1,1,tzinfo=timezone.utc)
    for fit in (fit_gain,fit_directional):
        assert fit(rows,cutoff=cutoff,trained_at=cutoff)['training_days']==want


@pytest.mark.parametrize('refresh,fit,schema',[
    (effective_if_changed,fit_gain,'earthship-pv-effective-calibration/v1'),
    (directional_if_changed,fit_directional,'earthship-pv-directional-calibration/v1'),
])
def test_legacy_models_remain_readable_but_cannot_noop_new_calendar_semantics(refresh,fit,schema):
    from weather_learning.pv_calibration import validate_model as scalar_validate
    from weather_learning.pv_directional_calibration import validate_model as directional_validate
    rows=pairs(SUPPORTED)
    legacy=deepcopy(fit(rows,cutoff=CUTOFF,trained_at=CUTOFF))
    legacy.update(schema=schema,training_days=99)
    legacy.pop('timezone',None);legacy.pop('independent_day_basis',None)
    legacy['rule']=legacy['rule'].removesuffix('_v2')+'_v1' if legacy['rule'].endswith('_v2') else legacy['rule']
    legacy['model_sha256']=identity({k:v for k,v in legacy.items() if k!='model_sha256'})
    before=deepcopy(legacy)
    validate=scalar_validate if fit is fit_gain else directional_validate
    assert validate(legacy)==before
    model,executed=refresh(legacy,rows,cutoff=CUTOFF,trained_at=CUTOFF+timedelta(days=1))
    assert executed is True
    assert model['schema'].endswith('/v3')
    assert model['training_days']==3
    assert model['timezone']=='America/Denver'
    assert model['independent_day_basis']=='interval_start_local_date'
    assert legacy==before
