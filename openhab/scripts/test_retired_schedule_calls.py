import unittest
from retired_schedule_calls import repair


def fixture(uid='1f692c798b', targets=None):
    return {'uid': uid, 'editable': True, 'triggers': [{'time': '21:00'}],
            'actions': [{'id': '2', 'type': 'core.ItemCommandAction',
                         'configuration': {'itemName': 'OverrideSwitch', 'command': 'ON'}},
                        {'id': '3', 'type': 'core.RunRuleAction', 'inputs': {},
                         'configuration': {'considerConditions': False,
                                           'ruleUIDs': targets if targets is not None else
                                           ['ab8a59e1da', 'GoatCamOff', '4e234eabea']}}]}


class RepairTests(unittest.TestCase):
    def test_on_preserves_coupling_and_schedule(self):
        source = fixture(); changed = repair(source)
        self.assertEqual(changed['triggers'], source['triggers'])
        self.assertEqual(changed['actions'][0], source['actions'][0])
        self.assertEqual(changed['actions'][1]['configuration'],
                         {'considerConditions': False, 'ruleUIDs': ['GoatCamOff']})
        self.assertEqual(len(source['actions'][1]['configuration']['ruleUIDs']), 3)
        self.assertEqual(repair(changed), changed)

    def test_off_removes_only_empty_call(self):
        source = fixture('b1501047a9', ['e647476610'])
        self.assertEqual(repair(source)['actions'], source['actions'][:1])

    def test_wrong_owner_refused(self):
        for uid in ('other', 'hex_night_load_override'):
            with self.assertRaises(ValueError):
                repair(fixture(uid))

    def test_wiring_refused(self):
        source = fixture('b1501047a9', ['e647476610'])
        source['actions'][1]['inputs'] = {'x': '2.y'}
        with self.assertRaises(ValueError):
            repair(source)


if __name__ == '__main__':
    unittest.main()
