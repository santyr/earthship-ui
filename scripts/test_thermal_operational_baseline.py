"""Pure summary and read-bound tests for the capture-safe baseline audit."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('thermal_operational_baseline',
    Path(__file__).with_name('audit-thermal-operational-baseline.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)

START = datetime(2026, 9, 20, 0, 45, tzinfo=timezone.utc)


def pair(hours, error):
    origin = START + timedelta(hours=hours)
    return {'status': 'paired', 'origin': origin,
            'target': origin + timedelta(hours=24),
            'absolute_error_f': abs(error), 'signed_error_f': error}


def test_nonoverlap_score_does_not_treat_hourly_origins_as_independent_days():
    report = module.summarize([pair(0, 2), pair(1, -4), pair(24, 1)],
                              origin_count=3, horizon_hours=24)
    assert report['overlapping'] == {'count': 3, 'mae_f': 2.3333, 'bias_f': -0.3333}
    assert report['nonoverlapping'] == {'count': 2, 'mae_f': 1.5, 'bias_f': 1.5}
    assert report['model_scored'] is False
    assert report['action_benefit_proven'] is False


def test_invalid_or_unbounded_window_is_rejected_before_any_reader():
    def forbidden(**_kwargs):
        pytest.fail('reader called for invalid window')
    for start, end in ((START, START),
                       (START, START + timedelta(days=5)),
                       (START + timedelta(minutes=1), START + timedelta(hours=1))):
        with pytest.raises(ValueError, match='bounded aligned'):
            module.audit(start=start, end=end, horizon_hours=24,
                         now=START + timedelta(days=10),
                         connection_factory=forbidden, temperature_reader=forbidden)
