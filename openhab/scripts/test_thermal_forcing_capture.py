from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest

from thermal_model.forcing_capture import capture_shadow_inputs, verify_capture

DECISION = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)


def inputs():
    return {'output': {'status': 'shadow', 'confidence': {'grade': 'low'},
                       'generatedAt': DECISION.isoformat()},
            'snapshot': {'hourly': {'temperature_2m': [50.0, 51.0]}},
            'rows': [{'at': DECISION, 'tempF': 50.0, 'mode': 'warm'}],
            'current': {'air': {'at': DECISION - timedelta(seconds=30), 'value': 70.0}}}


class ForcingCaptureTests(unittest.TestCase):
    def test_private_immutable_roundtrip_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            data = inputs()
            kwargs = dict(directory=directory, output=data['output'],
                          snapshot=data['snapshot'], rows=data['rows'],
                          current=data['current'],
                          inputs_available_at=DECISION - timedelta(seconds=1),
                          published_at=DECISION + timedelta(seconds=2))
            path = capture_shadow_inputs(**kwargs)
            self.assertEqual(path, capture_shadow_inputs(**kwargs))
            self.assertEqual(verify_capture(path)['forecast_rows'][0]['tempF'], 50.0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(len(list(path.parent.iterdir())), 1)
            kwargs['rows'] = [{'at': DECISION, 'tempF': 99.0, 'mode': 'warm'}]
            with self.assertRaisesRegex(ValueError, 'different content'):
                capture_shadow_inputs(**kwargs)
            self.assertEqual(verify_capture(path)['forecast_rows'][0]['tempF'], 50.0)

    def test_refuses_insecure_root_and_future_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            data = inputs()
            kwargs = dict(directory=directory, output=data['output'],
                          snapshot=data['snapshot'], rows=data['rows'],
                          current=data['current'], inputs_available_at=DECISION,
                          published_at=DECISION + timedelta(seconds=1))
            os.chmod(directory, 0o755)
            with self.assertRaisesRegex(ValueError, 'mode-0700'):
                capture_shadow_inputs(**kwargs)
            os.chmod(directory, 0o700)
            kwargs['inputs_available_at'] = DECISION + timedelta(seconds=1)
            with self.assertRaisesRegex(ValueError, 'not available'):
                capture_shadow_inputs(**kwargs)


if __name__ == '__main__':
    unittest.main()
