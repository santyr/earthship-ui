"""Pinned SDK interface verification; isolated environment, no live requests."""
import importlib.util,inspect,tempfile,unittest
from pathlib import Path
from capability_fixtures import reader
from weather_learning.archive import Archive
from weather_learning.worker import collect_once

@unittest.skipUnless(importlib.util.find_spec('ee'),'requires isolated pinned Earth Engine environment')
class CapabilitySDKTests(unittest.TestCase):
    def test_all_profiles_bind_native_point_queries_to_the_actual_sdk_signature(self):
        import ee
        signature=inspect.signature(ee.ImageCollection.getRegion)
        r,now=reader()
        with tempfile.TemporaryDirectory() as directory:
            value=collect_once(r,Archive(Path(directory)/'archive'),probe=False,horizon=360,include_interim=True,
                clock=lambda:now[0],optional_profiles=('uncertainty-v1','atmosphere-v1','rain-uncertainty-v1'))
        self.assertEqual(len(value['capabilities']),5)
        self.assertEqual(len(r.ee.queries),11)
        self.assertEqual({q['grid'] for q in r.ee.queries},{'station','gridded'})
        for query in r.ee.queries:
            bound=signature.bind(None,query['point'],scale=query['scale'],crs=query['crs'],crsTransform=query['crsTransform'])
            bound.apply_defaults()
            self.assertIs(bound.arguments['crs'],r.ee.projections[query['grid']])
            self.assertIsNone(bound.arguments['scale']);self.assertIsNone(bound.arguments['crsTransform'])

if __name__=='__main__':unittest.main()
