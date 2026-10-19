import unittest
from weather_learning.config import AccessPolicy,Site
class ConfigTests(unittest.TestCase):
 def test_rejects_full_ensemble_and_requester_billing(self):
  for change in [dict(bucket='weathernext3_spatial'),dict(requester_billing_project='earthship-weather-research'),dict(paid_access_allowed=True),dict(full_ensemble_allowed=True)]:
   with self.subTest(change=change),self.assertRaises(ValueError):AccessPolicy(**change)
 def test_earthengine_requires_approved_noncommercial_configuration(self):
  with self.assertRaises(ValueError):AccessPolicy(backend='earthengine')
  self.assertEqual(AccessPolicy(backend='earthengine',noncommercial_verified=True).backend,'earthengine')
 def test_resource_bounds_not_disabled_or_silently_expanded(self):
  for change in [dict(max_bytes=0),dict(max_bytes=10**10),dict(max_targets=361),dict(max_seconds=0),dict(max_attempts=4),dict(max_pixels=1000000)]:
   with self.subTest(change=change),self.assertRaises(ValueError):AccessPolicy(**change)
 def test_site_is_loaded_from_openhab_regional_config(self):
  s=Site.from_openhab_config({'location':'38.3739919,-105.7744609','timezone':'America/Denver'})
  self.assertEqual(s.longitude,-105.7744609)
  self.assertEqual(s.longitude_360,254.2255391)
 def test_missing_or_approximate_site_has_no_fallback(self):
  for data in ({},{'location':'nan,0','timezone':'UTC'},{'location':'91,0','timezone':'UTC'},{'location':'38,-105','timezone':'not/a/zone'}):
   with self.subTest(data=data),self.assertRaises(ValueError):Site.from_openhab_config(data)
if __name__=='__main__':unittest.main()
