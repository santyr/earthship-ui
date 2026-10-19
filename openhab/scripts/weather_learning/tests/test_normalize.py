from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import unittest
from weather_learning.normalize import normalize_point,daily_solar_energy,daily_rain_depth,nearest_cell
from weather_learning.config import Site
T=datetime(2026,10,18,tzinfo=timezone.utc)
BASE=dict(valid_at=T.isoformat(),source_ref='projects/gcp-public-data-weathernext/assets/run/image',source_digest='a'*64,latitude=38.4,longitude=-105.8)
def point(variable,value,unit,at=T,statistic='mean'):
 return normalize_point(variable,value,unit,**(BASE|dict(valid_at=at.isoformat())),statistic=statistic)
class NormalizeTests(unittest.TestCase):
 def test_temperature_original_and_units_preserved(self):
  r=point('station_head_temperature_2m',273.15,'K');self.assertEqual(r['value'],0);self.assertEqual(r['raw_value'],273.15);self.assertEqual(r['unit'],'degC')
 def test_hourly_solar_energy_to_mean_irradiance(self):
  r=point('surface_solar_radiation_downwards_1hr',360000,'J m**-2');self.assertEqual(r['value'],100);self.assertEqual(r['period_seconds'],3600)
 def test_unknown_schema_or_units_refused(self):
  for variable,value,unit in [('temperature_2m',0,'degC'),('unknown',1,'K')]:
   with self.assertRaises(ValueError):point(variable,value,unit)
 def test_missing_sun_stays_missing(self):
  self.assertIsNone(point('surface_solar_radiation_downwards_1hr',None,'J m**-2')['value'])
 def test_nonfinite_or_negative_accumulations_refused(self):
  for v in (float('nan'),float('inf'),-1):
   with self.assertRaises(ValueError):point('surface_solar_radiation_downwards_1hr',v,'J m**-2')
 def test_rain_depth_conversion(self):self.assertEqual(point('total_precipitation_1hr',.002,'m')['value'],2)
 def test_precipitation_products_keep_identity_native_depth_and_missingness(self):
  for variable in ('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr'):
   with self.subTest(variable=variable):
    row=point(variable,.002,'m')
    self.assertEqual((row['variable'],row['raw_value'],row['raw_unit'],row['value'],row['unit'],row['period_seconds']),(variable,.002,'m',2.,'mm',3600))
    self.assertIsNone(point(variable,None,'m')['value'])
    for invalid in (-.001,float('nan'),float('inf')):
     with self.assertRaises(ValueError):point(variable,invalid,'m')
    with self.assertRaises(ValueError):point(variable,2,'mm')
 def test_hourly_percentiles_are_not_summed_as_daily_percentiles(self):
  with self.assertRaises(ValueError):daily_solar_energy([point('surface_solar_radiation_downwards_1hr',360000,'J m**-2',statistic='p90')],date(2026,10,18),'UTC')
 def test_daily_energy_dst_and_incomplete_day(self):
  z=ZoneInfo('America/Denver')
  for d,hours in [(date(2026,3,8),23),(date(2026,11,1),25)]:
   first=datetime.combine(d,datetime.min.time(),z).astimezone(timezone.utc)
   points=[point('surface_solar_radiation_downwards_1hr',3600000,'J m**-2',first+timedelta(hours=i+1)) for i in range(hours)]
   self.assertAlmostEqual(daily_solar_energy(points,d,'America/Denver'),hours)
   self.assertIsNone(daily_solar_energy(points[:-1],d,'America/Denver'))
 def test_complete_rain_days_use_each_product_and_dst_hour_count(self):
  zone=ZoneInfo('America/Denver')
  for day,hours in ((date(2026,3,8),23),(date(2026,11,1),25)):
   start=datetime.combine(day,datetime.min.time(),zone).astimezone(timezone.utc)
   points=[point(variable,value,'m',start+timedelta(hours=hour+1)) for variable,value in (('total_precipitation_1hr',.001),('imerg_tp_1hr',.002),('experimental_tp_1hr',.003)) for hour in range(hours)]
   for variable,factor in (('total_precipitation_1hr',1),('imerg_tp_1hr',2),('experimental_tp_1hr',3)):
    with self.subTest(day=day,variable=variable):self.assertAlmostEqual(daily_rain_depth(points,day,zone.key,variable=variable),hours*factor)
 def test_rain_missing_hour_cannot_use_another_product_or_sum_quantiles(self):
  day=date(2026,10,18);start=datetime(2026,10,18,tzinfo=timezone.utc)
  points=[point(variable,.001,'m',start+timedelta(hours=hour+1)) for variable,hours in (('total_precipitation_1hr',23),('imerg_tp_1hr',24)) for hour in range(hours)]
  self.assertIsNone(daily_rain_depth(points,day,'UTC'))
  with self.assertRaises(ValueError):daily_rain_depth([point('imerg_tp_1hr',.001,'m',start+timedelta(hours=1),statistic='p90')],day,'UTC',variable='imerg_tp_1hr')
 def test_native_grid_selection_is_deterministic_and_wraps_longitude(self):
  s=Site(38.3739919,-105.7744609,'America/Denver')
  self.assertEqual(nearest_cell([38.3,38.4],[254.2,254.3],s),(1,0))
if __name__=='__main__':unittest.main()
