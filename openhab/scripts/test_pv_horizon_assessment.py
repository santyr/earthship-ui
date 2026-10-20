from datetime import timedelta
from test_household_pv_window import START
from test_weather_directional_pv import rows
from weather_learning.contracts import identity


def test_pv_lead_assessment_retains_raw_for_a_worse_or_unsupported_band():
    from weather_learning.pv_horizon_assessment import assess_horizons
    from weather_learning.pv_directional_calibration import fit_directional
    cutoff=START+timedelta(days=8);model=fit_directional(rows(),cutoff=cutoff,trained_at=START+timedelta(days=40));data=[]
    for day in range(25,29):
        for i in range(8):
            end=START+timedelta(days=day,minutes=5*i)
            for band,lead in enumerate((6,36)):
                row=dict(start=(end-timedelta(minutes=5)).isoformat(),end=end.isoformat(),origin=(end-timedelta(hours=lead)).isoformat(),
                    baseline_w=1000. if band==0 else 500.,outcome_w=700.,azimuth_degrees=110.,elevation_degrees=25.,horizon_elevation_degrees=10.,lead_hours=lead,
                    forecast_sha256='a'*63+str(band),energy_source_sha256='b'*64,potential_proxy_eligible=True)
                row['pair_sha256']=identity(row);data.append(row)
    report=assess_horizons(model,data,cutoff=cutoff,end=START+timedelta(days=30))
    assert report['by_lead']['0-24h']['supported'] is True
    assert report['by_lead']['24-48h']['supported'] is False
    assert report['by_lead']['48-72h']['pairs']==0
    assert report['supported_lead_ranges_hours']==[[0,24]]
    assert report['terrain']['independent_target_intervals']==32
    assert report['terrain']['horizon_update_qualified'] is False
    assert report['prospective_score'] is False and report['automatic_actuation'] is False


def test_horizon_assessment_excludes_origins_before_training_readiness():
    from weather_learning.pv_horizon_assessment import assess_horizons
    from weather_learning.pv_directional_calibration import fit_directional
    from datetime import datetime
    cutoff=START+timedelta(days=8);model=fit_directional(rows(),cutoff=cutoff,trained_at=START+timedelta(days=40));data=rows()
    # The fixture's post-cutoff outcomes retain their much earlier origin.
    report=assess_horizons(model,data,cutoff=cutoff,end=START+timedelta(days=30))
    assert all(row['pairs']==0 for row in report['by_lead'].values())
