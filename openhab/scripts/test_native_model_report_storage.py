"""Historical model reporting cannot displace the active model's statistics."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import pytest
from native_thermal_score import summarize

NOW = datetime(2026,10,14,19,tzinfo=timezone.utc)


def report(artifact):
    value = summarize([], artifact_sha256=artifact)
    value['assessed_at'] = NOW.isoformat()
    return value


def test_historical_refresh_preserves_current_model_report(tmp_path):
    import native_thermal_live as live
    tmp_path.chmod(0o700)
    current, old = report('a'*64), report('b'*64)
    live._write_native_report(tmp_path, current, lambda: None)
    live._write_native_report(tmp_path, old, lambda: None)
    assert live._read_monitoring_report(tmp_path, 'a'*64, NOW) == current
    assert live._read_monitoring_report(tmp_path, 'b'*64, NOW) == old


def test_legacy_report_fallback_requires_selected_model(tmp_path):
    import native_thermal_live as live
    tmp_path.chmod(0o700)
    path=tmp_path/'latest-native-provisional-performance.json'
    path.write_text(json.dumps(report('a'*64)));path.chmod(0o600)
    assert live._read_monitoring_report(tmp_path,'a'*64,NOW) == report('a'*64)
    assert live._read_monitoring_report(tmp_path,'b'*64,NOW) is None


def test_invalid_scoped_report_does_not_fall_back_to_older_legacy_cache(tmp_path):
    import native_thermal_live as live
    tmp_path.chmod(0o700)
    live._write_native_report(tmp_path,report('a'*64),lambda:None)
    path=live._native_report_path(tmp_path,'a'*64)
    path.write_text('{}')
    assert live._read_monitoring_report(tmp_path,'a'*64,NOW) is None


@pytest.mark.parametrize('available', [NOW-timedelta(seconds=1), NOW+timedelta(minutes=16)])
def test_scoped_reports_keep_existing_age_and_future_checks(tmp_path, available):
    import native_thermal_live as live
    tmp_path.chmod(0o700)
    live._write_native_report(tmp_path,report('a'*64),lambda:None)
    assert live._read_monitoring_report(tmp_path,'a'*64,available) is None
