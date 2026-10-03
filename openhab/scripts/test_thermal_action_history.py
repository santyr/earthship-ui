from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from thermal_model.action_history import (fetch_origin_actions,
                                         fetch_origin_actions_batch,
                                         hold_confirmed_shades,
                                         select_origin_actions)

ORIGIN = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)


def row(identity, *, name='outdoor_shade', state='installed',
        effective=None, received=None, created=None, supersedes=None,
        source='manual_dm'):
    return {'event_id': identity, 'effective_at': effective or ORIGIN - timedelta(hours=2),
            'received_at': received or ORIGIN - timedelta(hours=1),
            'created_at': created or ORIGIN - timedelta(minutes=50),
            'name': name, 'state': state, 'source': source,
            'confidence': 1.0, 'supersedes': supersedes}


class ActionHistoryTests(unittest.TestCase):
    def test_late_capture_and_late_correction_cannot_rewrite_origin(self):
        old = row('old')
        backdated = row('backdated', created=ORIGIN + timedelta(minutes=1),
                        state='removed', supersedes='old')
        later = row('later', received=ORIGIN + timedelta(minutes=1),
                    created=ORIGIN + timedelta(minutes=2), state='removed', supersedes='old')
        future = row('future', effective=ORIGIN + timedelta(minutes=1),
                     received=ORIGIN + timedelta(minutes=2),
                     created=ORIGIN + timedelta(minutes=3), state='removed')
        result = select_origin_actions([old, backdated, later, future], [], origin=ORIGIN)
        self.assertEqual(result['actions']['outdoor_shade']['event_id'], 'old')
        self.assertEqual(result['status'], 'as_of_snapshot_not_outcome_confirmation')
        self.assertIn('vent', result['missing_actions'])

    def test_known_correction_and_mode(self):
        old = row('old')
        corrected = row('correction', state='removed', supersedes='old',
                        received=ORIGIN - timedelta(minutes=20),
                        created=ORIGIN - timedelta(minutes=10))
        mode = row('mode', name='warm', state='warm')
        result = select_origin_actions([old, corrected], [mode], origin=ORIGIN)
        self.assertEqual(result['actions']['outdoor_shade']['state'], 'removed')
        self.assertEqual(result['mode']['state'], 'warm')

    def test_window_and_skylight_states_stay_distinct_at_origin(self):
        window = row('window-closed', name='window', state='closed')
        skylight = row('skylight-open', name='skylight', state='open')
        later = row('window-later', name='window', state='open',
                    supersedes='window-closed', received=ORIGIN + timedelta(minutes=1),
                    created=ORIGIN + timedelta(minutes=2))
        result = select_origin_actions([window, skylight, later], [], origin=ORIGIN,
                                       vocabulary_version=2)
        self.assertEqual(result['vocabulary_version'], 2)
        self.assertEqual(result['actions']['window']['state'], 'closed')
        self.assertEqual(result['actions']['skylight']['state'], 'open')
        self.assertNotIn('window', result['missing_actions'])
        self.assertNotIn('skylight', result['missing_actions'])
        self.assertIn('vent', result['missing_actions'])
        with self.assertRaisesRegex(ValueError, 'unexpected action'):
            select_origin_actions([window, skylight], [], origin=ORIGIN)

    def test_duplicate_and_future_effective_receipt_refused(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            select_origin_actions([row('same'), row('same')], [], origin=ORIGIN)
        with self.assertRaisesRegex(ValueError, 'chronology'):
            select_origin_actions([row('plan', effective=ORIGIN + timedelta(hours=1))],
                                  [], origin=ORIGIN)

    def test_fetch_requires_read_only_snapshot_and_closes_connection(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=None)
        cursor.fetchone.return_value = ('on',)
        cursor.fetchall.side_effect = [[], []]
        connection = Mock()
        connection.get_transaction_status.return_value = 0
        connection.cursor.return_value = cursor
        result = fetch_origin_actions(lambda: connection, origin=ORIGIN)
        self.assertEqual(result['actions'], {})
        connection.set_session.assert_called_once_with(
            readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        connection.close.assert_called_once()
        self.assertEqual(cursor.execute.call_count, 5)

    def test_v2_fetch_refuses_before_database_connection(self):
        with self.assertRaisesRegex(ValueError, 'not release-qualified'):
            fetch_origin_actions(lambda: self.fail('database connection opened'),
                                 origin=ORIGIN, vocabulary_version=2)

    def test_batch_uses_one_snapshot_and_keeps_receipt_availability_at_each_origin(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=None)
        cursor.fetchone.return_value = ('on',)
        event = row('new', name='indoor_shade', state='closed',
                    received=ORIGIN + timedelta(minutes=5),
                    created=ORIGIN + timedelta(minutes=6))
        cursor.fetchall.side_effect = [[tuple(event[key] for key in (
            'event_id', 'received_at', 'created_at', 'effective_at', 'name',
            'state', 'source', 'confidence', 'supersedes'))], []]
        connection = Mock()
        connection.get_transaction_status.return_value = 0
        connection.cursor.return_value = cursor
        origins = [ORIGIN, ORIGIN + timedelta(minutes=5), ORIGIN + timedelta(minutes=6)]
        snapshots = fetch_origin_actions_batch(lambda: connection, origins=origins)
        self.assertEqual([s['actions'] for s in snapshots[:2]], [{}, {}])
        self.assertEqual(snapshots[2]['actions']['indoor_shade']['state'], 'closed')
        self.assertEqual([s['origin'] for s in snapshots], origins)
        self.assertEqual(cursor.execute.call_count, 5)
        connection.set_session.assert_called_once_with(
            readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        connection.close.assert_called_once()

    def test_batch_invalid_bounds_refuse_before_connection(self):
        cases = [[], [ORIGIN, ORIGIN], [ORIGIN.replace(tzinfo=None)],
                 [ORIGIN, ORIGIN + timedelta(days=15)],
                 [ORIGIN + timedelta(minutes=i) for i in range(97)]]
        for origins in cases:
            with self.subTest(origins=origins), self.assertRaises(ValueError):
                fetch_origin_actions_batch(lambda: self.fail('connection opened'), origins=origins)

    def test_batch_closes_connection_on_incomplete_query(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=None)
        cursor.fetchone.return_value = ('on',)
        cursor.fetchall.side_effect = RuntimeError('query unavailable')
        connection = Mock()
        connection.get_transaction_status.return_value = 0
        connection.cursor.return_value = cursor
        with self.assertRaises(RuntimeError):
            fetch_origin_actions_batch(lambda: connection, origins=[ORIGIN])
        connection.close.assert_called_once()

    def test_batch_preserves_requested_order_without_backdating_correction(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=None)
        cursor.fetchone.return_value = ('on',)
        old = row('old', name='indoor_shade', state='open')
        late = row('late', name='indoor_shade', state='closed', supersedes='old',
                   received=ORIGIN+timedelta(minutes=1), created=ORIGIN+timedelta(minutes=2))
        keys = ('event_id', 'received_at', 'created_at', 'effective_at', 'name',
                'state', 'source', 'confidence', 'supersedes')
        cursor.fetchall.side_effect = [[tuple(r[k] for k in keys) for r in (old, late)], []]
        connection = Mock()
        connection.get_transaction_status.return_value = 0
        connection.cursor.return_value = cursor
        origins = [ORIGIN+timedelta(minutes=3), ORIGIN]
        result = fetch_origin_actions_batch(lambda: connection, origins=origins)
        self.assertEqual([s['origin'] for s in result], origins)
        self.assertEqual([s['actions']['indoor_shade']['state'] for s in result], ['closed', 'open'])
        for call in cursor.execute.call_args_list[-2:]:
            self.assertEqual(call.args[1], (origins[0],)*3 + (10001,))

    def test_batch_v2_gate_remains_closed_before_connection(self):
        with self.assertRaisesRegex(ValueError, 'not release-qualified'):
            fetch_origin_actions_batch(lambda: self.fail('connection opened'),
                                       origins=[ORIGIN], vocabulary_version=2)

    def test_confirmed_closed_shade_overrides_protocol_but_not_separate_airflow(self):
        shade = row('shade', name='indoor_shade', state='closed', source='nostr_confirmed')
        window = row('window', name='window', state='open', source='nostr_confirmed')
        snapshot = select_origin_actions([shade, window], [], origin=ORIGIN, vocabulary_version=2)
        forcing = [{'at': ORIGIN+timedelta(minutes=5), 'outdoor_f': 60.,
                    'radiation_wm2': 400., 'vent_open': 0.,
                    'indoor_shade_closed': 0., 'outdoor_shade_present': 0.}]
        result = hold_confirmed_shades(forcing, snapshot=snapshot, origin=ORIGIN)
        self.assertEqual(result['forcings'][0]['indoor_shade_closed'], 1.)
        self.assertEqual(result['forcings'][0]['vent_open'], 0.)
        self.assertEqual(forcing[0]['indoor_shade_closed'], 0.)
        self.assertEqual(result['held_actions']['indoor_shade']['event_id'], 'shade')
        self.assertIn('window', result['unresolved_forcing_actions'])
        self.assertFalse(result['future_action_evidence'])
        self.assertFalse(result['actuation_authority'])

    def test_unknown_or_expired_shades_do_not_become_held_observations(self):
        forcing = [{'at': ORIGIN+timedelta(minutes=5), 'outdoor_f': 60.,
                    'radiation_wm2': 400., 'vent_open': 0.,
                    'indoor_shade_closed': 0., 'outdoor_shade_present': 0.}]
        for event in [None,
                      row('old', name='indoor_shade', state='closed',
                          effective=ORIGIN-timedelta(days=3)),
                      row('inferred', name='indoor_shade', state='closed', source='model_inferred')]:
            snapshot = select_origin_actions([event] if event else [], [], origin=ORIGIN)
            with self.assertRaisesRegex(ValueError, 'recent confirmed shade'):
                hold_confirmed_shades(forcing, snapshot=snapshot, origin=ORIGIN)

    def test_held_shade_refuses_future_receipt_and_malformed_forcing(self):
        event = row('shade', name='indoor_shade', state='closed', source='nostr_confirmed')
        snapshot = select_origin_actions([event], [], origin=ORIGIN)
        base = {'at': ORIGIN+timedelta(minutes=5), 'outdoor_f': 60.,
                'radiation_wm2': 400., 'vent_open': 0.,
                'indoor_shade_closed': 0., 'outdoor_shade_present': 0.}
        for rows in [[], [base, base], [{**base, 'at': ORIGIN}],
                     [{**base, 'radiation_wm2': float('nan')}],
                     [{**base, 'indoor_shade_closed': True}], [{**base, 'unexpected': 1}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                hold_confirmed_shades(rows, snapshot=snapshot, origin=ORIGIN)
        snapshot['actions']['indoor_shade']['created_at'] = ORIGIN+timedelta(seconds=1)
        with self.assertRaises(ValueError):
            hold_confirmed_shades([base], snapshot=snapshot, origin=ORIGIN)

    def test_held_shades_preserve_full_native_horizon_and_independent_fraction(self):
        event = row('shade', name='indoor_shade', state='closed', source='nostr_confirmed')
        snapshot = select_origin_actions([event], [], origin=ORIGIN)
        rows = [{'at': ORIGIN+timedelta(minutes=5*(i+1)), 'outdoor_f': 60.,
                 'radiation_wm2': 400., 'vent_open': 1.5,
                 'indoor_shade_closed': .25, 'outdoor_shade_present': .75} for i in range(864)]
        result = hold_confirmed_shades(rows, snapshot=snapshot, origin=ORIGIN)
        self.assertEqual(len(result['forcings']), 864)
        self.assertEqual(result['maximum_scenario_horizon_hours'], 72)
        self.assertTrue(all(r['indoor_shade_closed'] == 1. and r['outdoor_shade_present'] == .75
                            and r['vent_open'] == 1.5 for r in result['forcings']))
        with self.assertRaises(ValueError):
            hold_confirmed_shades(rows+[{**rows[-1], 'at': ORIGIN+timedelta(hours=72, minutes=5)}],
                                  snapshot=snapshot, origin=ORIGIN)

    def test_held_outdoor_shade_and_confidence_boundaries(self):
        base = {'at': ORIGIN+timedelta(minutes=5), 'outdoor_f': 60.,
                'radiation_wm2': 400., 'vent_open': 0.,
                'indoor_shade_closed': .25, 'outdoor_shade_present': .75}
        for state, expected in [('absent', 0.), ('removed', 0.), ('present', 1.), ('installed', 1.)]:
            snapshot = select_origin_actions([row('outdoor', state=state)], [], origin=ORIGIN)
            result = hold_confirmed_shades([base], snapshot=snapshot, origin=ORIGIN)
            self.assertEqual(result['forcings'][0]['outdoor_shade_present'], expected)
            self.assertEqual(result['forcings'][0]['indoor_shade_closed'], .25)
        for confidence in (True, -1., 1.1, float('nan'), float('inf'), 0.):
            snapshot = select_origin_actions([row('outdoor')], [], origin=ORIGIN)
            snapshot['actions']['outdoor_shade']['confidence'] = confidence
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                hold_confirmed_shades([base], snapshot=snapshot, origin=ORIGIN)

    def test_held_shade_expiry_uses_effective_time_not_recent_receipt(self):
        base = {'at': ORIGIN+timedelta(minutes=5), 'outdoor_f': 60.,
                'radiation_wm2': 400., 'vent_open': 0.,
                'indoor_shade_closed': 0., 'outdoor_shade_present': 0.}
        event = row('shade', name='indoor_shade', state='closed', source='nostr_confirmed',
                    effective=ORIGIN-timedelta(hours=48))
        snapshot = select_origin_actions([event], [], origin=ORIGIN)
        self.assertEqual(hold_confirmed_shades([base], snapshot=snapshot, origin=ORIGIN)
                         ['forcings'][0]['indoor_shade_closed'], 1.)
        event['effective_at'] -= timedelta(microseconds=1)
        snapshot = select_origin_actions([event], [], origin=ORIGIN)
        with self.assertRaisesRegex(ValueError, 'recent confirmed shade'):
            hold_confirmed_shades([base], snapshot=snapshot, origin=ORIGIN)


if __name__ == '__main__':
    unittest.main()
