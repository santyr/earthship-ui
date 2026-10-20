"""Observation policy identity includes temperature validity and sensor policy."""
from dataclasses import replace
import unittest
from learning_fixtures import T,EPOCH
from weather_temperature_evidence import TemperaturePolicy
from weather_learning import monitor_worker

class MonitorPolicyTests(unittest.TestCase):
    def test_temperature_freshness_changes_observation_identity(self):
        self.assertTrue(hasattr(monitor_worker,'observation_policy_identity'))
        policy=TemperaturePolicy(model='Fineoffset-WH65B',sensor_id=123,minimum_f=-50,maximum_f=130,validity_seconds=120)
        def key(p=policy,**kw):
            return monitor_worker.observation_policy_identity(temperature_policy=p,
                policies=kw.get('policies',{'radiation':{'version':1},'rain':{'version':1}}),
                cutover=kw.get('cutover',T),sensor_epoch=kw.get('sensor_epoch',EPOCH))
        original=key()
        self.assertEqual(key(),original)
        self.assertNotEqual(key(replace(policy,validity_seconds=60)),original)
        self.assertNotEqual(key(replace(policy,sensor_id=124)),original)
        self.assertNotEqual(key(policies={'radiation':{'version':2}}),original)

    def test_database_reader_adapter_supplies_shared_remaining_deadline(self):
        from unittest.mock import Mock
        clock=Mock(return_value=100.)
        factory=Mock(return_value='fixture-connection')
        connect=monitor_worker.deadline_connection(factory,deadline=190.,clock=clock)
        self.assertEqual(connect(),'fixture-connection')
        remaining=factory.call_args.kwargs['remaining']
        self.assertEqual(remaining(),15.)
        clock.return_value=189.5
        with self.assertRaises(TimeoutError):connect()
        factory.assert_called_once()
