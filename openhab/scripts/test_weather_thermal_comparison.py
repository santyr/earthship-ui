from datetime import timedelta
import pytest
from test_household_pv_window import START


def test_google_thermal_forcings_use_known_origin_actions_and_hour_ending_irradiance():
 from weather_learning.thermal_comparison import google_forcings
 hours={at.isoformat():{'station_head_temperature_2m':temp,'surface_solar_radiation_downwards_1hr':radiation} for at,temp,radiation in [(START,10.,0.),(START+timedelta(hours=1),22.,600.),(START+timedelta(hours=2),34.,900.)]}
 actions={'indoor_shade_closed':.4,'outdoor_shade_present':0.,'vent_open':1.}
 forcing=google_forcings(hours,origin=START,actions=actions,horizon_hours=2)
 assert len(forcing)==24
 assert forcing[0].outdoor_f==pytest.approx(51.8)
 assert forcing[0].radiation_wm2==600
 assert forcing[12].radiation_wm2==900
 assert all(f.vent_open==1 and f.indoor_shade_closed==.4 for f in forcing)
 hours[(START+timedelta(hours=1)).isoformat()]['surface_solar_radiation_downwards_1hr']=None
 with pytest.raises(ValueError,match='complete'):google_forcings(hours,origin=START,actions=actions,horizon_hours=2)


def test_cadence_model_selection_never_uses_a_later_fit_or_current_weights():
 from weather_learning.thermal_comparison import select_fit
 base=START.replace(hour=6)
 models=[{'cutoff':(base+timedelta(hours=h)).isoformat(),'id':h} for h in (0,6,12,24)]
 origin=base+timedelta(hours=9)
 assert select_fit(models,origin=origin,cadence='six_hourly')['id']==6
 assert select_fit(models,origin=origin,cadence='daily')['id']==0
 assert select_fit(models,origin=base+timedelta(hours=6),cadence='six_hourly')['id']==0
 assert select_fit(models,origin=base-timedelta(hours=1),cadence='six_hourly') is None
