"""Bounds and aggregation for read-only operational-origin census."""

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('operational_origin_audit',
    Path(__file__).with_name('audit-thermal-operational-origins.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)

START = datetime(2026, 9, 22, tzinfo=timezone.utc)


def test_aware_requires_offset_and_five_minute_grid():
    assert module.aware('2026-09-22T00:00:00Z') == START
    with pytest.raises(ValueError, match='timezone'):
        module.aware('2026-09-22T00:00:00')
    with pytest.raises(ValueError, match='five minutes'):
        module.aware('2026-09-22T00:01:00Z')


def test_audit_counts_unavailable_pending_and_paired_without_model_claim(monkeypatch):
    calls = []
    def pair(origin, **kwargs):
        calls.append((origin, kwargs['action_reader']))
        if len(calls) == 1:
            return {'status': 'unavailable', 'reason': 'forecast_unavailable'}
        if len(calls) == 2:
            return {'status': 'paired', 'target': origin + timedelta(hours=6),
                    'absolute_error_f': 1.5, 'signed_error_f': -1.5,
                    'forecast_sha256': 'a' * 64,
                    'action_knowledge': 'not_qualified',
                    'action_snapshot_coverage': None}
        return {'status': 'pending', 'target': origin + timedelta(hours=6)}
    monkeypatch.setattr(module, 'pair_persistence_outcome', pair)
    report = module.audit(START, START + timedelta(hours=18), step_hours=6,
        horizon_hours=6, assessed_at=START + timedelta(hours=20),
        forecast_reader=lambda **kwargs: None,
        temperature_reader=lambda **kwargs: None)
    assert report['scope'] == 'origin_time_persistence_only_not_model_graduation'
    assert report['counts'] == {'forecast_unavailable': 1, 'paired': 1, 'pending': 1}
    assert report['paired'] == 1 and report['persistence_mae_f'] == 1.5
    assert len(report['pairs']) == 1 and len(calls) == 3
    assert report['action_as_of_requested'] is False
    assert report['action_snapshot_coverage']['paired_origins_with_snapshot'] == 0


def test_audit_rejects_unbounded_or_future_windows_before_read(monkeypatch):
    monkeypatch.setattr(module, 'pair_persistence_outcome',
                        lambda *args, **kwargs: pytest.fail('reader reached'))
    base = dict(step_hours=1, horizon_hours=24,
                forecast_reader=lambda **kwargs: None,
                temperature_reader=lambda **kwargs: None)
    with pytest.raises(ValueError, match='origin count'):
        module.audit(START, START + timedelta(days=5),
                     assessed_at=START + timedelta(days=5), **base)
    with pytest.raises(ValueError, match='bounded completed'):
        module.audit(START, START + timedelta(days=15),
                     assessed_at=START + timedelta(days=16), **base)
    with pytest.raises(ValueError, match='bounded completed'):
        module.audit(START, START + timedelta(days=1),
                     assessed_at=START + timedelta(hours=12), **base)
    with pytest.raises(ValueError, match='aware forecast timestamp'):
        module.audit(START.replace(tzinfo=None), START + timedelta(hours=1),
                     assessed_at=START + timedelta(hours=2), **base)
    with pytest.raises(ValueError, match='five minutes'):
        module.audit(START + timedelta(minutes=1), START + timedelta(hours=1),
                     assessed_at=START + timedelta(hours=2), **base)
