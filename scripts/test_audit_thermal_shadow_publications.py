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
