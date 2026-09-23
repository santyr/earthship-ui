from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from thermal_model.action_history import fetch_origin_actions, select_origin_actions

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


if __name__ == '__main__':
    unittest.main()
