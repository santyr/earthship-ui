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


def test_marginal_monitor_is_disabled_without_its_separate_index(tmp_path):
    from weather_learning.shadow import ShadowStore
    assert hasattr(monitor_worker,'marginal_monitor_callback'), 'Task7 optional marginal worker adapter missing'
    state=ShadowStore(tmp_path/'state');before=set(state.root.rglob('*'))
    callback=monitor_worker.marginal_monitor_callback(state,observation_policy_sha256='a'*64,sensor_epoch=EPOCH,
        read_temperature=lambda *a:None,read_wind=lambda *a:None,read_solar=lambda *a:None,clock=lambda:T)
    assert callback is None and set(state.root.rglob('*'))==before


def test_marginal_worker_scores_through_existing_native_temperature_reader(tmp_path):
    from test_marginal_queue import setup
    from learning_fixtures import receipt
    from datetime import timedelta
    assert hasattr(monitor_worker,'marginal_monitor_callback'), 'Task7 optional marginal worker adapter missing'
    state,_,_,_,at,_=setup(tmp_path);now=at+timedelta(hours=1,minutes=2);calls=[]
    def temperature(targets,assessed):calls.append((targets,assessed));return {t:receipt(t) for t in targets}
    def unexpected(*a):raise AssertionError('temperature target must not query another domain')
    callback=monitor_worker.marginal_monitor_callback(state,observation_policy_sha256='a'*64,sensor_epoch=EPOCH,
        read_temperature=temperature,read_wind=unexpected,read_solar=unexpected,clock=lambda:now)
    result=callback(now=now,limit=1,apply=True,guard=lambda:None)
    assert result['scored']==1 and len(calls)==1 and calls[0][0]==[at+timedelta(hours=1)]
