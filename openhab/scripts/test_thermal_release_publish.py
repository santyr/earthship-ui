"""Release transport must withdraw failed qualification, not retain active data."""
import json

import pytest

import thermal_intel
from test_thermal_release import inputs


@pytest.mark.parametrize('skill,mode', [(True, 'forecast_active'), (False, 'shadow')])
def test_release_publisher_recomputes_then_sends_one_explicit_mode(monkeypatch, skill, mode):
    data = inputs(monkeypatch, skill=skill)
    loader = data['qualification_loader']
    assessed = []
    def qualification(now):
        assessed.append(now)
        return loader(now)
    data['qualification_loader'] = qualification
    sent = []
    output = thermal_intel.publish_release_output(
        **data, put_state=lambda item, encoded: sent.append((item, encoded)))
    assert assessed == [data['now']]
    assert len(sent) == 1 and sent[0][0] == thermal_intel.THERMAL_MODEL_ITEM
    assert json.loads(sent[0][1]) == output
    assert output['version'] == 2 and output['status'] == mode
    assert output['release']['automaticActuation'] is False
    assert len(sent[0][1].encode()) < thermal_intel.MAX_SHADOW_BYTES


def test_failed_fresh_qualification_withdraws_previously_active_publication(monkeypatch):
    data = inputs(monkeypatch)
    sent = []
    transport = lambda item, encoded: sent.append(json.loads(encoded))
    first = thermal_intel.publish_release_output(**data, put_state=transport)
    assert first['status'] == 'forecast_active'
    def unavailable(now):
        raise OSError('source unavailable')
    data['qualification_loader'] = unavailable
    second = thermal_intel.publish_release_output(**data, put_state=transport)
    assert [payload['status'] for payload in sent] == ['forecast_active', 'unavailable']
    assert second['forecast']['trajectory'] == []
    assert second['release']['forecastQualified'] is False


def test_release_transport_failure_propagates_without_claiming_delivery(monkeypatch):
    data = inputs(monkeypatch)
    def failed_transport(item, encoded):
        raise OSError('delivery failed')
    with pytest.raises(OSError, match='delivery failed'):
        thermal_intel.publish_release_output(**data, put_state=failed_transport)
