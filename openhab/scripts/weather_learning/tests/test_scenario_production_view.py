"""Curated production schema carries quantities and provenance, never originals."""
from datetime import timedelta
import importlib
from test_scenario_reporting import args,ORIGIN
from weather_learning.scenario_reporting import prepare_report
from weather_learning.contracts import canonical


def test_closed_production_view_keeps_three_cases_and_qualified_quantity_names():
 api=importlib.import_module('weather_learning.scenario_retention');report=prepare_report(**args())
 view=api.production_view(report)
 assert view['schema']=='earthship-production-weather-sensitivity/v1'
 assert [r['name'] for r in view['cases']]==['central','reduced_solar','warm_high_gain']
 assert view['cases'][0]['raw_potential_pv_kwh']==report.to_dict()['output']['stress'][0]['pv']['potential_pv_kwh']
 assert view['joint_status']=='insufficient_evidence' and view['probability_claim'] is False
 assert view['initial_soc_pct']==80 and view['fixed_load_ac_w']==500
 assert view['valid_until']==(ORIGIN+timedelta(hours=1)).isoformat()
 assert all(word not in canonical(view) for word in [b'source_original',b'owned_sources',b'/home/',b'/tmp/'])
