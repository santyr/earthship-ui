from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name('audit-thermal-shadow-publications.py')
SPEC = importlib.util.spec_from_file_location('thermal_publication_audit', SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
from thermal_model.forcing_capture import capture_shadow_inputs
ISSUE = datetime(2026, 9, 20, 1, 25, tzinfo=timezone.utc)
TARGET = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)


def published():
    trajectory = [{'at': (ISSUE.replace(minute=0) + timedelta(hours=i)).isoformat(),
                   'hallwayF': 72.0, 'lowF': 69.0, 'highF': 75.0}
                  for i in range(1, 73)]
    return {'status': 'shadow', 'generatedAt': ISSUE.isoformat(),
            'provenance': {'currentAgeMinutes': {'air': 1, 'mass': 2}},
            'current': {'hallwayF': 68.0},
            'forecast': {'trajectory': trajectory},
            'model': {'codeRevision': 'a' * 40,
                      'createdAt': (ISSUE - timedelta(days=1)).isoformat(),
                      'trainedThrough': (ISSUE - timedelta(days=1)).isoformat()},
            'confidence': {'grade': 'low'}}


def row(value=None):
    return {'time': int((ISSUE + timedelta(seconds=3)).timestamp() * 1000),
            'state': json.dumps(value or published())}


def receipt(target):
    return {'temperatureF': 70, 'receivedAt': target - timedelta(seconds=30),
            'storedAt': target - timedelta(seconds=20),
            'validUntil': target + timedelta(seconds=90),
            'streamEpoch': '864142d5-99ee-4b7a-b5fc-e6a96e7274d8',
            'snapshotSha256': 'b' * 64}


class PublicationAuditTests(unittest.TestCase):
    def test_nonoverlapping_group_excludes_shared_forecast_windows(self):
        def shifted(hours):
            value = published()
            shift = timedelta(hours=hours)
            value['generatedAt'] = (ISSUE + shift).isoformat()
            for point in value['forecast']['trajectory']:
                point['at'] = (datetime.fromisoformat(point['at']) + shift).isoformat()
            return {'time': int((ISSUE + shift + timedelta(seconds=3)).timestamp() * 1000),
                    'state': json.dumps(value)}

        result = audit.score([shifted(0), shifted(12), shifted(24)],
                             now=TARGET + timedelta(days=3),
                             outcome_reader=receipt)
        self.assertEqual(result['groups']['overall']['n'], 3)
        self.assertEqual(result['groups']['nonoverlap:overall']['n'], 2)
        self.assertEqual(result['groups']['nonoverlap:revision:' + 'a' * 12]['n'], 2)
        self.assertEqual(result['nonoverlap_policy'],
                         'greedy_by_issue_time; next_issue_at_or_after_prior_target')

    def test_paired_published_baseline_and_qualified_outcome(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['groups']['overall']['model_mae_f'], 2.0)
        self.assertEqual(result['groups']['overall']['persistence_mae_f'], 2.0)
        self.assertEqual(result['groups']['overall']['interval_coverage'], 1.0)

    def test_future_target_and_stale_initial_are_excluded(self):
        pair, reason = audit.select_pair(row(), now=TARGET + timedelta(minutes=1))
        self.assertIsNone(pair)
        self.assertEqual(reason, 'outcome_not_yet_due')
        stale = published(); stale['provenance']['currentAgeMinutes']['air'] = 6
        self.assertEqual(audit.select_pair(row(stale), now=TARGET + timedelta(minutes=10))[1],
                         'stale_initial')

    def test_short_horizon_uses_its_own_mature_target(self):
        short_target = datetime(2026, 9, 20, 2, tzinfo=timezone.utc)
        pair, reason = audit.select_pair(row(), now=short_target + timedelta(minutes=6),
                                         horizon_hours=1)
        self.assertIsNone(reason)
        self.assertEqual(pair['target'], short_target)
        self.assertEqual(audit.select_pair(row(), now=short_target + timedelta(minutes=1),
                                           horizon_hours=1)[1], 'outcome_not_yet_due')
        scored = audit.score([row()], now=short_target + timedelta(minutes=6),
                             outcome_reader=receipt, horizon_hours=1)
        self.assertEqual(scored['horizon_hours'], 1)
        self.assertEqual(scored['counts']['scored'], 1)

    def test_unsupported_horizon_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'supported horizon'):
            audit.select_pair(row(), now=TARGET + timedelta(minutes=10), horizon_hours=3)

    def test_exact_captured_weather_is_compared_with_qualified_outdoor(self):
        captured = {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75.0}]}
        outdoor = lambda target: {**receipt(target), 'temperatureF': 72.0}
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt, capture_reader=lambda _: captured,
                             outdoor_reader=outdoor)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['weather']['n'], 1)
        self.assertEqual(result['weather']['outdoor_forecast_mae_f'], 3.0)
        self.assertEqual(result['weather']['paired_indoor_model_mae_f'], 2.0)

    def test_missing_outdoor_target_does_not_invalidate_indoor_score(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt,
                             capture_reader=lambda _: {'forecast_rows': []},
                             outdoor_reader=receipt)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['counts']['weather_forcing_target_unavailable'], 1)
        self.assertEqual(result['weather']['n'], 0)

    def test_unqualified_outdoor_does_not_invalidate_indoor_score(self):
        captured = {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75.0}]}
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt, capture_reader=lambda _: captured,
                             outdoor_reader=lambda _: None)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['counts']['qualified_outdoor_unavailable'], 1)
        self.assertEqual(result['weather']['n'], 0)

    def test_postdated_issue_is_refused(self):
        invalid = published(); invalid['generatedAt'] = (ISSUE + timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'not available'):
            audit.select_pair(row(invalid), now=TARGET + timedelta(minutes=10))

    def test_missing_outcome_never_counts_as_zero_error(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=lambda _: None)
        self.assertEqual(result['counts'], {'qualified_outcome_unavailable': 1})
        self.assertEqual(result['groups'], {})

    def test_capture_required_excludes_missing_and_verifies_exact_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            reader = lambda value: audit.capture_for_publication(value, directory)
            result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                                 outcome_reader=receipt, capture_reader=reader)
            self.assertEqual(result['counts'], {'forcing_capture_missing': 1})
            self.assertEqual(result['groups'], {})
            capture_shadow_inputs(
                directory, output=published(), snapshot={'hourly': {'time': []}},
                rows=[], current={}, inputs_available_at=ISSUE,
                published_at=ISSUE + timedelta(seconds=2),
            )
            result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                                 outcome_reader=receipt, capture_reader=reader)
            self.assertEqual(result['counts']['forcing_capture_verified'], 1)
            self.assertEqual(result['counts']['scored'], 1)
            self.assertEqual(result['groups']['overall']['model_mae_f'], 2.0)

    def test_capture_identity_cannot_match_changed_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            capture_shadow_inputs(
                directory, output=published(), snapshot={}, rows=[], current={},
                inputs_available_at=ISSUE, published_at=ISSUE + timedelta(seconds=2),
            )
            changed = published()
            changed['current']['hallwayF'] = 69.0
            self.assertIsNone(audit.capture_for_publication(changed, directory))


if __name__ == '__main__':
    unittest.main()
